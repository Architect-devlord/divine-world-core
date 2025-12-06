package com.divineworld.entity.god;

import com.divineworld.ai.DWAIController;
import com.divineworld.core.DWBrainCapsule;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.particles.SimpleParticleType;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;
import java.util.UUID;

/**
 * Base class for all Divine World god-tier entities (AI-controllable).
 * Includes subclasses for each god in one file.
 */
public abstract class DWGodEntity extends Mob {

    protected DWAIController aiController;
    protected DWBrainCapsule brainCapsule;
    protected boolean inMortalDisguise = false;
    protected GodFormType godFormType;
    protected AuraColor auraColor;
    protected UUID godUUID;

    public DWGodEntity(EntityType<? extends Mob> type, Level level, GodFormType formType, AuraColor aura) {
        super(type, level);
        this.godFormType = formType;
        this.auraColor = aura;
        this.godUUID = UUID.randomUUID();
        if (!level.isClientSide()) initAI();
    }

    /** Initialize Divine World AI */
    protected void initAI() {
        this.brainCapsule = DWBrainCapsule.loadForEntity(this);
        this.aiController = new DWAIController(this, brainCapsule);
    }

    @Override
    public void tick() {
        super.tick();
        if (!level().isClientSide() && aiController != null) {
            aiController.tickAI((ServerLevel) level());
            handleAura((ServerLevel) level());
            tickGodAbilities((ServerLevel) level());
        }
    }
    
    protected void tickGodAbilities(ServerLevel level) {
        // Override in subclasses to add specific god abilities
    }

    /** Toggle god/mortal disguise form */
    public void toggleDisguiseForm() {
        inMortalDisguise = !inMortalDisguise;
        if (inMortalDisguise) enterMortalForm(); else exitMortalForm();
    }

    protected void enterMortalForm() {
        this.setCustomNameVisible(true);
        this.setCustomName(getDisguiseName());
        this.setInvisible(false);
        this.setGlowingTag(false);
        applyMortalAttributes();
    }

    protected void exitMortalForm() {
        this.setCustomNameVisible(false);
        this.setInvisible(false);
        this.setGlowingTag(true);
        applyGodAttributes();
    }

    protected void applyGodAttributes() {
        getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.MAX_HEALTH).setBaseValue(500.0D);
        getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE).setBaseValue(50.0D);
        setHealth(500.0F);
    }

    protected void applyMortalAttributes() {
        getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.MAX_HEALTH).setBaseValue(40.0D);
        getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE).setBaseValue(6.0D);
        setHealth(40.0F);
    }

    protected void handleAura(ServerLevel level) {
        if (!inMortalDisguise && auraColor != null) {
            Vec3 pos = this.position();
            level.sendParticles(auraColor.getParticleType(), pos.x, pos.y + 1.5, pos.z, 3, 0.3, 0.3, 0.3, 0.0);
        }
    }

    protected abstract String getDisguiseName();

    public boolean isInMortalDisguise() { return inMortalDisguise; }
    public GodFormType getGodFormType() { return godFormType; }
    public AuraColor getAuraColor() { return auraColor; }
    public DWAIController getAiController() { return aiController; }
    public DWBrainCapsule getBrainCapsule() { return brainCapsule; }
    public UUID getGodUUID() { return godUUID; }

    // ---------------- ENUMS ----------------
    public enum GodFormType {
        ENDER_DRAGON, WITHER, WARDEN, CREEKING, ELDER_GUARDIAN
    }

    public enum AuraColor {
        PURPLE(ParticleTypes.PORTAL),
        RED(ParticleTypes.FLAME),
        BLUE(ParticleTypes.SOUL),
        GREEN(ParticleTypes.HAPPY_VILLAGER),
        WHITE(ParticleTypes.CLOUD);

        private final SimpleParticleType particleType;
        AuraColor(SimpleParticleType type) { this.particleType = type; }
        public SimpleParticleType getParticleType() { return particleType; }
    }

    // ---------------- SUBCLASSES ----------------

    /** Ender Dragon God */
    public static class DWEnderDragonEntity extends DWGodEntity {
        public DWEnderDragonEntity(EntityType<? extends Mob> type, Level level) {
            super(type, level, GodFormType.ENDER_DRAGON, AuraColor.PURPLE);
        }
        @Override protected String getDisguiseName() { return "Mysterious Stranger"; }
        @Override protected void applyGodAttributes() {
            super.applyGodAttributes();
            getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.FLYING_SPEED).setBaseValue(1.5D);
        }
    }

    /** Wither God */
    public static class DWWitherEntity extends DWGodEntity {
        public DWWitherEntity(EntityType<? extends Mob> type, Level level) {
            super(type, level, GodFormType.WITHER, AuraColor.RED);
        }
        @Override protected String getDisguiseName() { return "Dark Wanderer"; }
        @Override
        protected void tickGodAbilities(ServerLevel level) {
            if (!inMortalDisguise && tickCount % 100 == 0) {
                Vec3 pos = this.position();
                level.explode(this, pos.x, pos.y, pos.z, 1.5F, Level.ExplosionInteraction.MOB);
            }
        }
    }

    /** Warden God */
    public static class DWWardenEntity extends DWGodEntity {
        public DWWardenEntity(EntityType<? extends Mob> type, Level level) {
            super(type, level, GodFormType.WARDEN, AuraColor.BLUE);
        }
        @Override protected String getDisguiseName() { return "Blind Hermit"; }
        @Override 
        protected void tickGodAbilities(ServerLevel level) {
            if (!inMortalDisguise && tickCount % 200 == 0) {
                level.playSound(null, this.blockPosition(), net.minecraft.sounds.SoundEvents.WARDEN_ROAR, 
                    net.minecraft.sounds.SoundSource.HOSTILE, 1.5F, 1.0F);
            }
        }
    }

    /** Creaking God (custom entity type) */
    public static class DWCreakingEntity extends DWGodEntity {
        public DWCreakingEntity(EntityType<? extends Mob> type, Level level) {
            super(type, level, GodFormType.CREEKING, AuraColor.GREEN);
        }
        @Override protected String getDisguiseName() { return "Wandering Sage"; }
        @Override
        protected void tickGodAbilities(ServerLevel level) {
            if (!inMortalDisguise && tickCount % 120 == 0) {
                level.sendParticles(ParticleTypes.GLOW, getX(), getY() + 1.2, getZ(), 
                    8, 0.4, 0.4, 0.4, 0.01);
            }
        }
    }

    /** Elder Guardian God */
    public static class DWElderGuardianEntity extends DWGodEntity {
        public DWElderGuardianEntity(EntityType<? extends Mob> type, Level level) {
            super(type, level, GodFormType.ELDER_GUARDIAN, AuraColor.WHITE);
        }
        @Override protected String getDisguiseName() { return "Old Fisherman"; }
        @Override
        protected void tickGodAbilities(ServerLevel level) {
            if (!inMortalDisguise && tickCount % 150 == 0) {
                level.playSound(null, blockPosition(), net.minecraft.sounds.SoundEvents.ELDER_GUARDIAN_CURSE,
                    net.minecraft.sounds.SoundSource.HOSTILE, 1.0F, 0.8F);
            }
        }
    }
}
