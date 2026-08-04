package com.divineworld.entity.gods;

import com.divineworld.entity.ModEntities;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * AI Wither - God Entity
 * NOW EXTENDS BaseGodEntity for full player capabilities
 *
 * Abilities:
 * - Wither Skull projectiles (blue and black)
 * - Dash attack (high-speed charge)
 * - Summon Wither Skeletons
 * - Explosion (area damage)
 * - Flight
 * - Full player abilities (mining, crafting, using items, etc.)
 */
public class AIWither extends BaseGodEntity {

    // Ability cooldowns
    private int skullCooldown     = 0;
    private int blueSkullCooldown = 0;  // charged variant — longer range, sets fire
    private int dashCooldown      = 0;
    private int summonCooldown    = 0;
    private int explosionCooldown = 0;

    // States
    private boolean isFlying = true;
    private boolean isDashing = false;
    private int dashTicks = 0;

    public AIWither(EntityType<? extends Player> type, Level level) {
        super(type, level);
        setNoGravity(true);
    }

    public AIWither(Level level) {
        this(ModEntities.AI_WITHER.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 300.0)
                .add(Attributes.MOVEMENT_SPEED, 0.35)
                .add(Attributes.ATTACK_DAMAGE, 20.0)
                .add(Attributes.ARMOR, 4.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 1.0)
                .add(Attributes.FLYING_SPEED, 0.5)
                .add(Attributes.FOLLOW_RANGE, 80.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Cooldowns
        if (skullCooldown > 0) skullCooldown--;
        if (blueSkullCooldown > 0) blueSkullCooldown--;
        if (dashCooldown > 0) dashCooldown--;
        if (summonCooldown > 0) summonCooldown--;
        if (explosionCooldown > 0) explosionCooldown--;

        // Dash mechanics
        if (isDashing) {
            dashTicks++;

            // Fast-forward movement
            Vec3 lookVec = getLookAngle();
            setDeltaMovement(lookVec.scale(1.5));

            // Particles
            level().addParticle(ParticleTypes.SMOKE,
                    getX(), getY() + 1, getZ(),
                    0, 0, 0);

            if (dashTicks >= 20) { // 1 second dash
                isDashing = false;
                dashTicks = 0;
            }
        }

        // Flying particles
        if (isFlying && random.nextFloat() < 0.2f) {
            level().addParticle(ParticleTypes.LARGE_SMOKE,
                    getX(), getY(), getZ(),
                    0, 0.1, 0);
        }
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "wither_skull" -> launchWitherSkull(params);
            case "blue_skull"   -> launchBlueSkull(params);
            case "dash" -> performDash();
            case "summon_wither_skeletons" -> summonWitherSkeletons();
            case "explosion" -> createExplosion();
            case "fly" -> toggleFlight(true);
            case "transform" -> {
                if (params.length > 0) {
                    transformInto((String) params[0]);
                }
            }
            case "revert" -> revertTransformation();
        }
    }

