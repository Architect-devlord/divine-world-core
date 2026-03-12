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

@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GenesisManager {

    private static final Map<UUID, Long> GENESIS_COOLDOWNS   = new HashMap<>();
    private static final long            GENESIS_COOLDOWN_MS = 300_000L;

    private static boolean     divineResetActive = false;
    private static int         resetTicks        = 0;
    private static final int   RESET_DURATION    = 200;
    private static ServerLevel targetWorld       = null;
    private static Entity      initiator         = null;

    private static final int CIRCLE_INTERVAL = 3;

    private static boolean     genesisCircleActive     = false;
    private static int         genesisCircleTick       = 0;
    private static final int   GENESIS_CIRCLE_DURATION = 60;
    private static ServerLevel genesisCircleLevel      = null;
    private static BlockPos    genesisCircleCenter     = null;

    /**
     * Trigger genesis when the Genesis Codex is right-clicked while held
     * (clicking on a block / in the air with the book in hand).
     */
    @SubscribeEvent
    public static void onRightClickBlock(PlayerInteractEvent.RightClickBlock event) {
        if (event.getLevel().isClientSide()) return;
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        ItemStack stack = player.getItemInHand(event.getHand());
        if (!isGenesisCodex(stack)) return;
        event.setCanceled(true);
        event.setCancellationResult(InteractionResult.SUCCESS);
        triggerGenesisFromGround(player, (ServerLevel) event.getLevel(), event.getPos());
    }

    /**
     * Trigger genesis when a player right-clicks a DROPPED Genesis Codex
     * (an ItemEntity lying on the ground).
     *
     * WHY THIS EXISTS / WHY THE OLD VERSION CRASHED
     * ----------------------------------------------
     * PlayerInteractEvent.EntityInteract fires on BOTH logical sides.
     * The original handler ran PythonBackendClient and ServerLevel methods
     * on the client side → NullPointerException crash.
     *
     * FIX: isClientSide() guard — everything below runs server-side only.
     * event.setCanceled(true) prevents vanilla item pick-up so the book
     * stays on the ground after genesis fires.
     */
    @SubscribeEvent
    public static void onEntityInteract(PlayerInteractEvent.EntityInteract event) {
        // ── Server side only — THE crash fix ─────────────────────────────────
        if (event.getEntity().level().isClientSide()) return;
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        if (!(event.getTarget() instanceof ItemEntity itemEntity)) return;

        if (!isGenesisCodex(itemEntity.getItem())) return;

        // Suppress vanilla pickup — book stays on the ground
        event.setCanceled(true);

        ServerLevel level = (ServerLevel) player.level();

        if (!canUseGenesis(player)) {
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + getGenesisCooldown(player) + " seconds remaining"));
            return;
        }

        // Circle centred on the ItemEntity position; spawns relative to player
        triggerGenesisFromGround(player, level, itemEntity.blockPosition());
    }

    public static InteractionResult onGenesisUse(ServerPlayer player, Level level, InteractionHand hand) {
        ItemStack stack = player.getItemInHand(hand);
        if (!stack.is(Items.WRITTEN_BOOK)) return InteractionResult.PASS;
        if (!stack.hasCustomHoverName() ||
                !stack.getHoverName().getString().contains("Genesis Codex"))
            return InteractionResult.PASS;
        if (level.isClientSide()) return InteractionResult.SUCCESS;

        ServerLevel serverLevel = (ServerLevel) level;
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());
        if (lastUse != null && (now - lastUse) < GENESIS_COOLDOWN_MS) {
            long remainingSeconds = (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000;
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + remainingSeconds + " seconds remaining"));
            return InteractionResult.FAIL;
        }
        GENESIS_COOLDOWNS.put(player.getUUID(), now);
        BlockPos playerPos = player.blockPosition();
        BlockPos spawn1 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(2, 0, 0));
        BlockPos spawn2 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0));
        player.sendSystemMessage(Component.literal("§d[Genesis] §cCreating first beings..."));
        PythonBackendClient.spawnGenesisAgents(
                player.getName().getString(),
                serverLevel.dimension().location().toString(),
                spawn1, spawn2);
        DWMod.LOGGER.info("Genesis invoked by {} at {}", player.getName().getString(), playerPos);
        startGenesisCircle(serverLevel, playerPos);
        return InteractionResult.SUCCESS;
    }

    public static void triggerDivineReset(ServerLevel world, Entity initiatorEntity) {
        if (divineResetActive) { DWMod.LOGGER.warn("Divine Reset already in progress!"); return; }
        if (initiatorEntity instanceof ServerPlayer player) {
            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[Divine Reset] Only gods may invoke the Divine Reset!"));
                return;
            }
        }
        divineResetActive = true;
        resetTicks = 0;
        targetWorld = world;
        initiator = initiatorEntity;
        DWMod.LOGGER.info("⚡ DIVINE RESET INITIATED ⚡");
        broadcastToWorld(world, "§4§l⚡⚡⚡ DIVINE RESET ⚡⚡⚡");
        broadcastToWorld(world, "§cAll AI agents will be purged in 10 seconds...");
        broadcastToWorld(world, "§eTheir memories will be erased from existence.");
        if (initiatorEntity != null)
            world.playSound(null, initiatorEntity.blockPosition(),
                    SoundEvents.WITHER_SPAWN, SoundSource.AMBIENT, 1.0f, 0.8f);
    }

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        tickGenesisCircle();
        if (!divineResetActive) return;
        resetTicks++;
        if (resetTicks == 40) broadcastToWorld(targetWorld, "§c⚡ 8 seconds...");
        else if (resetTicks == 100) broadcastToWorld(targetWorld, "§c⚡ 5 seconds...");
        else if (resetTicks == 160) broadcastToWorld(targetWorld, "§c⚡ 2 seconds...");
        if (resetTicks % CIRCLE_INTERVAL == 0 && targetWorld != null && initiator != null)
            DivineMagicCircle.spawnDivineResetCircle(targetWorld, initiator.blockPosition(), resetTicks);
        if (resetTicks >= RESET_DURATION) {
            divineResetActive = false;
            resetTicks = 0;
            executeDivineReset();
        }
    }

    private static void executeDivineReset() {
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
        for (Entity entity : targetWorld.getAllEntities())
            if (entity instanceof ItemEntity) entity.remove(Entity.RemovalReason.DISCARDED);
        broadcastToWorld(targetWorld, "§a§l✨ DIVINE RESET COMPLETE ✨");
        broadcastToWorld(targetWorld, "§e" + aiAgents.size() + " AI agents have been purged");
        broadcastToWorld(targetWorld, "§7Their memories are being erased...");
        PythonBackendClient.notifyDivineReset(
                targetWorld.dimension().location().toString(), agentIds);
        targetWorld = null;
        initiator = null;
    }

    private static void triggerGenesisFromGround(ServerPlayer player,
                                                  ServerLevel serverLevel,
                                                  BlockPos circleCenter) {
        long now = System.currentTimeMillis();
        Long lastUse = GENESIS_COOLDOWNS.get(player.getUUID());
        if (lastUse != null && (now - lastUse) < GENESIS_COOLDOWN_MS) {
            long remainingSeconds = (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000;
            player.sendSystemMessage(Component.literal(
                    "§c[Genesis] Cooldown: " + remainingSeconds + " seconds remaining"));
            return;
        }
        GENESIS_COOLDOWNS.put(player.getUUID(), now);
        BlockPos playerPos = player.blockPosition();
        BlockPos spawn1 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(2, 0, 0));
        BlockPos spawn2 = getSafeSpawnPosition(serverLevel,
                playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0));
        player.sendSystemMessage(Component.literal("§d[Genesis] §cCreating first beings..."));
        PythonBackendClient.spawnGenesisAgents(
                player.getName().getString(),
                serverLevel.dimension().location().toString(),
                spawn1, spawn2);
        DWMod.LOGGER.info("Genesis (ground) invoked by {} at {} (circle at {})",
                player.getName().getString(), playerPos, circleCenter);
        startGenesisCircle(serverLevel, circleCenter);
    }

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
        if (genesisCircleTick % CIRCLE_INTERVAL == 0 && genesisCircleLevel != null)
            DivineMagicCircle.spawnGenesisCircle(genesisCircleLevel, genesisCircleCenter, genesisCircleTick);
        genesisCircleTick++;
    }

    private static boolean isGenesisCodex(ItemStack stack) {
        if (!stack.is(Items.WRITTEN_BOOK)) return false;
        if (stack.getTag() != null && stack.getTag().contains("title"))
            return stack.getTag().getString("title").contains("Genesis Codex");
        return stack.hasCustomHoverName() &&
                stack.getHoverName().getString().contains("Genesis Codex");
    }

    private static BlockPos getSafeSpawnPosition(ServerLevel level, BlockPos pos) {
        for (int i = 0; i < 10; i++) {
            if (level.getBlockState(pos).isAir() &&
                    level.getBlockState(pos.above()).isAir() &&
                    level.getBlockState(pos.below()).isSolid())
                return pos;
            pos = pos.above();
        }
        return pos;
    }

    private static void broadcastToWorld(ServerLevel world, String message) {
        for (ServerPlayer player : world.players())
            player.sendSystemMessage(Component.literal(message));
    }

    public static boolean isDivineResetActive() { return divineResetActive; }
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
        return Math.max(0, (GENESIS_COOLDOWN_MS - (now - lastUse)) / 1000);
    }
}