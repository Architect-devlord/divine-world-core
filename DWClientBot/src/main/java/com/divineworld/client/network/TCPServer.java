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
 * TCP Server for receiving actions from Python agent.
 * Primary low-latency communication channel.
 */
public class TCPServer {
    private static ServerSocket serverSocket;
    private static Socket clientSocket;
    private static DataInputStream input;
    private static boolean running = false;

    private static final ExecutorService executor = Executors.newSingleThreadExecutor(r -> {
        Thread t = new Thread(r, "DW-TCP-Server");
        t.setDaemon(true);
        return t;
    });

    public static void start(int port) {
        if (running) {
            DWClientMod.LOGGER.warn("TCP Server already running");
            return;
        }

        executor.execute(() -> runServer(port));
    }

    private static void runServer(int port) {
        running = true;

        try {
            serverSocket = new ServerSocket(port);
            DWClientMod.LOGGER.info("TCP Server listening on port {}", port);

            while (running) {
                try {
                    // Accept connection from Python agent
                    DWClientMod.LOGGER.info("Waiting for agent connection...");
                    clientSocket = serverSocket.accept();
                    clientSocket.setTcpNoDelay(true);

                    input = new DataInputStream(clientSocket.getInputStream());

                    DWClientMod.LOGGER.info("Agent connected via TCP: {}",
                            clientSocket.getRemoteSocketAddress());

                    // Handle action frames
                    while (clientSocket.isConnected()) {
                        handleActionFrame();
                    }

                } catch (IOException e) {
                    if (running) {
                        DWClientMod.LOGGER.warn("Client disconnected: {}", e.getMessage());
                    }
                }
            }

        } catch (IOException e) {
            DWClientMod.LOGGER.error("TCP Server error: {}", e.getMessage());
        } finally {
            cleanup();
        }
    }

    private static void handleActionFrame() throws IOException {
        // Read frame matching ForgeIPCClient.send_action() format:
        // struct.pack("!I{len}sQffffBBBBBBB", ...)

        // Agent ID length (4 bytes, big-endian int)
        int agentIdLen = input.readInt();

        // Agent ID (variable length string)
        byte[] agentIdBytes = new byte[agentIdLen];
        input.readFully(agentIdBytes);
        String agentId = new String(agentIdBytes, StandardCharsets.UTF_8);

        // Tick (8 bytes, big-endian long)
        long tick = input.readLong();

        // Movement (4 floats, big-endian)
        final float moveForward = input.readFloat();
        final float moveStrafe = input.readFloat();
        final float yawDelta = input.readFloat();
        final float pitchDelta = input.readFloat();

        // Boolean actions (7 bytes)
        byte jump = input.readByte();
        byte sneak = input.readByte();
        byte attack = input.readByte();
        byte use = input.readByte();
        byte drop = input.readByte();
        byte openInv = input.readByte();
        byte swapHand = input.readByte();

        // Pack into action flags for ActionExecutor
        byte flags = 0;
        if (jump != 0) flags |= (byte) 0b10000000;
        if (sneak != 0) flags |= (byte) 0b01000000;
        if (attack != 0) flags |= (byte) 0b00100000;
        if (use != 0) flags |= (byte) 0b00010000;
        if (drop != 0) flags |= (byte) 0b00001000;
        if (openInv != 0) flags |= (byte) 0b00000100;
        if (swapHand != 0) flags |= (byte) 0b00000010;

        // Make final for lambda
        final byte actionFlags = flags;

        // Execute on main thread
        Minecraft.getInstance().execute(() -> {
            ActionExecutor.executeAction(
                    moveForward,
                    moveStrafe,
                    yawDelta,
                    pitchDelta,
                    actionFlags,
                    -1  // No hotbar slot in TCP protocol
            );
        });
    }

    public static void stop() {
        running = false;
        cleanup();
        executor.shutdown();
    }

    private static void cleanup() {
        try {
            if (input != null) input.close();
            if (clientSocket != null) clientSocket.close();
            if (serverSocket != null) serverSocket.close();
        } catch (IOException e) {
            // Ignore cleanup errors
        }
    }

    public static boolean isConnected() {
        return clientSocket != null && clientSocket.isConnected();
    }
}