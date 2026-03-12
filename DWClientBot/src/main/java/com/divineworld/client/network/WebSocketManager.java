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
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * WebSocket Manager
 *
 * Manages the bidirectional binary WebSocket connection to the Python backend.
 *   Outbound: perception frames (JPEG + game state + audio) at ~20 FPS
 *   Inbound:  ActionFrames (movement + flags + god ability)
 *
 * Fixes applied
 * ─────────────
 * Bug C1 — Compile crash: ActionExecutor.initialize() removed.
 *   The new ActionExecutor has no initialize() method; all state is static
 *   and ready on first use.  Removing the call fixes the compile error.
 *
 * Bug C2 — God abilities silently dropped:
 *   handleActionFrame() previously stopped after reading hotbarSlot.
 *   The god_ability section ([2] len, [N] UTF-8, [4×3] params) was never
 *   consumed, so every god ability decision from the Python backend was
 *   discarded.  The fixed handler reads the full ability section and
 *   forwards it to GodEntityManager.executeGodAbility() on the main thread.
 *
 * Bug I — Static messageBuffer unsafe across reconnects:
 *   The old code used a single static ByteBuffer allocated once. On reconnect
 *   a partial/corrupt payload from the dead session could remain if the
 *   connection dropped mid-message before the `last=true` clear() call.
 *   Replaced with a per-connection ByteArrayOutputStream (msgAccum) that is
 *   allocated fresh in onOpen() so every new connection starts clean.
 *   ByteArrayOutputStream.write(byte[]) is also simpler than ByteBuffer.put()
 *   and avoids BufferOverflowException on unexpectedly large frames.
 */
public class WebSocketManager {

    private static WebSocket webSocket;
    private static String agentId;
    private static final AtomicBoolean connected = new AtomicBoolean(false);
    private static ScheduledExecutorService executor;

    private static final int MAGIC            = 0x44574149; // 'DWAI'
    private static final int FRAME_PERCEPTION = 0x01;
    private static final int FRAME_ACTION     = 0x02;

    /**
     * FIX Bug I — per-connection accumulator.
     * Declared volatile so the reference swap in onOpen is visible to onBinary.
     * ByteArrayOutputStream.write() and reset() are called only from the
     * single-threaded Java 11 WebSocket listener, so no additional locking
     * is needed within one connection lifetime.
     */
    private static volatile ByteArrayOutputStream msgAccum = new ByteArrayOutputStream(1024 * 1024);

    // -------------------------------------------------------------------------
    // Initialise
    // -------------------------------------------------------------------------

