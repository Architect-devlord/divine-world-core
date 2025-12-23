// src/main/java/com/divineworld/utils/GenesisManager.java
package com.divineworld.utils;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Genesis Manager - COMPLETE VERSION
 *
 * Handles:
 * 1. Genesis Book - Spawns 2 AI agents (male + female) from Python
 * 2. Divine Reset - Kills all AI agents and deletes their memories
 * 3. Cooldowns and permissions
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GenesisManager {

    // Genesis cooldowns (per player)
    private static final Map<UUID, Long> GENESIS_COOLDOWNS = new HashMap<>();
    private static final long GENESIS_COOLDOWN_MS = 300_000; // 5 minutes

    // Divine reset state
    private static boolean divineResetActive = false;
    private static int resetTicks = 0;
    private static final int RESET_DURATION = 200; // 10 seconds
    private static ServerLevel targetWorld = null;
    private static Entity initiator = null;

    /**
     * Called when Genesis Codex book is used
     * Spawns 2 AI agents (male + female) via Python backend
     */
    public static InteractionResult onGenesisUse(ServerPlayer player, Level level, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);

        if (!stack.is(Items.WRITTEN_BOOK)) {
            return InteractionResult.PASS;
        }

        // Check if it's the Genesis Codex
        if (!stack.hasCustomHoverName() ||
                !stack.getHoverName().getString().contains("Genesis Codex")) {
            return InteractionResult.PASS;
        }

        if (level.isClientSide()) {
            return InteractionResult.SUCCESS;
        }

        ServerLevel serverLevel = (ServerLevel) level;

        // Check cooldown
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());

        if (lastUse != null && (now - lastUse) < GENESIS_COOLDOWN_MS) {
            long remainingSeconds = (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000;
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + remainingSeconds + " seconds remaining"
            ));
            return InteractionResult.FAIL;
        }

        // Set cooldown
        GENESIS_COOLDOWNS.put(player.getUUID(), now);

        // Calculate spawn positions (safe locations in front of player)
        BlockPos playerPos = player.blockPosition();
        BlockPos spawn1 = getSafeSpawnPosition(serverLevel, playerPos.relative(player.getDirection(), 3).offset(2, 0, 0));
        BlockPos spawn2 = getSafeSpawnPosition(serverLevel, playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0));

        player.sendSystemMessage(Component.literal("§6[Genesis] §eCreating first beings..."));

        // Notify Python backend to spawn 2 agents
        PythonBackendClient.spawnGenesisAgents(
                player.getName().getString(),
                serverLevel.dimension().location().toString(),
                spawn1,
                spawn2
        );

        DWMod.LOGGER.info("Genesis invoked by {} at {}", player.getName().getString(), playerPos);

        return InteractionResult.SUCCESS;
    }

    /**
     * Trigger Divine Reset - Kills all AI agents and deletes memories
     */
    public static void triggerDivineReset(ServerLevel world, Entity initiatorEntity) {
        if (divineResetActive) {
            DWMod.LOGGER.warn("Divine Reset already in progress!");
            return;
        }

        // Check if initiator is a god (optional restriction)
        if (initiatorEntity instanceof ServerPlayer player) {
            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[Divine Reset] Only gods may invoke the Divine Reset!"
                ));
                return;
            }
        }

        divineResetActive = true;
        resetTicks = 0;
        targetWorld = world;
        initiator = initiatorEntity;

        DWMod.LOGGER.info("⚡ DIVINE RESET INITIATED ⚡");

        // Broadcast to all players
        broadcastToWorld(world, "§4§l⚡⚡⚡ DIVINE RESET ⚡⚡⚡");
        broadcastToWorld(world, "§cAll AI agents will be purged in 10 seconds...");
        broadcastToWorld(world, "§eTheir memories will be erased from existence.");
    }

    /**
     * Tick handler for Divine Reset countdown
     */
    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (!divineResetActive || event.phase != TickEvent.Phase.END) return;

        resetTicks++;

        // Countdown warnings
        if (resetTicks == 40) { // 2 seconds
            broadcastToWorld(targetWorld, "§c⚡ 8 seconds...");
        } else if (resetTicks == 100) { // 5 seconds
            broadcastToWorld(targetWorld, "§c⚡ 5 seconds...");
        } else if (resetTicks == 160) { // 8 seconds
            broadcastToWorld(targetWorld, "§c⚡ 2 seconds...");
        }

        // Execute Divine Reset
        if (resetTicks >= RESET_DURATION) {
            executeDivineReset();
            divineResetActive = false;
            resetTicks = 0;
        }
    }

    /**
     * Execute the Divine Reset
     */
    private static void executeDivineReset() {
        if (targetWorld == null) return;

        DWMod.LOGGER.info("Executing Divine Reset on world: " + targetWorld.dimension().location());

        // Get all AI agents
        List<ServerPlayer> aiAgents = DWNPCManager.getAIPlayers(targetWorld);

        DWMod.LOGGER.info("Divine Reset targeting {} AI agents", aiAgents.size());

        // Collect agent IDs for Python backend
        java.util.List<String> agentIds = new java.util.ArrayList<>();

        for (ServerPlayer agent : aiAgents) {
            String agentId = DWNPCManager.getAgentId(agent);
            if (agentId != null) {
                agentIds.add(agentId);

                // Disconnect the agent
                agent.connection.disconnect(Component.literal("§c[Divine Reset] Your existence has been erased"));

                DWMod.LOGGER.info("  - Purged: {}", agentId);
            }
        }

        // Clear items dropped by agents
        for (Entity entity : targetWorld.getAllEntities()) {
            if (entity instanceof ItemEntity) {
                entity.remove(Entity.RemovalReason.DISCARDED);
            }
        }

        broadcastToWorld(targetWorld, "§a§l✨ DIVINE RESET COMPLETE ✨");
        broadcastToWorld(targetWorld, "§e" + aiAgents.size() + " AI agents have been purged");
        broadcastToWorld(targetWorld, "§7Their memories are being erased...");

        // Notify Python backend to delete agent memories
        PythonBackendClient.notifyDivineReset(
                targetWorld.dimension().location().toString(),
                agentIds
        );

        targetWorld = null;
        initiator = null;
    }

    /**
     * Find safe spawn position (solid ground, air above)
     */
    private static BlockPos getSafeSpawnPosition(ServerLevel level, BlockPos pos) {
        for (int i = 0; i < 10; i++) {
            if (level.getBlockState(pos).isAir() &&
                    level.getBlockState(pos.above()).isAir() &&
                    level.getBlockState(pos.below()).isSolid()) {
                return pos;
            }
            pos = pos.above();
        }
        return pos; // Fallback
    }

    /**
     * Broadcast message to all players in world
     */
    private static void broadcastToWorld(ServerLevel world, String message) {
        for (ServerPlayer player : world.players()) {
            player.sendSystemMessage(Component.literal(message));
        }
    }

    /**
     * Check if Divine Reset is active
     */
    public static boolean isDivineResetActive() {
        return divineResetActive;
    }

    /**
     * Get Divine Reset progress (0.0 to 1.0)
     */
    public static float getDivineResetProgress() {
        if (!divineResetActive) return 0.0f;
        return (float) resetTicks / (float) RESET_DURATION;
    }

    /**
     * Check if player can use Genesis (cooldown check)
     */
    public static boolean canUseGenesis(ServerPlayer player) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());

        return lastUse == null || (now - lastUse) >= GENESIS_COOLDOWN_MS;
    }

    /**
     * Get remaining cooldown for player (in seconds)
     */
    public static long getGenesisCooldown(ServerPlayer player) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());

        if (lastUse == null) return 0;

        long remaining = GENESIS_COOLDOWN_MS - (now - lastUse);
        return Math.max(0, remaining / 1000);
    }
}