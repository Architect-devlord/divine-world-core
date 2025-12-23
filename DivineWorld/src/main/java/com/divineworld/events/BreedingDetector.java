// src/main/java/com/divineworld/events/BreedingDetector.java
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
 * Detects when AI agents breed
 * FIXED: Works with ServerPlayer agents
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingDetector {

    @SubscribeEvent
    public static void onBabySpawn(BabyEntitySpawnEvent event) {
        // Check if parents are AI-controlled ServerPlayers
        String parentAId = getAgentId(event.getParentA());
        String parentBId = getAgentId(event.getParentB());

        if (parentAId != null && parentBId != null) {
            // Both are AI agents - notify Python
            PythonBackendClient.notifyBreeding(
                    parentAId, parentBId,
                    getAgentType(event.getParentA()),
                    getAgentType(event.getParentB())
            );

            // Prevent vanilla baby spawn - Python will spawn packaged agent
            event.setCanceled(true);

            DWMod.LOGGER.info("AI breeding detected: {} x {}", parentAId, parentBId);
        }
    }

    private static String getAgentId(Entity entity) {
        if (entity instanceof ServerPlayer player) {
            if (DWNPCManager.isAIPlayer(player)) {
                return DWNPCManager.getAgentId(player);
            }
        }
        return null;
    }

    private static String getAgentType(Entity entity) {
        if (entity instanceof ServerPlayer player) {
            if (DWNPCManager.isGodPlayer(player)) {
                return "god";
            }
            return "npc";
        }
        return "unknown";
    }
}