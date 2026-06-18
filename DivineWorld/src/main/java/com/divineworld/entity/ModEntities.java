// src/main/java/com/divineworld/entity/ModEntities.java
// DivineWorld server mod
package com.divineworld.entity;

import com.divineworld.DWMod;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

/**
 * Entity Registration — DivineWorld server mod.
 *
 * divineworld:ai_creaking
 *   The Creaking god body entity. GeckoLib-animated, spawned by GodSpawnHandler
 *   when a god agent of type "creaking" joins the server.
 *   Renderer registered by DivineClientSetup (client-dist only).
 *   Attributes registered by EntityAttributeRegistrar.
 */
public class ModEntities {

    public static final DeferredRegister<EntityType<?>> ENTITIES =
            DeferredRegister.create(ForgeRegistries.ENTITY_TYPES, DWMod.MOD_ID);

    /**
     * The Creaking god's custom entity.
     * Size: 0.9w × 3.5h blocks (tall, slender — matches the BBmodel proportions).
     * clientTrackingRange: 12 so clients see it from further than the default 5-chunk range.
     */
    public static final RegistryObject<EntityType<AICreakingEntity>> AI_CREAKING =
            ENTITIES.register("ai_creaking",
                    () -> EntityType.Builder.<AICreakingEntity>of(
                                    AICreakingEntity::new,
                                    MobCategory.MONSTER)
                            .sized(0.9f, 3.5f)
                            .clientTrackingRange(12)
                            .updateInterval(3)           // sync every 3 ticks for smooth puppet sync
                            .build(DWMod.MOD_ID + ":ai_creaking")
            );
}