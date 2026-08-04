package com.divineworld.entity.gods;

import com.divineworld.entity.gods.IGodEntity;
import com.mojang.authlib.GameProfile;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.animal.Pig;
import net.minecraft.world.entity.animal.camel.Camel;
import net.minecraft.world.entity.animal.horse.AbstractHorse;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.monster.Strider;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.vehicle.AbstractMinecart;
import net.minecraft.world.entity.vehicle.Boat;
import net.minecraft.world.item.*;
import net.minecraft.world.item.enchantment.EnchantmentHelper;
import net.minecraft.world.level.Level;
import net.minecraft.world.phys.Vec3;

import software.bernie.geckolib.animatable.GeoEntity;
import software.bernie.geckolib.core.animatable.instance.AnimatableInstanceCache;
import software.bernie.geckolib.core.animation.*;
import software.bernie.geckolib.core.animation.AnimationState;
import software.bernie.geckolib.core.object.PlayState;
import software.bernie.geckolib.util.GeckoLibUtil;

import java.util.UUID;

/**
 * Base God Entity - FULLY FIXED VERSION
 * Extends Player to get ALL player mechanics including inventory
 * Uses Player's Inventory class instead of SimpleContainer
 *
 * FIX (humanoid form / GodBodyGeoRenderer): implements GeoEntity so
 * GodBodyGeoRenderer<T extends BaseGodEntity> (which extends
 * GeoEntityRenderer<T extends LivingEntity & GeoAnimatable>) can accept
 * any concrete god subclass as its type parameter.  GeoAnimatable is
 * satisfied via GeoEntity.  The registerControllers() override below covers
 * all shared animation names (walk/run/idle/swim/sneak/hit/mount from the
 * standard player movement set, PLUS god ability names: attack, burrow,
 * tentacles_out …) so the same trigger calls work for the boss body AND
 * the humanoid puppet; god_*.animation.json provides humanoid keyframes
 * for each of those same names.
 */
public abstract class BaseGodEntity extends Player implements IGodEntity, GeoEntity {

    // GeckoLib — one cache per ENTITY INSTANCE, not per class
    private final AnimatableInstanceCache geoCache = GeckoLibUtil.createInstanceCache(this);

    // ==================== ANIMATION CACHE ====================
    // Named RawAnimation constants for the humanoid base/ability controllers below.
    // Animation names must match the keyframe names in each god's god_*.animation.json.

    private static final RawAnimation DEATH            = RawAnimation.begin().thenPlay("death");
    private static final RawAnimation RIPTIDE          = RawAnimation.begin().thenLoop("riptide");
    private static final RawAnimation HURT             = RawAnimation.begin().thenPlay("hurt");
    /** NOTE: for smoother blending, consider removing this from the base controller entirely
     *  and instead triggering it from the ability_controller (abilityController.triggerAnim(
     *  "ability_controller", "hurt")) from an override of actuallyHurt(...). Handling it here,
     *  in the base state machine, is simpler and still correct, just a slightly harder cut. */

    private static final RawAnimation SLEEP            = RawAnimation.begin().thenLoop("sleep");

    private static final RawAnimation FROZEN           = RawAnimation.begin().thenLoop("frozen_freeze");
    private static final RawAnimation FROZEN_SHAKE     = RawAnimation.begin().thenLoop("frozen_shake");

    private static final RawAnimation BURNING          = RawAnimation.begin().thenLoop("burning");
    private static final RawAnimation LEVITATION       = RawAnimation.begin().thenLoop("levitation");

    private static final RawAnimation ELYTRA           = RawAnimation.begin().thenLoop("elytra_fly");
    private static final RawAnimation SWIM             = RawAnimation.begin().thenLoop("swim");
    private static final RawAnimation WATER_IDLE       = RawAnimation.begin().thenLoop("water_idle");
    private static final RawAnimation CRAWL            = RawAnimation.begin().thenLoop("crawl");