    /**
     * Launch Wither Skull projectile
     */
    private void launchWitherSkull(Object... params) {
        if (skullCooldown > 0) return;

        boolean isBlue = params.length > 0 && (boolean) params[0];
        Vec3 lookVec = getLookAngle();

        // Damage calculation
        float damage = isBlue ? 8.0f : 5.0f;

        // Find target in look direction
        level().getEntities(this, getBoundingBox().inflate(20)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                Vec3 toTarget = living.position().subtract(position()).normalize();
                double dot = lookVec.dot(toTarget);

                if (dot > 0.9) { // Within aim cone
                    living.hurt(damageSources().magic(), damage);

                    // Wither effect
                    if (isBlue) {
                        living.setSecondsOnFire(10);
                    }
                }
            }
        });

        // Particle trail
        for (int i = 0; i < 10; i++) {
            Vec3 particlePos = position().add(lookVec.scale(i * 2));
            level().addParticle(
                    isBlue ? ParticleTypes.SOUL_FIRE_FLAME : ParticleTypes.SMOKE,
                    particlePos.x, particlePos.y + 1, particlePos.z,
                    0, 0, 0
            );
        }

        skullCooldown = 20; // 1 second
    }

    /**
     * Launch Blue (Charged) Wither Skull
     *
     * The charged skull deals 8 damage (vs 5 for black skull), travels farther,
     * applies the Wither II effect for 10 seconds, and sets the target on fire.
     * Cooldown is 40 ticks (2 s) — same rate as vanilla charged skulls.
     *
     * Distinct from launchWitherSkull: separate cooldown tracker, separate
     * useAbility() case ("blue_skull"), separate particle trail (SOUL_FIRE_FLAME
     * vs SMOKE), and separate NBT persistence (BlueSkullCooldown).
     */
    private void launchBlueSkull(Object[] params) {
        if (blueSkullCooldown > 0) return;

        Vec3 lookVec = getLookAngle();
        float damage = 8.0f;

        // Hit scan within a wider cone than regular skull (charged skulls travel straight)
        level().getEntities(this, getBoundingBox().inflate(30)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                Vec3 toTarget = living.position().subtract(position()).normalize();
                double dot    = lookVec.dot(toTarget);
                if (dot > 0.92) { // tighter aim cone — charged skull is a precision weapon
                    living.hurt(damageSources().magic(), damage);
                    living.setSecondsOnFire(10);

                    // Wither II effect — 10 seconds (same as vanilla charged skull)
                    living.addEffect(new net.minecraft.world.effect.MobEffectInstance(
                            net.minecraft.world.effect.MobEffects.WITHER, 200, 1
                    ));
                }
            }
        });

        // Blue fire particle trail — visually distinct from black skull
        for (int i = 0; i < 12; i++) {
            Vec3 pp = position().add(lookVec.scale(i * 2.5));
            level().addParticle(ParticleTypes.SOUL_FIRE_FLAME,
                    pp.x, pp.y + 1, pp.z, 0, 0, 0);
        }

        blueSkullCooldown = 40; // 2 seconds
    }

    /**
     * Dash attack - high-speed charge
     */

    private void performDash() {
        if (dashCooldown > 0 || isDashing) return;

        isDashing = true;
        dashTicks = 0;
        dashCooldown = 60; // 3 seconds

        // Damage entities in path
        level().getEntities(this, getBoundingBox().inflate(2, 1, 2)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                living.hurt(damageSources().mobAttack(this), 15.0f);

                // Knockback
                Vec3 direction = living.position().subtract(position()).normalize();
                living.push(direction.x * 2, 0.5, direction.z * 2);
            }
        });
    }

    /**
     * Summon Wither Skeletons to aid in combat
     */
    private void summonWitherSkeletons() {
        if (summonCooldown > 0) return;

        int count = 3;

        for (int i = 0; i < count; i++) {
            // Spawn position around wither
            double angle = (2 * Math.PI * i) / count;
            double x = getX() + Math.cos(angle) * 3;
            double z = getZ() + Math.sin(angle) * 3;

            // In production, spawn actual WitherSkeleton entities
            // For now, just visual effect
            for (int j = 0; j < 20; j++) {
                level().addParticle(ParticleTypes.SOUL,
                        x, getY() + j * 0.1, z,
                        0, 0.1, 0);
            }
        }

        summonCooldown = 200; // 10 seconds
    }

    /**
     * Create explosion around wither
     */
    private void createExplosion() {
        if (explosionCooldown > 0) return;

        // Damage all nearby entities
        level().getEntities(this, getBoundingBox().inflate(8)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                double distance = living.distanceTo(this);
                float damage = (float) (25.0 * (1.0 - distance / 8.0));

                living.hurt(damageSources().explosion(this, this), damage);

                // Knockback
                Vec3 direction = living.position().subtract(position()).normalize();
                double force = 2.0 * (1.0 - distance / 8.0);
                living.push(direction.x * force, 0.5 * force, direction.z * force);
            }
        });

        // Visual explosion
        for (int i = 0; i < 100; i++) {
            double offsetX = (random.nextDouble() - 0.5) * 16;
            double offsetY = (random.nextDouble() - 0.5) * 16;
            double offsetZ = (random.nextDouble() - 0.5) * 16;

            level().addParticle(ParticleTypes.EXPLOSION,
                    getX() + offsetX,
                    getY() + offsetY,
                    getZ() + offsetZ,
                    0, 0, 0);
        }

        explosionCooldown = 160; // 8 seconds
    }

    @Override
    public void toggleFlight(boolean enable) {
        isFlying = enable;
        setNoGravity(enable);
    }

    @Override
    public String getGodType() {
        return "wither";
    }

    @Override
    public float getScale() {
        return 1.8f; // Wither size
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsFlying", isFlying);
        tag.putBoolean("IsDashing", isDashing);
        tag.putInt("DashTicks", dashTicks);
        tag.putInt("SkullCooldown",     skullCooldown);
        tag.putInt("BlueSkullCooldown", blueSkullCooldown);
        tag.putInt("DashCooldown",      dashCooldown);
        tag.putInt("SummonCooldown", summonCooldown);
        tag.putInt("ExplosionCooldown", explosionCooldown);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isFlying = tag.getBoolean("IsFlying");
        isDashing = tag.getBoolean("IsDashing");
        dashTicks = tag.getInt("DashTicks");
        skullCooldown     = tag.getInt("SkullCooldown");
        blueSkullCooldown = tag.getInt("BlueSkullCooldown");
        dashCooldown      = tag.getInt("DashCooldown");
        summonCooldown = tag.getInt("SummonCooldown");
        explosionCooldown = tag.getInt("ExplosionCooldown");
    }
}