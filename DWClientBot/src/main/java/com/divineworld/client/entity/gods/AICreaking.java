// src/main/java/com/divineworld/client/entity/gods/AICreaking.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.ModEntities;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import software.bernie.geckolib.animatable.GeoEntity;
import software.bernie.geckolib.core.animatable.instance.AnimatableInstanceCache;
import software.bernie.geckolib.core.animation.*;
import software.bernie.geckolib.core.object.PlayState;
import software.bernie.geckolib.util.GeckoLibUtil;

/**
 * AI Creaking — DWClientBot client-side god entity.
 *
 * FIX (plan-creaking-geckolib-and-oracle-teach.md, Part 1, Step 1):
 * This class previously had ZERO GeckoLib wiring despite the project's
 * .geo.json / .animation.json / ai_creaking.png assets already being
 * present in DWClientBot's resources. Those assets use a UV layout
 * designed for the new GeckoLib geometry, not the old hand-coded
 * texOffs() box layout — rendering against the old model would produce
 * garbled/misaligned textures. The fix implements GeoEntity exactly
 * the same way DivineWorld's authoritative AICreakingEntity does:
 *   • implements GeoEntity
 *   • AnimatableInstanceCache via GeckoLibUtil.createInstanceCache(this)
 *   • registerControllers() with base_controller + ability_controller
 *     (same two-controller split — see AICreakingEntity.java for the
 *     design rationale)
 *   • getAnimatableInstanceCache()
 *
 * Game logic (underground movement, ceiling mode, tentacles, ability
 * dispatch, save/load) is preserved verbatim — only the rendering
 * infrastructure is being added here; the gameplay behaviour was
 * already correct.
 */
public class AICreaking extends BaseGodEntity implements GeoEntity {

    // =========================================================================
    // State fields (preserved from original)
    // =========================================================================

    private boolean isUnderground = false;
    private boolean isOnCeiling = false;
    private boolean isAngry = false;
    private boolean tentaclesDeployed = false;
    private TentacleController tentacleController;
    private MovementMode currentMode = MovementMode.NORMAL;

    // =========================================================================
    // GeckoLib — animation constants (names must match ai_creaking.animation.json)
    // Mirroring DivineWorld's AICreakingEntity.java animation set exactly —
    // both sides export from the same Blockbench project, so the animation
    // names are identical.
    // =========================================================================

    private static final RawAnimation WALK_ANIM =
            RawAnimation.begin().thenLoop("walk");
    private static final RawAnimation RUN_ANIM =
            RawAnimation.begin().thenLoop("run");
    private static final RawAnimation TENTACLES_RUN_ANIM =
            RawAnimation.begin().thenLoop("tentacles_run");
    private static final RawAnimation TENTACLES_HOLD_ANIM =
            RawAnimation.begin().thenLoop("tentacles_out");
    private static final RawAnimation TENTACLES_WALL_CLIMB_ANIM =
            RawAnimation.begin().thenLoop("tentacles_wall_climb");

