// src/main/java/com/divineworld/client/entity/gods/AIWarden.java
package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.ModEntities;
import net.minecraft.core.particles.ParticleOptions;
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
 * AI Warden - God Entity
 * NOW EXTENDS BaseGodEntity for full player capabilities
 *
 * Abilities:
 * - Sonic Boom (ranged attack, ignores armor)
 * - Darkness effect (blind nearby entities)
 * - Sniff (detect vibrations, track entities)
 * - Burrow (go underground temporarily)
 * - Emerge (surface attack)
 * - Full player abilities (mining, crafting, using items, etc.)
 *
 * FIXED:
 * - Now extends BaseGodEntity (Player-based)
 * - Removed Monster inheritance conflicts
 * - Uses Player's Inventory system
 * - All player mechanics work properly
 */
public class AIWarden extends BaseGodEntity {

    // Ability cooldowns
    private int sonicBoomCooldown = 0;
    private int darknessCooldown = 0;
    private int sniffCooldown = 0;
    private int burrowCooldown = 0;

    // States
    private boolean isBurrowed = false;
    private int burrowTicks = 0;
    private boolean isSniffing = false;

    // Vibration detection
    private Vec3 lastVibrationPos = null;
    private int vibrationAge = 0;

    public AIWarden(EntityType<? extends Player> type, Level level) {
        super(type, level);
    }

    public AIWarden(Level level) {
        this(ModEntities.AI_WARDEN.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 500.0)
                .add(Attributes.MOVEMENT_SPEED, 0.3)
                .add(Attributes.ATTACK_DAMAGE, 30.0)
                .add(Attributes.ARMOR, 10.0)
                .add(Attributes.ARMOR_TOUGHNESS, 4.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 1.0)
                .add(Attributes.FOLLOW_RANGE, 64.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Cooldowns
        if (sonicBoomCooldown > 0) sonicBoomCooldown--;
        if (darknessCooldown > 0) darknessCooldown--;
        if (sniffCooldown > 0) {
            sniffCooldown--;
            // Stop sniffing when cooldown expires
            if (sniffCooldown == 0) {
                isSniffing = false;
            }
        }
        if (burrowCooldown > 0) burrowCooldown--;

        // Burrow mechanics
        if (isBurrowed) {
            burrowTicks++;

            // Invisible and invulnerable while burrowed
            setInvisible(true);
            setInvulnerable(true);
            this.noPhysics = true;
            setDeltaMovement(Vec3.ZERO);

            // Slowly sink into ground
            if (burrowTicks < 20) {
                setDeltaMovement(getDeltaMovement().add(0, -0.1, 0));
            }

            // Particles
            if (random.nextFloat() < 0.3f) {
                level().addParticle(ParticleTypes.SCULK_SOUL,
                        getX(), getY() + 1, getZ(),
                        0, 0, 0);
            }

            // Auto-emerge after 5 seconds
            if (burrowTicks >= 100) {
                emergFromBurrow();
            }
        }

        // Vibration aging
        if (lastVibrationPos != null) {
            vibrationAge++;
            if (vibrationAge > 100) {
                lastVibrationPos = null;
            }
        }

        // Ambient particles
        if (random.nextFloat() < 0.1f) {
            level().addParticle(ParticleTypes.SCULK_SOUL,
                    getX() + (random.nextDouble() - 0.5),
                    getY() + random.nextDouble() * 2,
                    getZ() + (random.nextDouble() - 0.5),
                    0, 0.05, 0);
        }

        // Sniffing detection particles
        if (isSniffing && random.nextFloat() < 0.2f) {
            level().addParticle(ParticleTypes.SCULK_CHARGE_POP,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY() + 0.5,
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0, 0);
        }
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "sonic_boom" -> useSonicBoom(params);
            case "darkness" -> applyDarkness();
            case "sniff" -> performSniff();
            case "burrow" -> burrowUnderground();
            case "emerge" -> emergFromBurrow();
            case "transform" -> {
                if (params.length > 0) {
                    transformInto((String) params[0]);
                }
            }
            case "revert" -> revertTransformation();
        }
    }

    /**
     * Sonic Boom - Powerful ranged attack that ignores armor
     */
    private void useSonicBoom(Object... params) {
        if (sonicBoomCooldown > 0) return;

        Vec3 lookVec = getLookAngle();
        Vec3 startPos = position().add(0, getEyeHeight(), 0);

        // Raycast for target (30 blocks range)
        for (double d = 0; d < 30; d += 0.5) {
            Vec3 checkPos = startPos.add(lookVec.scale(d));

            // Check for entities
            level().getEntities(this, getBoundingBox().inflate(30)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != this) {
                    if (living.position().distanceTo(checkPos) < 1.5) {
                        // Direct damage (ignores armor)
                        living.hurt(damageSources().sonicBoom(this), 25.0f);

                        // Strong knockback
                        Vec3 direction = living.position().subtract(position()).normalize();
                        living.push(direction.x * 3, 1.0, direction.z * 3);
                    }
                }
            });

