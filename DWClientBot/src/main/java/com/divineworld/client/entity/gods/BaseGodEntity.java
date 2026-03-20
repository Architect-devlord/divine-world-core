package com.divineworld.client.entity.gods;

import com.divineworld.client.entity.IGodEntity;
import com.mojang.authlib.GameProfile;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.tags.FluidTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.*;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.npc.Villager;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.*;
import net.minecraft.world.food.FoodProperties;
import net.minecraft.world.item.*;
import net.minecraft.world.item.alchemy.PotionUtils;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.item.context.UseOnContext;
import net.minecraft.world.item.enchantment.Enchantment;
import net.minecraft.world.item.enchantment.EnchantmentHelper;
import net.minecraft.world.item.trading.MerchantOffer;
import net.minecraft.world.item.trading.MerchantOffers;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.UUID;

/**
 * Base God Entity - FULLY FIXED VERSION
 * Extends Player to get ALL player mechanics including inventory
 * Uses Player's Inventory class instead of SimpleContainer
 */
public abstract class BaseGodEntity extends Player implements IGodEntity {

    // Use Player's standard Inventory - has getDestroySpeed()
    

    // Transformation state
    protected boolean isTransformed = false;
    protected String transformedMobName = null;

    // Player ability flags
    protected boolean canMineBlocks = true;
    protected boolean canPlaceBlocks = true;
    protected boolean canCraft = true;
    protected boolean canUseItems = true;

    // Item usage tracking (from Player.java)
    protected ItemStack useItem = ItemStack.EMPTY;
    protected int useItemRemaining;

    // Attack tracking
    protected int attackStrengthTicker;

    /**
     * FIXED: Proper constructor with GameProfile
     */
    public BaseGodEntity(EntityType<? extends Player> type, Level level) {
        super(level, BlockPos.ZERO, 0.0F, createGodProfile());
        // FIXED: Use Player's Inventory class which has getDestroySpeed()
        
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
        // FIX B-02: ++this.attackStrengthTicker REMOVED.
        // Player.tick() already calls tickAttackStrength() which increments it.
        // Having it here too made attack cooldown recharge at 2× speed and
        // caused every second hit to become a premature critical.

        // Handle item usage
        if (!this.useItem.isEmpty() && this.useItemRemaining > 0) {
            --this.useItemRemaining;
            if (this.useItemRemaining == 0) {
                this.completeUsingItem();
            }
        }

        
    }

    // ==================== MINING - PRODUCTION READY ====================

    /**
     * Mine a block using equipped tool - Based on Player.java logic
     */
    public void mineBlock(BlockPos pos) {
        if (!canMineBlocks) return;

        ItemStack tool = getMainHandItem();
        BlockState blockState = level().getBlockState(pos);

        // Check if can mine this block
        if (!hasCorrectToolForDrops(blockState)) {
            // Still break but no drops
            level().destroyBlock(pos, false);
            return;
        }

        // Break block with drops (Player.java style)
        Block.dropResources(blockState, level(), pos,
                blockState.hasBlockEntity() ? level().getBlockEntity(pos) : null,
                this, tool);

        // Destroy the block
        boolean removed = level().removeBlock(pos, false);

        if (removed) {
            blockState.getBlock().destroy(level(), pos, blockState);
        }

        // Damage tool
        if (!tool.isEmpty() && removed) {
            tool.mineBlock(level(), blockState, pos, this);

            // Check if tool broke
            if (tool.isEmpty()) {
                onItemBroke(tool);
            }
        }

        // Play break sound
        level().playSound(null, pos, blockState.getSoundType().getBreakSound(),
                SoundSource.BLOCKS, 1.0f, 1.0f);

        // Spawn break particles
        level().levelEvent(2001, pos, Block.getId(blockState));
    }

    /**
     * Check if entity has correct tool for drops
     */
    public boolean hasCorrectToolForDrops(BlockState state) {
        if (!state.requiresCorrectToolForDrops()) {
            return true;
        }
        return getMainHandItem().isCorrectToolForDrops(state);
    }

