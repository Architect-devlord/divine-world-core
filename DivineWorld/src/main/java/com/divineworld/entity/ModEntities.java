// src/main/java/com/divineworld/entity/ModEntities.java
package com.divineworld.entity;

import com.divineworld.DWMod;
import net.minecraft.world.entity.EntityType;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;

/**
 * Entity Registration - MINIMAL
 *
 * Only registers Creaking since it doesn't exist in 1.20.1
 * All agents (normal + gods) are ServerPlayer entities
 */
public class ModEntities {
    public static final DeferredRegister<EntityType<?>> ENTITIES =
            DeferredRegister.create(ForgeRegistries.ENTITY_TYPES, DWMod.MOD_ID);

    // Creaking entity will be added when client-side Creaking is ready
    // For now, gods use vanilla mobs (dragon, wither, warden, etc.)

    // Future: Register custom Creaking entity type here
}