    private static final RawAnimation CLIMB            = RawAnimation.begin().thenLoop("climb_moving");
    private static final RawAnimation CLIMB_IDLE        = RawAnimation.begin().thenLoop("climb_idle");

    private static final RawAnimation BOAT             = RawAnimation.begin().thenLoop("ride_boat");
    private static final RawAnimation HORSE            = RawAnimation.begin().thenLoop("ride_horse");
    private static final RawAnimation CAMEL            = RawAnimation.begin().thenLoop("ride_camel");
    private static final RawAnimation MINECART         = RawAnimation.begin().thenLoop("ride_minecart");
    private static final RawAnimation RIDE_GENERIC      = RawAnimation.begin().thenLoop("ride_generic");

    private static final RawAnimation CROSSBOW_CHARGE  = RawAnimation.begin().thenLoop("crossbow_charge");
    private static final RawAnimation CROSSBOW_HOLD    = RawAnimation.begin().thenLoop("crossbow_hold");

    private static final RawAnimation BOW              = RawAnimation.begin().thenLoop("bow_pull");
    private static final RawAnimation SPEAR            = RawAnimation.begin().thenLoop("spear_aim");
    private static final RawAnimation SHIELD           = RawAnimation.begin().thenLoop("shield_block");
    private static final RawAnimation SPYGLASS         = RawAnimation.begin().thenLoop("spyglass_look");
    private static final RawAnimation HORN             = RawAnimation.begin().thenLoop("horn_blow");
    private static final RawAnimation BRUSH            = RawAnimation.begin().thenLoop("brushing");
    private static final RawAnimation EAT              = RawAnimation.begin().thenLoop("eat");

    private static final RawAnimation ATTACK           = RawAnimation.begin().thenPlay("attack");

    private static final RawAnimation JUMP             = RawAnimation.begin().thenPlay("jump");
    private static final RawAnimation FALL             = RawAnimation.begin().thenLoop("fall");

    private static final RawAnimation RUN              = RawAnimation.begin().thenLoop("run");
    private static final RawAnimation WALK             = RawAnimation.begin().thenLoop("walk");
    private static final RawAnimation SNEAK_WALK       = RawAnimation.begin().thenLoop("sneak_walk");

    private static final RawAnimation IDLE             = RawAnimation.begin().thenLoop("idle");
    private static final RawAnimation SNEAK_IDLE       = RawAnimation.begin().thenLoop("sneak_idle");

    // Transformation state
    protected boolean isTransformed = false;
    protected String transformedMobName = null;

    // NOTE: useItem / useItemRemaining are likewise NOT redeclared here for the same reason
    // attackStrengthTicker isn't (see note below) — LivingEntity already declares both
    // (protected). They were previously shadowed here too, and are moot now anyway since this
    // class no longer has any code path that starts an item-use (see ACTION API REMOVED below).
    // canMineBlocks/canPlaceBlocks/canUseItems/canCraft flags were removed along with the
    // methods that read them (mineBlock/placeBlock/useItem/craftItem) — they had nothing left
    // to gate.

    // NOTE: attackStrengthTicker is intentionally NOT redeclared here. LivingEntity already
    // declares it (protected), and Player.tick() -> LivingEntity.tick() increments
    // `this.attackStrengthTicker` directly every tick. A local `protected int
    // attackStrengthTicker;` field here would SHADOW that inherited field rather than share it:
    // super.tick()'s increment would update the inherited slot, while every method in this class
    // (getAttackStrengthScale, resetAttackStrengthTicker, save/load) would read/write a second,
    // never-incremented field of the same name. That was happening here previously — attack
    // cooldown and critical-hit timing were silently broken because the field was shadowed.
    // Removed the redeclaration so `this.attackStrengthTicker` everywhere in this class resolves
    // to the one real, inherited field that Player/LivingEntity's tick() maintains.

