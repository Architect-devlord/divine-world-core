package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.GodEntityManager;
import com.divineworld.client.vision.AudioCaptureSystem;
import com.divineworld.client.vision.VisionCaptureSystem;
import com.divineworld.client.control.ActionExecutor;
import net.minecraft.client.Minecraft;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * WebSocket Manager — Non-blocking rewrite
 *
 * KEY FIXES FOR FREEZE ON OLD HARDWARE
 * =====================================
 *
 * FIX F1 — wsFuture.join() removed from main thread
 *   The old code called CompletableFuture.join() on the Minecraft main thread
 *   while waiting for the WebSocket TCP handshake.  If the Python backend was
 *   not ready, this blocked the entire game loop (freeze until timeout).
 *   Fix: connect asynchronously via thenAccept().  The game continues normally
 *   while the connection is being established in the background.
 *
 * FIX F2 — JPEG encoding moved off the main thread
 *   captureScreenAsJPEG() was called inside Minecraft.getInstance().execute()
 *   (= main thread) then JPEG-encoded there via ImageIO.write() — a CPU-heavy
 *   operation that took 100-500 ms on older hardware, starving the game loop
 *   at 20 FPS.
 *   Fix: VisionCaptureSystem.grabPixels() captures the NativeImage pixels on
 *   the main thread (required for GPU readback), then encoding is submitted
 *   to the encode executor (off-thread).  sendBinary() is also off-thread.
 *
 * FIX F3 — sendBinary() moved off the main thread
 *   Sending a 20-100 KB WebSocket frame on the main thread blocked it for the
 *   duration of the kernel socket write.  Moved to the encode executor.
 *
 * FIX F4 — Reduced default capture resolution
 *   640×480 = 307 200 pixels per frame.  For old hardware the default is now
 *   320×240 (76 800 pixels) — ¼ the work.  Override with
 *   -Ddw.vision.width=640 -Ddw.vision.height=480 when needed.
 *
 * Other bugs preserved from previous version:
 *   Bug C1 — ActionExecutor.initialize() removed (no such method)
 *   Bug C2 — god ability section fully read and dispatched
 *   Bug I  — per-connection ByteArrayOutputStream accumulator
 */
public class WebSocketManager {

    private static volatile WebSocket       webSocket;
    private static volatile String          agentId;
    private static final AtomicBoolean      connected   = new AtomicBoolean(false);
    private static final AtomicBoolean      connecting  = new AtomicBoolean(false);

    private static ScheduledExecutorService perceptionExecutor;

