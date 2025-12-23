package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;

/**
 * Network Handler
 * Registers custom network packets (if needed)
 */
public class NetworkHandler {

    public static void register() {
        DWClientMod.LOGGER.info("Network handler registered");

        // For now, we use WebSocket for all communication
        // This is a placeholder for future Forge packet system integration

        // Initialize WebSocket when player joins
        // (handled in ClientEventHandler)
    }
}