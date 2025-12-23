package com.divineworld.client.control;

import com.divineworld.client.DWClientMod;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;

/**
 * Action Executor - FIXED VERSION
 * Converts AI commands into Minecraft player actions
 *
 * FIXES:
 * - Use gameMode for attack/use instead of private methods
 * - Use proper inventory screen opening
 * - Handle all action flags correctly
 */
public class ActionExecutor {
    private static Minecraft mc;

    // Action flag bit masks (from communication_protocol.py)
    private static final byte FLAG_JUMP = (byte) 0b10000000;
    private static final byte FLAG_SNEAK = (byte) 0b01000000;
    private static final byte FLAG_ATTACK = (byte) 0b00100000;
    private static final byte FLAG_USE = (byte) 0b00010000;
    private static final byte FLAG_DROP = (byte) 0b00001000;
    private static final byte FLAG_OPEN_INV = (byte) 0b00000100;
    private static final byte FLAG_SWAP_HAND = (byte) 0b00000010;

    // Cooldowns to prevent spam
    private static int attackCooldown = 0;
    private static int useCooldown = 0;
    private static int inventoryCooldown = 0;

    public static void initialize() {
        mc = Minecraft.getInstance();
        DWClientMod.LOGGER.info("Action Executor initialized");
    }

    /**
     * Execute an action frame from the AI
     * Must be called from the main game thread
     */
    public static void executeAction(
            float moveForward,
            float moveStrafe,
            float yawDelta,
            float pitchDelta,
            byte actionFlags,
            int hotbarSlot
    ) {
        LocalPlayer player = mc.player;
        if (player == null) return;

        // Tick cooldowns
        if (attackCooldown > 0) attackCooldown--;
        if (useCooldown > 0) useCooldown--;
        if (inventoryCooldown > 0) inventoryCooldown--;

        // Movement inputs
        player.input.forwardImpulse = moveForward;
        player.input.leftImpulse = moveStrafe;

        // Camera rotation
        float newYaw = player.getYRot() + yawDelta;
        float newPitch = player.getXRot() + pitchDelta;

        // Clamp pitch to valid range
        newPitch = Math.max(-90.0f, Math.min(90.0f, newPitch));

        player.setYRot(newYaw);
        player.setXRot(newPitch);
        player.setYHeadRot(newYaw);

        // Boolean actions
        handleActionFlags(actionFlags, player);

        // Hotbar slot selection
        if (hotbarSlot >= 0 && hotbarSlot < 9) {
            player.getInventory().selected = hotbarSlot;
        }
    }

    private static void handleActionFlags(byte flags, LocalPlayer player) {
        // Jump
        if ((flags & FLAG_JUMP) != 0) {
            if (player.onGround()) {
                player.jumpFromGround();
            }
        }

        // Sneak
        boolean shouldSneak = (flags & FLAG_SNEAK) != 0;
        player.setShiftKeyDown(shouldSneak);

        // Attack (left click) - FIXED: Use gameMode instead of private method
        if ((flags & FLAG_ATTACK) != 0 && attackCooldown == 0) {
            performAttack(player);
            attackCooldown = 4; // 4 ticks = 0.2 seconds
        }

        // Use (right click) - FIXED: Use gameMode instead of private method
        if ((flags & FLAG_USE) != 0 && useCooldown == 0) {
            performUse(player);
            useCooldown = 4; // 4 ticks = 0.2 seconds
        }

        // Drop item
        if ((flags & FLAG_DROP) != 0) {
            player.drop(false); // false = drop one, true = drop stack
        }

        // Open inventory - FIXED: Use proper screen opening
        if ((flags & FLAG_OPEN_INV) != 0 && inventoryCooldown == 0) {
            openInventoryScreen();
            inventoryCooldown = 20; // 1 second cooldown
        }

        // Swap hands
        if ((flags & FLAG_SWAP_HAND) != 0) {
            // Swap main hand and offhand items
            player.getInventory().pickSlot(40); // Slot 40 is offhand
        }
    }

