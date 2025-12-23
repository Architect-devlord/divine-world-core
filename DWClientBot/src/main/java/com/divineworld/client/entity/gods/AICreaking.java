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

/**
 * AI Creaking - FULLY FIXED VERSION
 * Extends BaseGodEntity properly
 * FIXED: noPhysics field access, proper entity type
 */
public class AICreaking extends BaseGodEntity {
    private boolean isUnderground = false;
    private boolean isOnCeiling = false;
    private boolean isAngry = false;
    private boolean tentaclesDeployed = false;
    private TentacleController tentacleController;
    private MovementMode currentMode = MovementMode.NORMAL;

    public AICreaking(EntityType<? extends Player> type, Level level) {
        super(type, level);
        tentacleController = new TentacleController(this);
    }

    public AICreaking(Level level) {
        this(ModEntities.AI_CREAKING.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 200.0)
                .add(Attributes.MOVEMENT_SPEED, 0.35)
                .add(Attributes.ATTACK_DAMAGE, 12.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 1.0)
                .add(Attributes.FOLLOW_RANGE, 64.0);
    }

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
            case "toggle_ceiling" -> toggleCeilingMode();
            case "deploy_tentacles" -> deployTentacles();
            case "life_steal" -> {
                if (params.length > 0 && params[0] instanceof LivingEntity) {
                    lifeSteal((LivingEntity) params[0]);
                }
            }
            case "tentacle_whip" -> {
                if (params.length > 0 && params[0] instanceof LivingEntity) {
                    tentacleWhip((LivingEntity) params[0]);
                }
            }
            case "transform" -> {
                if (params.length > 0) {
                    transformInto((String) params[0]);
                }
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
            currentMode = MovementMode.NORMAL;
        }
    }

    private void handleUndergroundMovement() {

        this.noPhysics=true;

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

        double distance = distanceTo(target);
        if (distance > 8.0) return;

        target.hurt(damageSources().mobAttack(this), 8.0f);

        double dx = target.getX() - getX();
        double dz = target.getZ() - getZ();
        double magnitude = Math.sqrt(dx * dx + dz * dz);

        target.push(dx / magnitude * 0.5, 0.3, dz / magnitude * 0.5);

        for (int i = 0; i < 10; i++) {
            level().addParticle(ParticleTypes.SWEEP_ATTACK,
                    target.getX(), target.getY() + 1, target.getZ(),
                    0, 0, 0);
        }
    }

    private void lifeSteal(LivingEntity target) {
        if (!tentaclesDeployed) return;

        float targetHealthPercent = target.getHealth() / target.getMaxHealth();

        if (targetHealthPercent < 0.2) {
            float drainAmount = 5.0f;

            target.hurt(damageSources().magic(), drainAmount);
            heal(drainAmount);

            for (int i = 0; i < 20; i++) {
                Vec3 particlePos = target.position().add(
                        (random.nextDouble() - 0.5) * 0.5,
                        random.nextDouble() * target.getBbHeight(),
                        (random.nextDouble() - 0.5) * 0.5
                );

                Vec3 direction = position().subtract(particlePos).normalize();

                level().addParticle(ParticleTypes.CRIMSON_SPORE,
                        particlePos.x, particlePos.y, particlePos.z,
                        direction.x * 0.1, direction.y * 0.1, direction.z * 0.1);
            }
        }
    }

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

    @Override
    public void toggleFlight(boolean enable) {
        // Creaking doesn't fly
    }

    @Override
    public String getGodType() {
        return "creaking";
    }

    @Override
    public float getScale() {
        return 1.2f;
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsUnderground", isUnderground);
        tag.putBoolean("IsOnCeiling", isOnCeiling);
        tag.putBoolean("IsAngry", isAngry);
        tag.putBoolean("TentaclesDeployed", tentaclesDeployed);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isUnderground = tag.getBoolean("IsUnderground");
        isOnCeiling = tag.getBoolean("IsOnCeiling");
        isAngry = tag.getBoolean("IsAngry");
        tentaclesDeployed = tag.getBoolean("TentaclesDeployed");
    }

    public enum MovementMode {
        NORMAL, UNDERGROUND, WALL_CLIMBING, CEILING
    }

    private static class TentacleController {
        private final AICreaking owner;
        private boolean deployed = false;
        private final TentacleSegment[] tentacles = new TentacleSegment[4];
        private int animationTick = 0;

        public TentacleController(AICreaking owner) {
            this.owner = owner;
            for (int i = 0; i < 4; i++) {
                double angle = (Math.PI * 2 * i) / 4;
                tentacles[i] = new TentacleSegment(angle);
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

            for (int i = 0; i < tentacles.length; i++) {
                TentacleSegment tentacle = tentacles[i];
                tentacle.update(animationTick);

                if (animationTick % 5 == 0) {
                    Vec3 tentaclePos = owner.position().add(
                            Math.cos(tentacle.angle) * tentacle.length,
                            1.5,
                            Math.sin(tentacle.angle) * tentacle.length
                    );

                    owner.level().addParticle(ParticleTypes.WARPED_SPORE,
                            tentaclePos.x, tentaclePos.y, tentaclePos.z,
                            0, 0, 0);
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
            private double targetLength = 2.0;
            private double wave = 0.0;

            public TentacleSegment(double angle) {
                this.angle = angle;
            }

            public void update(int tick) {
                if (length < targetLength) {
                    length += 0.1;
                }
                wave = Math.sin(tick * 0.1 + angle) * 0.3;
            }
        }
    }
}