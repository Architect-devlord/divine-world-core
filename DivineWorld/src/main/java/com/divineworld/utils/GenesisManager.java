// DivineWorld/src/main/java/com/divineworld/utils/GenesisManager.java (Updated)
package com.divineworld.utils;

import com.divineworld.DWMod;
import com.divineworld.entity.god.DWGodEntity;
import net.minecraft.entity.Entity;
import net.minecraft.entity.item.ItemEntity;
import net.minecraft.entity.player.ServerPlayerEntity;
import net.minecraft.util.math.BlockPos;
import net.minecraft.util.text.StringTextComponent;
import net.minecraft.world.server.ServerWorld;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.List;

/**
 * Genesis Manager - handles divine world resets triggered by gods.
 * Updated to use TaggedEntitySystem for preserving NPCs and Gods.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GenesisManager {

    private static boolean genesisActive = false;
    private static int genesisTicks = 0;
    private static final int GENESIS_DURATION = 200; // 10 seconds
    private static ServerWorld targetWorld = null;
    private static Entity initiator = null;

    /**
     * Trigger Genesis reset
     */
    public static void triggerGenesis(ServerWorld world, Entity god) {
        if (genesisActive) {
            DWMod.LOGGER.warn("Genesis already in progress!");
            return;
        }

        // Verify god has permission
        if (!TaggedEntitySystem.hasTag(god, TaggedEntitySystem.TAG_DW_GOD)) {
            DWMod.LOGGER.warn("Non-god entity attempted Genesis: " + god.getName().getString());
            return;
        }

        int divinePower = TaggedEntitySystem.getDivinePower(god);
        if (divinePower < 100) {
            DWMod.LOGGER.warn("God lacks sufficient power for Genesis: " + divinePower);
            return;
        }

        genesisActive = true;
        genesisTicks = 0;
        targetWorld = world;
        initiator = god;

        String godType = TaggedEntitySystem.getGodType(god);

        DWMod.LOGGER.info("⚡ GENESIS INITIATED by " + godType + " ⚡");

        // Broadcast to all players
        broadcastToWorld(world, "§4§l⚡⚡⚡ GENESIS ⚡⚡⚡");
        broadcastToWorld(world, "§c" + godType.toUpperCase() + " has triggered a divine reset!");
        broadcastToWorld(world, "§eThe world will be reborn in 10 seconds...");

        // Notify Python backend
        notifyBackendGenesis(god, world);
    }

    /**
     * Tick handler for Genesis progression
     */
    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (!genesisActive || event.phase != TickEvent.Phase.END) return;

        genesisTicks++;

        // Countdown warnings
        if (genesisTicks == 40) { // 2 seconds
            broadcastToWorld(targetWorld, "§c⚡ 8 seconds until Genesis...");
        } else if (genesisTicks == 100) { // 5 seconds
            broadcastToWorld(targetWorld, "§c⚡ 5 seconds...");
        } else if (genesisTicks == 160) { // 8 seconds
            broadcastToWorld(targetWorld, "§c⚡ 2 seconds...");
        }

        // Execute Genesis
        if (genesisTicks >= GENESIS_DURATION) {
            executeGenesis();
            genesisActive = false;
            genesisTicks = 0;
        }
    }

    /**
     * Execute the Genesis reset
     */
    private static void executeGenesis() {
        if (targetWorld == null) return;

        DWMod.LOGGER.info("Executing Genesis on world: " + targetWorld.dimension().location());

        // Get immune entities BEFORE clearing
        List<Entity> immuneEntities = TaggedEntitySystem.getGenesisImmuneEntities(targetWorld);

        DWMod.LOGGER.info("Genesis-immune entities: " + immuneEntities.size());
        for (Entity e : immuneEntities) {
            String aiId = TaggedEntitySystem.getAIID(e);
            DWMod.LOGGER.info("  - " + e.getName().getString() + " (AI: " + aiId + ")");
        }

        // Remove all non-immune entities
        int removedCount = 0;
        for (Entity entity : targetWorld.getAllEntities()) {
            // Skip immune entities
            if (TaggedEntitySystem.hasTag(entity, TaggedEntitySystem.TAG_GENESIS_IMMUNE)) {
                continue;
            }

            // Skip players (handle separately)
            if (entity instanceof ServerPlayerEntity) {
                ServerPlayerEntity player = (ServerPlayerEntity) entity;
                // Reset player to spawn
                BlockPos spawn = targetWorld.getSharedSpawnPos();
                player.teleportTo(targetWorld, spawn.getX(), spawn.getY(), spawn.getZ(), 0, 0);
                player.setHealth(player.getMaxHealth());
                player.getFoodData().setFoodLevel(20);
                continue;
            }

            // Remove entity
            entity.remove();
            removedCount++;
        }

        DWMod.LOGGER.info("Genesis removed " + removedCount + " entities");

        // Clear items (except near immune entities)
        for (Entity entity : targetWorld.getAllEntities()) {
            if (entity instanceof ItemEntity) {
                boolean nearImmune = false;
                for (Entity immune : immuneEntities) {
                    if (entity.distanceTo(immune) < 10.0) {
                        nearImmune = true;
                        break;
                    }
                }
                if (!nearImmune) {
                    entity.remove();
                }
            }
        }

        // Regenerate terrain (placeholder - implement world reset logic)
        // This would involve resetting chunks or restoring from backup

        broadcastToWorld(targetWorld, "§a§l✨ GENESIS COMPLETE ✨");
        broadcastToWorld(targetWorld, "§eThe world has been reborn!");
        broadcastToWorld(targetWorld, "§7" + immuneEntities.size() + " divine entities survived the reset");

        // Notify Python backend
        notifyBackendGenesisComplete(targetWorld, immuneEntities);

        targetWorld = null;
        initiator = null;
    }

    /**
     * Broadcast message to all players in world
     */
    private static void broadcastToWorld(ServerWorld world, String message) {
        for (ServerPlayerEntity player : world.players()) {
            player.sendMessage(
                    new StringTextComponent(message),
                    player.getUUID()
            );
        }
    }

    /**
     * Notify Python backend of Genesis start
     */
    private static void notifyBackendGenesis(Entity god, ServerWorld world) {
        // Send async HTTP request to Python backend
        String godType = TaggedEntitySystem.getGodType(god);
        String aiId = TaggedEntitySystem.getAIID(god);

        // TODO: Implement HTTP request
        DWMod.LOGGER.info("Would notify backend: Genesis by " + godType + " (AI: " + aiId + ")");
    }

    /**
     * Notify Python backend of Genesis completion
     */
    private static void notifyBackendGenesisComplete(ServerWorld world, List<Entity> survivors) {
        // TODO: Implement HTTP request with survivor list
        DWMod.LOGGER.info("Would notify backend: Genesis complete, " + survivors.size() + " survivors");
    }

    /**
     * Check if Genesis is active
     */
    public static boolean isGenesisActive() {
        return genesisActive;
    }

    /**
     * Get Genesis progress (0.0 to 1.0)
     */
    public static float getGenesisProgress() {
        if (!genesisActive) return 0.0f;
        return (float) genesisTicks / (float) GENESIS_DURATION;
    }
}