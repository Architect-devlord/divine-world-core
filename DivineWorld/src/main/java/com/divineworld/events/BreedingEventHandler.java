// src/main/java/com/divineworld/events/BreedingEventHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.utils.TaggedEntitySystem;
import com.divineworld.integration.PythonBackendClient;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraftforge.event.entity.living.BabyEntitySpawnEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Detects when AI agents breed (proximity-based)
 * Notifies Python backend to create child agent
 *
 * FIXED: Works with ServerPlayer entities (no custom NPCs)
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingEventHandler {

    @SubscribeEvent
    public static void onBabySpawn(BabyEntitySpawnEvent event) {
        // Check if parents are AI-controlled ServerPlayers
        Entity parentA = event.getParentA();
        Entity parentB = event.getParentB();

        if (!(parentA instanceof ServerPlayer) || !(parentB instanceof ServerPlayer)) {
            return; // Not AI agents
        }

        ServerPlayer playerA = (ServerPlayer) parentA;
        ServerPlayer playerB = (ServerPlayer) parentB;

        // Check if both are AI agents
        if (!DWNPCManager.isAIPlayer(playerA) || !DWNPCManager.isAIPlayer(playerB)) {
            return; // Not AI agents
        }

        String parentAId = DWNPCManager.getAgentId(playerA);
        String parentBId = DWNPCManager.getAgentId(playerB);

        if (parentAId == null || parentBId == null) {
            return; // Missing agent IDs
        }

        // Both are AI agents - notify Python
        String typeA = DWNPCManager.isGodPlayer(playerA) ? "god" : "npc";
        String typeB = DWNPCManager.isGodPlayer(playerB) ? "god" : "npc";

        PythonBackendClient.notifyBreeding(
                parentAId, parentBId,
                typeA, typeB
        );

        DWMod.LOGGER.info("Breeding detected: {} x {}", parentAId, parentBId);

        // Cancel vanilla baby spawn - Python will spawn packaged agent
        event.setCanceled(true);
    }
}