    // NOTE: no separate Inventory field here either, for the exact same reason. Player already
    // constructs its own real inventory (`private final Inventory inventory = new Inventory
    // (this);`) the moment super() runs — that field initializer fires regardless of what this
    // subclass's constructor does. A second `godInventory` here was never necessary; it was a
    // parallel, disconnected inventory that this class then had to keep re-pointing every
    // Player method at by hand. Every method below now uses whatever Player/LivingEntity
    // already provide, which talk to the real (single) inventory directly — so any inventory-
    // related method Mojang adds to Player in a future update works here automatically, with
    // nothing to maintain.

    /**
     * FIXED: Proper constructor with GameProfile
     */
    public BaseGodEntity(EntityType<? extends Player> type, Level level) {
        super(level, BlockPos.ZERO, 0.0F, createGodProfile());
    }

    /**
     * Create a GameProfile for god entities
     */
    private static GameProfile createGodProfile() {
        return new GameProfile(UUID.randomUUID(), "GodEntity");
    }

    @Override
    public void tick() {
        super.tick();
        // FIX M-06: do NOT increment attackStrengthTicker here.
        // Player.tick() already calls tickAttackStrength() which does ++attackStrengthTicker.
        // A second increment here doubled the recharge speed, making every second
        // swing a premature critical hit.

        // No manual inventory tick needed either — Player.aiStep() (called via super.tick())
        // already does `this.inventory.tick()` on its own real inventory, which is now the
        // one and only inventory this entity has.
    }

    // ==================== ACTION API REMOVED ====================
    // mineBlock/placeBlock/useItem(+startUsingItem/completeUsingItem)/throwSnowball/
    // throwEgg/throwEnderPearl/throwExperienceBottle/shootArrow/findArrow/useFlintAndSteel/
    // launchFirework/getTargetBlock were removed here. This entity is a no-AI, position-
    // synced puppet body (see GodControlHandler) — the real acting entity is the invisible
    // ServerPlayer, which already gets correct mining/placing/item-use/firing behavior for
    // free from vanilla ServerPlayerGameMode over its real network connection. Reimplementing
    // it a second time here on the no-AI body was dead weight nothing ever called.


    // ==================== INVENTORY MANAGEMENT ====================
    // getMainHandItem/setItemInHand/getItemInHand/getOffhandItem/getItemBySlot/setItemSlot/
    // getInventory/addItem are NOT redeclared here at all anymore. Player already implements
    // every one of them against its own real inventory, and that's now the only inventory this
    // entity has — so all of these just work, including things this class never had to
    // reimplement in the first place, like setItemSlot()'s onEquipItem() call (equip sound +
    // GameEvent.EQUIP) and verifyEquippedItem() (component tag verification), both of which the
    // old override quietly skipped.

    public void setOffhandItem(ItemStack stack) {
        this.setItemSlot(EquipmentSlot.OFFHAND, stack);
    }

    public void selectHotbarSlot(int slot) {
        if (slot >= 0 && slot < 9) {
            this.getInventory().selected = slot;
        }
    }

    public void dropItem(ItemStack stack) {
        if (stack.isEmpty()) return;
        // Player.drop(stack, dropAround, includeThrowerName) already computes the exact same
        // eye-height/pitch/yaw toss trajectory that used to be hand-rolled here — reuse it
        // instead of maintaining a second copy of the same math.
        this.drop(stack, false, true);
    }

    public void dropHeldItem() {
        ItemStack held = getMainHandItem();
        if (!held.isEmpty()) {
            dropItem(held.split(1));
        }
    }

    // ==================== HELPER METHODS ====================

    @Override
    public boolean isCreative() {
        return false; // God entities work like survival players
    }

    // onItemBroke() was removed — LivingEntity.broadcastBreakEvent(InteractionHand) already
    // broadcasts the proper ENTITY_EVENT (break sound + break particles, client-synced)
    // through the normal handleEntityEvent() pipeline; the manual playSound()-only version
    // here was a weaker duplicate of that. The one call site below now calls
    // broadcastBreakEvent(InteractionHand.MAIN_HAND) directly.

    // getAttackStrengthScale(float) and resetAttackStrengthTicker() were removed — Player's
    // own implementations are byte-for-byte identical to what was here (same formula, same
    // inherited attackStrengthTicker field), so this class now just inherits them.

