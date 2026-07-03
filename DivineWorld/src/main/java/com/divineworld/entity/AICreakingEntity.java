// src/main/java/com/divineworld/entity/AICreakingEntity.java
// DivineWorld server mod — GeckoLib 4.4.x, Forge 1.20.1, Parchment 47.4.10
package com.divineworld.entity;

import com.divineworld.DWMod;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.network.syncher.EntityDataAccessor;
import net.minecraft.network.syncher.EntityDataSerializers;
import net.minecraft.network.syncher.SynchedEntityData;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.MobCategory;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.level.Level;
import software.bernie.geckolib.animatable.GeoEntity;
import software.bernie.geckolib.core.animatable.instance.AnimatableInstanceCache;
import software.bernie.geckolib.core.animation.*;
import software.bernie.geckolib.core.object.PlayState;
import software.bernie.geckolib.util.GeckoLibUtil;

/**
 * AICreakingEntity — The Creaking god's server-side body entity.
 *
 * Registered in ModEntities as "divineworld:ai_creaking".
 * Spawned by GodSpawnHandler when a Creaking-type god agent joins.
 * The invisible ServerPlayer puppet is synced to this entity by GodControlHandler.
 *
 * GeckoLib 4.4 is a required dependency on BOTH server and client.
 * Animation triggers (triggerAnim) use SynchedEntityData internally —
 * no custom packets needed; Minecraft handles the sync automatically.
 *
 * ANIMATION → ABILITY MAPPING
 * ----------------------------
 * Looping (base_controller):
 *   walk               — slow ground movement
 *   run                — fast ground movement (speed > 0.25 m/tick)
 *   tentacle_run      — movement with tentacles deployed
 *   tentacles_wall_climb — ceiling/wall movement mode
 *   tentacles_out      — idle hold while tentacles are deployed
 *
 * One-shot (ability_controller, triggered via triggerAnim):
 *   attack             — ServerGodAbilityExecutor: "tentacle_whip" (no tentacles)
 *   tentacle_attack   — ServerGodAbilityExecutor: "tentacle_whip" (tentacles out)
 *   grab_eat           — ServerGodAbilityExecutor: "life_steal"
 *   tentacles_out      — ServerGodAbilityExecutor: "deploy_tentacles"
 *   tentacles_retract  — ServerGodAbilityExecutor: when tentacles retract
 *   tentacle_jump     — ServerGodAbilityExecutor: "toggle_ceiling" entry leap
 *   burrow             — ServerGodAbilityExecutor: "burrow"
 *   dig_out            — ServerGodAbilityExecutor: "emerge"
 *
 * BUILD REQUIREMENT  (build.gradle for DivineWorld mod):
 *   repositories { maven { url "https://dl.cloudsmith.io/public/geckolib3/geckolib/maven/" } }
 *   dependencies { implementation fg.deobf("software.bernie.geckolib:geckolib-forge-1.20.1:4.4.7") }
 */
public class AICreakingEntity extends Monster implements GeoEntity {

    // =========================================================================
    // Synced state (server → all clients automatically)
    // =========================================================================

    public static final EntityDataAccessor<Boolean> IS_UNDERGROUND =
            SynchedEntityData.defineId(AICreakingEntity.class, EntityDataSerializers.BOOLEAN);
    public static final EntityDataAccessor<Boolean> IS_ON_CEILING =
            SynchedEntityData.defineId(AICreakingEntity.class, EntityDataSerializers.BOOLEAN);
    public static final EntityDataAccessor<Boolean> TENTACLES_DEPLOYED =
            SynchedEntityData.defineId(AICreakingEntity.class, EntityDataSerializers.BOOLEAN);

    // =========================================================================
    // Animation constants (match names in the .bbmodel / animation.json)
    // =========================================================================

    private static final RawAnimation WALK_ANIM =
            RawAnimation.begin().thenLoop("walk");
    private static final RawAnimation RUN_ANIM =
            RawAnimation.begin().thenLoop("run");
    private static final RawAnimation tentacle_run_ANIM =
            RawAnimation.begin().thenLoop("tentacle_run");
    private static final RawAnimation TENTACLES_HOLD_ANIM =
            RawAnimation.begin().thenLoop("tentacles_out");
    private static final RawAnimation TENTACLES_WALL_CLIMB_ANIM =
            RawAnimation.begin().thenLoop("tentacles_wall_climb");