    /**
     * FIXED: Get mining speed using Inventory.getDestroySpeed()
     */
    @Override
    public float getDestroySpeed(BlockState state) {
        float speed = this.inventory.getDestroySpeed(state);

        // Efficiency enchantment bonus
        if (speed > 1.0F) {
            int efficiency = EnchantmentHelper.getBlockEfficiency(this);
            ItemStack tool = getMainHandItem();
            if (efficiency > 0 && !tool.isEmpty()) {
                speed += (float)(efficiency * efficiency + 1);
            }
        }

        // Water penalty
        if (this.isEyeInFluid(FluidTags.WATER) && !EnchantmentHelper.hasAquaAffinity(this)) {
            speed /= 5.0F;
        }

        // Not on ground penalty
        if (!this.onGround()) {
            speed /= 5.0F;
        }

        return speed;
    }

    // ==================== BLOCK PLACEMENT - PRODUCTION READY ====================

    /**
     * Place a block - Full Player.java logic with UseOnContext
     */
    public void placeBlock(BlockPos pos, ItemStack blockItem) {
        if (!canPlaceBlocks || blockItem.isEmpty()) return;

        if (!(blockItem.getItem() instanceof BlockItem blockItemObj)) {
            return;
        }

        BlockState existingState = level().getBlockState(pos);
        if (!existingState.canBeReplaced()) {
            return;
        }

        // Create proper placement context
        Direction facing = getDirectionFromYaw(getYRot());
        Vec3 hitVec = new Vec3(pos.getX() + 0.5, pos.getY() + 0.5, pos.getZ() + 0.5);

        BlockHitResult hitResult = new BlockHitResult(
                hitVec,
                facing.getOpposite(),
                pos,
                false
        );

        // Create use context
        UseOnContext useContext = new UseOnContext(
                level(),
                this,
                InteractionHand.MAIN_HAND,
                blockItem,
                hitResult
        );

        // Create block place context
        BlockPlaceContext placeContext = new BlockPlaceContext(useContext);

        // Get placement state from the block
        BlockState stateToPlace = blockItemObj.getBlock().getStateForPlacement(placeContext);

        if (stateToPlace == null) {
            stateToPlace = blockItemObj.getBlock().defaultBlockState();
            stateToPlace = getPlacementState(stateToPlace, pos, facing);
        }

        // Place the block
        if (level().setBlock(pos, stateToPlace, 11)) { // 11 = flags for update + notify

            BlockState placedState = level().getBlockState(pos);

            // Play place sound
            level().playSound(null, pos,
                    placedState.getSoundType().getPlaceSound(),
                    SoundSource.BLOCKS,
                    (placedState.getSoundType().getVolume() + 1.0F) / 2.0F,
                    placedState.getSoundType().getPitch() * 0.8F
            );

            // Spawn place particles
            for (int i = 0; i < 5; i++) {
                double d0 = pos.getX() + 0.5 + (random.nextDouble() - 0.5) * 0.5;
                double d1 = pos.getY() + 0.5;
                double d2 = pos.getZ() + 0.5 + (random.nextDouble() - 0.5) * 0.5;
                level().addParticle(ParticleTypes.CRIT, d0, d1, d2, 0, 0, 0);
            }

            // Consume item
            if (!isCreative()) {
                blockItem.shrink(1);
            }

            // Post-placement
            blockItemObj.getBlock().setPlacedBy(level(), pos, placedState, this, blockItem);
        }
    }

    /**
     * Fallback placement state logic
     */
    private BlockState getPlacementState(BlockState state, BlockPos pos, Direction facing) {
        if (state.hasProperty(BlockStateProperties.FACING)) {
            state = state.setValue(BlockStateProperties.FACING, facing);
        }
        else if (state.hasProperty(BlockStateProperties.HORIZONTAL_FACING)) {
            state = state.setValue(BlockStateProperties.HORIZONTAL_FACING,
                    facing.getAxis().isHorizontal() ? facing : Direction.NORTH);
        }
        else if (state.hasProperty(BlockStateProperties.AXIS)) {
            state = state.setValue(BlockStateProperties.AXIS, facing.getAxis());
        }
        return state;
    }

