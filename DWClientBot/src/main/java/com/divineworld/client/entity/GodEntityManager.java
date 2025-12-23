package com.divineworld.client.entity;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.*;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;

/**
 * God Entity Manager
 * Manages custom god entities with special abilities
 */
public class GodEntityManager {
    private static Entity currentGodEntity;
    private static String currentGodType;
    private static boolean isPlayerForm = false;

    /**
     * Initialize god entity based on type
     */
    public static void initializeGodEntity(String godType) {
        currentGodType = godType;

        DWClientMod.LOGGER.info("Initializing god entity: {}", godType);

        // Spawn the appropriate god entity
        switch (godType.toLowerCase()) {
            case "ender_dragon", "dragon" -> currentGodEntity = spawnEnderDragonGod();
            case "wither" -> currentGodEntity = spawnWitherGod();
            case "warden" -> currentGodEntity = spawnWardenGod();
            case "oracle" -> currentGodEntity = spawnOracleGod();
            case "elder_guardian" -> currentGodEntity = spawnElderGuardianGod();
            case "creaking" -> currentGodEntity = spawnCreakingGod();
            default -> {
                DWClientMod.LOGGER.warn("Unknown god type: {}", godType);
                return;
            }
        }

        DWClientMod.LOGGER.info("God entity spawned successfully");
    }

    private static Entity spawnOracleGod() {
        return new AIOracle(Minecraft.getInstance().level);
    }

    private static Entity spawnEnderDragonGod() {
        return new AIEnderDragon(Minecraft.getInstance().level);
    }

    private static Entity spawnWitherGod() {
        return new AIWither(Minecraft.getInstance().level);
    }

    private static Entity spawnWardenGod() {
        return new AIWarden(Minecraft.getInstance().level);
    }

    private static Entity spawnElderGuardianGod() {
        return new AIElderGuardian(Minecraft.getInstance().level);
    }

    private static Entity spawnCreakingGod() {
        return new AICreaking(Minecraft.getInstance().level);
    }

    /**
     * Transform between god form and player form
     */
    public static void transformToPlayerForm() {
        if (!isPlayerForm && currentGodEntity != null) {
            // Store god entity state
            saveGodEntityState();

            // Switch to player entity
            // (Implementation depends on how you handle the player entity)

            isPlayerForm = true;
            DWClientMod.LOGGER.info("Transformed to player form");
        }
    }

    public static void transformToGodForm() {
        if (isPlayerForm) {
            // Restore god entity
            restoreGodEntityState();

            isPlayerForm = false;
            DWClientMod.LOGGER.info("Transformed to god form");
        }
    }

    /**
     * Execute god-specific ability
     */
    public static void executeGodAbility(String abilityName, Object... params) {
        if (currentGodEntity == null) return;

        // Delegate to specific god entity
        if (currentGodEntity instanceof IGodEntity) {
            ((IGodEntity) currentGodEntity).useAbility(abilityName, params);
        }
    }

    private static void saveGodEntityState() {
        // Save position, health, inventory
        if (currentGodEntity instanceof IGodEntity god) {
            // State is automatically saved in entity NBT
            DWClientMod.LOGGER.debug("God entity state saved");
        }
    }

    private static void restoreGodEntityState() {
        // State is automatically restored from NBT
        if (currentGodEntity instanceof IGodEntity god) {
            DWClientMod.LOGGER.debug("God entity state restored");
        }
    }

    public static Entity getCurrentGodEntity() {
        return currentGodEntity;
    }

    public static String getCurrentGodType() {
        return currentGodType;
    }

    public static boolean isPlayerForm() {
        return isPlayerForm;
    }
}