    // One-shot ability animations
    private static final RawAnimation ATTACK_ANIM =
            RawAnimation.begin().then("attack",             Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_ATTACK_ANIM =
            RawAnimation.begin().then("tentacles_attack",   Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation GRAB_EAT_ANIM =
            RawAnimation.begin().then("grab_eat",           Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_OUT_TRIGGER_ANIM =
            RawAnimation.begin().then("tentacles_out",      Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_RETRACT_ANIM =
            RawAnimation.begin().then("tentacles_retract",  Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation TENTACLES_JUMP_ANIM =
            RawAnimation.begin().then("tentacles_jump",     Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation BURROW_ANIM =
            RawAnimation.begin().then("burrow",             Animation.LoopType.PLAY_ONCE);
    private static final RawAnimation DIG_OUT_ANIM =
            RawAnimation.begin().then("dig_out",            Animation.LoopType.PLAY_ONCE);

    // =========================================================================
    // GeckoLib AnimatableInstanceCache (one per entity instance, not shared)
    // =========================================================================

    private final AnimatableInstanceCache geoCache = GeckoLibUtil.createInstanceCache(this);

    // =========================================================================
    // Constructors (preserved from original)
    // =========================================================================

    public AICreaking(EntityType<? extends Player> type, Level level) {
        super(type, level);
        tentacleController = new TentacleController(this);
    }

    public AICreaking(Level level) {
        this(ModEntities.AI_CREAKING.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH,            200.0)
                .add(Attributes.MOVEMENT_SPEED,         0.35)
                .add(Attributes.ATTACK_DAMAGE,          12.0)
                .add(Attributes.KNOCKBACK_RESISTANCE,    1.0)
                .add(Attributes.FOLLOW_RANGE,           64.0);
    }

    // =========================================================================
    // GeckoLib — controller registration
    // Two controllers mirror DivineWorld's AICreakingEntity:
    //   base_controller    — looping state animations (5-tick blend)
    //   ability_controller — one-shot triggered animations (0-tick snap)
    // =========================================================================

    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {

        // Looping state machine
        controllers.add(new AnimationController<>(this, "base_controller", 5,
                this::baseAnimController));

        // One-shot ability overlay — returns CONTINUE so it never blocks
        // the base controller's looping animations
        controllers.add(new AnimationController<>(
                this, "ability_controller", 0, state -> PlayState.CONTINUE)
                .triggerableAnim("attack",            ATTACK_ANIM)
                .triggerableAnim("tentacles_attack",  TENTACLES_ATTACK_ANIM)
                .triggerableAnim("grab_eat",          GRAB_EAT_ANIM)
                .triggerableAnim("tentacles_out",     TENTACLES_OUT_TRIGGER_ANIM)
                .triggerableAnim("tentacles_retract", TENTACLES_RETRACT_ANIM)
                .triggerableAnim("tentacles_jump",    TENTACLES_JUMP_ANIM)
                .triggerableAnim("burrow",            BURROW_ANIM)
                .triggerableAnim("dig_out",           DIG_OUT_ANIM)
        );
    }

    /**
     * Base animation state machine — runs each render tick.
     * Mirrors AICreakingEntity.baseAnimController() logic exactly so
     * the two mods stay in sync on what the Creaking looks like.
     */
    private <E extends AICreaking> PlayState baseAnimController(AnimationState<E> state) {
        if (isUnderground) {
            // Hide the entity while underground — no visible animation needed
            return PlayState.STOP;
        }
        if (isOnCeiling) {
            return state.setAndContinue(TENTACLES_WALL_CLIMB_ANIM);
        }
        if (tentaclesDeployed) {
            return state.isMoving()
                    ? state.setAndContinue(TENTACLES_RUN_ANIM)
                    : state.setAndContinue(TENTACLES_HOLD_ANIM);
        }
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
    // Game logic (preserved verbatim from original)
    // =========================================================================

    @Override
    public void tick() {
        super.tick();
        if (tentaclesDeployed) {
            tentacleController.update();
        }
        if (isUnderground) {
            handleUndergroundMovement();
        }
        if (isOnCeiling) {
            handleCeilingMovement();
        }
        updateAngryState();
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "toggle_underground" -> toggleUndergroundMode();
            case "toggle_ceiling"     -> toggleCeilingMode();
            case "deploy_tentacles"   -> deployTentacles();
            case "life_steal" -> {
                if (params.length > 0 && params[0] instanceof LivingEntity)
                    lifeSteal((LivingEntity) params[0]);
            }
            case "tentacle_whip" -> {
                if (params.length > 0 && params[0] instanceof LivingEntity)
                    tentacleWhip((LivingEntity) params[0]);
            }
            case "transform" -> {
                if (params.length > 0) transformInto((String) params[0]);
            }
            case "revert" -> revertTransformation();
        }
    }

    public void toggleUndergroundMode() {
        if (!isUnderground) {
            if (onGround()) {
                isUnderground = true;
                setNoGravity(true);
                currentMode = MovementMode.UNDERGROUND;
            }
        } else {
            isUnderground = false;
            setNoGravity(false);
            this.noPhysics = false;
            currentMode = MovementMode.NORMAL;
        }
    }

    private void handleUndergroundMovement() {
        this.noPhysics = true;
        BlockPos belowPos = blockPosition().below();
        BlockState belowState = level().getBlockState(belowPos);
        if (!belowState.isSolid()) {
            toggleUndergroundMode();
        }
    }

    public void toggleCeilingMode() {
        if (!isOnCeiling) {
            BlockPos abovePos = blockPosition().above(3);
            BlockState aboveState = level().getBlockState(abovePos);
            if (aboveState.isSolid()) {
                isOnCeiling = true;
                setNoGravity(true);
                currentMode = MovementMode.CEILING;
                refreshDimensions();
            }
        } else {
            isOnCeiling = false;
            setNoGravity(false);
            currentMode = MovementMode.NORMAL;
        }
    }

    private void handleCeilingMovement() {
        BlockPos abovePos = blockPosition().above(3);
        BlockState aboveState = level().getBlockState(abovePos);
        if (!aboveState.isSolid()) {
            toggleCeilingMode();
            return;
        }
        setDeltaMovement(getDeltaMovement().add(0, 0.1, 0));
    }

    private void updateAngryState() {
        LivingEntity target = getLastHurtByMob();
        if (target != null) {
            float targetHealthPercent = target.getHealth() / target.getMaxHealth();
            if (targetHealthPercent < 0.8 && !isAngry) {
                isAngry = true;
                deployTentacles();
            }
        } else if (isAngry) {
            isAngry = false;
            retractTentacles();
        }
    }

    private void deployTentacles() {
        if (!tentaclesDeployed) {
            tentaclesDeployed = true;
            tentacleController.deploy();
        }
    }

    private void retractTentacles() {
        if (tentaclesDeployed) {
            tentaclesDeployed = false;
            tentacleController.retract();
        }
    }

    private void tentacleWhip(LivingEntity target) {
        if (!tentaclesDeployed) return;
        if (distanceTo(target) > 8.0) return;
        target.hurt(damageSources().mobAttack(this), 8.0f);
        double dx = target.getX() - getX();
        double dz = target.getZ() - getZ();
        double magnitude = Math.sqrt(dx * dx + dz * dz);
        target.push(dx / magnitude * 0.5, 0.3, dz / magnitude * 0.5);
        for (int i = 0; i < 10; i++) {
            level().addParticle(ParticleTypes.SWEEP_ATTACK,
                    target.getX(), target.getY() + 1, target.getZ(), 0, 0, 0);
        }
    }

    private void lifeSteal(LivingEntity target) {
        if (!tentaclesDeployed) return;
        if (target.getHealth() / target.getMaxHealth() >= 0.2) return;
        float drain = 5.0f;
        target.hurt(damageSources().magic(), drain);
        heal(drain);
        for (int i = 0; i < 20; i++) {
            Vec3 particlePos = target.position().add(
                    (random.nextDouble() - 0.5) * 0.5,
                    random.nextDouble() * target.getBbHeight(),
                    (random.nextDouble() - 0.5) * 0.5);
            Vec3 direction = position().subtract(particlePos).normalize();
            level().addParticle(ParticleTypes.CRIMSON_SPORE,
                    particlePos.x, particlePos.y, particlePos.z,
                    direction.x * 0.1, direction.y * 0.1, direction.z * 0.1);
        }
    }

    // =========================================================================
    // BaseGodEntity overrides (preserved from original)
    // =========================================================================

    @Override
    protected void spawnTransformParticles() {
        for (int i = 0; i < 50; i++) {
            level().addParticle(ParticleTypes.SPORE_BLOSSOM_AIR,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY() + random.nextDouble() * 3,
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0.3, 0);
        }
    }

    @Override public void toggleFlight(boolean enable) { /* Creaking doesn't fly */ }
    @Override public String getGodType() { return "creaking"; }
    @Override public float getScale()    { return 1.2f; }

    // Expose state for CreakingGeoRenderer's underground-visibility check,
    // matching AICreakingEntity.isUnderground()
    public boolean isUnderground()        { return isUnderground; }
    public boolean isTentaclesDeployed()  { return tentaclesDeployed; }
    public boolean isOnCeiling()          { return isOnCeiling; }

    // =========================================================================
    // Save / load (preserved from original)
    // =========================================================================

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsUnderground",    isUnderground);
        tag.putBoolean("IsOnCeiling",      isOnCeiling);
        tag.putBoolean("IsAngry",          isAngry);
        tag.putBoolean("TentaclesDeployed", tentaclesDeployed);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isUnderground    = tag.getBoolean("IsUnderground");
        isOnCeiling      = tag.getBoolean("IsOnCeiling");
        isAngry          = tag.getBoolean("IsAngry");
        tentaclesDeployed = tag.getBoolean("TentaclesDeployed");
    }

    // =========================================================================
    // Enums and inner classes (preserved from original)
    // =========================================================================

    public enum MovementMode { NORMAL, UNDERGROUND, WALL_CLIMBING, CEILING }

    private static class TentacleController {
        private final AICreaking owner;
        private boolean deployed = false;
        private final TentacleSegment[] tentacles = new TentacleSegment[4];
        private int animationTick = 0;

        public TentacleController(AICreaking owner) {
            this.owner = owner;
            for (int i = 0; i < 4; i++) {
                tentacles[i] = new TentacleSegment((Math.PI * 2 * i) / 4);
            }
        }

        public void deploy() {
            deployed = true;
            animationTick = 0;
            for (int i = 0; i < 30; i++) {
                owner.level().addParticle(ParticleTypes.WARPED_SPORE,
                        owner.getX(), owner.getY() + 1.5, owner.getZ(),
                        (owner.random.nextDouble() - 0.5) * 0.5,
                        owner.random.nextDouble() * 0.3,
                        (owner.random.nextDouble() - 0.5) * 0.5);
            }
        }

        public void retract() {
            deployed = false;
            for (int i = 0; i < 20; i++) {
                owner.level().addParticle(ParticleTypes.SMOKE,
                        owner.getX(), owner.getY() + 1.5, owner.getZ(),
                        (owner.random.nextDouble() - 0.5) * 0.2,
                        owner.random.nextDouble() * 0.1,
                        (owner.random.nextDouble() - 0.5) * 0.2);
            }
        }

        public void update() {
            if (!deployed) return;
            animationTick++;
            for (TentacleSegment tentacle : tentacles) {
                tentacle.update(animationTick);
                if (animationTick % 5 == 0) {
                    Vec3 tentaclePos = owner.position().add(
                            Math.cos(tentacle.angle) * tentacle.length,
                            1.5,
                            Math.sin(tentacle.angle) * tentacle.length);
                    owner.level().addParticle(ParticleTypes.WARPED_SPORE,
                            tentaclePos.x, tentaclePos.y, tentaclePos.z, 0, 0, 0);
                }
            }
            owner.level().getEntities(owner, owner.getBoundingBox().inflate(3)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != owner) {
                    if (owner.random.nextFloat() < 0.1f) {
                        living.hurt(owner.damageSources().mobAttack(owner), 3.0f);
                    }
                }
            });
        }

        private static class TentacleSegment {
            private final double angle;
            private double length = 0.0;
            private final double targetLength = 2.0;

            public TentacleSegment(double angle) { this.angle = angle; }

            public void update(int tick) {
                if (length < targetLength) length += 0.1;
                // wave unused for motion but kept — GeckoLib handles visible
                // tentacle animation from the .animation.json now, not Java
            }
        }
    }
}