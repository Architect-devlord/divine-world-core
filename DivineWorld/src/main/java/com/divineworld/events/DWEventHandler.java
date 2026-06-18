// src/main/java/com/divineworld/events/DWEventHandler.java
// DivineWorld server mod
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.commands.ServerGodAbilityExecutor;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * DWEventHandler
 * ==============
 * Handles player join / leave / server-tick events.
 *
 * Detection is purely agents.json-based. The Minecraft username IS
 * the clean name stored in agents.json — no DW_ or DWGOD_ prefix.
 *
 *   "Adam"  → NPCs.male         → registered as NPC (male)
 *   "Eve"   → NPCs.female       → registered as NPC (female)
 *   "Zeus"  → GODs.dual.oracle  → GOD — body spawned by GodSpawnHandler
 *
 * TaggedEntitySystem.detectAgentType() is the single source of truth.
 * It reads agents.json once per fresh login and caches the result in NBT
 * so all subsequent tick-level checks are O(1) NBT reads.
 *
 * FIX Bug 1 — Double registerGodPlayer (previously applied):
 *   DWEventHandler no longer calls registerGodPlayer for GOD agents.
 *   GodSpawnHandler is the sole owner, called after the body is in the world.
 *   This handler still calls detectAgentType() so "dw_god_type" is written
 *   into NBT before GodSpawnHandler.onPlayerJoin reads it on the same tick.
 *
 * FIX Bug 13 — tickAbilityCooldowns never wired to server tick:
 *   ServerGodAbilityExecutor stores per-ability cooldowns in player NBT under
 *   keys like "cd_sonic_boom". Without a per-tick decrement those cooldowns
 *   never expired and every ability was permanently blocked after the first use.
 *
 *   Fix: onServerTick now iterates all online god players and calls
 *   ServerGodAbilityExecutor.tickAbilityCooldowns(player) once per tick.
 *   The method simply decrements every NBT int key starting with "cd_" by 1,
 *   stopping at 0. The cost is negligible — there are at most a handful of
 *   god players and the NBT read/write is O(number of active cooldown keys).
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class DWEventHandler {

    // -------------------------------------------------------------------------
    // Player join
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        String username = player.getName().getString();
        DWMod.LOGGER.info("Player joined: {} (UUID: {})", username, player.getUUID());

        // agents.json is the sole authority — username IS the agent's clean name.
        // detectAgentType() writes "dw_god_type" (and "dw_gender") into NBT so
        // GodSpawnHandler.onPlayerJoin can read the cached type on the same tick.
        TaggedEntitySystem.AgentType agentType = TaggedEntitySystem.detectAgentType(player);

        switch (agentType) {

            case GOD -> {
                // Read the type detectAgentType() just cached in NBT.
                // FIX Bug 1: do NOT call registerGodPlayer here —
                // GodSpawnHandler owns full god registration after the body spawns.
                String godType = TaggedEntitySystem.extractGodType(player);
                if (godType == null || godType.isEmpty()) godType = "oracle";

                // Notify the Python backend immediately so it knows a god connected.
                notifyBackend(username, player.getUUID().toString(), "god_" + godType, "connected");

                DWMod.LOGGER.info("✅ GOD joined: {} (type={}), body spawn in 40 ticks", username, godType);
            }

            case NPC_MALE -> {
                DWNPCManager.registerAIPlayer(player, username);
                player.getPersistentData().putString("dw_gender", "male");
                notifyBackend(username, player.getUUID().toString(), "npc_male", "connected");
                DWMod.LOGGER.info("✅ NPC (male) joined: {}", username);
            }

            case NPC_FEMALE -> {
                DWNPCManager.registerAIPlayer(player, username);
                player.getPersistentData().putString("dw_gender", "female");
                notifyBackend(username, player.getUUID().toString(), "npc_female", "connected");
                DWMod.LOGGER.info("✅ NPC (female) joined: {}", username);
            }

            case REAL_PLAYER -> {
                DWMod.LOGGER.debug("Real player joined: {}", username);
            }
        }
    }

    // -------------------------------------------------------------------------
    // Player leave
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onPlayerLeave(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        if (DWNPCManager.isAIPlayer(player)) {
            String agentId = DWNPCManager.getAgentId(player);
            DWNPCManager.unregisterAIPlayer(player);
            if (agentId != null) {
                notifyBackend(agentId, player.getUUID().toString(), "any", "disconnected");
                DWMod.LOGGER.info("❌ Agent disconnected: {}", agentId);
            }
        }
    }

    // -------------------------------------------------------------------------
    // Server tick — cooldown management
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        // NPC chat rate-limit cooldowns
        DWNPCManager.tickCooldowns();

        // FIX SGS-2: tickMorphBodies() was never called — real-player (op-4) morph
        // entities stayed frozen at their spawn position instead of following the player.
        if (event.getServer() != null) {
            for (net.minecraft.server.level.ServerLevel level : event.getServer().getAllLevels()) {
                com.divineworld.events.GodDisguiseHandler.tickMorphBodies(level);
            }
        }

        // FIX Bug 13: tick god ability cooldowns every server tick.
        // Without this, ServerGodAbilityExecutor.setCooldown() stored a value
        // that was never decremented, permanently blocking abilities after first use.
        // We iterate all players, skip non-gods, and call tickAbilityCooldowns once.
        if (event.getServer() != null) {
            for (ServerPlayer player : event.getServer().getPlayerList().getPlayers()) {
                if (DWNPCManager.isGodPlayer(player)) {
                    ServerGodAbilityExecutor.tickAbilityCooldowns(player);
                }
            }
        }
    }

    // -------------------------------------------------------------------------
    // Backend notification (fire-and-forget on a daemon thread)
    // -------------------------------------------------------------------------

    /**
     * Notify Python backend and — on "connected" events — read back the
     * spawn_pos the backend stored when it launched this agent.
     *
     * SPAWN COORDINATE FIX:
     * When an agent is spawned via /api/agents/spawn_single (or genesis/god spawn),
     * main.py stores the requested coordinates in agent_info["spawn_pos"].
     * The /api/player_event "connected" response now includes that field.
     * We read it here and teleport the ServerPlayer immediately so the agent
     * arrives at the position that was specified in the API call — not at
     * vanilla world spawn or their last bed.
     *
     * If no spawn_pos is returned (auto-connect, or no position was set),
     * the player stays wherever Minecraft placed them.
     */
    private static void notifyBackend(String agentId, String playerUuid,
                                      String agentType, String eventType) {
        // Capture the server reference once so the lambda can schedule work on it
        net.minecraft.server.MinecraftServer srv = DWMod.getInstance().getServer();

        Thread t = new Thread(() -> {
            try {
                String url = System.getProperty("dw.backend", "http://127.0.0.1:11400")
                        + "/api/player_event";

                String json = String.format(
                        "{\"agent_id\":\"%s\",\"player_uuid\":\"%s\"," +
                        "\"agent_type\":\"%s\",\"event\":\"%s\"}",
                        agentId, playerUuid, agentType, eventType);

                java.net.http.HttpClient client = java.net.http.HttpClient.newHttpClient();
                java.net.http.HttpRequest req = java.net.http.HttpRequest.newBuilder()
                        .uri(java.net.URI.create(url))
                        .header("Content-Type", "application/json")
                        .POST(java.net.http.HttpRequest.BodyPublishers.ofString(json))
                        .build();

                var resp = client.send(req, java.net.http.HttpResponse.BodyHandlers.ofString());

                if (resp.statusCode() != 200) {
                    DWMod.LOGGER.warn("⚠ Backend notify failed for {} (HTTP {})",
                            agentId, resp.statusCode());
                    return;
                }

                DWMod.LOGGER.info("✅ Backend notified: {} {}", agentId, eventType);

                // On "connected" events, check if the backend returned a spawn_pos.
                if (!"connected".equals(eventType) || srv == null) return;

                com.google.gson.JsonObject body = new com.google.gson.Gson()
                        .fromJson(resp.body(), com.google.gson.JsonObject.class);
                if (body == null || !body.has("spawn_pos")) return;

                com.google.gson.JsonObject pos = body.getAsJsonObject("spawn_pos");
                if (!pos.has("x") || !pos.has("y") || !pos.has("z")) return;

                double tx = pos.get("x").getAsDouble();
                double ty = pos.get("y").getAsDouble();
                double tz = pos.get("z").getAsDouble();

                DWMod.LOGGER.info("[SpawnPos] Teleporting {} to ({}, {}, {})", agentId, tx, ty, tz);

                // Schedule teleport on the server thread — teleportTo is NOT thread-safe
                srv.execute(() -> {
                    net.minecraft.server.level.ServerPlayer player =
                            srv.getPlayerList().getPlayerByName(agentId);
                    if (player != null) {
                        player.teleportTo(tx, ty, tz);
                        DWMod.LOGGER.info("✅ Teleported {} to ({}, {}, {})", agentId, tx, ty, tz);
                    } else {
                        DWMod.LOGGER.warn("[SpawnPos] Player {} not found for teleport", agentId);
                    }
                });

            } catch (Exception e) {
                DWMod.LOGGER.error("Failed to notify backend ({}): {}", eventType, e.getMessage());
            }
        }, "DW-BackendNotify-" + agentId);
        t.setDaemon(true);
        t.start();
    }
}