    /**
     * FIX F2/F3: single-thread executor for JPEG encoding + WS sends.
     * Keeps encoding sequential (no frame reordering) and off the main thread.
     */
    private static final ExecutorService encodeExecutor =
        Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "DW-Encode-Send");
            t.setDaemon(true);
            t.setPriority(Thread.NORM_PRIORITY - 1);
            return t;
        });

    private static final int MAGIC            = 0x44574149;
    private static final int FRAME_CHAT       = 0x03;  // Python → Java chat message
    private static final int FRAME_PERCEPTION = 0x01;
    private static final int FRAME_ACTION     = 0x02;

    private static volatile ByteArrayOutputStream msgAccum =
        new ByteArrayOutputStream(1024 * 1024);

    // -------------------------------------------------------------------------
    // Initialise — NON-BLOCKING (FIX F1)
    // -------------------------------------------------------------------------

    public static void initialize(String url, int port, String agentIdParam) {
        agentId = agentIdParam;

        // VisionCaptureSystem.initialize() only reads system properties
        // and initialises AudioCaptureSystem — safe on main thread.
        VisionCaptureSystem.initialize();

        if (connecting.getAndSet(true)) {
            DWClientMod.LOGGER.info("[WS] Already connecting — skipping duplicate init");
            return;
        }

        URI serverUri = URI.create(url + ":" + port + "/ws/agent");
        DWClientMod.LOGGER.info("[WS] Connecting async to {}", serverUri);

        HttpClient client = HttpClient.newHttpClient();

        // FIX F1: thenAccept() instead of join() — never blocks the main thread.
        client.newWebSocketBuilder()
            .buildAsync(serverUri, new WebSocket.Listener() {

                @Override
                public void onOpen(WebSocket ws) {
                    DWClientMod.LOGGER.info("[WS] Connected to backend at {}", serverUri);
                    msgAccum = new ByteArrayOutputStream(1024 * 1024);
                    webSocket = ws;
                    connected.set(true);
                    connecting.set(false);
                    // request(1) MUST come before sendHandshake so the Java
                    // HTTP client's receive pump is running before we send.
                    // Without this, the Python side's receive_json() hangs
                    // waiting for a frame that the client hasn't flushed yet.
                    ws.request(1);
                    sendHandshake(ws);
                    startPerceptionLoop();
                }

                @Override
                public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                    DWClientMod.LOGGER.debug("[WS] JSON: {}", data);
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last) {
                    byte[] chunk = new byte[data.remaining()];
                    data.get(chunk);
                    try { msgAccum.write(chunk); } catch (Exception ignored) {}
                    if (last) {
                        ByteBuffer complete = ByteBuffer.wrap(msgAccum.toByteArray());
                        msgAccum.reset();
                        // Peek at frame type to dispatch correctly
                        if (complete.remaining() >= 8) {
                            int peekMagic = complete.getInt();
                            int peekType  = complete.getInt();
                            complete.rewind();
                            if (peekMagic == MAGIC && peekType == FRAME_CHAT) {
                                handleChatFrame(complete);
                            } else {
                                handleActionFrame(complete);
                            }
                        }
                    }
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                    DWClientMod.LOGGER.warn("[WS] Closed: {} {}", statusCode, reason);
                    connected.set(false);
                    connecting.set(false);
                    scheduleReconnect(url, port);
                    return null;
                }

                @Override
                public void onError(WebSocket ws, Throwable error) {
                    DWClientMod.LOGGER.error("[WS] Error: {}", error.getMessage());
                    connected.set(false);
                    connecting.set(false);
                    scheduleReconnect(url, port);
                }
            })
            .exceptionally(ex -> {
                DWClientMod.LOGGER.error("[WS] Connect failed: {}", ex.getMessage());
                connected.set(false);
                connecting.set(false);
                scheduleReconnect(url, port);
                return null;
            });

        DWClientMod.LOGGER.info("[WS] Connection initiated (non-blocking) — game will not freeze");
    }

    // -------------------------------------------------------------------------
    // Handshake
    // -------------------------------------------------------------------------

    private static void sendHandshake(WebSocket ws) {
        String msg = String.format(
            "{\"agent_id\":\"%s\",\"protocol\":\"binary\",\"version\":\"2.1.0\"}",
            agentId);
        ws.sendText(msg, true);
    }

    // -------------------------------------------------------------------------
    // Perception loop (FIX F2 + F3)
    // -------------------------------------------------------------------------

    private static void startPerceptionLoop() {
        if (perceptionExecutor != null && !perceptionExecutor.isShutdown()) return;

        perceptionExecutor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "DW-Perception-Scheduler");
            t.setDaemon(true);
            return t;
        });

        // Schedule the CAPTURE trigger at 20 FPS on the scheduler thread.
        // The scheduler posts pixel-grab to the main thread, then hands off
        // encoding + sending to the encode executor.
        perceptionExecutor.scheduleAtFixedRate(() -> {
            if (!connected.get() || webSocket == null) return;
            // Step 1: grab pixels on Minecraft main thread (GPU readback must be there)
            Minecraft.getInstance().execute(WebSocketManager::captureAndScheduleEncode);
        }, 200, 50, TimeUnit.MILLISECONDS);

        DWClientMod.LOGGER.info("[WS] Perception loop started (20 FPS)");
    }

    /**
     * FIX F2: Runs on Minecraft main thread — only pixel readback here.
     * Hands everything CPU-heavy to encodeExecutor immediately.
     */
    private static void captureAndScheduleEncode() {
        try {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.level == null) return;
            if (!connected.get() || webSocket == null) return;

            // Grab game state — cheap
            final float  health = mc.player.getHealth();
            final float  hunger = mc.player.getFoodData().getFoodLevel();
            final double x      = mc.player.getX();
            final double y      = mc.player.getY();
            final double z      = mc.player.getZ();
            final float  yaw    = mc.player.getYRot();
            final float  pitch  = mc.player.getXRot();

            // Grab raw pixels on main thread (MUST be here for GPU readback).
            // VisionCaptureSystem.grabPixels() returns the raw int[] pixel data
            // without doing any CPU-heavy encoding.
            final int[] pixels  = VisionCaptureSystem.grabPixels();
            final int   imgW    = VisionCaptureSystem.getWidth();
            final int   imgH    = VisionCaptureSystem.getHeight();
            if (pixels == null) return;

            // Audio capture — fine on main thread, just reads from a buffer
            final byte[] audioData = AudioCaptureSystem.captureAudioFrame();

            // FIX F2+F3: hand off JPEG encoding + WS send to encode executor
            encodeExecutor.submit(() -> {
                try {
                    byte[] imageData = VisionCaptureSystem.encodePixelsToJPEG(pixels, imgW, imgH);
                    if (imageData == null) return;

                    ByteBuffer frame = buildPerceptionFrame(
                        imageData, audioData != null ? audioData : new byte[0],
                        health, hunger, x, y, z, yaw, pitch, imgW, imgH);

                    WebSocket ws = webSocket;
                    if (ws != null && connected.get()) {
                        ws.sendBinary(frame, true);
                    }
                } catch (Exception e) {
                    DWClientMod.LOGGER.error("[WS] Encode/send error: {}", e.getMessage());
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] captureAndScheduleEncode error: {}", e.getMessage());
        }
    }

    private static ByteBuffer buildPerceptionFrame(
            byte[] imageData, byte[] audioData,
            float health, float hunger,
            double x, double y, double z,
            float yaw, float pitch,
            int imgW, int imgH) {

        byte[] idBytes = agentId.getBytes(StandardCharsets.UTF_8);
        int audioSection = 4 + audioData.length + 4 + 1 + 1;
        int total = 4 + 4
                  + 4 + idBytes.length
                  + 8
                  + 4 + imageData.length
                  + 2 + 2
                  + 4 + 4
                  + 4 + 4 + 4
                  + 4 + 4
                  + 2
                  + audioSection;

        ByteBuffer buf = ByteBuffer.allocate(total);
        buf.putInt(MAGIC);
        buf.putInt(FRAME_PERCEPTION);
        buf.putInt(idBytes.length); buf.put(idBytes);
        buf.putDouble(System.currentTimeMillis() / 1000.0);
        buf.putInt(imageData.length); buf.put(imageData);
        buf.putShort((short) imgW); buf.putShort((short) imgH);
        buf.putFloat(health); buf.putFloat(hunger);
        buf.putFloat((float) x); buf.putFloat((float) y); buf.putFloat((float) z);
        buf.putFloat(yaw); buf.putFloat(pitch);
        buf.putShort((short) 0); // entity count
        buf.putInt(audioData.length);
        if (audioData.length > 0) buf.put(audioData);
        buf.putInt(AudioCaptureSystem.getSampleRate());
        buf.put((byte) AudioCaptureSystem.getChannels());
        buf.put((byte) AudioCaptureSystem.getBitsPerSample());
        buf.flip();
        return buf;
    }

    // -------------------------------------------------------------------------
    // Inbound: ChatFrame (Python → Minecraft, agent speaks in-world)
    // -------------------------------------------------------------------------

    /**
     * Parse a FRAME_CHAT (0x03) from the Python backend and send it as
     * in-game chat via the Minecraft client.
     *
     * Wire layout (matches BinaryProtocol.pack_chat() in communication_protocol.py):
     *   [4]  MAGIC  0x44574149
     *   [4]  type   0x03
     *   [4]  agent-ID length
     *   [N]  agent-ID UTF-8
     *   [8]  timestamp (double, ignored)
     *   [4]  message length
     *   [N]  message UTF-8
     */
    private static void handleChatFrame(ByteBuffer buf) {
        try {
            if (buf.remaining() < 8) return;
            int magic = buf.getInt();
            if (magic != MAGIC) return;
            int type = buf.getInt();
            if (type != FRAME_CHAT) return;

            // Skip agent ID
            int aidLen = buf.getInt();
            if (aidLen > 0 && buf.remaining() >= aidLen)
                buf.position(buf.position() + aidLen);

            // Skip timestamp
            if (buf.remaining() >= 8) buf.getDouble();

            // Read message
            if (buf.remaining() < 4) return;
            int msgLen = buf.getInt();
            if (msgLen <= 0 || buf.remaining() < msgLen) return;
            byte[] msgBytes = new byte[msgLen];
            buf.get(msgBytes);
            final String message = new String(msgBytes, StandardCharsets.UTF_8);

            // Send on Minecraft main thread
            Minecraft.getInstance().execute(() -> {
                net.minecraft.client.multiplayer.ClientPacketListener conn =
                    Minecraft.getInstance().getConnection();
                if (conn != null && !message.isEmpty()) {
                    // Trim to Minecraft chat limit (256 chars)
                    String trimmed = message.length() > 256
                        ? message.substring(0, 256) : message;
                    conn.sendChat(trimmed);
                    DWClientMod.LOGGER.info("[WS] Agent spoke: {}", trimmed);
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] handleChatFrame error: {}", e.getMessage());
        }
    }

    // -------------------------------------------------------------------------
    // Inbound: ActionFrame
    // -------------------------------------------------------------------------

    private static void handleActionFrame(ByteBuffer buf) {
        try {
            if (buf.remaining() < 8) return;
            int magic = buf.getInt();
            if (magic != MAGIC) {
                DWClientMod.LOGGER.warn("[WS] Bad magic 0x{}", Integer.toHexString(magic));
                return;
            }
            if (buf.getInt() != FRAME_ACTION) return;

            int aidLen = buf.getInt();
            if (aidLen > 0 && buf.remaining() >= aidLen)
                buf.position(buf.position() + aidLen);

            buf.getDouble(); // timestamp

            final float moveForward = buf.getFloat();
            final float moveStrafe  = buf.getFloat();
            final float yawDelta    = buf.getFloat();
            final float pitchDelta  = buf.getFloat();
            final byte  actionFlags = buf.get();
            final int   rawHotbar   = buf.get() & 0xFF;
            final int   hotbar      = (rawHotbar == 0xFF) ? -1 : rawHotbar;

            String godAbility = null;
            float  p1 = 0f, p2 = 0f, p3 = 0f;
            if (buf.remaining() >= 2) {
                int alen = buf.getShort() & 0xFFFF;
                if (alen > 0 && buf.remaining() >= alen) {
                    byte[] ab = new byte[alen];
                    buf.get(ab);
                    godAbility = new String(ab, StandardCharsets.UTF_8);
                    if (buf.remaining() >= 12) {
                        p1 = buf.getFloat(); p2 = buf.getFloat(); p3 = buf.getFloat();
                    }
                }
            }

            final String fa = godAbility;
            final float fp1 = p1, fp2 = p2, fp3 = p3;
            final int   fHotbar = hotbar;

            Minecraft.getInstance().execute(() -> {
                ActionExecutor.executeAction(
                    moveForward, moveStrafe, yawDelta, pitchDelta, actionFlags, fHotbar);
                if (fa != null && !fa.isEmpty()) {
                    GodEntityManager.executeGodAbility(fa, fp1, fp2, fp3);
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] handleActionFrame error: {}", e.getMessage());
        }
    }

    // -------------------------------------------------------------------------
    // Reconnect
    // -------------------------------------------------------------------------

    private static void scheduleReconnect(String url, int port) {
        if (perceptionExecutor != null && !perceptionExecutor.isShutdown()) {
            perceptionExecutor.schedule(() ->
                initialize(url, port, agentId), 5, TimeUnit.SECONDS);
        }
    }

    // -------------------------------------------------------------------------
    // Chat
    // -------------------------------------------------------------------------

    public static void sendChatObservation(String speaker, String message) {
        if (!connected.get() || webSocket == null) return;
        String s = message.replace("\\", "\\\\").replace("\"", "\\\"");
        String sp = speaker.replace("\\", "\\\\").replace("\"", "\\\"");
        String json = String.format(
            "{\"type\":\"chat_heard\",\"agent_id\":\"%s\","
          + "\"speaker\":\"%s\",\"message\":\"%s\",\"timestamp\":%d}",
            agentId, sp, s, System.currentTimeMillis());
        webSocket.sendText(json, true);
    }

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    public static void shutdown() {
        connected.set(false);
        connecting.set(false);
        if (perceptionExecutor != null) perceptionExecutor.shutdown();
        // Do NOT call encodeExecutor.shutdown() — it is static final and cannot
        // be restarted.  Shutting it down here means captureAndScheduleEncode()
        // throws RejectedExecutionException on the next login.  It is a daemon
        // thread and will die naturally with the JVM / game process.
        WebSocket ws = webSocket;
        if (ws != null) ws.sendClose(WebSocket.NORMAL_CLOSURE, "Shutting down");
        VisionCaptureSystem.cleanup();
    }

    public static boolean isConnected() { return connected.get(); }
}