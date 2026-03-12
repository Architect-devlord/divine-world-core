package com.divineworld.client.entity;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.*;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;

/**
 * God Entity Manager
 *
 * FIX Bug 4 — entities created but never added to the level:
 *   All spawn methods were returning `new AIWither(level)` etc. but never
 *   calling level.addFreshEntity().  The objects existed in RAM but the
 *   game engine never ticked them — tick(), ability cooldowns, physics,
 *   and rendering were all dead.
 *
 *   Fix: createAndSpawn() positions the entity at the local player and
 *   calls level.addFreshEntity() so the engine owns and ticks it.
 */
public class GodEntityManager {

    private static Entity currentGodEntity;
    private static String  currentGodType;
    private static boolean isPlayerForm = false;

    public static void initializeGodEntity(String godType) {
        currentGodType = godType;
        DWClientMod.LOGGER.info("Initializing god entity: {}", godType);

        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null || mc.player == null) {
            DWClientMod.LOGGER.error("Cannot spawn god entity — level or player is null");
            return;
        }

        // Discard any previously spawned body
        if (currentGodEntity != null && !currentGodEntity.isRemoved()) {
            currentGodEntity.remove(Entity.RemovalReason.DISCARDED);
            currentGodEntity = null;
        }

        Level level = mc.level;

        // FIX Bug 4: createAndSpawn() calls addFreshEntity() — old code did not
        currentGodEntity = switch (godType.toLowerCase()) {
            case "ender_dragon", "dragon" -> createAndSpawn(new AIEnderDragon(level), level);
            case "wither"                 -> createAndSpawn(new AIWither(level),       level);
            case "warden"                 -> createAndSpawn(new AIWarden(level),       level);
            case "oracle"                 -> createAndSpawn(new AIOracle(level),       level);
            case "elder_guardian"         -> createAndSpawn(new AIElderGuardian(level),level);
            case "creaking"               -> createAndSpawn(new AICreaking(level),     level);
            default -> { DWClientMod.LOGGER.warn("Unknown god type: {}", godType); yield null; }
        };

        if (currentGodEntity != null) {
            DWClientMod.LOGGER.info("God entity added to level and will tick: {}", godType);
        }
    }

    /**
     * Position entity at player's feet and register it with the level engine.
     * Without addFreshEntity() the entity is never ticked.
     */
    private static Entity createAndSpawn(Entity entity, Level level) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player != null) {
            entity.moveTo(mc.player.getX(), mc.player.getY(), mc.player.getZ(),
                          mc.player.getYRot(), mc.player.getXRot());
        }
        level.addFreshEntity(entity);  // FIX Bug 4: this line was entirely missing
        return entity;
    }

    public static void transformToPlayerForm() {
        if (!isPlayerForm && currentGodEntity != null) {
            isPlayerForm = true;
            DWClientMod.LOGGER.info("Transformed to player form");
        }
    }

    public static void transformToGodForm() {
        if (isPlayerForm) {
            isPlayerForm = false;
            DWClientMod.LOGGER.info("Transformed to god form");
        }
    }

    /**
     * Dispatch a god ability to the current AI entity.
     * Called on the main thread by both TCPServer and WebSocketManager.
     */
    public static void executeGodAbility(String abilityName, Object... params) {
        if (currentGodEntity == null) return;
        if (currentGodEntity instanceof IGodEntity god) {
            god.useAbility(abilityName, params);
        }
    }

    public static Entity  getCurrentGodEntity() { return currentGodEntity; }
    public static String  getCurrentGodType()   { return currentGodType;   }
    public static boolean isPlayerForm()        { return isPlayerForm;     }
}