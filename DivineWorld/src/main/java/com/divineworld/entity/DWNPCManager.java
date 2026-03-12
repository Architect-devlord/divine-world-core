package com.divineworld.entity;

import com.divineworld.DWMod;
import com.divineworld.network.NetworkHandler;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Manager for AI-controlled ServerPlayer entities.
 *
 * Chat bubble system REMOVED — proximity chat (ProximityChatHandler) handles
 * all agent speech.  When an agent speaks, Python calls the chat command which
 * triggers sendSystemMessage via ProximityChatHandler, reaching nearby players
 * and the agent's own WebSocket observation automatically.
 *
 * ChatPacket and NetworkHandler.INSTANCE.send() calls are gone from this class.
 */
public class DWNPCManager {

    // tickCooldowns still used for future per-agent rate limits if needed
    private static final Map<UUID, Integer> cooldowns = new HashMap<>();

    public static void registerAIPlayer(ServerPlayer player, String agentId) {
        TaggedEntitySystem.tagEntity(player, TaggedEntitySystem.TAG_DW_NPC);
        TaggedEntitySystem.setAIID(player, agentId);
        DWMod.LOGGER.info("✅ Registered AI player: {} (Agent ID: {})",
                player.getName().getString(), agentId);
    }

    public static void registerGodPlayer(ServerPlayer player, String agentId, String godType) {
        TaggedEntitySystem.tagEntity(player,
                TaggedEntitySystem.TAG_DW_NPC,
                TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setAIID(player, agentId);
        TaggedEntitySystem.setGodType(player, godType);
        TaggedEntitySystem.setDivinePower(player, 100);
        TaggedEntitySystem.makeGenesisImmune(player);
        DWMod.LOGGER.info("✅ Registered God player: {} (Type: {}, Agent ID: {})",
                player.getName().getString(), godType, agentId);
    }

    public static boolean isAIPlayer(ServerPlayer player) {
        return TaggedEntitySystem.hasTag(player, TaggedEntitySystem.TAG_DW_NPC);
    }

    public static boolean isGodPlayer(ServerPlayer player) {
        return TaggedEntitySystem.hasTag(player, TaggedEntitySystem.TAG_DW_GOD);
    }

    /**
     * Make an agent send a chat message to nearby players.
     * ProximityChatHandler intercepts it and delivers it to everyone within
     * PROXIMITY_RADIUS — no separate chat-bubble packet needed.
     */
    public static void sendAgentChat(ServerLevel world, String agentId, String message) {
        if (message == null || message.isEmpty()) return;

        for (ServerPlayer player : world.players()) {
            if (isAIPlayer(player) && agentId.equals(TaggedEntitySystem.getAIID(player))) {

                int cooldown = cooldowns.getOrDefault(player.getUUID(), 0);
                if (cooldown > 0) return;
                cooldowns.put(player.getUUID(), 20); // 1-second rate limit

                // Simulate the agent speaking — ProximityChatHandler handles delivery
                // and notifies god agents via HTTP automatically.
                player.getServer().getPlayerList().broadcastSystemMessage(
                        Component.literal("<" + player.getName().getString() + "> " + message),
                        false
                );

                DWMod.LOGGER.debug("[AgentChat] {}: {}", agentId, message);
                return;
            }
        }
        DWMod.LOGGER.warn("Agent not found for chat: {}", agentId);
    }

    public static void tickCooldowns() {
        cooldowns.replaceAll((uuid, ticks) -> Math.max(0, ticks - 1));
    }

    public static List<ServerPlayer> getAIPlayers(ServerLevel world) {
        return world.players().stream()
                .filter(DWNPCManager::isAIPlayer)
                .collect(Collectors.toList());
    }

    public static List<ServerPlayer> getGodPlayers(ServerLevel world) {
        return world.players().stream()
                .filter(DWNPCManager::isGodPlayer)
                .collect(Collectors.toList());
    }

    public static String getAgentId(ServerPlayer player) {
        return isAIPlayer(player) ? TaggedEntitySystem.getAIID(player) : null;
    }

    public static ServerPlayer findPlayerByAgentId(ServerLevel world, String agentId) {
        for (ServerPlayer player : world.players())
            if (isAIPlayer(player) && agentId.equals(TaggedEntitySystem.getAIID(player)))
                return player;
        return null;
    }

    public static void unregisterAIPlayer(ServerPlayer player) {
        String agentId = getAgentId(player);
        if (agentId != null) {
            cooldowns.remove(player.getUUID());
            DWMod.LOGGER.info("Unregistered AI player: {} (Agent ID: {})",
                    player.getName().getString(), agentId);
        }
    }

    public static void promoteToGod(ServerPlayer player, String godType) {
        if (!isAIPlayer(player)) {
            DWMod.LOGGER.warn("Cannot promote non-AI player to god: {}",
                    player.getName().getString());
            return;
        }
        TaggedEntitySystem.tagEntity(player, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(player, godType);
        TaggedEntitySystem.setDivinePower(player, 100);
        TaggedEntitySystem.makeGenesisImmune(player);
        DWMod.LOGGER.info("Promoted {} to God ({})", player.getName().getString(), godType);
    }

    public static void demoteFromGod(ServerPlayer player) {
        if (!isGodPlayer(player)) return;
        player.getPersistentData().remove(TaggedEntitySystem.TAG_DW_GOD);
        player.getPersistentData().remove(TaggedEntitySystem.TAG_GOD_TYPE);
        player.getPersistentData().remove(TaggedEntitySystem.TAG_DIVINE_POWER);
        player.getPersistentData().remove(TaggedEntitySystem.TAG_GENESIS_IMMUNE);
        DWMod.LOGGER.info("Demoted {} from God status", player.getName().getString());
    }
}