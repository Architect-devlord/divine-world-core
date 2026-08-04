package com.divineworld.entity.gods;

import com.divineworld.entity.ModEntities;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.ai.attributes.AttributeSupplier;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

/**
 * AI Oracle - Wise God Entity
 * NOW EXTENDS BaseGodEntity for full player capabilities
 *
 * Abilities:
 * - Wisdom Aura (buff nearby allies)
 * - Foresight (predict danger, sense entities)
 * - Teleportation (short-range teleport)
 * - Healing Wave (heal nearby allies)
 * - Knowledge Beam (damage based on intelligence)
 * - Flight
 * - Full player abilities (mining, crafting, using items, etc.)
 */
public class AIOracle extends BaseGodEntity {

    // Ability cooldowns
    private int wisdomAuraCooldown = 0;
    private int foresightCooldown = 0;
    private int teleportCooldown = 0;
    private int healingCooldown = 0;
    private int knowledgeBeamCooldown = 0;

    // States
    private boolean isFlying = true;
    private boolean wisdomAuraActive = false;
    private int wisdomAuraTicks = 0;

    // Foresight data
    private Vec3 predictedDangerPos = null;
    private int dangerPredictionAge = 0;

    public AIOracle(EntityType<? extends Player> type, Level level) {
        super(type, level);
        setNoGravity(true);
    }

    public AIOracle(Level level) {
        this(ModEntities.AI_ORACLE.get(), level);
    }

    public static AttributeSupplier.Builder createAttributes() {
        return Player.createAttributes()
                .add(Attributes.MAX_HEALTH, 150.0)
                .add(Attributes.MOVEMENT_SPEED, 0.3)
                .add(Attributes.ATTACK_DAMAGE, 8.0)
                .add(Attributes.ARMOR, 2.0)
                .add(Attributes.KNOCKBACK_RESISTANCE, 0.5)
                .add(Attributes.FLYING_SPEED, 0.4)
                .add(Attributes.FOLLOW_RANGE, 100.0);
    }

    @Override
    public void tick() {
        super.tick();

        // Cooldowns
        if (wisdomAuraCooldown > 0) wisdomAuraCooldown--;
        if (foresightCooldown > 0) foresightCooldown--;
        if (teleportCooldown > 0) teleportCooldown--;
        if (healingCooldown > 0) healingCooldown--;
        if (knowledgeBeamCooldown > 0) knowledgeBeamCooldown--;

        // Wisdom Aura effect
        if (wisdomAuraActive) {
            wisdomAuraTicks++;

            // Buff nearby allies
            level().getEntities(this, getBoundingBox().inflate(15)).forEach(entity -> {
                if (entity instanceof LivingEntity living && !isEnemy(living)) {
                    // Apply beneficial effects
                    living.addEffect(new MobEffectInstance(
                            MobEffects.REGENERATION, 40, 0, true, false
                    ));
                    living.addEffect(new MobEffectInstance(
                            MobEffects.DAMAGE_RESISTANCE, 40, 0, true, false
                    ));
                }
            });

            // Particles
            if (random.nextFloat() < 0.3f) {
                double angle = random.nextDouble() * Math.PI * 2;
                double radius = 5 + random.nextDouble() * 10;
                double x = getX() + Math.cos(angle) * radius;
                double z = getZ() + Math.sin(angle) * radius;

                level().addParticle(ParticleTypes.ENCHANT,
                        x, getY() + 1, z,
                        0, 0.1, 0);
            }

            // Aura lasts 10 seconds
            if (wisdomAuraTicks >= 200) {
                wisdomAuraActive = false;
                wisdomAuraTicks = 0;
            }
        }

        // Foresight danger prediction aging
        if (predictedDangerPos != null) {
            dangerPredictionAge++;
            if (dangerPredictionAge > 100) {
                predictedDangerPos = null;
            }
        }

        // Ambient particles
        if (random.nextFloat() < 0.15f) {
            level().addParticle(ParticleTypes.ENCHANTED_HIT,
                    getX() + (random.nextDouble() - 0.5),
                    getY() + random.nextDouble() * 2,
                    getZ() + (random.nextDouble() - 0.5),
                    0, 0.05, 0);
        }
    }

