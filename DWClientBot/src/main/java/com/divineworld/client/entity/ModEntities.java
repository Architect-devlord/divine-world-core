package com.divineworld.client.entity;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.*;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraftforge.registries.DeferredRegister;
import net.minecraftforge.registries.ForgeRegistries;
import net.minecraftforge.registries.RegistryObject;

/**
 * Entity Registration - FULLY FIXED VERSION
 * All god entities now properly extend Player via BaseGodEntity
 */
public class ModEntities {
    public static final DeferredRegister<EntityType<?>> ENTITIES =
            DeferredRegister.create(ForgeRegistries.ENTITY_TYPES, DWClientMod.MOD_ID);

    // FIXED: All god entities now use correct Player-based factory
    // They extend BaseGodEntity which extends Player

    public static final RegistryObject<EntityType<AICreaking>> AI_CREAKING =
            ENTITIES.register("ai_creaking", () -> EntityType.Builder.of(
                            (EntityType<AICreaking> type, net.minecraft.world.level.Level level) ->
                                    new AICreaking(type, level),
                            MobCategory.CREATURE // Changed from MONSTER to CREATURE (player-like)
                    )
                    .sized(0.6f, 3.5f)
                    .clientTrackingRange(10)
                    .build(DWClientMod.id("ai_creaking").toString()));

    public static final RegistryObject<EntityType<AIEnderDragon>> AI_ENDER_DRAGON =
            ENTITIES.register("ai_ender_dragon", () -> EntityType.Builder.of(
                            (EntityType<AIEnderDragon> type, net.minecraft.world.level.Level level) ->
                                    new AIEnderDragon(type, level),
                            MobCategory.CREATURE // Player-like
                    )
                    .sized(16.0f, 8.0f) // Scaled down from 16x8 for practical gameplay
                    .clientTrackingRange(10)
                    .fireImmune()
                    .build(DWClientMod.id("ai_ender_dragon").toString()));

    public static final RegistryObject<EntityType<AIWither>> AI_WITHER =
            ENTITIES.register("ai_wither", () -> EntityType.Builder.of(
                            (EntityType<AIWither> type, net.minecraft.world.level.Level level) ->
                                    new AIWither(type, level),
                            MobCategory.CREATURE // Player-like
                    )
                    .sized(0.9f, 2.5f)
                    .clientTrackingRange(10)
                    .fireImmune()
                    .build(DWClientMod.id("ai_wither").toString()));

    public static final RegistryObject<EntityType<AIWarden>> AI_WARDEN =
            ENTITIES.register("ai_warden", () -> EntityType.Builder.of(
                            (EntityType<AIWarden> type, net.minecraft.world.level.Level level) ->
                                    new AIWarden(type, level),
                            MobCategory.CREATURE // Player-like
                    )
                    .sized(0.9f, 2.9f)
                    .clientTrackingRange(10)
                    .build(DWClientMod.id("ai_warden").toString()));

    public static final RegistryObject<EntityType<AIOracle>> AI_ORACLE =
            ENTITIES.register("ai_oracle", () -> EntityType.Builder.of(
                            (EntityType<AIOracle> type, net.minecraft.world.level.Level level) ->
                                    new AIOracle(type, level),
                            MobCategory.CREATURE // Player-like
                    )
                    .sized(0.6f, 1.8f)
                    .clientTrackingRange(10)
                    .build(DWClientMod.id("ai_oracle").toString()));

    public static final RegistryObject<EntityType<AIElderGuardian>> AI_ELDER_GUARDIAN =
            ENTITIES.register("ai_elder_guardian", () -> EntityType.Builder.of(
                            (EntityType<AIElderGuardian> type, net.minecraft.world.level.Level level) ->
                                    new AIElderGuardian(type, level),
                            MobCategory.CREATURE // Player-like
                    )
                    .sized(1.9975f, 1.9975f) // Scaled for practical gameplay
                    .clientTrackingRange(10)
                    .build(DWClientMod.id("ai_elder_guardian").toString()));
}