    // NOTE ON getCurrentItemAttackStrengthDelay(): Player's own version is
    // `(float)(1.0D / getAttributeValue(ATTACK_SPEED) * 20.0D)` with no empty-hand special
    // case, and no (int) truncation. This class's version below adds a "return 4 for empty
    // hand" branch and truncates the real formula to an int, which is a precision bug on top
    // of a deliberate behavior change. Left as-is for now since removing it changes bare-fist
    // attack timing — flagging rather than silently deleting.
    public float getCurrentItemAttackStrengthDelay() {
        ItemStack mainHand = getMainHandItem();
        if (mainHand.isEmpty()) {
            return 4; // Default punch speed
        }
        return (int)(20.0 / getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_SPEED));
    }

    // ==================== TRANSFORMATION ====================

    protected void transformInto(String mobName) {
        if (isTransformed) {
            revertTransformation();
        }

        isTransformed = true;
        transformedMobName = mobName;
        refreshDimensions();

        spawnTransformParticles();
    }

    protected void revertTransformation() {
        isTransformed = false;
        transformedMobName = null;
        refreshDimensions();

        spawnTransformParticles();
    }

    protected void spawnTransformParticles() {
        // Default portal particles
        for (int i = 0; i < 50; i++) {
            level().addParticle(ParticleTypes.PORTAL,
                    getX() + (random.nextDouble() - 0.5) * 2,
                    getY() + random.nextDouble() * 2,
                    getZ() + (random.nextDouble() - 0.5) * 2,
                    0, 0.3, 0);
        }
    }

    @Override
    public boolean isInPlayerForm() {
        return isTransformed && "player".equals(transformedMobName);
    }

    // ==================== ATTACK MECHANICS ====================

    public void attackEntity(Entity target) {
        if (!target.isAttackable()) return;
        if (target.skipAttackInteraction(this)) return;

        float damage = (float)getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_DAMAGE);

        // Enchantment bonus
        if (target instanceof LivingEntity living) {
            damage += EnchantmentHelper.getDamageBonus(getMainHandItem(), living.getMobType());
        }

        // Attack strength scale
        float attackStrength = getAttackStrengthScale(0.5F);
        damage *= 0.2F + attackStrength * attackStrength * 0.8F;

        if (damage > 0.0F) {
            // Knockback
            int knockback = EnchantmentHelper.getKnockbackBonus(this);

            // Critical hit check
            boolean isCritical = attackStrength > 0.9F && !onGround() &&
                    !isInWater() && !hasEffect(net.minecraft.world.effect.MobEffects.BLINDNESS);

            if (isCritical) {
                damage *= 1.5F;

                // Critical particles
                for (int i = 0; i < 10; i++) {
                    level().addParticle(ParticleTypes.CRIT,
                            target.getX() + (random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (random.nextDouble() - 0.5),
                            (random.nextDouble() - 0.5) * 0.2,
                            random.nextDouble() * 0.2,
                            (random.nextDouble() - 0.5) * 0.2);
                }

                level().playSound(null, getX(), getY(), getZ(),
                        SoundEvents.PLAYER_ATTACK_CRIT, SoundSource.PLAYERS,
                        1.0f, 1.0f);
            }

            // Apply damage
            boolean hurt = target.hurt(damageSources().mobAttack(this), damage);

            if (hurt) {
                // Apply knockback
                if (knockback > 0 && target instanceof LivingEntity living) {
                    living.knockback(
                            (double)((float)knockback * 0.5F),
                            (double)net.minecraft.util.Mth.sin(getYRot() * ((float)Math.PI / 180F)),
                            (double)(-net.minecraft.util.Mth.cos(getYRot() * ((float)Math.PI / 180F)))
                    );
                    setDeltaMovement(getDeltaMovement().multiply(0.6D, 1.0D, 0.6D));
                }

                // Fire aspect
                int fireAspect = EnchantmentHelper.getFireAspect(this);
                if (fireAspect > 0) {
                    target.setSecondsOnFire(fireAspect * 4);
                }

                // Apply enchantment effects
                if (target instanceof LivingEntity living) {
                    EnchantmentHelper.doPostHurtEffects(living, this);
                }
                EnchantmentHelper.doPostDamageEffects(this, target);

                // Damage weapon
                ItemStack weapon = getMainHandItem();
                if (!weapon.isEmpty() && target instanceof LivingEntity living) {
                    weapon.hurtEnemy(living, this);
                    if (weapon.isEmpty()) {
                        setItemInHand(InteractionHand.MAIN_HAND, ItemStack.EMPTY);
                        this.broadcastBreakEvent(InteractionHand.MAIN_HAND);
                    }
                }

                // Play attack sound
                level().playSound(null, getX(), getY(), getZ(),
                        attackStrength > 0.9F ? SoundEvents.PLAYER_ATTACK_STRONG : SoundEvents.PLAYER_ATTACK_WEAK,
                        SoundSource.PLAYERS, 1.0f, 1.0f);
            } else {
                // Attack failed sound
                level().playSound(null, getX(), getY(), getZ(),
                        SoundEvents.PLAYER_ATTACK_NODAMAGE, SoundSource.PLAYERS,
                        1.0f, 1.0f);
            }
        }

        resetAttackStrengthTicker();
    }

    // interactOn/interactWithBlock/craftItem(+hasIngredient/consumeIngredient) removed —
    // same reasoning as the mining/placement/item-use block above: the invisible
    // ServerPlayer already handles right-click interaction and the crafting-grid UI
    // natively over its real connection (see ActionExecutor.executeInventoryAction).


    // ==================== PERSISTENCE ====================

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);
        // super.addAdditionalSaveData() (Player's own) already writes the "Inventory" list from
        // its real inventory — which is now the only inventory this entity has — so there's
        // nothing left to save here beyond this class's own extra state.

        tag.putBoolean("IsTransformed", isTransformed);
        tag.putInt("AttackStrengthTicker", attackStrengthTicker);

        if (transformedMobName != null) {
            tag.putString("TransformedMob", transformedMobName);
        }
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);
        // Likewise, super.readAdditionalSaveData() already loads "Inventory" into the real
        // inventory.

        isTransformed = tag.getBoolean("IsTransformed");
        attackStrengthTicker = tag.getInt("AttackStrengthTicker");

        if (tag.contains("TransformedMob")) {
            transformedMobName = tag.getString("TransformedMob");
        }
    }

    @Override
    public void addPlayerInventory() {
        // No-op — Player already constructs and manages its own real inventory the moment
        // super() runs; there's no separate inventory left to set up here.
    }

    // ==================== ABSTRACT METHODS - Must be implemented by subclasses ====================

    @Override
    public abstract String getGodType();

    @Override
    public abstract void useAbility(String abilityName, Object... params);

    @Override
    public abstract void toggleFlight(boolean enable);

    // ==================== GECKOLIB — GeoEntity (humanoid form) ====================

    /**
     * Shared animation controllers for the humanoid form.
     *
     * Two controllers — same split as AICreakingEntity (DWClientBot):
     *
     *   base_controller    (5-tick blend)  — looping movement/state machine.
     *     Covers the full player animation set that vanilla PlayerRenderer normally
     *     drives natively (death, riptide, hurt, sleep, freezing, burning, levitation,
     *     elytra, swim, crawl, climb, item-use poses, mounts, attack swing, jump/fall,
     *     walk/run/sneak/idle). GodBodyGeoRenderer needs all of these as explicit
     *     keyframes because GeckoLib drives geometry from scratch here — nothing is
     *     inherited "for free" the way it would be for a real client-rendered player.
     *
     *   ability_controller (0-tick snap)   — one-shot triggered ability animations.
     *     All god ability names are registered here so useAbility() calls in the
     *     Python backend fire the same animation regardless of which form is active.
     *     Subclasses can add additional god-specific triggers by overriding
     *     registerExtraAbilityTriggers() below.
     *
     * Animation names in god_*.animation.json MUST match these keys exactly.
     */
    @Override
    public void registerControllers(AnimatableManager.ControllerRegistrar controllers) {
        controllers.add(new AnimationController<>(this, "base_controller", 5,
                this::baseHumanoidAnimController));

        AnimationController<BaseGodEntity> abilityController =
                new AnimationController<>(this, "ability_controller", 0,
                        state -> PlayState.CONTINUE)
                        .triggerableAnim("attack",         RawAnimation.begin().then("attack",         Animation.LoopType.PLAY_ONCE))
                        .triggerableAnim("hit",            RawAnimation.begin().then("hit",            Animation.LoopType.PLAY_ONCE))
                        .triggerableAnim("mount",          RawAnimation.begin().then("mount",          Animation.LoopType.PLAY_ONCE));
        registerExtraAbilityTriggers(abilityController);
        controllers.add(abilityController);
    }

    /**
     * Base movement/state machine, checked in priority order every base_controller tick.
     * Subclasses can short-circuit any of this via playCustomAnimation() below (e.g. Creaking
     * ceiling-crawl, Warden sniff, EnderDragon hovering glide) before the shared logic runs.
     */
    protected <E extends BaseGodEntity> PlayState baseHumanoidAnimController(
            AnimationState<E> state) {

        if (playCustomAnimation(state)) {
            return PlayState.CONTINUE;
        }

        // ========== 1. Absolute critical overrides ==========
        if (this.isDeadOrDying()) {
            return state.setAndContinue(DEATH);
        }

        // Riptide trident spin attack
        if (this.isAutoSpinAttack()) {
            return state.setAndContinue(RIPTIDE);
        }

        // Hurt flash — see NOTE on the HURT constant re: smoother triggered-anim alternative
        if (this.hurtTime > 0) {
            return state.setAndContinue(HURT);
        }

        if (this.isSleeping()) {
            return state.setAndContinue(SLEEP);
        }

        // Powder snow freeze
        if (this.isFullyFrozen()) {
            return state.setAndContinue(FROZEN);
        } else if (this.isFreezing()) {
            return state.setAndContinue(FROZEN_SHAKE);
        }

        if (this.isOnFire()) {
            return state.setAndContinue(BURNING);
        }

        if (this.hasEffect(MobEffects.LEVITATION)) {
            return state.setAndContinue(LEVITATION);
        }

        // ========== 2. Displaced locomotion ==========
        if (this.isFallFlying()) {
            return state.setAndContinue(ELYTRA);
        }

        if (this.isSwimming() || (this.isInWater() && state.isMoving())) {
            return state.setAndContinue(SWIM);
        }
        if (this.isInWater()) {
            return state.setAndContinue(WATER_IDLE);
        }

        if (this.isVisuallyCrawling()) {
            return state.setAndContinue(CRAWL);
        }

        if (this.onClimbable()) {
            return state.setAndContinue(state.isMoving() ? CLIMB : CLIMB_IDLE);
        }

        // ========== 3. Action/item-use overlays ==========
        if (this.isUsingItem()) {
            UseAnim useAnim = this.getUseItem().getUseAnimation();
            if (useAnim == UseAnim.CROSSBOW) {
                return state.setAndContinue(CROSSBOW_CHARGE);
            } else if (useAnim == UseAnim.SPEAR) {
                return state.setAndContinue(SPEAR);
            } else if (useAnim == UseAnim.BOW) {
                return state.setAndContinue(BOW);
            } else if (useAnim == UseAnim.BLOCK) {
                return state.setAndContinue(SHIELD);
            } else if (useAnim == UseAnim.SPYGLASS) {
                return state.setAndContinue(SPYGLASS);
            } else if (useAnim == UseAnim.TOOT_HORN) {
                return state.setAndContinue(HORN);
            } else if (useAnim == UseAnim.BRUSH) {
                return state.setAndContinue(BRUSH);
            } else if (useAnim == UseAnim.EAT || useAnim == UseAnim.DRINK) {
                return state.setAndContinue(EAT);
            }
        }

        // Passive hold pose: crossbow already charged, not currently firing
        ItemStack mainHandItem = this.getMainHandItem();
        if (mainHandItem.getItem() instanceof CrossbowItem && CrossbowItem.isCharged(mainHandItem)) {
            return state.setAndContinue(CROSSBOW_HOLD);
        }

        // ========== 4. Mount/vehicle riding ==========
        if (this.isPassenger()) {
            Entity vehicle = this.getVehicle();
            if (vehicle instanceof Boat) {
                return state.setAndContinue(BOAT);
            } else if (vehicle instanceof AbstractMinecart) {
                return state.setAndContinue(MINECART);
            } else if (vehicle instanceof Camel) {
                return state.setAndContinue(CAMEL);
            } else if (vehicle instanceof AbstractHorse) {
                return state.setAndContinue(HORSE);
            } else if (vehicle instanceof Strider || vehicle instanceof Pig) {
                return state.setAndContinue(RIDE_GENERIC);
            }
            return state.setAndContinue(RIDE_GENERIC);
        }

        // ========== 5. Attack swing ==========
        if (this.swinging) {
            return state.setAndContinue(ATTACK);
        }

        // ========== 6. Verticality ==========
        if (!this.onGround() && !this.isInWater()) {
            return state.setAndContinue(this.getDeltaMovement().y > 0.0 ? JUMP : FALL);
        }

        // ========== 7. Base ground locomotion ==========
        if (this.isCrouching()) {
            return state.setAndContinue(state.isMoving() ? SNEAK_WALK : SNEAK_IDLE);
        }
        if (state.isMoving()) {
            double hSpeed = this.getDeltaMovement().horizontalDistance();
            return state.setAndContinue(hSpeed > 0.22 ? RUN : WALK);
        }
        return state.setAndContinue(IDLE);
    }

    /**
     * Extension hook for god-specific animations that should pre-empt the shared state
     * machine above (e.g. Creaking ceiling-crawl, Warden sniff). Return true if this call
     * already set an animation on the controller (via state.setAndContinue(...) or similar),
     * so baseHumanoidAnimController() should not evaluate the shared states this tick.
     */
    protected <E extends BaseGodEntity> boolean playCustomAnimation(AnimationState<E> state) {
        return false;
    }

    /**
     * Extension point for god-specific ability triggers on the ability_controller.
     * Called during registerControllers() so subclasses don't need to override
     * the full registerControllers() method just to add extra triggerable anims.
     *
     * Example:
     *   {@code controller.triggerableAnim("tentacles_out",
     *       RawAnimation.begin().then("tentacles_out", Animation.LoopType.PLAY_ONCE)); }
     */
    protected void registerExtraAbilityTriggers(
            AnimationController<BaseGodEntity> controller) {
        // Default: no extra triggers — concrete god classes override as needed
    }

    @Override
    public AnimatableInstanceCache getAnimatableInstanceCache() {
        return geoCache;
    }



    // getScale() was removed — LivingEntity's own default (`isBaby() ? 0.5F : 1.0F`) already
    // returns 1.0F here since nothing makes a god entity a baby; the override added nothing.

    // ==================== REQUIRED PLAYER METHODS ====================

    @Override
    public boolean isSpectator() {
        return false;
    }

    // isLocalPlayer() was removed — Player.isLocalPlayer() already returns false by default;
    // unlike isSpectator()/isCreative(), Player does not re-declare this one abstract, so
    // there was nothing to satisfy and nothing this override changed.

    // trade(Villager)(+hasItems/hasStack/removeItems/rewardVillagerTradeXp) and
    // enchantItem(...) removed — trading opens a merchant screen over a real network
    // connection, which this no-AI body doesn't have; the invisible ServerPlayer performs
    // the trade and enchant natively when the agent right-clicks a villager or enchanting
    // table through ActionExecutor, exactly like a real client would.

}