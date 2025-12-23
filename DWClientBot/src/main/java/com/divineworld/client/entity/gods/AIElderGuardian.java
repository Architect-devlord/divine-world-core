package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.ModEntities;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * AI Elder Guardian - God Entity
 * NOW EXTENDS BaseGodEntity for full player capabilities
 *
 * Abilities:
 * - Mining Fatigue (inflict on enemies)
 * - Laser Beam (precise long-range attack)
 * - Water Breathing (permanent underwater capability)
 * - Thorn Attack (reflect damage)
 * - Guardian Spikes (defensive mode)
 * - Full player abilities (mining, crafting, using items, etc.)
 */
public class AIElderGuardian extends BaseGodEntity {

    // Ability cooldowns
    private int miningFatigueCooldown = 0;
    private int laserBeamCooldown = 0;
    private int thornCooldown = 0;
    private int spikesCooldown = 0;

    // States
    private boolean spikesActive = false;
    private int spikesTicks = 0;
    private boolean isLaserCharging = false;
    private int laserChargeTicks = 0;

    public AIElderGuardian(EntityType<? extends Player> type, Level level) {
        super(type, level);

        // Permanent water breathing
        addEffect(new MobEffectInstance(MobEffects.WATER_BREATHING, Integer.MAX_VALUE, 0, false, false));
    }

    public AIElderGuardian(Level level) {
        this(ModEntities.AI_ELDER_GUARDIAN.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 250.0)
                .add(Attributes.MOVEMENT_SPEED, 0.25)
                .add(Attributes.ATTACK_DAMAGE, 18.0)
                .add(Attributes.ARMOR, 8.0)
                .add(Attributes.ARMOR_TOUGHNESS, 4.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 0.8)
                .add(Attributes.FOLLOW_RANGE, 50.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Cooldowns
        if (miningFatigueCooldown > 0) miningFatigueCooldown--;
        if (laserBeamCooldown > 0) laserBeamCooldown--;
        if (thornCooldown > 0) thornCooldown--;
        if (spikesCooldown > 0) spikesCooldown--;

        // Spikes mode
        if (spikesActive) {
            spikesTicks++;

            // Reflect damage to nearby entities
            level().getEntities(this, getBoundingBox().inflate(3)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != this) {
                    if (living.distanceTo(this) < 3) {
                        living.hurt(damageSources().thorns(this), 2.0f);
                    }
                }
            });

            // Spike particles
            if (random.nextFloat() < 0.3f) {
                double angle = random.nextDouble() * Math.PI * 2;
                double radius = 2;
                level().addParticle(ParticleTypes.CRIT,
                        getX() + Math.cos(angle) * radius,
                        getY() + 1,
                        getZ() + Math.sin(angle) * radius,
                        0, 0, 0);
            }

            // Spikes last 10 seconds
            if (spikesTicks >= 200) {
                spikesActive = false;
                spikesTicks = 0;
            }
        }

        // Laser charging
        if (isLaserCharging) {
            laserChargeTicks++;

            // Charging particles
            Vec3 lookVec = getLookAngle();
            Vec3 eyePos = position().add(0, getEyeHeight(), 0);

            for (int i = 0; i < 3; i++) {
                level().addParticle(ParticleTypes.END_ROD,
                        eyePos.x + lookVec.x * i,
                        eyePos.y + lookVec.y * i,
                        eyePos.z + lookVec.z * i,
                        0, 0, 0);
            }

            if (laserChargeTicks >= 40) { // 2 second charge
                fireLaser();
                isLaserCharging = false;
                laserChargeTicks = 0;
            }
        }

