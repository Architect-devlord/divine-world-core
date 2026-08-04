// src/main/java/com/divineworld/entity/EntityAttributeRegistrar.java
// DivineWorld server mod
package com.divineworld.entity;

import com.divineworld.DWMod;
import com.divineworld.entity.gods.AIElderGuardian;
import com.divineworld.entity.gods.AIEnderDragon;
import com.divineworld.entity.gods.AIOracle;
import com.divineworld.entity.gods.AIWarden;
import com.divineworld.entity.gods.AIWither;
import net.minecraftforge.event.entity.EntityAttributeCreationEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Registers entity attributes for all DivineWorld custom entities.
 * Must be on the MOD bus (EntityAttributeCreationEvent fires on mod bus).
 * Without this, the game crashes with "has no attributes" on entity spawn.
 *
 * Deliberately has NO Dist restriction on the class (unlike the equivalent
 * class in DWClientBot, which is Dist.CLIENT-only) — EntityAttributeCreationEvent
 * is a both-sides event, and these entities are spawned server-side by
 * GodSpawnHandler, so attributes must exist there regardless of whether any
 * client is even connected.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD)
public class EntityAttributeRegistrar {

    @SubscribeEvent
    public static void onEntityAttributeCreation(EntityAttributeCreationEvent event) {
        event.put(ModEntities.AI_CREAKING.get(),
                AICreakingEntity.createAttributes().build());

        event.put(ModEntities.AI_WARDEN.get(),
                AIWarden.createAttributes().build());
        event.put(ModEntities.AI_WITHER.get(),
                AIWither.createAttributes().build());
        event.put(ModEntities.AI_ORACLE.get(),
                AIOracle.createAttributes().build());
        event.put(ModEntities.AI_ELDER_GUARDIAN.get(),
                AIElderGuardian.createAttributes().build());
        event.put(ModEntities.AI_ENDER_DRAGON.get(),
                AIEnderDragon.createAttributes().build());

        DWMod.LOGGER.info("[EntityAttributes] ✅ All 6 god body attributes registered");
    }
}