    public static void initialize(String url, int port, String agentIdParam) {
        agentId = agentIdParam;

        // Initialise vision system (idempotent)
        VisionCaptureSystem.initialize();

        // FIX Bug C1: ActionExecutor.initialize() REMOVED — the new ActionExecutor
        // has no such method.  Its cooldown counters are static primitives that
        // are ready on first call to executeAction().

        try {
            URI serverUri = URI.create(url + ":" + port + "/ws/agent");
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<WebSocket> wsFuture = client.newWebSocketBuilder()
                    .buildAsync(serverUri, new WebSocket.Listener() {

                        @Override
                        public void onOpen(WebSocket ws) {
                            DWClientMod.LOGGER.info("[WS] Connected to backend");
                            // FIX Bug I: allocate a fresh accumulator on every new connection
                            // so stale bytes from a previous session never survive the reconnect.
                            msgAccum = new ByteArrayOutputStream(1024 * 1024);
                            connected.set(true);
                            sendHandshake(ws);
                            startPerceptionLoop();
                            ws.request(1);
                        }

                        /**
                         * Text frames: JSON control messages from the backend (debug, chat acks).
                         * Not used for action delivery but logged at DEBUG for visibility.
                         */
                        @Override
                        public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                            DWClientMod.LOGGER.debug("[WS] JSON received: {}", data.toString());
                            ws.request(1);
                            return null;
                        }

                        /**
                         * Binary frames: ActionFrame payloads from the Python backend.
                         *
                         * FIX Bug I: accumulate into a per-connection ByteArrayOutputStream
                         * instead of the old static ByteBuffer.  This prevents stale bytes
                         * from a dropped connection poisoning the first frame of a new session.
                         *
                         * Java 11 WebSocket guarantees sequential delivery within one
                         * connection, so no synchronisation is required here.
                         */
                        @Override
                        public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last) {
                            // Drain the ByteBuffer into the accumulator
                            byte[] chunk = new byte[data.remaining()];
                            data.get(chunk);
                            try {
                                msgAccum.write(chunk);
                            } catch (Exception e) {
                                DWClientMod.LOGGER.warn("[WS] msgAccum write error: {}", e.getMessage());
                            }

                            if (last) {
                                // Wrap accumulated bytes and hand off to the action parser
                                ByteBuffer complete = ByteBuffer.wrap(msgAccum.toByteArray());
                                msgAccum.reset(); // ready for next message
                                handleActionFrame(complete);
                            }

                            ws.request(1);
                            return null;
                        }

                        @Override
                        public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                            DWClientMod.LOGGER.warn("[WS] Closed: {} {}", statusCode, reason);
                            connected.set(false);
                            scheduleReconnect();
                            return null;
                        }

                        @Override
                        public void onError(WebSocket ws, Throwable error) {
                            DWClientMod.LOGGER.error("[WS] Error", error);
                            connected.set(false);
                            scheduleReconnect();
                        }
                    });

            webSocket = wsFuture.join();

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] Failed to initialize", e);
        }
    }

    // -------------------------------------------------------------------------
    // Handshake
    // -------------------------------------------------------------------------

    private static void sendHandshake(WebSocket ws) {
        String handshake = String.format(
                "{\"agent_id\":\"%s\",\"protocol\":\"binary\",\"version\":\"2.1.0\"}",
                agentId
        );
        ws.sendText(handshake, true);
    }

    // -------------------------------------------------------------------------
    // Perception loop (client → Python, 20 FPS)
    // -------------------------------------------------------------------------

    private static void startPerceptionLoop() {
        if (executor != null && !executor.isShutdown()) return;

        executor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "DW-Perception-Loop");
            t.setDaemon(true);
            return t;
        });

        // 50 ms period = 20 FPS
        executor.scheduleAtFixedRate(() -> {
            if (connected.get() && webSocket != null) {
                Minecraft.getInstance().execute(WebSocketManager::sendPerceptionFrame);
            }
        }, 100, 50, TimeUnit.MILLISECONDS);
    }

    private static void sendPerceptionFrame() {
        try {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.level == null) return;

            byte[] imageData = VisionCaptureSystem.captureScreenAsJPEG();
            if (imageData == null) return;

            byte[] audioData = AudioCaptureSystem.captureAudioFrame();

            float  health = mc.player.getHealth();
            float  hunger = mc.player.getFoodData().getFoodLevel();
            double x      = mc.player.getX();
            double y      = mc.player.getY();
            double z      = mc.player.getZ();
            float  yaw    = mc.player.getYRot();
            float  pitch  = mc.player.getXRot();

            ByteBuffer buffer = buildPerceptionFrame(
                    imageData, audioData, health, hunger, x, y, z, yaw, pitch);

            webSocket.sendBinary(buffer, true);

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] Failed to send perception frame", e);
        }
    }

    private static ByteBuffer buildPerceptionFrame(
            byte[] imageData, byte[] audioData,
            float health, float hunger,
            double x, double y, double z,
            float yaw, float pitch) {

        byte[] agentIdBytes = agentId.getBytes(StandardCharsets.UTF_8);

        // Audio section (always present, even when silent):
        //   [4]  audio data length (0 = silent)
        //   [N]  raw PCM bytes
        //   [4]  sample rate
        //   [1]  channels
        //   [1]  bits per sample
        int audioSection = 4 + audioData.length + 4 + 1 + 1;

        int totalSize = 4                          // MAGIC
                + 4                                // frame type
                + 4 + agentIdBytes.length          // agent ID
                + 8                                // timestamp (double)
                + 4 + imageData.length             // JPEG
                + 2 + 2                            // width + height (shorts)
                + 4 + 4                            // health, hunger
                + 4 + 4 + 4                        // x, y, z
                + 4 + 4                            // yaw, pitch
                + 2                                // entity count
                + audioSection;

        ByteBuffer buf = ByteBuffer.allocate(totalSize);

        buf.putInt(MAGIC);
        buf.putInt(FRAME_PERCEPTION);

        buf.putInt(agentIdBytes.length);
        buf.put(agentIdBytes);

        buf.putDouble(System.currentTimeMillis() / 1000.0);

        buf.putInt(imageData.length);
        buf.put(imageData);
        buf.putShort((short) VisionCaptureSystem.getWidth());
        buf.putShort((short) VisionCaptureSystem.getHeight());

        buf.putFloat(health);
        buf.putFloat(hunger);
        buf.putFloat((float) x);
        buf.putFloat((float) y);
        buf.putFloat((float) z);
        buf.putFloat(yaw);
        buf.putFloat(pitch);

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
    // Inbound: ActionFrame (Python → client)
    // -------------------------------------------------------------------------

    /**
     * Parse a complete binary ActionFrame and apply it on the Minecraft main thread.
     *
     * Wire layout (must match BinaryProtocol.pack_action in communication_protocol.py):
     *   [4]  MAGIC  0x44574149
     *   [4]  type   0x02
     *   [4]  agent-ID length
     *   [N]  agent-ID UTF-8
     *   [8]  timestamp (double)
     *   [4]  move_forward  float
     *   [4]  move_strafe   float
     *   [4]  yaw_delta     float
     *   [4]  pitch_delta   float
     *   [1]  action_flags  uint8
     *   [1]  hotbar_slot   uint8  (0xFF = no change)
     *   [2]  ability_len   uint16 (0 = no ability this frame)
     *   [N]  ability name  UTF-8  (present when len > 0)
     *   [4]  param1  float  (present when len > 0)
     *   [4]  param2  float
     *   [4]  param3  float
     *
     * FIX Bug C2 — god ability section now fully consumed and dispatched.
     * Previously the parser stopped at hotbarSlot; the ability bytes piled up
     * and were discarded with the buffer.  Now ability name + params are read
     * and forwarded to GodEntityManager.executeGodAbility() so client-side
     * effects (particles, cooldown tracking) fire correctly.
     */
    private static void handleActionFrame(ByteBuffer buf) {
        try {
            // ── Header ────────────────────────────────────────────────────────
            if (buf.remaining() < 8) return;
            int magic = buf.getInt();
            if (magic != MAGIC) {
                DWClientMod.LOGGER.warn("[WS] Bad magic: 0x{}", Integer.toHexString(magic));
                return;
            }
            int frameType = buf.getInt();
            if (frameType != FRAME_ACTION) {
                DWClientMod.LOGGER.debug("[WS] Non-action frame: {}", frameType);
                return;
            }

            // ── Agent ID (skip — single-agent process) ────────────────────────
            int aidLen = buf.getInt();
            if (aidLen > 0 && buf.remaining() >= aidLen) {
                buf.position(buf.position() + aidLen);
            }

            // ── Timestamp (skip) ──────────────────────────────────────────────
            buf.getDouble();

            // ── Movement ─────────────────────────────────────────────────────
            final float moveForward = buf.getFloat();
            final float moveStrafe  = buf.getFloat();
            final float yawDelta    = buf.getFloat();
            final float pitchDelta  = buf.getFloat();

            // ── Flags + hotbar ────────────────────────────────────────────────
            final byte actionFlags = buf.get();
            final int  hotbar;
            {
                int raw = buf.get() & 0xFF;
                hotbar  = (raw == 0xFF) ? -1 : raw;
            }

            // ── God ability section (FIX Bug C2) ──────────────────────────────
            // Previously this entire section was ignored, dropping all god ability
            // commands from the Python backend.
            String godAbility = null;
            float  param1 = 0f, param2 = 0f, param3 = 0f;

            if (buf.remaining() >= 2) {
                int abilityLen = buf.getShort() & 0xFFFF;
                if (abilityLen > 0 && buf.remaining() >= abilityLen) {
                    byte[] abBytes = new byte[abilityLen];
                    buf.get(abBytes);
                    godAbility = new String(abBytes, StandardCharsets.UTF_8);

                    if (buf.remaining() >= 12) {
                        param1 = buf.getFloat();
                        param2 = buf.getFloat();
                        param3 = buf.getFloat();
                    }
                }
            }

            // ── Dispatch on main thread ───────────────────────────────────────
            final String  fAbility = godAbility;
            final float   fP1 = param1, fP2 = param2, fP3 = param3;

            Minecraft.getInstance().execute(() -> {
                // 1. Movement + boolean inputs
                ActionExecutor.executeAction(
                        moveForward, moveStrafe,
                        yawDelta,    pitchDelta,
                        actionFlags, hotbar);

                // 2. God ability (FIX Bug C2: was never dispatched before)
                if (fAbility != null && !fAbility.isEmpty()) {
                    GodEntityManager.executeGodAbility(fAbility, fP1, fP2, fP3);
                    DWClientMod.LOGGER.debug("[WS] God ability dispatched: {} ({},{},{})",
                            fAbility, fP1, fP2, fP3);
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] handleActionFrame failed", e);
        }
    }

    // -------------------------------------------------------------------------
    // Reconnect
    // -------------------------------------------------------------------------

    private static void scheduleReconnect() {
        if (executor != null && !executor.isShutdown()) {
            executor.schedule(() -> {
                DWClientMod.LOGGER.info("[WS] Reconnecting...");
                initialize(DWClientMod.getBackendUrl(), DWClientMod.getBackendPort(), agentId);
            }, 5, TimeUnit.SECONDS);
        }
    }

    // -------------------------------------------------------------------------
    // Chat observation (client → Python, JSON)
    // -------------------------------------------------------------------------

    /**
     * Forward a proximity-chat message to the Python backend so the agent
     * can hear what was said near it.  Called by ClientChatEventHandler.
     *
     * JSON: {"type":"chat_heard","agent_id":"<id>","speaker":"<n>","message":"<text>","timestamp":<ms>}
     */
    public static void sendChatObservation(String speaker, String message) {
        if (!connected.get() || webSocket == null) return;
        String safeMsg     = message.replace("\\", "\\\\").replace("\"", "\\\"");
        String safeSpeaker = speaker.replace("\\", "\\\\").replace("\"", "\\\"");
        String json = String.format(
                "{\"type\":\"chat_heard\",\"agent_id\":\"%s\"," +
                "\"speaker\":\"%s\",\"message\":\"%s\",\"timestamp\":%d}",
                agentId, safeSpeaker, safeMsg, System.currentTimeMillis());
        webSocket.sendText(json, true);
    }

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

    public static void shutdown() {
        connected.set(false);
        if (executor != null) executor.shutdown();
        if (webSocket != null) webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "Shutting down");
        VisionCaptureSystem.cleanup();
    }

    public static boolean isConnected() {
        return connected.get();
    }
}