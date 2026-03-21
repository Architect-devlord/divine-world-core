package com.divineworld.client.entity;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.*;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.Level;

/**
 * God Entity Manager — client-side tracker.
 *
 * FIX B-01: This class NO LONGER spawns entities into the level.
 * The server mod (GodSpawnHandler) spawns the real boss body on ServerLevel.
 * Calling level.addFreshEntity() on a ClientLevel is illegal in Forge 1.20.1
 * (the entity exists only on this client, is invisible to the server, and all
 * damage/ability methods that check !level.isClientSide() silently no-op).
 *
 * This class is now a pure client-side tracker:
 *   - currentGodType  — which god type the local player is
 *   - executeGodAbility() — dispatches ability visuals to whichever
 *     entity is already in the world (spawned by the server mod)
 *
 * Transformation calls still delegate to the legacy helpers for visual sync,
 * but createAndSpawn() is removed.
 */
public class GodEntityManager {

    private static Entity currentGodEntity;
    private static String  currentGodType;
    private static boolean isPlayerForm = false;

    /**
     * Called when the local player loads in as a god agent.
     * Records the god type — the server mod handles the actual body spawn.
     */
    public static void initializeGodEntity(String godType) {
        currentGodType = godType;
        DWClientMod.LOGGER.info("[GodEntityManager] God type set to '{}' — body spawned by server mod", godType);
        // FIX B-01: do NOT create entities or call level.addFreshEntity() here.
        // The server mod (GodSpawnHandler.spawnGodBody) adds the boss entity to
        // ServerLevel.  All clients see it through normal entity sync.
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

    /**
     * Returns true if the given entity is the current client-side god body.
     * WebSocketManager uses this to tag the entity with ENTITY_GOD type_id
     * so the agent's perception system identifies its own body in the field.
     */
    public static boolean isGodEntity(Entity entity) {
        return currentGodEntity != null && entity == currentGodEntity;
    }
}
