// src/main/java/com/divineworld/utils/GenesisManager.java
package com.divineworld.utils;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.Level;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Genesis Manager — UPDATED
 *
 * All original features preserved exactly. New additions only:
 *  1. Genesis Codex book now ALSO triggers genesis when right-clicked on the
 *     GROUND (RightClickBlock), in addition to the existing air-use path.
 *  2. Both genesis AND divine-reset display an animated 5-block magic circle
 *     via DivineMagicCircle for their full durations.
 *
 * Original behaviour unchanged:
 *  - onGenesisUse() public API, signature, and all return values identical.
 *  - triggerDivineReset() god-only restriction kept ACTIVE.
 *  - Countdown warnings at original tick milestones (40 / 100 / 160).
 *  - executeDivineReset() null-guard, item clear, backend notify all present.
 *  - divineResetActive + resetTicks cleared in onServerTick BEFORE execute.
 *  - getSafeSpawnPosition() identical logic (10-iteration loop, checks above).
 *  - canUseGenesis() / getGenesisCooldown() / isDivineResetActive() /
 *    getDivineResetProgress() all preserved without change.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GenesisManager {

    // -------------------------------------------------------------------------
    // Constants / state (unchanged from original)
    // -------------------------------------------------------------------------

    private static final Map<UUID, Long> GENESIS_COOLDOWNS   = new HashMap<>();
    private static final long            GENESIS_COOLDOWN_MS = 300_000L; // 5 minutes

    private static boolean     divineResetActive = false;
    private static int         resetTicks        = 0;
    private static final int   RESET_DURATION    = 200;       // 10 seconds
    private static ServerLevel targetWorld       = null;
    private static Entity      initiator         = null;

    // -------------------------------------------------------------------------
    // NEW: magic circle state
    // -------------------------------------------------------------------------

    private static final int CIRCLE_INTERVAL = 3; // refresh every 3 ticks

    // Genesis circle
    private static boolean     genesisCircleActive   = false;
    private static int         genesisCircleTick     = 0;
    private static final int   GENESIS_CIRCLE_DURATION = 60; // 3 seconds
    private static ServerLevel genesisCircleLevel    = null;
    private static BlockPos    genesisCircleCenter   = null;

    // -------------------------------------------------------------------------
    // NEW: Ground right-click trigger
    // -------------------------------------------------------------------------

    /**
     * Fires when a player right-clicks any block while holding the Genesis
     * Codex.  Cancels the vanilla book-GUI and triggers genesis centred on the
     * clicked block.
     */
    @SubscribeEvent
    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        if (event.getLevel().isClientSide()) return;
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        ItemStack stack = player.getItemInHand(event.getHand());
        if (!isGenesisCodex(stack)) return;

        event.setCanceled(true);
        event.setCancellationResult(InteractionResult.SUCCESS);

        // Use the clicked block as magic-circle anchor; spawn positions still
        // calculated relative to the player (consistent with original behaviour)
        triggerGenesisFromGround(player, (ServerLevel) event.getLevel(), event.getPos());
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: Air right-click / command path (public API — unchanged)
    // -------------------------------------------------------------------------

    /**
     * Called when the Genesis Codex is used (right-clicked in the air).
     * Signature and all return values identical to the original.
     */
    public static InteractionResult onGenesisUse(ServerPlayer player, Level level, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);

        if (!stack.is(Items.WRITTEN_BOOK)) {
            return InteractionResult.PASS;
        }

        if (!stack.hasCustomHoverName() ||
                !stack.getHoverName().getString().contains("Genesis Codex")) {
            return InteractionResult.PASS;
        }

        if (level.isClientSide()) {
            return InteractionResult.SUCCESS;
        }

        ServerLevel serverLevel = (ServerLevel) level;

        // Original cooldown — returns FAIL (not void/null) on cooldown
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());

        if (lastUse != null && (now - lastUse) < GENESIS_COOLDOWN_MS) {
            long remainingSeconds = (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000;
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + remainingSeconds + " seconds remaining"
            ));
            return InteractionResult.FAIL;
        }

        GENESIS_COOLDOWNS.put(player.getUUID(), now);

        // Original spawn positions (relative to PLAYER)
        BlockPos playerPos = player.blockPosition();
        BlockPos spawn1 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(2, 0, 0));
        BlockPos spawn2 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0));

        player.sendSystemMessage(Component.literal("§d[Genesis] §cCreating first beings..."));

        PythonBackendClient.spawnGenesisAgents(
                player.getName().getString(),
                serverLevel.dimension().location().toString(),
                spawn1,
                spawn2
        );

        DWMod.LOGGER.info("Genesis invoked by {} at {}", player.getName().getString(), playerPos);

        // NEW: magic circle centred at player position
        startGenesisCircle(serverLevel, playerPos);

        return InteractionResult.SUCCESS;
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: triggerDivineReset — god restriction KEPT ACTIVE
    // -------------------------------------------------------------------------

    public static void triggerDivineReset(ServerLevel world, Entity initiatorEntity) {
        if (divineResetActive) {
            DWMod.LOGGER.warn("Divine Reset already in progress!");
            return;
        }

        // ORIGINAL god-only restriction — active and unchanged
        if (initiatorEntity instanceof ServerPlayer player) {
            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[Divine Reset] Only gods may invoke the Divine Reset!"
                ));
                return;
            }
        }

        divineResetActive = true;
        resetTicks        = 0;
        targetWorld       = world;
        initiator         = initiatorEntity;

        DWMod.LOGGER.info("⚡ DIVINE RESET INITIATED ⚡");

        broadcastToWorld(world, "§4§l⚡⚡⚡ DIVINE RESET ⚡⚡⚡");
        broadcastToWorld(world, "§cAll AI agents will be purged in 10 seconds...");
        broadcastToWorld(world, "§eTheir memories will be erased from existence.");

        // NEW: opening sound
        if (initiatorEntity != null) {
            world.playSound(null, initiatorEntity.blockPosition(),
                    SoundEvents.WITHER_SPAWN, SoundSource.AMBIENT, 1.0f, 0.8f);
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: onServerTick — countdown milestones preserved exactly
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        // NEW: genesis circle animation
        tickGenesisCircle();

        if (!divineResetActive) return;

        resetTicks++;

        // ORIGINAL countdown warnings — exact tick values (40 / 100 / 160) preserved
        if (resetTicks == 40) {
            broadcastToWorld(targetWorld, "§c⚡ 8 seconds...");
        } else if (resetTicks == 100) {
            broadcastToWorld(targetWorld, "§c⚡ 5 seconds...");
        } else if (resetTicks == 160) {
            broadcastToWorld(targetWorld, "§c⚡ 2 seconds...");
        }

        // NEW: magic circle during reset countdown
        if (resetTicks % CIRCLE_INTERVAL == 0 && targetWorld != null && initiator != null) {
            DivineMagicCircle.spawnDivineResetCircle(
                    targetWorld, initiator.blockPosition(), resetTicks);
        }

        // ORIGINAL: clear active-flag and resetTicks BEFORE calling execute
        // (original order preserved to match re-entrancy behaviour)
        if (resetTicks >= RESET_DURATION) {
            divineResetActive = false;
            resetTicks        = 0;
            executeDivineReset();
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: executeDivineReset — null guard, item clear, backend identical
    // -------------------------------------------------------------------------

    private static void executeDivineReset() {
        // ORIGINAL null guard
        if (targetWorld == null) return;

        DWMod.LOGGER.info("Executing Divine Reset on world: " + targetWorld.dimension().location());

        List<ServerPlayer> aiAgents = DWNPCManager.getAIPlayers(targetWorld);

        DWMod.LOGGER.info("Divine Reset targeting {} AI agents", aiAgents.size());

        java.util.List<String> agentIds = new java.util.ArrayList<>();

        for (ServerPlayer agent : aiAgents) {
            String agentId = DWNPCManager.getAgentId(agent);
            if (agentId != null) {
                agentIds.add(agentId);
                agent.connection.disconnect(
                        Component.literal("§c[Divine Reset] Your existence has been erased"));
                DWMod.LOGGER.info("  - Purged: {}", agentId);
            }
        }

        // ORIGINAL: clear all item entities
        for (Entity entity : targetWorld.getAllEntities()) {
            if (entity instanceof ItemEntity) {
                entity.remove(Entity.RemovalReason.DISCARDED);
            }
        }

        broadcastToWorld(targetWorld, "§a§l✨ DIVINE RESET COMPLETE ✨");
        broadcastToWorld(targetWorld, "§e" + aiAgents.size() + " AI agents have been purged");
        broadcastToWorld(targetWorld, "§7Their memories are being erased...");

        PythonBackendClient.notifyDivineReset(
                targetWorld.dimension().location().toString(),
                agentIds
        );

        // ORIGINAL cleanup order
        targetWorld = null;
        initiator   = null;
    }

    // -------------------------------------------------------------------------
    // NEW: ground-click genesis (shared cooldown, player-relative spawns)
    // -------------------------------------------------------------------------

    private static void triggerGenesisFromGround(ServerPlayer player,
                                                  ServerLevel serverLevel,
                                                  BlockPos circleCenter) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());

        if (lastUse != null && (now - lastUse) < GENESIS_COOLDOWN_MS) {
            long remainingSeconds = (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000;
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + remainingSeconds + " seconds remaining"
            ));
            return;
        }

        GENESIS_COOLDOWNS.put(player.getUUID(), now);

        // Spawn positions relative to PLAYER (matches original behaviour)
        BlockPos playerPos = player.blockPosition();
        BlockPos spawn1 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(2, 0, 0));
        BlockPos spawn2 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0));

        player.sendSystemMessage(Component.literal("§d[Genesis] §cCreating first beings..."));

        PythonBackendClient.spawnGenesisAgents(
                player.getName().getString(),
                serverLevel.dimension().location().toString(),
                spawn1,
                spawn2
        );

        DWMod.LOGGER.info("Genesis (ground) invoked by {} at {} (circle at {})",
                player.getName().getString(), playerPos, circleCenter);

        // Magic circle centred at the tapped block
        startGenesisCircle(serverLevel, circleCenter);
    }

    // -------------------------------------------------------------------------
    // NEW: magic circle helpers
    // -------------------------------------------------------------------------

    private static void startGenesisCircle(ServerLevel level, BlockPos center) {
        genesisCircleActive = true;
        genesisCircleTick   = 0;
        genesisCircleLevel  = level;
        genesisCircleCenter = center;
    }

    private static void tickGenesisCircle() {
        if (!genesisCircleActive) return;

        if (genesisCircleTick >= GENESIS_CIRCLE_DURATION) {
            genesisCircleActive = false;
            genesisCircleLevel  = null;
            genesisCircleCenter = null;
            return;
        }

        if (genesisCircleTick % CIRCLE_INTERVAL == 0 && genesisCircleLevel != null) {
            DivineMagicCircle.spawnGenesisCircle(
                    genesisCircleLevel, genesisCircleCenter, genesisCircleTick);
        }

        genesisCircleTick++;
    }

    // -------------------------------------------------------------------------
    // Helper: identify the Genesis Codex
    // -------------------------------------------------------------------------

    private static boolean isGenesisCodex(ItemStack stack) {
        if (!stack.is(Items.WRITTEN_BOOK)) return false;
        // Primary: NBT title tag written by BookFactory
        if (stack.getTag() != null && stack.getTag().contains("title")) {
            return stack.getTag().getString("title").contains("Genesis Codex");
        }
        // Fallback: hover name
        return stack.hasCustomHoverName() &&
                stack.getHoverName().getString().contains("Genesis Codex");
    }

    // -------------------------------------------------------------------------
    // ORIGINAL helpers — preserved exactly
    // -------------------------------------------------------------------------

    /**
     * Find safe spawn position (solid ground, air above).
     * Identical to original — 10-iteration loop, checks pos.above() for air.
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

    private static void broadcastToWorld(ServerLevel world, String message) {
        for (ServerPlayer player : world.players()) {
            player.sendSystemMessage(Component.literal(message));
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL public query helpers — preserved exactly
    // -------------------------------------------------------------------------

    public static boolean isDivineResetActive() {
        return divineResetActive;
    }

    public static float getDivineResetProgress() {
        if (!divineResetActive) return 0.0f;
        return (float) resetTicks / (float) RESET_DURATION;
    }

    public static boolean canUseGenesis(ServerPlayer player) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());
        return lastUse == null || (now - lastUse) >= GENESIS_COOLDOWN_MS;
    }

    public static long getGenesisCooldown(ServerPlayer player) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());
        if (lastUse == null) return 0;
        long remaining = GENESIS_COOLDOWN_MS - (now - lastUse);
        return Math.max(0, remaining / 1000);
    }
}