    // One-shot ability animations
    private static final RawAnimation ATTACK_ANIM =
            RawAnimation.begin().then("attack",            Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation tentacle_attack_ANIM =
            RawAnimation.begin().then("tentacle_attack",  Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation GRAB_EAT_ANIM =
            RawAnimation.begin().then("grab_eat",          Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_OUT_TRIGGER_ANIM =
            RawAnimation.begin().then("tentacles_out",     Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_RETRACT_ANIM =
            RawAnimation.begin().then("tentacles_retract", Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation tentacle_jump_ANIM =
            RawAnimation.begin().then("tentacle_jump",    Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation BURROW_ANIM =
            RawAnimation.begin().then("burrow",            Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation DIG_OUT_ANIM =
            RawAnimation.begin().then("dig_out",           Animation.LoopType.PLAY_ONCE);

    // =========================================================================
    // GeckoLib AnimatableInstanceCache
    // =========================================================================

    private final AnimatableInstanceCache geoCache = GeckoLibUtil.createInstanceCache(this);

    // =========================================================================
    // Constructor & attributes
    // =========================================================================

    public AICreakingEntity(EntityType<? extends AICreakingEntity> type, Level level) {
        super(type, level);
        // AI goals are intentionally empty — GodControlHandler drives movement
        // by syncing the puppet player position to this entity every tick.
        this.goalSelector.removeAllGoals(g -> true);
        this.targetSelector.removeAllGoals(g -> true);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Monster.createMonsterAttributes()
                .add(Attributes.MAX_HEALTH,             200.0)
                .add(Attributes.MOVEMENT_SPEED,          0.35)
                .add(Attributes.ATTACK_DAMAGE,           12.0)
                .add(Attributes.KNOCKBACK_RESISTANCE,     1.0)
                .add(Attributes.FOLLOW_RANGE,            64.0);
    }

    // =========================================================================
    // Synced data
    // =========================================================================

    @Override
    protected void defineSynchedData() {
        super.defineSynchedData();
        entityData.define(IS_UNDERGROUND,    false);
        entityData.define(IS_ON_CEILING,     false);
        entityData.define(TENTACLES_DEPLOYED, false);
    }

    // =========================================================================
    // GeckoLib — animation controller registration
    // =========================================================================

    /**
     * Two controllers allow blending:
     *   base_controller    — looping state animations (walk / run / wall-climb)
     *   ability_controller — one-shot triggered animations (burrow / attack / …)
     *
     * Transition ticks: 5 for base (smooth blend), 0 for ability (instant snap).
     */
    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {

        // Looping state controller
        controllers.add(new AnimationController<>(this, "base_controller", 5,
                this::baseAnimController));

        // One-shot ability controller — always returns CONTINUE so triggerable
        // animations fire over the base loop without stopping it.
        controllers.add(new AnimationController<>(
                this, "ability_controller", 0, state -> PlayState.CONTINUE)
                .triggerableAnim("attack",             ATTACK_ANIM)
                .triggerableAnim("tentacle_attack",   tentacle_attack_ANIM)
                .triggerableAnim("grab_eat",           GRAB_EAT_ANIM)
                .triggerableAnim("tentacles_out",      TENTACLES_OUT_TRIGGER_ANIM)
                .triggerableAnim("tentacles_retract",  TENTACLES_RETRACT_ANIM)
                .triggerableAnim("tentacle_jump",     tentacle_jump_ANIM)
                .triggerableAnim("burrow",             BURROW_ANIM)
                .triggerableAnim("dig_out",            DIG_OUT_ANIM)
        );
    }

    /** Base animation state machine — runs every render tick on the client. */
    private <E extends AICreakingEntity> PlayState baseAnimController(AnimationState<E> state) {

        // Underground — entity is hidden; no visible animation needed
        if (entityData.get(IS_UNDERGROUND)) {
            return PlayState.STOP;
        }

        // Ceiling / wall-climb mode
        if (entityData.get(IS_ON_CEILING)) {
            return state.setAndContinue(TENTACLES_WALL_CLIMB_ANIM);
        }

        boolean tentacles = entityData.get(TENTACLES_DEPLOYED);

        if (tentacles) {
            // Moving with tentacles out
            if (state.isMoving()) {
                return state.setAndContinue(tentacle_run_ANIM);
            }
            // Stationary with tentacles deployed → hold pose
            return state.setAndContinue(TENTACLES_HOLD_ANIM);
        }

        // Normal movement
        if (state.isMoving()) {
            double hSpeed = getDeltaMovement().horizontalDistance();
            return state.setAndContinue(hSpeed > 0.22 ? RUN_ANIM : WALK_ANIM);
        }

        return PlayState.STOP;
    }

    @Override
    public AnimatableInstanceCache getAnimatableInstanceCache() {
        return geoCache;
    }

    // =========================================================================
    // State setters — called by ServerGodAbilityExecutor
    // (automatically synced to all clients via SynchedEntityData)
    // =========================================================================

    public void setUnderground(boolean underground) {
        entityData.set(IS_UNDERGROUND, underground);
        setInvisible(underground);
        setNoGravity(underground);
        noPhysics = underground;
    }

    public void setOnCeiling(boolean ceiling) {
        entityData.set(IS_ON_CEILING, ceiling);
        setNoGravity(ceiling);
    }

    public void setTentaclesDeployed(boolean deployed) {
        entityData.set(TENTACLES_DEPLOYED, deployed);
    }

    public boolean isUnderground()      { return entityData.get(IS_UNDERGROUND); }
    public boolean isOnCeiling()        { return entityData.get(IS_ON_CEILING); }
    public boolean isTentaclesDeployed(){ return entityData.get(TENTACLES_DEPLOYED); }

    // =========================================================================
    // Save / load
    // =========================================================================

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("creaking_underground", isUnderground());
        tag.putBoolean("creaking_ceiling",     isOnCeiling());
        tag.putBoolean("creaking_tentacles",   isTentaclesDeployed());
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        setUnderground(tag.getBoolean("creaking_underground"));
        setOnCeiling(tag.getBoolean("creaking_ceiling"));
        setTentaclesDeployed(tag.getBoolean("creaking_tentacles"));
    }
}