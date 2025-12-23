package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.IGodEntity;
import com.divineworld.client.entity.ModEntities;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.world.SimpleContainer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * AI Warden - God Entity
 *
 * Abilities:
 * - Sonic Boom (ranged attack, ignores armor)
 * - Darkness effect (blind nearby entities)
 * - Sniff (detect vibrations, track entities)
 * - Burrow (go underground temporarily)
 * - Transform into any mob/player while retaining abilities
 */
public class AIWarden extends Monster implements IGodEntity {

    private boolean isTransformed = false;
    private String transformedMobName = null;
    private SimpleContainer inventory;

    // Ability cooldowns
    private int sonicBoomCooldown = 0;
    private int darknessCooldown = 0;
    private int burrowCooldown = 0;

    // States
    private boolean isBurrowed = false;
    private int burrowTicks = 0;
    private boolean isSniffing = false;

    // Vibration detection
    private Vec3 lastVibrationPos = null;
    private int vibrationAge = 0;

    public AIWarden(EntityType<? extends Monster> type, Level level) {
        super(type, level);
        this.inventory = new SimpleContainer(36);
    }

    public AIWarden(Level level) {
        this(ModEntities.AI_WARDEN.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Monster.createMonsterAttributes()
                .add(Attributes.MAX_HEALTH, 500.0)
                .add(Attributes.MOVEMENT_SPEED, 0.3)
                .add(Attributes.ATTACK_DAMAGE, 30.0)
                .add(Attributes.ARMOR, 10.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 1.0)
                .add(Attributes.FOLLOW_RANGE, 64.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Cooldowns
        if (sonicBoomCooldown > 0) sonicBoomCooldown--;
        if (darknessCooldown > 0) darknessCooldown--;
        if (burrowCooldown > 0) burrowCooldown--;

        // Burrow mechanics
        if (isBurrowed) {
            burrowTicks++;

            // Invisible and invulnerable while burrowed
            setInvisible(true);
            setInvulnerable(true);
            this.noPhysics = true;
            this.setDeltaMovement(Vec3.ZERO);
            this.setPos(getX(), getY(), getZ());


            // Slowly sink into ground
            if (burrowTicks < 20) {
                setDeltaMovement(getDeltaMovement().add(0, -0.1, 0));
            }

            // Particles
            level().addParticle(ParticleTypes.SCULK_SOUL,
                    getX(), getY() + 1, getZ(),
                    0, 0, 0);

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

        // Raycast for target
        for (double d = 0; d < 30; d += 0.5) {
            Vec3 checkPos = startPos.add(lookVec.scale(d));

            // Check for entities
            level().getEntities(this, getBoundingBox().inflate(30)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != this) {
                    if (living.position().distanceTo(checkPos) < 1.0) {
                        // Direct damage (ignores armor)
                        living.hurt(damageSources().sonicBoom(this), 25.0f);

                        // Strong knockback
                        Vec3 direction = living.position().subtract(position()).normalize();
                        living.push(direction.x * 3, 1.0, direction.z * 3);
                    }
                }
            });

            // Visual beam
            level().addParticle(ParticleTypes.SONIC_BOOM,
                    checkPos.x, checkPos.y, checkPos.z,
                    0, 0, 0);
        }

        sonicBoomCooldown = 100; // 5 seconds
    }

    /**
     * Apply Darkness effect to nearby entities
     */
    private void applyDarkness() {
        if (darknessCooldown > 0) return;

        // Affect all entities in radius
        level().getEntities(this, getBoundingBox().inflate(20)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                // Apply darkness effect (blindness + limited vision)
                living.addEffect(new MobEffectInstance(
                        MobEffects.BLINDNESS, 300, 0, false, true
                ));

                living.addEffect(new MobEffectInstance(
                        MobEffects.DARKNESS, 300, 0, false, true
                ));
            }
        });

        // Visual effect
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
        isSniffing = true;

