package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.ModEntities;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * AI Ender Dragon - God Entity
 * NOW EXTENDS BaseGodEntity for full player capabilities
 *
 * Abilities:
 * - Flight (natural dragon flight)
 * - Dragon Breath (area damage)
 * - Fireball attack (projectile)
 * - Perching (land and attack from ground)
 * - Full player abilities (mining, crafting, using items, etc.)
 */
public class AIEnderDragon extends BaseGodEntity {

    // Ability states
    private boolean isFlying = true;
    private boolean isPerched = false;
    private int breathCooldown = 0;
    private int fireballCooldown = 0;

    public AIEnderDragon(EntityType<? extends Player> type, Level level) {
        super(type, level);
        setNoGravity(true); // Dragons fly
    }

    public AIEnderDragon(Level level) {
        this(ModEntities.AI_ENDER_DRAGON.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 200.0)
                .add(Attributes.MOVEMENT_SPEED, 0.3)
                .add(Attributes.ATTACK_DAMAGE, 15.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 1.0)
                .add(Attributes.FLYING_SPEED, 0.4)
                .add(Attributes.FOLLOW_RANGE, 128.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Decrease cooldowns
        if (breathCooldown > 0) breathCooldown--;
        if (fireballCooldown > 0) fireballCooldown--;

        // Flight mechanics (even when transformed)
        if (isFlying && !onGround()) {
            setDeltaMovement(getDeltaMovement().add(0, 0.02, 0)); // Slight upward force
        }

        // Visual effects when flying
        if (isFlying && random.nextFloat() < 0.1f) {
            level().addParticle(ParticleTypes.DRAGON_BREATH,
                    getX(), getY(), getZ(),
                    0, 0, 0);
        }
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "dragon_breath" -> useDragonBreath();
            case "fireball" -> launchFireball(params);
            case "perch" -> togglePerch();
            case "fly" -> toggleFlight(true);
            case "transform" -> {
                if (params.length > 0) {
                    String targetMob = (String) params[0];
                    transformInto(targetMob);
                }
            }
            case "revert" -> revertTransformation();
        }
    }

    /**
     * Dragon Breath - Area damage over time
     */
    private void useDragonBreath() {
        if (breathCooldown > 0) return;

        // Create damage area in front of dragon
        Vec3 lookVec = getLookAngle();
        Vec3 breathPos = position().add(lookVec.scale(3));

        // Damage entities in area
        level().getEntities(this, getBoundingBox().inflate(8, 4, 8)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                double dist = entity.distanceTo(this);
                if (dist < 8) {
                    living.hurt(damageSources().dragonBreath(), 6.0f);

                    // Add lingering damage
                    living.setSecondsOnFire(5);
                }
            }
        });

        // Visual effects
        for (int i = 0; i < 50; i++) {
            double offsetX = (random.nextDouble() - 0.5) * 4;
            double offsetY = (random.nextDouble() - 0.5) * 2;
            double offsetZ = (random.nextDouble() - 0.5) * 4;

            level().addParticle(ParticleTypes.DRAGON_BREATH,
                    breathPos.x + offsetX,
                    breathPos.y + offsetY,
                    breathPos.z + offsetZ,
                    0, 0.1, 0);
        }

        breathCooldown = 100; // 5 seconds
    }

    /**
     * Launch Fireball projectile
     */
    private void launchFireball(Object... params) {
        if (fireballCooldown > 0) return;

        Vec3 lookVec = getLookAngle();

        // Create fireball entity
        // In production, use DragonFireball entity
        // For now, just damage target directly

        if (params.length > 0 && params[0] instanceof LivingEntity target) {
            // Direct hit
            target.hurt(damageSources().mobProjectile(null, this), 12.0f);
            target.setSecondsOnFire(10);
        }

        fireballCooldown = 40; // 2 seconds
    }

    /**
     * Toggle perch mode (land on ground)
     */
    private void togglePerch() {
        isPerched = !isPerched;

        if (isPerched) {
            setNoGravity(false);
            isFlying = false;
        } else {
            setNoGravity(true);
            isFlying = true;
        }
    }

    @Override
    public void toggleFlight(boolean enable) {
        isFlying = enable;
        setNoGravity(enable);

        if (!enable) {
            // Slowly descend
            setDeltaMovement(getDeltaMovement().multiply(1, 0.5, 1));
        }
    }

    @Override
    protected void spawnTransformParticles() {
        for (int i = 0; i < 100; i++) {
            double offsetX = (random.nextDouble() - 0.5) * 2;
            double offsetY = random.nextDouble() * 3;
            double offsetZ = (random.nextDouble() - 0.5) * 2;

            level().addParticle(ParticleTypes.PORTAL,
                    getX() + offsetX,
                    getY() + offsetY,
                    getZ() + offsetZ,
                    0, 0.5, 0);
        }
    }

    @Override
    public String getGodType() {
        return "ender_dragon";
    }

    @Override
    public float getScale() {
        return 4.0f; // Large dragon
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsFlying", isFlying);
        tag.putBoolean("IsPerched", isPerched);
        tag.putInt("BreathCooldown", breathCooldown);
        tag.putInt("FireballCooldown", fireballCooldown);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isFlying = tag.getBoolean("IsFlying");
        isPerched = tag.getBoolean("IsPerched");
        breathCooldown = tag.getInt("BreathCooldown");
        fireballCooldown = tag.getInt("FireballCooldown");
    }
}