    /**
     * Perform attack action - FIXED VERSION
     * Uses gameMode.attack() instead of private Minecraft.startAttack()
     */
    private static void performAttack(LocalPlayer player) {
        if (mc.gameMode == null) return;

        HitResult hitResult = mc.hitResult;

        if (hitResult != null && hitResult.getType() == HitResult.Type.ENTITY) {
            // Attack entity
            EntityHitResult entityHit = (EntityHitResult) hitResult;
            Entity target = entityHit.getEntity();

            // Swing arm for visual feedback
            player.swing(InteractionHand.MAIN_HAND);

            // Attack the entity
            mc.gameMode.attack(player, target);

        } else if (hitResult != null && hitResult.getType() == HitResult.Type.BLOCK) {
            // Start breaking block
            if (mc.gameMode.isDestroying()) {
                // Continue breaking
                mc.gameMode.continueDestroyBlock(
                        ((net.minecraft.world.phys.BlockHitResult) hitResult).getBlockPos(),
                        ((net.minecraft.world.phys.BlockHitResult) hitResult).getDirection()
                );
            } else {
                // Start breaking
                mc.gameMode.startDestroyBlock(
                        ((net.minecraft.world.phys.BlockHitResult) hitResult).getBlockPos(),
                        ((net.minecraft.world.phys.BlockHitResult) hitResult).getDirection()
                );
            }

            // Swing arm
            player.swing(InteractionHand.MAIN_HAND);

        } else {
            // Swing at air
            player.swing(InteractionHand.MAIN_HAND);
        }
    }

    /**
     * Perform use action - FIXED VERSION
     * Uses gameMode.useItem() and useItemOn() instead of private Minecraft.startUseItem()
     */
    private static void performUse(LocalPlayer player) {
        if (mc.gameMode == null) return;

        HitResult hitResult = mc.hitResult;
        InteractionHand hand = InteractionHand.MAIN_HAND;

        if (hitResult != null) {
            switch (hitResult.getType()) {
                case BLOCK -> {
                    // Use item on block (e.g., place block, open door)
                    net.minecraft.world.phys.BlockHitResult blockHit =
                            (net.minecraft.world.phys.BlockHitResult) hitResult;

                    net.minecraft.world.InteractionResult result = mc.gameMode.useItemOn(
                            player,
                            hand,
                            blockHit
                    );

                    if (result.consumesAction()) {
                        player.swing(hand);
                    }
                }

                case ENTITY -> {
                    // Interact with entity
                    EntityHitResult entityHit = (EntityHitResult) hitResult;
                    Entity target = entityHit.getEntity();

                    net.minecraft.world.InteractionResult result = mc.gameMode.interact(
                            player,
                            target,
                            hand
                    );

                    if (!result.consumesAction()) {
                        // Try interacting at location
                        result = mc.gameMode.interactAt(
                                player,
                                target,
                                entityHit,
                                hand
                        );
                    }

                    if (result.consumesAction()) {
                        player.swing(hand);
                    }
                }

                case MISS -> {
                    // Use item in air (e.g., eat food, drink potion, shoot bow)
                    mc.gameMode.useItem(player, hand);
                }
            }
        } else {
            // No hit result, just use item
            mc.gameMode.useItem(player, hand);
        }
    }

    /**
     * Open inventory screen - FIXED VERSION
     * Uses setScreen() instead of non-existent openInventory()
     */
    private static void openInventoryScreen() {
        if (mc.screen != null) {
            // Already have a screen open, close it first
            mc.setScreen(null);
            return;
        }

        LocalPlayer player = mc.player;
        if (player == null) return;

        // Open inventory screen
        if (player.isCreative()) {
            // Creative mode inventory
            mc.setScreen(new net.minecraft.client.gui.screens.inventory.CreativeModeInventoryScreen(
                    player,
                    player.level().enabledFeatures(),
                    player.canUseGameMasterBlocks()
            ));
        } else {
            // Survival mode inventory
            mc.setScreen(new net.minecraft.client.gui.screens.inventory.InventoryScreen(player));
        }
    }

    /**
     * Alternative: Close any open screen
     */
    public static void closeScreen() {
        if (mc.screen != null) {
            mc.setScreen(null);
        }
    }

    /**
     * Get current action state (for debugging)
     */
    public static String getActionState() {
        if (mc.player == null) return "No player";

        LocalPlayer player = mc.player;
        return String.format(
                "Slot:%d Sneak:%b OnGround:%b Health:%.1f",
                player.getInventory().selected,
                player.isShiftKeyDown(),
                player.onGround(),
                player.getHealth()
        );
    }
}