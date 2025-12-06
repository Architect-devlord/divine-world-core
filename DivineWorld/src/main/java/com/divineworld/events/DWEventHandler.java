// com/divineworld/events/DWEventHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;

import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Server-side event handler for AI player management.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class DWEventHandler {

    /**
     * Called when a player joins the server.
     * Detects AI agents and registers them.
     */
    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        String username = player.getName().getString();

        // Check if this is an AI agent
        // AI agents are identified by:
        // 1. Username pattern: "AI_<agentId>" or "GOD_<type>_<agentId>"
        // 2. Custom player data (set by DWClientBot on login)

        if (username.startsWith("AI_")) {
            // Regular NPC agent
            String agentId = username.substring(3); // Remove "AI_" prefix
            DWNPCManager.registerAIPlayer(player, agentId);

            // Notify Python backend
            notifyBackendPlayerConnected(agentId, player.getUUID().toString(), "npc");

        } else if (username.startsWith("GOD_")) {
            // God-tier agent
            // Format: GOD_<type>_<agentId>
            String[] parts = username.substring(4).split("_", 2);
            if (parts.length == 2) {
                String godType = parts[0].toLowerCase();
                String agentId = parts[1];

                DWNPCManager.registerGodPlayer(player, agentId, godType);

                // Notify Python backend
                notifyBackendPlayerConnected(agentId, player.getUUID().toString(), "god_" + godType);
            }
        }

        // Alternative: Check persistent data set by client mod
        if (player.getPersistentData().contains("dw_agent_id")) {
            String agentId = player.getPersistentData().getString("dw_agent_id");
            String agentType = player.getPersistentData().getString("dw_agent_type");

            if (agentType.startsWith("god_")) {
                String godType = agentType.substring(4);
                DWNPCManager.registerGodPlayer(player, agentId, godType);
            } else {
                DWNPCManager.registerAIPlayer(player, agentId);
            }

            notifyBackendPlayerConnected(agentId, player.getUUID().toString(), agentType);
        }
    }

    /**
     * Called when a player leaves the server.
     */
    @SubscribeEvent
    public static void onPlayerLeave(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        if (DWNPCManager.isAIPlayer(player)) {
            String agentId = DWNPCManager.getAgentId(player);
            DWNPCManager.unregisterAIPlayer(player);

            // Notify Python backend
            notifyBackendPlayerDisconnected(agentId, player.getUUID().toString());
        }
    }

    /**
     * Server tick event for cooldown management.
     */
    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase == TickEvent.Phase.END) {
            DWNPCManager.tickCooldowns();
        }
    }

    /**
     * Notify Python backend that an AI player connected.
     * This is done via HTTP POST (async).
     */
    private static void notifyBackendPlayerConnected(String agentId, String playerUuid, String agentType) {
        // Run in separate thread to avoid blocking server
        new Thread(() -> {
            try {
                String backendUrl = System.getProperty("dw.backend", "http://127.0.0.1:11400");

                java.net.http.HttpClient client = java.net.http.HttpClient.newHttpClient();

                String json = String.format(
                        "{\"agent_id\":\"%s\",\"player_uuid\":\"%s\",\"agent_type\":\"%s\",\"event\":\"connected\"}",
                        agentId, playerUuid, agentType
                );

                java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(backendUrl + "/api/player_event"))
                        .header("Content-Type", "application/json")
                        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(json))
                        .build();

                java.net.http.HttpResponse<String> response = client.send(
                        request,
                        java.net.http.HttpResponse.BodyHandlers.ofString()
                );

                if (response.statusCode() == 200) {
                    DWMod.LOGGER.info("✅ Notified backend: {} connected", agentId);
                } else {
                    DWMod.LOGGER.warn("⚠️ Backend notification failed: {} (code: {})",
                            agentId, response.statusCode());
                }

            } catch (Exception e) {
                DWMod.LOGGER.error("Failed to notify backend: {}", e.getMessage());
            }
        }, "DW-BackendNotify-" + agentId).start();
    }

    /**
     * Notify Python backend that an AI player disconnected.
     */
    private static void notifyBackendPlayerDisconnected(String agentId, String playerUuid) {
        new Thread(() -> {
            try {
                String backendUrl = System.getProperty("dw.backend", "http://127.0.0.1:11400");

                java.net.http.HttpClient client = java.net.http.HttpClient.newHttpClient();

                String json = String.format(
                        "{\"agent_id\":\"%s\",\"player_uuid\":\"%s\",\"event\":\"disconnected\"}",
                        agentId, playerUuid
                );

                java.net.http.HttpRequest request = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(backendUrl + "/api/player_event"))
                        .header("Content-Type", "application/json")
                        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(json))
                        .build();

                client.send(request, java.net.http.HttpResponse.BodyHandlers.ofString());

            } catch (Exception e) {
                DWMod.LOGGER.error("Failed to notify backend of disconnect: {}", e.getMessage());
            }
        }, "DW-BackendNotify-Disconnect-" + agentId).start();
    }
}