    /**
     * Convert yaw rotation to direction
     */
    private Direction getDirectionFromYaw(float yaw) {
        return Direction.fromYRot(yaw);
    }

    // ==================== ITEM USAGE - PRODUCTION READY ====================

    /**
     * Use an item - Complete Player.java implementation
     */
    public void useItem(ItemStack item) {
        if (!canUseItems || item.isEmpty()) return;

        Item itemType = item.getItem();

        // FOOD
        if (item.isEdible()) {
            startUsingItem(item);
            return;
        }

        // POTIONS
        else if (itemType instanceof PotionItem) {
            startUsingItem(item);
            return;
        }

        // PROJECTILES
        else if (itemType instanceof BowItem || itemType instanceof CrossbowItem) {
            startUsingItem(item);
            return;
        }

        // THROWABLES
        else if (itemType instanceof SnowballItem) {
            throwSnowball(item);
        }
        else if (itemType instanceof EggItem) {
            throwEgg(item);
        }
        else if (itemType == Items.ENDER_PEARL) {
            throwEnderPearl(item);
        }
        else if (itemType == Items.EXPERIENCE_BOTTLE) {
            throwExperienceBottle(item);
        }

        // MILK BUCKET
        else if (itemType == Items.MILK_BUCKET) {
            removeAllEffects();
            level().playSound(null, getX(), getY(), getZ(),
                    SoundEvents.GENERIC_DRINK, SoundSource.PLAYERS,
                    0.5f, random.nextFloat() * 0.1f + 0.9f);

            if (!isCreative()) {
                item.shrink(1);
                if (item.isEmpty()) {
                    setItemInHand(InteractionHand.MAIN_HAND, new ItemStack(Items.BUCKET));
                } else {
                    this.inventory.add(new ItemStack(Items.BUCKET));
                }
            }
        }

        // FLINT AND STEEL
        else if (itemType == Items.FLINT_AND_STEEL) {
            useFlintAndSteel(item);
        }

        // SHIELD
        else if (itemType instanceof ShieldItem) {
            startUsingItem(item);
        }

        // FIREWORK
        else if (itemType == Items.FIREWORK_ROCKET) {
            launchFirework(item);
        }

        // GENERIC USE
        else {
            InteractionResult result = item.use(level(), this, InteractionHand.MAIN_HAND).getResult();
            if (result.consumesAction() && !isCreative()) {
                item.shrink(1);
            }
        }
    }

    /**
     * Start using an item (from Player.java)
     */
    private void startUsingItem(ItemStack item) {
        this.useItem = item.copy();
        this.useItemRemaining = item.getUseDuration();

        if (!level().isClientSide) {
            this.setLivingEntityFlag(1, true);
            this.setLivingEntityFlag(2, InteractionHand.MAIN_HAND == InteractionHand.OFF_HAND);
        }
    }

    /**
     * Complete using item (from Player.java)
     */
    public void completeUsingItem() {
        if (this.useItem.isEmpty()) return;

        ItemStack itemstack = this.useItem;
        Item item = itemstack.getItem();

        // FOOD
        if (itemstack.isEdible()) {
            FoodProperties food = itemstack.getFoodProperties(this);
            if (food != null) {
                heal(food.getNutrition() * 0.5f);

                // Apply food effects
                for (var pair : food.getEffects()) {
                    if (random.nextFloat() < pair.getSecond()) {
                        addEffect(new net.minecraft.world.effect.MobEffectInstance(pair.getFirst()));
                    }
                }
            }

            level().playSound(null, getX(), getY(), getZ(),
                    SoundEvents.PLAYER_BURP, SoundSource.PLAYERS,
                    0.5f, random.nextFloat() * 0.1f + 0.9f);
        }

        // POTIONS
        else if (item instanceof PotionItem) {
            for (net.minecraft.world.effect.MobEffectInstance effect : PotionUtils.getMobEffects(itemstack)) {
                addEffect(new net.minecraft.world.effect.MobEffectInstance(effect));
            }

            level().playSound(null, getX(), getY(), getZ(),
                    SoundEvents.GENERIC_DRINK, SoundSource.PLAYERS,
                    0.5f, random.nextFloat() * 0.1f + 0.9f);

            if (!isCreative()) {
                itemstack.shrink(1);
                if (itemstack.isEmpty()) {
                    setItemInHand(InteractionHand.MAIN_HAND, new ItemStack(Items.GLASS_BOTTLE));
                } else {
                    this.inventory.add(new ItemStack(Items.GLASS_BOTTLE));
                }
            }
        }

        // BOW
        else if (item instanceof BowItem) {
            shootArrow(itemstack);
        }

        // Finalize item use
        if (!isCreative()) {
            itemstack.shrink(1);
            if (itemstack.isEmpty()) {
                setItemInHand(InteractionHand.MAIN_HAND, ItemStack.EMPTY);
            }
        }

        this.useItem = ItemStack.EMPTY;
        this.useItemRemaining = 0;

        if (!level().isClientSide) {
            this.setLivingEntityFlag(1, false);
        }
    }

