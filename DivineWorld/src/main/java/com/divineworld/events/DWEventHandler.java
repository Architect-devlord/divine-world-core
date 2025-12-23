// src/main/java/com/divineworld/events/DWEventHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * FIXED - Server-side event handler for AI player management
 * Minecraft Forge 1.20.1 with Parchment mappings
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class DWEventHandler {

    /**
     * Called when a player joins the server
     */
    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        String username = player.getName().getString();

        DWMod.LOGGER.info("Player joined: {} (UUID: {})", username, player.getUUID());

        // PATTERN 1: Username-based detection
        // Format: AI_<agentId> or GOD_<type>_<agentId>

        if (username.startsWith("GOD_")) {
            // God-tier agent
            // Format: GOD_<type>_<agentId>
            String[] parts = username.substring(4).split("_", 2);
            if (parts.length == 2) {
                String godType = parts[0].toLowerCase();
                String agentId = parts[1];

                DWNPCManager.registerGodPlayer(player, agentId, godType);
                notifyBackendPlayerConnected(agentId, player.getUUID().toString(), "god_" + godType);

                DWMod.LOGGER.info("✅ Registered GOD player: {} (Type: {}, Agent: {})",
                        username, godType, agentId);
            }
        }
        else if (username.startsWith("AI_")) {
            // Regular NPC agent
            String agentId = username.substring(3); // Remove "AI_" prefix

            DWNPCManager.registerAIPlayer(player, agentId);
            notifyBackendPlayerConnected(agentId, player.getUUID().toString(), "npc");

            DWMod.LOGGER.info("✅ Registered AI player: {} (Agent: {})", username, agentId);
        }

        // PATTERN 2: Persistent data from client mod
        // DWClientMod sets this data when connecting
        if (player.getPersistentData().contains("dw_agent_id")) {
            String agentId = player.getPersistentData().getString("dw_agent_id");
            String agentType = player.getPersistentData().getString("dw_agent_type");

            if (agentType.startsWith("god_")) {
                String godType = agentType.substring(4);
                DWNPCManager.registerGodPlayer(player, agentId, godType);

                DWMod.LOGGER.info("✅ Registered GOD player via NBT: {} (Type: {})",
                        agentId, godType);
            } else {
                DWNPCManager.registerAIPlayer(player, agentId);

                DWMod.LOGGER.info("✅ Registered AI player via NBT: {}", agentId);
            }

            notifyBackendPlayerConnected(agentId, player.getUUID().toString(), agentType);
        }
    }

    /**
     * Called when a player leaves the server
     */
    @SubscribeEvent
    public static void onPlayerLeave(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) {
            return;
        }

        if (DWNPCManager.isAIPlayer(player)) {
            String agentId = DWNPCManager.getAgentId(player);

            DWNPCManager.unregisterAIPlayer(player);

            if (agentId != null) {
                notifyBackendPlayerDisconnected(agentId, player.getUUID().toString());
                DWMod.LOGGER.info("❌ AI player disconnected: {} (Agent: {})",
                        player.getName().getString(), agentId);
            }
        }
    }

    /**
     * Server tick event for cooldown management
     */
    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase == TickEvent.Phase.END) {
            DWNPCManager.tickCooldowns();
        }
    }

    /**
     * Notify Python backend that an AI player connected
     */
    private static void notifyBackendPlayerConnected(String agentId, String playerUuid, String agentType) {
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
                    DWMod.LOGGER.info("✅ Backend notified: {} connected", agentId);
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
     * Notify Python backend that an AI player disconnected
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