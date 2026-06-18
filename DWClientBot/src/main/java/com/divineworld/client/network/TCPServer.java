// src/main/java/com/divineworld/client/network/TCPServer.java
// Forge 1.20.1 / Parchment 47.4.10
package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.control.ActionExecutor;
import net.minecraft.client.Minecraft;
import net.minecraft.world.inventory.ClickType;

import java.io.DataInputStream;
import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * TCP Server — primary action channel from Python agent to Minecraft client.
 *
 * Wire format (ForgeIPCClient.send_action() in actuators.py):
 *   [4]  agent_id length  (uint32 big-endian)
 *   [N]  agent_id         (UTF-8)
 *   [8]  tick             (int64 big-endian, ms timestamp)
 *   [4]  move_forward     (float32)
 *   [4]  move_strafe      (float32)
 *   [4]  yaw_delta        (float32)
 *   [4]  pitch_delta      (float32)
 *   [1]  action_flags     (uint8, packed — see ActionExecutor javadoc)
 *   [1]  hotbar_slot      (uint8, 0xFF = no change)
 *   [2]  ability_len      (uint16 big-endian, 0 = no ability)
 *   [M]  ability          (UTF-8, present when ability_len > 0)
 *   [4]  param1           (float32, present when ability_len > 0)
 *   [4]  param2           (float32, present when ability_len > 0)
 *   [4]  param3           (float32, present when ability_len > 0)
 *
 * Special ability string prefixes (all agents, not just gods):
 *
 *   "inv:SLOT,BUTTON,CLICK_TYPE"
 *     Inventory slot click dispatched to ActionExecutor.executeInventoryAction().
 *     See ActionExecutor javadoc for full slot/button/ClickType documentation.
 *     Examples:
 *       "inv:9,0,2"   → SWAP slot 9 with hotbar slot 0 (moves item to hotbar)
 *       "inv:0,0,1"   → QUICK_MOVE (shift-click) slot 0 (craft result → inventory)
 *       "inv:36,0,0"  → PICKUP click hotbar slot 0 (picks up item onto cursor)
 *
 *   "screen:COMMAND"
 *     GUI screen control dispatched to ActionExecutor.executeScreenAction().
 *       "screen:close" → close any open container screen.
 *       "screen:inv"   → open player inventory.
 *
 *   Anything else → god ability dispatched to GodEntityManager.executeGodAbility().
 */
public class TCPServer {

    private static ServerSocket    serverSocket;
    private static Socket          clientSocket;
    private static DataInputStream input;
    private static boolean         running    = false;
    private static volatile int    cachedPort = 0;

    private static final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "DW-TCP-Server");
        t.setDaemon(true);
        return t;
    });

    // =========================================================================
    // Start / Stop
    // =========================================================================

    public static void start(int port) {
        if (running) {
            DWClientMod.LOGGER.warn("[TCPServer] Already running on port {}", cachedPort);
            return;
        }
        cachedPort = port;
        DWClientMod.LOGGER.info("[TCPServer] Starting on port {} (agent: {})",
                port, DWClientMod.getAgentId());
        executor.execute(() -> runServer(port));
    }

    private static void runServer(int port) {
        running = true;
        try {
            serverSocket = new ServerSocket(port);
            DWClientMod.LOGGER.info("[TCPServer] Listening on port {}", port);

            while (running) {
                try {
                    DWClientMod.LOGGER.info("[TCPServer] Waiting for agent connection...");
                    clientSocket = serverSocket.accept();
                    clientSocket.setTcpNoDelay(true);
                    input = new DataInputStream(clientSocket.getInputStream());
                    DWClientMod.LOGGER.info("[TCPServer] Agent connected: {}",
                            clientSocket.getRemoteSocketAddress());

                    while (!clientSocket.isClosed()) {
                        try {
                            handleActionFrame();
                        } catch (IOException e) {
                            if (running) {
                                DWClientMod.LOGGER.warn("[TCPServer] Client disconnected: {}",
                                        e.getMessage());
                            }
                            try { clientSocket.close(); } catch (IOException ignored) {}
                            break;
                        }
                    }
                } catch (IOException e) {
                    if (running) {
                        DWClientMod.LOGGER.warn("[TCPServer] Accept error: {}", e.getMessage());
                    }
                }
            }
        } catch (IOException e) {
            DWClientMod.LOGGER.error("[TCPServer] Server error on port {}: {}", port, e.getMessage());
        } finally {
            cleanup();
        }
    }

    // =========================================================================
    // Frame parsing
    // =========================================================================

    private static void handleActionFrame() throws IOException {
        // Agent ID
        int agentIdLen = input.readInt();
        byte[] agentIdBytes = new byte[agentIdLen];
        input.readFully(agentIdBytes);

        // Tick (skip)
        input.readLong();

        // Movement
        final float moveForward = input.readFloat();
        final float moveStrafe  = input.readFloat();
        final float yawDelta    = input.readFloat();
        final float pitchDelta  = input.readFloat();

        // Flags (1 packed byte — must match ActionExecutor bit layout)
        final byte actionFlags = input.readByte();

        // Hotbar slot (0xFF = no change)
        final int rawHotbar  = input.readByte() & 0xFF;
        final int hotbarSlot = (rawHotbar == 0xFF) ? -1 : rawHotbar;

        // Ability / special-action section
        String ability = null;
        float  p1 = 0f, p2 = 0f, p3 = 0f;
        int abilityLen = input.readShort() & 0xFFFF;
        if (abilityLen > 0) {
            byte[] abBytes = new byte[abilityLen];
            input.readFully(abBytes);
            ability = new String(abBytes, StandardCharsets.UTF_8);
            p1 = input.readFloat();
            p2 = input.readFloat();
            p3 = input.readFloat();
        }

        final String fAbility = ability;
        final float  fP1 = p1, fP2 = p2, fP3 = p3;

        // ── Dispatch on main thread ───────────────────────────────────────
        Minecraft.getInstance().execute(() -> {
            // 1. Movement + boolean flags (always applied)
            ActionExecutor.executeAction(
                moveForward, moveStrafe, yawDelta, pitchDelta, actionFlags, hotbarSlot);

            // 2. Special action routing
            if (fAbility == null || fAbility.isEmpty()) return;

            if (fAbility.startsWith("inv:")) {
                // Inventory slot click — works for ALL agents
                ActionExecutor.executeInventoryAction(fAbility);

            } else if (fAbility.startsWith("screen:")) {
                // Screen control (open/close GUIs) — works for ALL agents
                ActionExecutor.executeScreenAction(fAbility);

            } else {
                // God ability — dispatched to GodEntityManager
                try {
                    com.divineworld.client.entity.GodEntityManager
                            .executeGodAbility(fAbility, fP1, fP2, fP3);
                } catch (Exception e) {
                    DWClientMod.LOGGER.debug("[TCPServer] God ability dispatch error: {}",
                            e.getMessage());
                }
            }
        });
    }

    // =========================================================================
    // Lifecycle
    // =========================================================================

    public static void stop() {
        running = false;
        cleanup();
        executor.shutdown();
    }

    private static void cleanup() {
        try { if (input        != null) input.close();        } catch (IOException ignored) {}
        try { if (clientSocket != null) clientSocket.close(); } catch (IOException ignored) {}
        try { if (serverSocket != null) serverSocket.close(); } catch (IOException ignored) {}
    }

    public static boolean isConnected() {
        return clientSocket != null
                && clientSocket.isConnected()
                && !clientSocket.isClosed();
    }

    public static int getPort() {
        return cachedPort > 0 ? cachedPort : 0;
    }
}