    @Override
    public void useAbility(String abilityName, Object... params) {
        switch (abilityName) {
            case "wisdom_aura" -> activateWisdomAura();
            case "foresight" -> useForesight();
            case "teleport" -> teleportToLocation(params);
            case "healing_wave" -> useHealingWave();
            case "knowledge_beam" -> useKnowledgeBeam(params);
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
     * Activate Wisdom Aura - buffs nearby allies
     */
    private void activateWisdomAura() {
        if (wisdomAuraCooldown > 0) return;

        wisdomAuraActive = true;
        wisdomAuraTicks = 0;
        wisdomAuraCooldown = 600; // 30 seconds

        // Initial burst effect
        for (int i = 0; i < 50; i++) {
            double angle = (Math.PI * 2 * i) / 50;
            double radius = 10;
            double x = getX() + Math.cos(angle) * radius;
            double z = getZ() + Math.sin(angle) * radius;

            level().addParticle(ParticleTypes.ENCHANT,
                    x, getY() + 1, z,
                    0, 0.3, 0);
        }
    }

    /**
     * Foresight - predict danger and sense all entities
     */
    private void useForesight() {
        if (foresightCooldown > 0) return;

        // Find hostile entities
        level().getEntities(this, getBoundingBox().inflate(50)).forEach(entity -> {
            if (entity instanceof LivingEntity living && isEnemy(living)) {
                // Predict where enemy will be
                Vec3 predictedPos = living.position().add(
                        living.getDeltaMovement().scale(20)
                );

                predictedDangerPos = predictedPos;
                dangerPredictionAge = 0;

                // Visual indicator at predicted location
                for (int i = 0; i < 20; i++) {
                    level().addParticle(ParticleTypes.GLOW,
                            predictedPos.x + (random.nextDouble() - 0.5),
                            predictedPos.y + (random.nextDouble() - 0.5),
                            predictedPos.z + (random.nextDouble() - 0.5),
                            0, 0, 0);
                }
            }
        });

        foresightCooldown = 100; // 5 seconds
    }

    /**
     * Teleport to target location
     */
    private void teleportToLocation(Object... params) {
        if (teleportCooldown > 0) return;

        Vec3 targetPos;

        if (params.length >= 3) {
            // Specific coordinates
            double x = (double) params[0];
            double y = (double) params[1];
            double z = (double) params[2];
            targetPos = new Vec3(x, y, z);
        } else {
            // Teleport in look direction
            Vec3 lookVec = getLookAngle();
            targetPos = position().add(lookVec.scale(20));
        }

        // Particles at start location
        for (int i = 0; i < 30; i++) {
            level().addParticle(ParticleTypes.PORTAL,
                    getX(), getY() + 1, getZ(),
                    (random.nextDouble() - 0.5) * 0.5,
                    random.nextDouble() * 0.5,
                    (random.nextDouble() - 0.5) * 0.5);
        }

        // Teleport
        teleportTo(targetPos.x, targetPos.y, targetPos.z);

        // Particles at end location
        for (int i = 0; i < 30; i++) {
            level().addParticle(ParticleTypes.PORTAL,
                    getX(), getY() + 1, getZ(),
                    (random.nextDouble() - 0.5) * 0.5,
                    random.nextDouble() * 0.5,
                    (random.nextDouble() - 0.5) * 0.5);
        }

        teleportCooldown = 60; // 3 seconds
    }

    /**
     * Healing Wave - heal nearby allies
     */
    private void useHealingWave() {
        if (healingCooldown > 0) return;

        // Heal all nearby entities (including self)
        level().getEntities(this, getBoundingBox().inflate(20)).forEach(entity -> {
            if (entity instanceof LivingEntity living && !isEnemy(living)) {
                living.heal(10.0f);

                // Healing particles
                for (int i = 0; i < 10; i++) {
                    level().addParticle(ParticleTypes.HEART,
                            living.getX(),
                            living.getY() + 1,
                            living.getZ(),
                            (random.nextDouble() - 0.5) * 0.1,
                            random.nextDouble() * 0.2,
                            (random.nextDouble() - 0.5) * 0.1);
                }
            }
        });

        healingCooldown = 200; // 10 seconds
    }

    /**
     * Knowledge Beam - damage based on wisdom
     */
    private void useKnowledgeBeam(Object... params) {
        if (knowledgeBeamCooldown > 0) return;

        Vec3 lookVec = getLookAngle();
        Vec3 startPos = position().add(0, getEyeHeight(), 0);

        // Beam travels 40 blocks
        for (double d = 0; d < 40; d += 0.5) {
            Vec3 beamPos = startPos.add(lookVec.scale(d));

            // Damage entities in beam path
            level().getEntities(this, getBoundingBox().inflate(40)).forEach(entity -> {
                if (entity instanceof LivingEntity living && entity != this) {
                    if (living.position().distanceTo(beamPos) < 1.0) {
                        // Damage ignores armor (wisdom-based)
                        living.hurt(damageSources().magic(), 12.0f);

                        // Slow effect
                        living.addEffect(new MobEffectInstance(
                                MobEffects.MOVEMENT_SLOWDOWN, 60, 1
                        ));
                    }
                }
            });

            // Visual beam
            level().addParticle(ParticleTypes.END_ROD,
                    beamPos.x, beamPos.y, beamPos.z,
                    0, 0, 0);
        }

        knowledgeBeamCooldown = 80; // 4 seconds
    }

    private boolean isEnemy(LivingEntity entity) {
        // Simple check - in production, use proper team/faction system
        return entity instanceof Monster && entity != this;
    }

    @Override
    public void toggleFlight(boolean enable) {
        isFlying = enable;
        setNoGravity(enable);
    }

    @Override
    public String getGodType() {
        return "oracle";
    }

    @Override
    public float getScale() {
        return 1.0f; // Human-like size
    }

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        tag.putBoolean("IsFlying", isFlying);
        tag.putBoolean("WisdomAuraActive", wisdomAuraActive);
        tag.putInt("WisdomAuraTicks", wisdomAuraTicks);
        tag.putInt("WisdomAuraCooldown", wisdomAuraCooldown);
        tag.putInt("ForesightCooldown", foresightCooldown);
        tag.putInt("TeleportCooldown", teleportCooldown);
        tag.putInt("HealingCooldown", healingCooldown);
        tag.putInt("KnowledgeBeamCooldown", knowledgeBeamCooldown);
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        isFlying = tag.getBoolean("IsFlying");
        wisdomAuraActive = tag.getBoolean("WisdomAuraActive");
        wisdomAuraTicks = tag.getInt("WisdomAuraTicks");
        wisdomAuraCooldown = tag.getInt("WisdomAuraCooldown");
        foresightCooldown = tag.getInt("ForesightCooldown");
        teleportCooldown = tag.getInt("TeleportCooldown");
        healingCooldown = tag.getInt("HealingCooldown");
        knowledgeBeamCooldown = tag.getInt("KnowledgeBeamCooldown");
    }
}