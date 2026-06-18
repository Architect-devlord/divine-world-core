// src/main/java/com/divineworld/entity/EntityAttributeRegistrar.java
// DivineWorld server mod
package com.divineworld.entity;

import com.divineworld.DWMod;
import net.minecraftforge.event.entity.EntityAttributeCreationEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Registers entity attributes for all DivineWorld custom entities.
 * Must be on the MOD bus (EntityAttributeCreationEvent fires on mod bus).
 * Without this, the game crashes with "has no attributes" on entity spawn.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD)
public class EntityAttributeRegistrar {

    @SubscribeEvent
    public static void onEntityAttributeCreation(EntityAttributeCreationEvent event) {
        event.put(ModEntities.AI_CREAKING.get(),
                AICreakingEntity.createAttributes().build());

        DWMod.LOGGER.info("[EntityAttributes] ✅ Creaking god attributes registered");
    }
}