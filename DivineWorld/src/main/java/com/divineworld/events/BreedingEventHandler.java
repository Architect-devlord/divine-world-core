// src/main/java/com/divineworld/events/BreedingEventHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraftforge.event.entity.living.BabyEntitySpawnEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * UNIFIED Breeding Handler - Detects when AI agents breed
 * FIXED: Only ONE handler, no duplicates
 * SERVER-SIDE ONLY - No client references
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingEventHandler {

    @SubscribeEvent
    public static void onBabySpawn(BabyEntitySpawnEvent event) {
        // Get parents
        Entity parentA = event.getParentA();
        Entity parentB = event.getParentB();

        // Validate both are ServerPlayer (AI agents join as ServerPlayer)
        if (!(parentA instanceof ServerPlayer) || !(parentB instanceof ServerPlayer)) {
            return; // Not AI agents
        }

        ServerPlayer playerA = (ServerPlayer) parentA;
        ServerPlayer playerB = (ServerPlayer) parentB;

        // Check if both are AI-controlled
        if (!DWNPCManager.isAIPlayer(playerA) || !DWNPCManager.isAIPlayer(playerB)) {
            return; // At least one is not an AI agent
        }

        // Get agent IDs
        String parentAId = DWNPCManager.getAgentId(playerA);
        String parentBId = DWNPCManager.getAgentId(playerB);

        if (parentAId == null || parentBId == null) {
            DWMod.LOGGER.warn("Breeding detected but missing agent IDs: {} x {}",
                    playerA.getName().getString(), playerB.getName().getString());
            return;
        }

        // Determine agent types
        String typeA = DWNPCManager.isGodPlayer(playerA) ? "god" : "npc";
        String typeB = DWNPCManager.isGodPlayer(playerB) ? "god" : "npc";

        // Notify Python backend
        PythonBackendClient.notifyBreeding(
                parentAId, parentBId,
                typeA, typeB
        );

        DWMod.LOGGER.info("✅ AI breeding detected: {} ({}) x {} ({})",
                parentAId, typeA, parentBId, typeB);

        // Cancel vanilla baby spawn - Python will spawn packaged agent
        event.setCanceled(true);
    }
}