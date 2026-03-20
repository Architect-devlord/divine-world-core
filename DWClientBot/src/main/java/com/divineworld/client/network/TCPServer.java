package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.control.ActionExecutor;
import net.minecraft.client.Minecraft;

import java.io.DataInputStream;
import java.io.IOException;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * TCP Server for receiving actions from the Python agent.
 * Primary low-latency action channel (Python → Java).
 *
 * Wire format sent by ForgeIPCClient.send_action() in actuators.py:
 *   [4]   agentId length  (big-endian int)
 *   [N]   agentId         (UTF-8)
 *   [8]   tick            (big-endian long, ms timestamp)
 *   [4]   move_forward    (big-endian float)
 *   [4]   move_strafe     (big-endian float)
 *   [4]   yaw_delta       (big-endian float)
 *   [4]   pitch_delta     (big-endian float)
 *   [1]   action_flags    (uint8, packed bits — see ActionExecutor.java)
 *   [1]   hotbar_slot     (uint8, 0xFF = no change)
 *   [2]   ability_len     (big-endian uint16, 0 = no ability)
 *   [N]   ability name    (UTF-8, present when ability_len > 0)
 *   [4]   param1          (float, present when ability_len > 0)
 *   [4]   param2          (float)
 *   [4]   param3          (float)
 *
 * FIX: old handleActionFrame() read 7 individual boolean bytes.
 *   Python ForgeIPCClient.send_action() packs ONE flags byte + ONE hotbar byte,
 *   not 7 individual bytes. Reading 7 bytes consumed data from the next frame,
 *   corrupting the stream and silently dropping all actions.
 *   Fixed to read 1 flags byte + 1 hotbar byte, matching the Python sender.
 *
 * Port resolution:
 *   The port passed to start(port) comes from ClientEventHandler.onPlayerJoinedWorld()
 *   which has already resolved it from agents.json via DWClientMod.getTcpPort().
 *   cachedPort stores the resolved port so getPort() returns it without logging.
 */
public class TCPServer {

    private static ServerSocket     serverSocket;
    private static Socket           clientSocket;
    private static DataInputStream  input;
    private static boolean          running    = false;
    private static volatile int     cachedPort = 0;

    private static final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "DW-TCP-Server");
        t.setDaemon(true);
        return t;
    });

    // -------------------------------------------------------------------------
    // Start / Stop
    // -------------------------------------------------------------------------

    /**
     * Start the TCP server on the given port.
     * Port is resolved by ClientEventHandler from agents.json before calling here.
     */
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

                    // FIX B-10: isConnected() stays true after the remote end closes;
                    // use !isClosed() instead and break on IOException.
                    while (!clientSocket.isClosed()) {
                        try {
                            handleActionFrame();
                        } catch (IOException e) {
                            if (running) {
                                DWClientMod.LOGGER.warn("[TCPServer] Client disconnected: {}", e.getMessage());
                            }
                            try { clientSocket.close(); } catch (IOException ignored) {}
                            break; // exit inner loop; outer loop waits for next accept()
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

    // -------------------------------------------------------------------------
    // Frame parsing — must match ForgeIPCClient.send_action() exactly
    // -------------------------------------------------------------------------

    private static void handleActionFrame() throws IOException {
        // ── Agent ID ──────────────────────────────────────────────────────────
        int agentIdLen = input.readInt();
        byte[] agentIdBytes = new byte[agentIdLen];
        input.readFully(agentIdBytes);
        // agentId available for debug: new String(agentIdBytes, StandardCharsets.UTF_8)

        // ── Tick (skip) ───────────────────────────────────────────────────────
        input.readLong();

        // ── Movement ─────────────────────────────────────────────────────────
        final float moveForward = input.readFloat();
        final float moveStrafe  = input.readFloat();
        final float yawDelta    = input.readFloat();
        final float pitchDelta  = input.readFloat();

        // ── Flags byte (FIX: 1 packed byte, NOT 7 individual bytes) ──────────
        // Python: struct.pack('!B', flags)   — one byte, bits packed MSB→LSB:
        //   bit7=jump, bit6=sneak, bit5=attack, bit4=use,
        //   bit3=drop, bit2=open_inv, bit1=swap_hand, bit0=sprint
        final byte actionFlags = input.readByte();

        // ── Hotbar slot (FIX: new field, was missing) ─────────────────────────
        // Python: struct.pack('!B', hotbar_byte)  — 0xFF means no change
        final int rawHotbar  = input.readByte() & 0xFF;
        final int hotbarSlot = (rawHotbar == 0xFF) ? -1 : rawHotbar;

        // ── God ability section ───────────────────────────────────────────────
        // Python: struct.pack('!H', len) + name_bytes + struct.pack('!fff', p1,p2,p3)
        //         or struct.pack('!H', 0) when no ability
        String godAbility = null;
        float  p1 = 0f, p2 = 0f, p3 = 0f;
        int abilityLen = input.readShort() & 0xFFFF;
        if (abilityLen > 0) {
            byte[] abBytes = new byte[abilityLen];
            input.readFully(abBytes);
            godAbility = new String(abBytes, StandardCharsets.UTF_8);
            p1 = input.readFloat();
            p2 = input.readFloat();
            p3 = input.readFloat();
        }

        final String fAbility = godAbility;
        final float  fP1 = p1, fP2 = p2, fP3 = p3;

        // ── Dispatch on main thread ───────────────────────────────────────────
        Minecraft.getInstance().execute(() -> {
            ActionExecutor.executeAction(
                moveForward, moveStrafe,
                yawDelta,    pitchDelta,
                actionFlags, hotbarSlot);

            if (fAbility != null && !fAbility.isEmpty()) {
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

    // -------------------------------------------------------------------------
    // Lifecycle
    // -------------------------------------------------------------------------

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

    /**
     * The port this server is (or will be) listening on.
     * Returns cachedPort after start() is called — no warning spam.
     */
    public static int getPort() {
        return cachedPort > 0 ? cachedPort : 0;
    }
}