        // Underwater particles
        if (isInWater() && random.nextFloat() < 0.1f) {
            level().addParticle(ParticleTypes.BUBBLE,
                    getX() + (random.nextDouble() - 0.5),
                    getY() + random.nextDouble() * 2,
                    getZ() + (random.nextDouble() - 0.5),
                    0, 0.1, 0);
        }
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "mining_fatigue" -> applyMiningFatigue();
            case "laser_beam" -> chargeLaserBeam();
            case "thorn_attack" -> activateThornAttack();
            case "guardian_spikes" -> activateGuardianSpikes();
            case "transform" -> {
                if (params.length > 0) {
                    transformInto((String) params[0]);
                }
            }
            case "revert" -> revertTransformation();
        }
    }

    /**
     * Apply Mining Fatigue to all nearby enemies
     */
    private void applyMiningFatigue() {
        if (miningFatigueCooldown > 0) return;

        level().getEntities(this, getBoundingBox().inflate(30)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                // Apply Mining Fatigue III for 5 minutes
                living.addEffect(new MobEffectInstance(
                        MobEffects.DIG_SLOWDOWN, 6000, 2, true, true
                ));

                // Visual effect
                for (int i = 0; i < 10; i++) {
                    level().addParticle(ParticleTypes.ELDER_GUARDIAN,
                            living.getX(),
                            living.getY() + 1,
                            living.getZ(),
                            (random.nextDouble() - 0.5) * 0.2,
                            random.nextDouble() * 0.2,
                            (random.nextDouble() - 0.5) * 0.2);
                }
            }
        });

        miningFatigueCooldown = 1200; // 60 seconds
    }

    /**
     * Charge laser beam
     */
    private void chargeLaserBeam() {
        if (laserBeamCooldown > 0 || isLaserCharging) return;

        isLaserCharging = true;
        laserChargeTicks = 0;
    }

    /**
     * Fire charged laser beam
     */
    private void fireLaser() {
        Vec3 lookVec = getLookAngle();
        Vec3 startPos = position().add(0, getEyeHeight(), 0);

        // Laser travels 50 blocks
        for (double d = 0; d < 50; d += 0.5) {
            Vec3 beamPos = startPos.add(lookVec.scale(d));

            // Damage entities
            level().getEntities(this, getBoundingBox().inflate(50)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != this) {
                    if (living.position().distanceTo(beamPos) < 1.0) {
                        living.hurt(damageSources().indirectMagic(this, this), 15.0f);

                        // Knockback
                        Vec3 direction = living.position().subtract(position()).normalize();
                        living.push(direction.x, 0.5, direction.z);
                    }
                }
            });

            // Visual beam
            level().addParticle(ParticleTypes.END_ROD,
                    beamPos.x, beamPos.y, beamPos.z,
                    0, 0, 0);
        }

        laserBeamCooldown = 60; // 3 seconds
    }

    /**
     * Activate Thorn Attack - reflect damage
     */
    private void activateThornAttack() {
        if (thornCooldown > 0) return;

        // Next entity that attacks gets damaged
        // Implemented in hurt() method

        thornCooldown = 100; // 5 seconds
    }

    /**
     * Activate Guardian Spikes - defensive mode
     */
    private void activateGuardianSpikes() {
        if (spikesCooldown > 0 || spikesActive) return;

        spikesActive = true;
        spikesTicks = 0;
        spikesCooldown = 400; // 20 seconds

        // Spike burst effect
        for (int i = 0; i < 50; i++) {
            double angle = (Math.PI * 2 * i) / 50;
            double radius = 3;

            level().addParticle(ParticleTypes.CRIT,
                    getX() + Math.cos(angle) * radius,
                    getY() + 1,
                    getZ() + Math.sin(angle) * radius,
                    Math.cos(angle) * 0.5,
                    0.3,
                    Math.sin(angle) * 0.5);
        }
    }

    @Override
    public boolean hurt(DamageSource source, float amount) {
        // Thorn reflection
        if (thornCooldown < 100 && thornCooldown > 0 && source.getEntity() instanceof LivingEntity attacker) {
            attacker.hurt(damageSources().thorns(this), amount * 0.5f);
        }

        return super.hurt(source, amount);
    }

    @Override
    public void toggleFlight(boolean enable) {
        // Elder Guardian doesn't fly but has excellent water mobility
        // Could add special water movement here
    }

    @Override
    public String getGodType() {
        return "elder_guardian";
    }

    @Override
    public float getScale() {
        return 1.9975f; // Elder Guardian size
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("SpikesActive", spikesActive);
        tag.putInt("SpikesTicks", spikesTicks);
        tag.putBoolean("IsLaserCharging", isLaserCharging);
        tag.putInt("LaserChargeTicks", laserChargeTicks);
        tag.putInt("MiningFatigueCooldown", miningFatigueCooldown);
        tag.putInt("LaserBeamCooldown", laserBeamCooldown);
        tag.putInt("ThornCooldown", thornCooldown);
        tag.putInt("SpikesCooldown", spikesCooldown);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        spikesActive = tag.getBoolean("SpikesActive");
        spikesTicks = tag.getInt("SpikesTicks");
        isLaserCharging = tag.getBoolean("IsLaserCharging");
        laserChargeTicks = tag.getInt("LaserChargeTicks");
        miningFatigueCooldown = tag.getInt("MiningFatigueCooldown");
        laserBeamCooldown = tag.getInt("LaserBeamCooldown");
        thornCooldown = tag.getInt("ThornCooldown");
        spikesCooldown = tag.getInt("SpikesCooldown");
    }
}