        // Detect all vibration sources (moving entities)
        level().getEntities(this, getBoundingBox().inflate(32)).forEach(entity -> {
            if (entity instanceof LivingEntity && entity != this) {
                Vec3 entityVel = entity.getDeltaMovement();

                // If entity is moving, detect it
                if (entityVel.length() > 0.01) {
                    lastVibrationPos = entity.position();
                    vibrationAge = 0;

                    // Visual indicator
                    level().addParticle(ParticleTypes.SCULK_CHARGE_POP,
                            entity.getX(), entity.getY() + 1, entity.getZ(),
                            0, 0, 0);
                }
            }
        });

        // Can't be used constantly
        new Thread(() -> {
            try {
                Thread.sleep(2000);
                isSniffing = false;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }).start();
    }

    /**
     * Burrow underground (become invulnerable, invisible)
     */
    private void burrowUnderground() {
        if (burrowCooldown > 0 || isBurrowed) return;

        isBurrowed = true;
        burrowTicks = 0;

        // Particle effect
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

        this.noPhysics = false;
        this.setPos(getX(), getY(), getZ());

        setInvisible(false);
        setInvulnerable(false);



        // Emergence effect - damage nearby entities
        level().getEntities(this, getBoundingBox().inflate(5)).forEach(entity -> {
            if (entity instanceof LivingEntity living && entity != this) {
                living.hurt(damageSources().mobAttack(this), 20.0f);

                Vec3 direction = living.position().subtract(position()).normalize();
                living.push(direction.x * 2, 1.5, direction.z * 2);
            }
        });

        // Particles
        for (int i = 0; i < 100; i++) {
            level().addParticle(ParticleTypes.SCULK_CHARGE_POP,
                    getX() + (random.nextDouble() - 0.5) * 4,
                    getY(),
                    getZ() + (random.nextDouble() - 0.5) * 4,
                    0, 0.5, 0);
        }
    }

    @Override
    public void toggleFlight(boolean enable) {
        // Warden doesn't fly, but can burrow
    }

    private void transformInto(String mobName) {
        if (isTransformed) {
            revertTransformation();
        }

        isTransformed = true;
        transformedMobName = mobName;
        refreshDimensions();

        // Transformation particles
        for (int i = 0; i < 50; i++) {
            level().addParticle(ParticleTypes.SCULK_SOUL,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY() + random.nextDouble() * 3,
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0.3, 0);
        }
    }

    private void revertTransformation() {
        isTransformed = false;
        transformedMobName = null;
        refreshDimensions();
    }

    @Override
    public void addPlayerInventory() {
        // Already has inventory
    }

    @Override
    public boolean isInPlayerForm() {
        return isTransformed && "player".equals(transformedMobName);
    }

    @Override
    public String getGodType() {
        return "warden";
    }

    public SimpleContainer getInventory() {
        return inventory;
    }

    public Vec3 getLastVibrationPos() {
        return lastVibrationPos;
    }

    @Override
    public EntityDimensions getDimensions(Pose pose) {
        if (isTransformed) {
            if ("player".equals(transformedMobName)) {
                return EntityDimensions.scalable(0.6f, 1.8f);
            }
            return EntityDimensions.scalable(1.0f, 1.0f);
        }
        return EntityDimensions.scalable(0.9f, 2.9f); // Warden size
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsTransformed", isTransformed);
        tag.putBoolean("IsBurrowed", isBurrowed);

        if (transformedMobName != null) {
            tag.putString("TransformedMob", transformedMobName);
        }

        ListTag list = inventory.createTag();
        tag.put("Inventory", list);

    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isTransformed = tag.getBoolean("IsTransformed");
        isBurrowed = tag.getBoolean("IsBurrowed");

        if (tag.contains("TransformedMob")) {
            transformedMobName = tag.getString("TransformedMob");
        }

        if (tag.contains("Inventory")) {
            inventory.fromTag(tag.getList("Inventory", 10)); // 10 = CompoundTag type
        }
    }
}