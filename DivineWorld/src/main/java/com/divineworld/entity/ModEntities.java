// src/main/java/com/divineworld/entity/ModEntities.java
// DivineWorld server mod
package com.divineworld.entity;

import com.divineworld.DWMod;
import com.divineworld.entity.gods.AIElderGuardian;
import com.divineworld.entity.gods.AIEnderDragon;
import com.divineworld.entity.gods.AIOracle;
import com.divineworld.entity.gods.AIWarden;
import com.divineworld.entity.gods.AIWither;
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
 *
 * divineworld:ai_warden / ai_wither / ai_oracle / ai_elder_guardian / ai_ender_dragon
 *   The remaining five god body entities, moved here from DWClientBot's
 *   com.divineworld.client.entity.gods package. These extend BaseGodEntity
 *   (Player-based, full GeckoLib animation controller), same as AICreaking
 *   did before DivineWorld got its own simpler Monster-based AICreakingEntity.
 *   GodSpawnHandler previously spawned plain vanilla EntityType.WARDEN/
 *   WITHER/ENDER_DRAGON/ELDER_GUARDIAN/EVOKER for these — this registration
 *   plus the matching GodSpawnHandler.getGodEntityType() change makes the
 *   rich custom entities the ones that actually spawn as the visible body.
 *   Dimensions match each type's real vanilla counterpart; the imposing
 *   "god scale" is a render-only multiplier applied by GodBodyGeoRenderer,
 *   same pattern AIWarden's own getDimensions() override already used
 *   (hitbox stays gameplay-reasonable even though the model renders larger).
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

    /** The Warden god's custom entity. Size matches vanilla Warden (0.9w × 2.9h). */
    public static final RegistryObject<EntityType<AIWarden>> AI_WARDEN =
            ENTITIES.register("ai_warden",
                    () -> EntityType.Builder.<AIWarden>of(AIWarden::new, MobCategory.MONSTER)
                            .sized(0.9f, 2.9f)
                            .clientTrackingRange(12)
                            .updateInterval(3)
                            .build(DWMod.MOD_ID + ":ai_warden")
            );

    /** The Wither god's custom entity. Size matches vanilla Wither (0.9w × 3.5h). */
    public static final RegistryObject<EntityType<AIWither>> AI_WITHER =
            ENTITIES.register("ai_wither",
                    () -> EntityType.Builder.<AIWither>of(AIWither::new, MobCategory.MONSTER)
                            .sized(0.9f, 3.5f)
                            .fireImmune()
                            .clientTrackingRange(12)
                            .updateInterval(3)
                            .build(DWMod.MOD_ID + ":ai_wither")
            );

    /** The Oracle god's custom entity. Size matches vanilla Evoker (0.6w × 1.95h). */
    public static final RegistryObject<EntityType<AIOracle>> AI_ORACLE =
            ENTITIES.register("ai_oracle",
                    () -> EntityType.Builder.<AIOracle>of(AIOracle::new, MobCategory.MONSTER)
                            .sized(0.6f, 1.95f)
                            .clientTrackingRange(12)
                            .updateInterval(3)
                            .build(DWMod.MOD_ID + ":ai_oracle")
            );

    /** The Elder Guardian god's custom entity. Size matches vanilla Elder Guardian (~2.0w × 2.0h). */
    public static final RegistryObject<EntityType<AIElderGuardian>> AI_ELDER_GUARDIAN =
            ENTITIES.register("ai_elder_guardian",
                    () -> EntityType.Builder.<AIElderGuardian>of(AIElderGuardian::new, MobCategory.MONSTER)
                            .sized(1.9975f, 1.9975f)
                            .clientTrackingRange(12)
                            .updateInterval(3)
                            .build(DWMod.MOD_ID + ":ai_elder_guardian")
            );

    /** The Ender Dragon god's custom entity. Size matches vanilla Ender Dragon (16w × 8h). */
    public static final RegistryObject<EntityType<AIEnderDragon>> AI_ENDER_DRAGON =
            ENTITIES.register("ai_ender_dragon",
                    () -> EntityType.Builder.<AIEnderDragon>of(AIEnderDragon::new, MobCategory.MONSTER)
                            .sized(16.0f, 8.0f)
                            .fireImmune()
                            .clientTrackingRange(64)     // dragon-sized — needs a much larger tracking range
                            .updateInterval(3)
                            .build(DWMod.MOD_ID + ":ai_ender_dragon")
            );
}