package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.vision.VisionCaptureSystem;
import com.divineworld.client.control.ActionExecutor;
import net.minecraft.client.Minecraft;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * WebSocket Manager - FIXED VERSION
 * Thread-safe WebSocket communication
 */
public class WebSocketManager {
    private static WebSocket webSocket;
    private static String agentId;
    private static final AtomicBoolean connected = new AtomicBoolean(false);
    private static ScheduledExecutorService executor;

    private static final int MAGIC = 0x44574149; // 'DWAI'
    private static final int FRAME_PERCEPTION = 0x01;
    private static final int FRAME_ACTION = 0x02;

    private static ByteBuffer messageBuffer = ByteBuffer.allocate(1024 * 1024);

    public static void initialize(String url, int port, String agentIdParam) {
        agentId = agentIdParam;

        // Initialize vision system
        VisionCaptureSystem.initialize();

        // Initialize action executor
        ActionExecutor.initialize();

        try {
            URI serverUri = URI.create(url + ":" + port + "/ws/agent");
            HttpClient client = HttpClient.newHttpClient();

            CompletableFuture<WebSocket> wsFuture = client.newWebSocketBuilder()
                    .buildAsync(serverUri, new WebSocket.Listener() {

                        @Override
                        public void onOpen(WebSocket ws) {
                            DWClientMod.LOGGER.info("WebSocket connected to backend");
                            connected.set(true);
                            sendHandshake(ws);
                            startPerceptionLoop();
                            ws.request(1);
                        }

                        @Override
                        public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                            DWClientMod.LOGGER.debug("Received JSON: {}", data.toString());
                            ws.request(1);
                            return null;
                        }

                        @Override
                        public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last) {
                            messageBuffer.put(data);
                            if (last) {
                                messageBuffer.flip();
                                handleActionFrame(ByteBuffer.wrap(messageBuffer.array(), 0, messageBuffer.limit()));
                                messageBuffer.clear();
                            }
                            ws.request(1);
                            return null;
                        }

                        @Override
                        public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                            DWClientMod.LOGGER.warn("WebSocket closed: {} - {}", statusCode, reason);
                            connected.set(false);
                            scheduleReconnect();
                            return null;
                        }

                        @Override
                        public void onError(WebSocket ws, Throwable error) {
                            DWClientMod.LOGGER.error("WebSocket error", error);
                        }
                    });

            webSocket = wsFuture.join();

        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to initialize WebSocket", e);
        }
    }

    private static void sendHandshake(WebSocket ws) {
        String handshake = String.format(
                "{\"agent_id\":\"%s\",\"protocol\":\"binary\",\"version\":\"2.1.0\"}",
                agentId
        );
        ws.sendText(handshake, true);
    }

    private static void startPerceptionLoop() {
        if (executor != null && !executor.isShutdown()) {
            return;
        }

        executor = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "DW-Perception-Loop");
            t.setDaemon(true);
            return t;
        });

        // Send at 20 FPS
        executor.scheduleAtFixedRate(() -> {
            if (connected.get() && webSocket != null) {
                // FIXED: Schedule on main thread
                Minecraft.getInstance().execute(() -> {
                    sendPerceptionFrame();
                });
            }
        }, 100, 50, TimeUnit.MILLISECONDS);
    }

    private static void sendPerceptionFrame() {
        try {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null) return;

            // FIXED: Now called from render thread
            byte[] imageData = VisionCaptureSystem.captureScreenAsJPEG();
            if (imageData == null) return;

            float health = mc.player.getHealth();
            float hunger = mc.player.getFoodData().getFoodLevel();
            double x = mc.player.getX();
            double y = mc.player.getY();
            double z = mc.player.getZ();
            float yaw = mc.player.getYRot();
            float pitch = mc.player.getXRot();

            ByteBuffer buffer = buildPerceptionFrame(
                    imageData, health, hunger, x, y, z, yaw, pitch
            );

            webSocket.sendBinary(buffer, true);

        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to send perception frame", e);
        }
    }

    private static ByteBuffer buildPerceptionFrame(
            byte[] imageData,
            float health, float hunger,
            double x, double y, double z,
            float yaw, float pitch
    ) {
        int agentIdBytes = agentId.getBytes().length;
        int totalSize = 4 + 4 + 4 + agentIdBytes + 8 + 4 + imageData.length +
                2 + 2 + 4 + 4 + 12 + 8 + 2 + 4;

        ByteBuffer buffer = ByteBuffer.allocate(totalSize);

        // Header
        buffer.putInt(MAGIC);
        buffer.putInt(FRAME_PERCEPTION);

        // Agent ID
        buffer.putInt(agentIdBytes);
        buffer.put(agentId.getBytes());

        // Timestamp
        buffer.putDouble(System.currentTimeMillis() / 1000.0);

        // Image
        buffer.putInt(imageData.length);
        buffer.put(imageData);
        buffer.putShort((short) VisionCaptureSystem.getWidth());
        buffer.putShort((short) VisionCaptureSystem.getHeight());

        // Game state
        buffer.putFloat(health);
        buffer.putFloat(hunger);
        buffer.putFloat((float) x);
        buffer.putFloat((float) y);
        buffer.putFloat((float) z);
        buffer.putFloat(yaw);
        buffer.putFloat(pitch);

        // Entities
        buffer.putShort((short) 0);

        // Audio
        buffer.putInt(0);

        buffer.flip();
        return buffer;
    }

    private static void handleActionFrame(ByteBuffer buffer) {
        try {
            int magic = buffer.getInt();
            if (magic != MAGIC) return;

            int frameType = buffer.getInt();
            if (frameType != FRAME_ACTION) return;

            int agentIdLen = buffer.getInt();
            buffer.position(buffer.position() + agentIdLen);

            double timestamp = buffer.getDouble();

            float moveForward = buffer.getFloat();
            float moveStrafe = buffer.getFloat();
            float yawDelta = buffer.getFloat();
            float pitchDelta = buffer.getFloat();

            byte actionFlags = buffer.get();
            byte hotbarSlot = buffer.get();

            // FIXED: Execute on main thread
            Minecraft.getInstance().execute(() -> {
                ActionExecutor.executeAction(
                        moveForward, moveStrafe,
                        yawDelta, pitchDelta,
                        actionFlags,
                        hotbarSlot == (byte) 0xFF ? -1 : hotbarSlot
                );
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to handle action frame", e);
        }
    }

    private static void scheduleReconnect() {
        if (executor != null && !executor.isShutdown()) {
            executor.schedule(() -> {
                DWClientMod.LOGGER.info("Attempting to reconnect...");
                initialize(
                        DWClientMod.getBackendUrl(),
                        DWClientMod.getBackendPort(),
                        agentId
                );
            }, 5, TimeUnit.SECONDS);
        }
    }

    public static void shutdown() {
        connected.set(false);
        if (executor != null) {
            executor.shutdown();
        }
        if (webSocket != null) {
            webSocket.sendClose(WebSocket.NORMAL_CLOSURE, "Shutting down");
        }
        VisionCaptureSystem.cleanup();
    }

    public static boolean isConnected() {
        return connected.get();
    }
}