            // Visual beam - spawn particles along path
            if (d % 1.0 < 0.5) { // Every block
                level().addParticle(ParticleTypes.SONIC_BOOM,
                        checkPos.x, checkPos.y, checkPos.z,
                        0, 0, 0);
            }
        }

        // Charging sound/particles before boom
        for (int i = 0; i < 20; i++) {
            double offsetX = (random.nextDouble() - 0.5) * 2;
            double offsetY = random.nextDouble() * 2;
            double offsetZ = (random.nextDouble() - 0.5) * 2;

            level().addParticle((ParticleOptions) ParticleTypes.SCULK_CHARGE,
                    getX() + offsetX,
                    getY() + offsetY,
                    getZ() + offsetZ,
                    0, 0, 0);
        }

        sonicBoomCooldown = 100; // 5 seconds
    }

    /**
     * Apply Darkness effect to nearby entities
     */
    private void applyDarkness() {
        if (darknessCooldown > 0) return;

        // Affect all entities in 20 block radius
        level().getEntities(this, getBoundingBox().inflate(20)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                // Apply darkness effect (blindness + darkness)
                living.addEffect(new MobEffectInstance(
                        MobEffects.BLINDNESS, 300, 0, false, true
                ));

                living.addEffect(new MobEffectInstance(
                        MobEffects.DARKNESS, 300, 0, false, true
                ));
            }
        });

        // Visual effect - spreading darkness
        for (int i = 0; i < 200; i++) {
            double angle = random.nextDouble() * Math.PI * 2;
            double distance = 5 + random.nextDouble() * 15;
            double x = getX() + Math.cos(angle) * distance;
            double z = getZ() + Math.sin(angle) * distance;
            double y = getY() + random.nextDouble() * 5;

            level().addParticle((ParticleOptions) ParticleTypes.SCULK_CHARGE,
                    x, y, z,
                    0, -0.1, 0);
        }

        darknessCooldown = 300; // 15 seconds
    }

    /**
     * Sniff for vibrations - detect nearby entities
     */
    private void performSniff() {
        if (sniffCooldown > 0) return;

        isSniffing = true;
        sniffCooldown = 40; // 2 seconds - sniffing will stop when cooldown expires

        // Detect all vibration sources (moving entities)
        level().getEntities(this, getBoundingBox().inflate(32)).forEach(entity -> {
            if (entity instanceof LivingEntity && entity != this) {
                Vec3 entityVel = entity.getDeltaMovement();

                // If entity is moving, detect it
                if (entityVel.length() > 0.01) {
                    lastVibrationPos = entity.position();
                    vibrationAge = 0;

                    // Visual indicator at entity location
                    for (int i = 0; i < 10; i++) {
                        level().addParticle(ParticleTypes.SCULK_CHARGE_POP,
                                entity.getX() + (random.nextDouble() - 0.5),
                                entity.getY() + 1,
                                entity.getZ() + (random.nextDouble() - 0.5),
                                0, 0.1, 0);
                    }

                    // Visual line from warden to detected entity
                    Vec3 start = position().add(0, getEyeHeight(), 0);
                    Vec3 end = entity.position().add(0, entity.getEyeHeight(), 0);
                    Vec3 direction = end.subtract(start);
                    double distance = direction.length();
                    direction = direction.normalize();

                    // Spawn particles along line
                    for (double d = 0; d < distance; d += 1.0) {
                        Vec3 particlePos = start.add(direction.scale(d));
                        level().addParticle((ParticleOptions) ParticleTypes.SCULK_CHARGE,
                                particlePos.x, particlePos.y, particlePos.z,
                                0, 0, 0);
                    }
                }
            }
        });

        // Stop sniffing after 2 seconds (handled by cooldown)
        // isSniffing will be set to false when sniffCooldown reaches 0
    }

    /**
     * Burrow underground (become invulnerable, invisible)
     */
    private void burrowUnderground() {
        if (burrowCooldown > 0 || isBurrowed) return;
        if (!onGround()) return; // Must be on ground to burrow

        isBurrowed = true;
        burrowTicks = 0;

        // Particle effect - sinking into ground
        for (int i = 0; i < 50; i++) {
            level().addParticle(ParticleTypes.SCULK_SOUL,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY(),
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0.2, 0);
        }
    }

    /**
     * Emerge from burrow
     */
    private void emergFromBurrow() {
        if (!isBurrowed) return;

        isBurrowed = false;
        burrowTicks = 0;
        burrowCooldown = 200; // 10 seconds

        // Restore physics
        this.noPhysics = false;
        setInvisible(false);
        setInvulnerable(false);

        // Emergence effect - damage nearby entities
        level().getEntities(this, getBoundingBox().inflate(5)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                living.hurt(damageSources().mobAttack(this), 20.0f);

                // Knockback
                Vec3 direction = living.position().subtract(position()).normalize();
                living.push(direction.x * 2, 1.5, direction.z * 2);
            }
        });

        // Particles - eruption from ground
        for (int i = 0; i < 100; i++) {
            level().addParticle(ParticleTypes.SCULK_CHARGE_POP,
                    getX() + (random.nextDouble() - 0.5) * 4,
                    getY(),
                    getZ() + (random.nextDouble() - 0.5) * 4,
                    (random.nextDouble() - 0.5) * 0.5,
                    random.nextDouble() * 0.5,
                    (random.nextDouble() - 0.5) * 0.5);
        }

        // Ground shake particles
        for (int i = 0; i < 50; i++) {
            double angle = (Math.PI * 2 * i) / 50;
            double radius = 5;
            double x = getX() + Math.cos(angle) * radius;
            double z = getZ() + Math.sin(angle) * radius;

            level().addParticle(ParticleTypes.POOF,
                    x, getY(), z,
                    Math.cos(angle) * 0.3,
                    0.2,
                    Math.sin(angle) * 0.3);
        }
    }

    @Override
    public void toggleFlight(boolean enable) {
        // Warden doesn't fly, but can burrow
        // Flight control is ignored for Warden
    }

    @Override
    protected void spawnTransformParticles() {
        // Sculk-themed transformation
        for (int i = 0; i < 50; i++) {
            level().addParticle(ParticleTypes.SCULK_SOUL,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY() + random.nextDouble() * 3,
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0.3, 0);
        }
    }

    @Override
    public String getGodType() {
        return "warden";
    }

    @Override
    public float getScale() {
        return 1.5f; // Warden size (slightly larger than player)
    }

    @Override
    public boolean hurt(DamageSource source, float amount) {
        // Warden has high resistance but can still be damaged
        if (isBurrowed) {
            return false; // Invulnerable while burrowed
        }

        // Detect vibration from attacker
        if (source.getEntity() != null) {
            lastVibrationPos = source.getEntity().position();
            vibrationAge = 0;
        }

        return super.hurt(source, amount);
    }

    // Getters for vibration tracking
    public Vec3 getLastVibrationPos() {
        return lastVibrationPos;
    }

    public boolean isSniffing() {
        return isSniffing;
    }

    public boolean isBurrowed() {
        return isBurrowed;
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);

        tag.putBoolean("IsBurrowed", isBurrowed);
        tag.putInt("BurrowTicks", burrowTicks);
        tag.putBoolean("IsSniffing", isSniffing);

        tag.putInt("SonicBoomCooldown", sonicBoomCooldown);
        tag.putInt("DarknessCooldown", darknessCooldown);
        tag.putInt("SniffCooldown", sniffCooldown);
        tag.putInt("BurrowCooldown", burrowCooldown);

        if (lastVibrationPos != null) {
            tag.putDouble("LastVibrationX", lastVibrationPos.x);
            tag.putDouble("LastVibrationY", lastVibrationPos.y);
            tag.putDouble("LastVibrationZ", lastVibrationPos.z);
            tag.putInt("VibrationAge", vibrationAge);
        }
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);

        isBurrowed = tag.getBoolean("IsBurrowed");
        burrowTicks = tag.getInt("BurrowTicks");
        isSniffing = tag.getBoolean("IsSniffing");

        sonicBoomCooldown = tag.getInt("SonicBoomCooldown");
        darknessCooldown = tag.getInt("DarknessCooldown");
        sniffCooldown = tag.getInt("SniffCooldown");
        burrowCooldown = tag.getInt("BurrowCooldown");

        if (tag.contains("LastVibrationX")) {
            lastVibrationPos = new Vec3(
                    tag.getDouble("LastVibrationX"),
                    tag.getDouble("LastVibrationY"),
                    tag.getDouble("LastVibrationZ")
            );
            vibrationAge = tag.getInt("VibrationAge");
        }
    }

    /**
     * Custom dimensions for Warden (tall and bulky)
     */
    @Override
    public EntityDimensions getDimensions(Pose pose) {
        if (isTransformed && isInPlayerForm()) {
            return EntityDimensions.scalable(0.6f, 1.8f); // Normal player size when disguised
        }
        return EntityDimensions.scalable(0.9f, 2.9f); // Warden size
    }
}