    // ==================== PROJECTILE THROWING ====================

    private void throwSnowball(ItemStack item) {
        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.SNOWBALL_THROW, SoundSource.PLAYERS,
                0.5f, 0.4f / (random.nextFloat() * 0.4f + 0.8f));

        if (!level().isClientSide) {
            Snowball snowball = new Snowball(level(), this);
            snowball.setItem(item);
            snowball.shootFromRotation(this, getXRot(), getYRot(), 0.0F, 1.5F, 1.0F);
            level().addFreshEntity(snowball);
        }

        if (!isCreative()) {
            item.shrink(1);
        }
    }

    private void throwEgg(ItemStack item) {
        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.EGG_THROW, SoundSource.PLAYERS,
                0.5f, 0.4f / (random.nextFloat() * 0.4f + 0.8f));

        if (!level().isClientSide) {
            ThrownEgg egg = new ThrownEgg(level(), this);
            egg.setItem(item);
            egg.shootFromRotation(this, getXRot(), getYRot(), 0.0F, 1.5F, 1.0F);
            level().addFreshEntity(egg);
        }

        if (!isCreative()) {
            item.shrink(1);
        }
    }

    private void throwEnderPearl(ItemStack item) {
        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.ENDER_PEARL_THROW, SoundSource.PLAYERS,
                0.5f, 0.4f / (random.nextFloat() * 0.4f + 0.8f));

        if (!level().isClientSide) {
            ThrownEnderpearl pearl = new ThrownEnderpearl(level(), this);
            pearl.setItem(item);
            pearl.shootFromRotation(this, getXRot(), getYRot(), 0.0F, 1.5F, 1.0F);
            level().addFreshEntity(pearl);
        }

        if (!isCreative()) {
            item.shrink(1);
        }
    }

    private void throwExperienceBottle(ItemStack item) {
        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.EXPERIENCE_BOTTLE_THROW, SoundSource.PLAYERS,
                0.5f, 0.4f / (random.nextFloat() * 0.4f + 0.8f));

        if (!level().isClientSide) {
            ThrownExperienceBottle bottle = new ThrownExperienceBottle(level(), this);
            bottle.setItem(item);
            bottle.shootFromRotation(this, getXRot(), getYRot(), -20.0F, 0.7F, 1.0F);
            level().addFreshEntity(bottle);
        }

        if (!isCreative()) {
            item.shrink(1);
        }
    }

    private void shootArrow(ItemStack bow) {
        // Find arrow in inventory
        ItemStack arrowStack = findArrow();
        if (arrowStack.isEmpty() && !isCreative()) return;

        if (!level().isClientSide) {
            Arrow arrow = new Arrow(level(), this);
            arrow.shootFromRotation(this, getXRot(), getYRot(), 0.0F, 3.0F, 1.0F);

            // Enchantment effects
            int power = EnchantmentHelper.getItemEnchantmentLevel(
                    net.minecraft.world.item.enchantment.Enchantments.POWER_ARROWS, bow);
            if (power > 0) {
                arrow.setBaseDamage(arrow.getBaseDamage() + (double)power * 0.5D + 0.5D);
            }

            int punch = EnchantmentHelper.getItemEnchantmentLevel(
                    net.minecraft.world.item.enchantment.Enchantments.PUNCH_ARROWS, bow);
            if (punch > 0) {
                arrow.setKnockback(punch);
            }

            if (EnchantmentHelper.getItemEnchantmentLevel(
                    net.minecraft.world.item.enchantment.Enchantments.FLAMING_ARROWS, bow) > 0) {
                arrow.setSecondsOnFire(100);
            }

            level().addFreshEntity(arrow);
        }

        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.ARROW_SHOOT, SoundSource.PLAYERS,
                1.0f, 1.0f / (random.nextFloat() * 0.4f + 1.2f) + 0.5f);

        if (!isCreative()) {
            arrowStack.shrink(1);
        }
    }

    private ItemStack findArrow() {
        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            ItemStack stack = this.inventory.getItem(i);
            if (stack.getItem() instanceof ArrowItem) {
                return stack;
            }
        }
        return ItemStack.EMPTY;
    }

    private void useFlintAndSteel(ItemStack item) {
        BlockHitResult hit = getTargetBlock(5.0);
        if (hit.getType() != HitResult.Type.BLOCK) return;

        BlockPos hitPos = hit.getBlockPos();
        Direction face = hit.getDirection();
        BlockPos placePos = hitPos.relative(face);

        if (level().isEmptyBlock(placePos)) {
            level().playSound(null, placePos, SoundEvents.FLINTANDSTEEL_USE,
                    SoundSource.BLOCKS, 1.0f, random.nextFloat() * 0.4f + 0.8f);

            BlockState fireState = Blocks.FIRE.defaultBlockState();
            level().setBlock(placePos, fireState, 11);

            if (!isCreative()) {
                item.hurtAndBreak(1, this, (entity) -> {});
            }
        }
    }

    private void launchFirework(ItemStack item) {
        if (!level().isClientSide) {
            FireworkRocketEntity firework = new FireworkRocketEntity(
                    level(), item, this,
                    getX(), getY() + getEyeHeight(), getZ(), true
            );
            level().addFreshEntity(firework);
        }

        if (!isCreative()) {
            item.shrink(1);
        }
    }

    private BlockHitResult getTargetBlock(double reach) {
        Vec3 eyePos = new Vec3(getX(), getY() + getEyeHeight(), getZ());
        Vec3 lookVec = getLookAngle();
        Vec3 reachVec = eyePos.add(lookVec.x * reach, lookVec.y * reach, lookVec.z * reach);

        return level().clip(new ClipContext(
                eyePos, reachVec,
                ClipContext.Block.OUTLINE,
                ClipContext.Fluid.NONE,
                this
        ));
    }

    // ==================== INVENTORY MANAGEMENT ====================

    @Override
    public ItemStack getMainHandItem() {
        return this.inventory.getSelected();
    }

    @Override
    public void setItemInHand(InteractionHand hand, ItemStack stack) {
        if (hand == InteractionHand.MAIN_HAND) {
            this.inventory.setItem(this.inventory.selected, stack);
        } else {
            this.inventory.offhand.set(0, stack);
        }
    }

    @Override
    public ItemStack getItemInHand(InteractionHand hand) {
        return hand == InteractionHand.MAIN_HAND ? getMainHandItem() : getOffhandItem();
    }

    @Override
    public ItemStack getOffhandItem() {
        return this.inventory.offhand.get(0);
    }

    public void setOffhandItem(ItemStack stack) {
        this.inventory.offhand.set(0, stack);
    }

    public void selectHotbarSlot(int slot) {
        if (slot >= 0 && slot < 9) {
            this.inventory.selected = slot;
        }
    }

    public boolean addItem(ItemStack stack) {
        return this.inventory.add(stack);
    }

    public void dropItem(ItemStack stack) {
        if (stack.isEmpty()) return;

        double eyeY = getEyeY() - 0.3;
        ItemEntity itemEntity = new ItemEntity(level(), getX(), eyeY, getZ(), stack);
        itemEntity.setPickUpDelay(40);
        itemEntity.setThrower(getUUID());

        // Calculate throw trajectory
        float pitch = getXRot();
        float yaw = getYRot();
        float f = -net.minecraft.util.Mth.sin(yaw * ((float)Math.PI / 180F)) *
                net.minecraft.util.Mth.cos(pitch * ((float)Math.PI / 180F));
        float f1 = -net.minecraft.util.Mth.sin(pitch * ((float)Math.PI / 180F));
        float f2 = net.minecraft.util.Mth.cos(yaw * ((float)Math.PI / 180F)) *
                net.minecraft.util.Mth.cos(pitch * ((float)Math.PI / 180F));

        itemEntity.setDeltaMovement(
                (double)f * 0.3,
                (double)f1 * 0.3 + 0.1,
                (double)f2 * 0.3
        );

        level().addFreshEntity(itemEntity);
    }

    public void dropHeldItem() {
        ItemStack held = getMainHandItem();
        if (!held.isEmpty()) {
            dropItem(held.split(1));
        }
    }

    @Override
    public ItemStack getItemBySlot(EquipmentSlot slot) {
        return switch (slot.getType()) {
            case HAND -> slot == EquipmentSlot.MAINHAND ? getMainHandItem() : getOffhandItem();
            case ARMOR -> this.inventory.armor.get(slot.getIndex());
            default -> ItemStack.EMPTY;
        };
    }

    @Override
    public void setItemSlot(EquipmentSlot slot, ItemStack stack) {
        switch (slot.getType()) {
            case HAND -> {
                if (slot == EquipmentSlot.MAINHAND) {
                    this.inventory.setItem(this.inventory.selected, stack);
                } else {
                    setOffhandItem(stack);
                }
            }
            case ARMOR -> this.inventory.armor.set(slot.getIndex(), stack);
        }
    }

    // ==================== HELPER METHODS ====================

    @Override
    public boolean isCreative() {
        return false; // God entities work like survival players
    }

    private void onItemBroke(ItemStack item) {
        level().playSound(null, getX(), getY(), getZ(),
                SoundEvents.ITEM_BREAK, SoundSource.PLAYERS,
                0.8f, 0.8f + level().random.nextFloat() * 0.4f);
    }

    public float getAttackStrengthScale(float adjustTicks) {
        return net.minecraft.util.Mth.clamp(
                ((float)this.attackStrengthTicker + adjustTicks) /
                        (float)getCurrentItemAttackStrengthDelay(),
                0.0F, 1.0F
        );
    }

    public float getCurrentItemAttackStrengthDelay() {
        ItemStack mainHand = getMainHandItem();
        if (mainHand.isEmpty()) {
            return 4; // Default punch speed
        }
        return (int)(20.0 / getAttributeValue(net.minecraft.world.entity.ai.attributes.Attributes.ATTACK_SPEED));
    }

    public void resetAttackStrengthTicker() {
        this.attackStrengthTicker = 0;
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
                        onItemBroke(weapon);
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

    // ==================== INTERACTION WITH BLOCKS/ENTITIES ====================

    public InteractionResult interactOn(Entity target, InteractionHand hand) {
        ItemStack handStack = getItemInHand(hand);
        ItemStack copyStack = handStack.copy();

        // Let entity handle interaction first
        InteractionResult result = target.interact(this, hand);
        if (result.consumesAction()) {
            return result;
        }

        // Try using item on entity
        if (!handStack.isEmpty() && target instanceof LivingEntity living) {
            InteractionResult itemResult = handStack.interactLivingEntity(this, living, hand);
            if (itemResult.consumesAction()) {
                if (handStack.isEmpty() && !copyStack.isEmpty()) {
                    setItemInHand(hand, ItemStack.EMPTY);
                }
                return itemResult;
            }
        }

        return InteractionResult.PASS;
    }

    public InteractionResult interactWithBlock(BlockPos pos, InteractionHand hand) {
        ItemStack handStack = getItemInHand(hand);
        BlockState state = level().getBlockState(pos);

        // Block interaction
        InteractionResult blockResult = state.use(level(), this, hand,
                new BlockHitResult(Vec3.atCenterOf(pos), Direction.UP, pos, false));

        if (blockResult.consumesAction()) {
            return blockResult;
        }

        // Item on block
        if (!handStack.isEmpty()) {
            UseOnContext context = new UseOnContext(this, hand,
                    new BlockHitResult(Vec3.atCenterOf(pos), Direction.UP, pos, false));
            InteractionResult itemResult = handStack.useOn(context);

            if (itemResult.consumesAction() && !isCreative()) {
                if (handStack.isEmpty()) {
                    setItemInHand(hand, ItemStack.EMPTY);
                }
            }

            return itemResult;
        }

        return InteractionResult.PASS;
    }

    // ==================== CRAFTING ====================

    public boolean craftItem(net.minecraft.world.item.crafting.Recipe<?> recipe) {
        if (!canCraft) return false;

        // Check if has ingredients
        for (net.minecraft.world.item.crafting.Ingredient ingredient : recipe.getIngredients()) {
            if (!hasIngredient(ingredient)) {
                return false;
            }
        }

        // Consume ingredients
        for (net.minecraft.world.item.crafting.Ingredient ingredient : recipe.getIngredients()) {
            consumeIngredient(ingredient);
        }

        // Give result
        ItemStack result = recipe.getResultItem(level().registryAccess());
        if (!result.isEmpty()) {
            if (!addItem(result.copy())) {
                dropItem(result.copy());
            }
        }

        return true;
    }

    private boolean hasIngredient(net.minecraft.world.item.crafting.Ingredient ingredient) {
        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            if (ingredient.test(this.inventory.getItem(i))) {
                return true;
            }
        }
        return false;
    }

    private void consumeIngredient(net.minecraft.world.item.crafting.Ingredient ingredient) {
        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            ItemStack stack = this.inventory.getItem(i);
            if (ingredient.test(stack)) {
                stack.shrink(1);
                if (stack.isEmpty()) {
                    this.inventory.setItem(i, ItemStack.EMPTY);
                }
                return;
            }
        }
    }

    // ==================== PERSISTENCE ====================

    @Override
    public void addAdditionalSaveData(CompoundTag tag) {
        super.addAdditionalSaveData(tag);

        tag.putBoolean("IsTransformed", isTransformed);
        tag.putInt("AttackStrengthTicker", attackStrengthTicker);

        if (transformedMobName != null) {
            tag.putString("TransformedMob", transformedMobName);
        }

        // Save inventory using Player's Inventory save method
        ListTag inventoryTag = new ListTag();
        this.inventory.save(inventoryTag);
        tag.put("Inventory", inventoryTag);

        // Save item in use
        if (!useItem.isEmpty()) {
            CompoundTag useTag = new CompoundTag();
            useItem.save(useTag);
            tag.put("UseItem", useTag);
            tag.putInt("UseItemRemaining", useItemRemaining);
        }
    }

    @Override
    public void readAdditionalSaveData(CompoundTag tag) {
        super.readAdditionalSaveData(tag);

        isTransformed = tag.getBoolean("IsTransformed");
        attackStrengthTicker = tag.getInt("AttackStrengthTicker");

        if (tag.contains("TransformedMob")) {
            transformedMobName = tag.getString("TransformedMob");
        }

        // Load inventory using Player's Inventory load method
        if (tag.contains("Inventory", 9)) {
            ListTag inventoryTag = tag.getList("Inventory", 10);
            this.inventory.load(inventoryTag);
        }

        // Load item in use
        if (tag.contains("UseItem")) {
            useItem = ItemStack.of(tag.getCompound("UseItem"));
            useItemRemaining = tag.getInt("UseItemRemaining");
        }
    }

    @Override
    public void addPlayerInventory() {
        // Already implemented in constructor with Player's Inventory
    }

    // ==================== ABSTRACT METHODS - Must be implemented by subclasses ====================

    @Override
    public abstract String getGodType();

    @Override
    public abstract void useAbility(String abilityName, Object... params);

    @Override
    public abstract void toggleFlight(boolean enable);

    /**
     * Get custom scale for this god entity
     */
    public float getScale() {
        return 1.0f; // Default 1.0, override for larger/smaller gods
    }

    // ==================== REQUIRED PLAYER METHODS ====================

    @Override
    public boolean isSpectator() {
        return false;
    }

    @Override
    public boolean isLocalPlayer() {
        return false;
    }

    //Trading logic for the gods

    public void trade(Villager villager) {
        if (villager == null || villager.isRemoved()) return;
        if (level().isClientSide) return;

        MerchantOffers offers = villager.getOffers();
        if (offers.isEmpty()) return;

        for (MerchantOffer offer : offers) {
            if (offer.isOutOfStock()) continue;

            ItemStack costA = offer.getCostA();
            ItemStack costB = offer.getCostB();

            if (!hasItems(costA, costB)) continue;

            // Consume payment
            removeItems(costA.copy());
            if (!costB.isEmpty()) {
                removeItems(costB.copy());
            }

            // Give result
            ItemStack result = offer.assemble();
            if (!addItem(result.copy())) {
                dropItem(result.copy());
            }

            // Finalize trade
            offer.increaseUses();
            villager.notifyTrade(offer);

            // ✅ Correct XP handling
            rewardVillagerTradeXp(villager, offer);

            // Sound
            level().playSound(
                    null,
                    villager.blockPosition(),
                    SoundEvents.VILLAGER_TRADE,
                    SoundSource.NEUTRAL,
                    1.0f,
                    1.0f
            );

            return; // one trade per call
        }
    }

    private void rewardVillagerTradeXp(Villager villager, MerchantOffer offer) {
        if (!(level() instanceof ServerLevel serverLevel)) return;

        int xp = offer.getXp();
        if (xp <= 0) return;

        ExperienceOrb.award(serverLevel, villager.position(), xp);
    }



    private boolean hasItems(ItemStack costA, ItemStack costB) {
        return hasStack(costA) && (costB.isEmpty() || hasStack(costB));
    }

    private boolean hasStack(ItemStack stack) {
        int needed = stack.getCount();

        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            ItemStack inv = this.inventory.getItem(i);
            if (ItemStack.isSameItemSameTags(inv, stack)) {
                needed -= inv.getCount();
                if (needed <= 0) return true;
            }
        }
        return false;
    }

    private void removeItems(ItemStack stack) {
        int remaining = stack.getCount();

        for (int i = 0; i < this.inventory.getContainerSize(); i++) {
            ItemStack inv = this.inventory.getItem(i);
            if (ItemStack.isSameItemSameTags(inv, stack)) {
                int taken = Math.min(inv.getCount(), remaining);
                inv.shrink(taken);
                remaining -= taken;

                if (inv.isEmpty()) {
                    this.inventory.setItem(i, ItemStack.EMPTY);
                }

                if (remaining <= 0) return;
            }
        }
    }

    //enchanting logic for the gods
    public void enchantItem(ItemStack item, Enchantment ench) {
        if (item.isEmpty() || ench == null) return;
        if (!ench.canEnchant(item)) return;
        if (level().isClientSide) return;

        // Do not exceed max level
        int currentLevel = EnchantmentHelper.getItemEnchantmentLevel(ench, item);
        if (currentLevel >= ench.getMaxLevel()) return;

        // XP cost (simple & tunable)
        int cost = 5 + currentLevel * 10;
        if (experienceLevel < cost) return;

        // Apply enchantment
        item.enchant(ench, currentLevel + 1);

        // Consume XP
        giveExperienceLevels(-cost);

        // Enchant sound
        level().playSound(
                null,
                blockPosition(),
                SoundEvents.ENCHANTMENT_TABLE_USE,
                SoundSource.PLAYERS,
                1.0f,
                random.nextFloat() * 0.1f + 0.9f
        );
    }

}