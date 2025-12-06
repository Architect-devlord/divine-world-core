// com/divineworld/entity/DWNPCManager.java
package com.divineworld.entity;

import com.divineworld.DWMod;
import com.divineworld.network.ChatPacket;
import com.divineworld.network.NetworkHandler;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraftforge.network.PacketDistributor;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Manager for AI-controlled player entities.
 * AI agents join as normal ServerPlayer instances via their own Minecraft clients.
 * This class handles tagging, chat bubbles, and differentiation from real players.
 */
public class DWNPCManager {

    // Track AI player cooldowns
    private static final Map<UUID, Integer> chatCooldowns = new HashMap<>();

    /**
     * Register a ServerPlayer as AI-controlled.
     * Called when an AI agent's Minecraft client joins the server.
     */
    public static void registerAIPlayer(ServerPlayer player, String agentId) {
        // Tag the player entity
        TaggedEntitySystem.tagEntity(player, TaggedEntitySystem.TAG_DW_NPC);
        TaggedEntitySystem.setAIID(player, agentId);

        DWMod.LOGGER.info("✅ Registered AI player: {} (Agent ID: {})",
                player.getName().getString(), agentId);
    }

    /**
     * Register a god-tier player entity.
     */
    public static void registerGodPlayer(ServerPlayer player, String agentId, String godType) {
        // Tag as both NPC and God
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

    /**
     * Check if a player is AI-controlled.
     */
    public static boolean isAIPlayer(ServerPlayer player) {
        return TaggedEntitySystem.hasTag(player, TaggedEntitySystem.TAG_DW_NPC);
    }

    /**
     * Check if a player is a god entity.
     */
    public static boolean isGodPlayer(ServerPlayer player) {
        return TaggedEntitySystem.hasTag(player, TaggedEntitySystem.TAG_DW_GOD);
    }

    /**
     * Send overhead chat bubble (NOT global chat).
     * This is called by Python backend via network packet.
     */
    public static void sendChatBubble(ServerLevel world, String agentId, String message) {
        if (message == null || message.isEmpty()) {
            return;
        }

        // Find the ServerPlayer with matching AI ID
        for (ServerPlayer player : world.players()) {
            if (isAIPlayer(player) &&
                    TaggedEntitySystem.getAIID(player).equals(agentId)) {

                // Check cooldown
                int cooldown = chatCooldowns.getOrDefault(player.getUUID(), 0);
                if (cooldown > 0) {
                    return; // Still on cooldown
                }

                // Set cooldown (20 ticks = 1 second)
                chatCooldowns.put(player.getUUID(), 20);

                // Send chat bubble packet to nearby players
                ChatPacket packet = new ChatPacket(player.getUUID(), message);

                for (ServerPlayer nearbyPlayer : world.players()) {
                    double distSq = nearbyPlayer.distanceToSqr(player);
                    if (distSq < 64 * 64) { // Within 64 blocks
                        NetworkHandler.INSTANCE.send(
                                PacketDistributor.PLAYER.with(() -> nearbyPlayer),
                                packet
                        );
                    }
                }

                // Log to server console (optional)
                DWMod.LOGGER.debug("[Chat Bubble] {}: {}",
                        player.getName().getString(), message);

                return;
            }
        }

        DWMod.LOGGER.warn("Agent not found for chat bubble: {}", agentId);
    }

    /**
     * Update cooldowns (call every server tick).
     */
    public static void tickCooldowns() {
        chatCooldowns.replaceAll((uuid, ticks) -> Math.max(0, ticks - 1));
    }

    /**
     * Get all AI-controlled players in world.
     */
    public static List<ServerPlayer> getAIPlayers(ServerLevel world) {
        return world.players().stream()
                .filter(DWNPCManager::isAIPlayer)
                .collect(Collectors.toList());
    }

    /**
     * Get all god-tier players in world.
     */
    public static List<ServerPlayer> getGodPlayers(ServerLevel world) {
        return world.players().stream()
                .filter(DWNPCManager::isGodPlayer)
                .collect(Collectors.toList());
    }

    /**
     * Get agent ID from player.
     */
    public static String getAgentId(ServerPlayer player) {
        if (!isAIPlayer(player)) {
            return null;
        }
        return TaggedEntitySystem.getAIID(player);
    }

    /**
     * Find player by agent ID.
     */
    public static ServerPlayer findPlayerByAgentId(ServerLevel world, String agentId) {
        for (ServerPlayer player : world.players()) {
            if (isAIPlayer(player) &&
                    TaggedEntitySystem.getAIID(player).equals(agentId)) {
                return player;
            }
        }
        return null;
    }

    /**
     * Unregister AI player (on disconnect).
     */
    public static void unregisterAIPlayer(ServerPlayer player) {
        String agentId = getAgentId(player);
        if (agentId != null) {
            chatCooldowns.remove(player.getUUID());
            DWMod.LOGGER.info("Unregistered AI player: {} (Agent ID: {})",
                    player.getName().getString(), agentId);
        }
    }
}