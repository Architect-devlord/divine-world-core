// src/main/java/com/divineworld/client/EntityAttributeRegistration.java
package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.entity.gods.*;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.event.entity.EntityAttributeCreationEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Entity Attribute Registration
 * Registers attributes for all god entities
 * CRITICAL: Without this, entities will crash with "has no attributes" error
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public class EntityAttributeRegistration {

    @SubscribeEvent
    public static void onEntityAttributeCreation(EntityAttributeCreationEvent event) {
        DWClientMod.LOGGER.info("[AttributeRegistration] Registering god entity attributes...");

        // Register attributes for all god entities
        event.put(ModEntities.AI_ORACLE.get(), AIOracle.createAttributes().build());
        event.put(ModEntities.AI_ELDER_GUARDIAN.get(), AIElderGuardian.createAttributes().build());
        event.put(ModEntities.AI_ENDER_DRAGON.get(), AIEnderDragon.createAttributes().build());
        event.put(ModEntities.AI_WITHER.get(), AIWither.createAttributes().build());
        event.put(ModEntities.AI_WARDEN.get(), AIWarden.createAttributes().build());
        event.put(ModEntities.AI_CREAKING.get(), AICreaking.createAttributes().build());

        DWClientMod.LOGGER.info("[AttributeRegistration] ✅ All god entity attributes registered");
    }
}