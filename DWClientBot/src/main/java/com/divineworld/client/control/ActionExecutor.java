// src/main/java/com/divineworld/client/control/ActionExecutor.java
// Forge 1.20.1 / Parchment mappings
package com.divineworld.client.control;

import com.divineworld.client.DWClientMod;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ClickType;
import net.minecraft.world.phys.EntityHitResult;
import net.minecraft.world.phys.HitResult;

/**
 * ActionExecutor — applies one decoded action frame to the local player.
 *
 * Forge 1.20.1 / Parchment 47.4.10
 *
 * CALL CONVENTION:
 *   executeAction()  MUST be called on the Minecraft main thread.
 *   TCPServer and WebSocketManager already wrap calls with
 *   Minecraft.getInstance().execute(() -> {...}).
 *
 * INVENTORY SLOT CLICKS (added):
 *   Callers (TCPServer) detect the "inv:" prefix on the ability string and
 *   call executeInventoryAction() directly, before dispatching to
 *   GodEntityManager.  ActionExecutor owns this method because:
 *     1. It must run on the main thread (already the case for all action dispatch).
 *     2. It needs access to mc.gameMode and player.containerMenu — both
 *        are Minecraft client objects, matching this class's purpose.
 *
 *   Inventory action string format: "inv:SLOT,BUTTON,CLICK_TYPE"
 *     SLOT       — 0-based slot index in the currently open container.
 *                  For the player inventory (InventoryMenu):
 *                    0    = crafting result
 *                    1-4  = crafting grid
 *                    5-8  = armour (head→feet)
 *                    9-35 = main inventory (row-major, top-left first)
 *                    36-44= hotbar (36=slot0 .. 44=slot8)
 *                    45   = offhand
 *     BUTTON     — 0 = left click, 1 = right click, 2 = middle click.
 *                  For SWAP clicks: button = target hotbar slot index (0–8).
 *     CLICK_TYPE — ClickType ordinal:
 *                    0 = PICKUP      (normal left/right click)
 *                    1 = QUICK_MOVE  (shift-click → moves item automatically)
 *                    2 = SWAP        (swaps slot with hotbar[button])
 *                    3 = CLONE       (creative middle-click copy)
 *                    4 = THROW       (drop with Q)
 *                    5 = SPREAD      (drag-spread)
 *
 *   Example: move main-inventory slot 9 to hotbar slot 0:
 *     ability string = "inv:9,0,2"   (slot=9, button=0, SWAP)
 *   Example: shift-click craft result to inventory:
 *     ability string = "inv:0,0,1"   (slot=0, button=0, QUICK_MOVE)
 *
 * SCREEN ACTIONS:
 *   "screen:close"  — close any open GUI screen.
 *   "screen:inv"    — open the player inventory.
 *
 * INTERACTIVE BLOCKS (CraftingTable, StoneCutter, Furnace…):
 *   No special handling needed here. The agent:
 *     1. Sets 'use'=true while looking at the block → vanilla sends
 *        ServerboundUseItemOnPacket → server opens the container → client
 *        receives ClientboundOpenScreenPacket → screen appears automatically.
 *     2. Then sends "inv:SLOT,BUTTON,CLICK_TYPE" to interact with slots.
 *     3. Sends "screen:close" when done.
 *   The containerId in player.containerMenu is updated by Minecraft when
 *   the server opens the container, so handleInventoryMouseClick always
 *   targets the correct container without any extra work here.
 *
 * ACTION FLAGS BYTE (bit 7 = MSB):
 *   bit 7  jump
 *   bit 6  sneak
 *   bit 5  attack
 *   bit 4  use
 *   bit 3  drop
 *   bit 2  open_inv
 *   bit 1  swap_hand
 *   bit 0  sprint
 */
public class ActionExecutor {

    /** Minimum ticks between attack or use actions. */
    private static final int ATTACK_USE_COOLDOWN = 4;
    /** Minimum ticks between inventory-open actions. */
    private static final int INVENTORY_COOLDOWN  = 20;

    private static int attackUseCooldownTicks = 0;
    private static int inventoryCooldownTicks = 0;

    // =========================================================================
    // Main action entry point  (movement + flags)
    // =========================================================================

    /**
     * Apply one decoded action frame to the local player.
     * Must be called on the Minecraft main thread.
     *
     * @param moveForward  [-1.0, 1.0]  forward/backward movement
     * @param moveStrafe   [-1.0, 1.0]  left/right movement
     * @param yawDelta     degrees       camera yaw rotation this frame
     * @param pitchDelta   degrees       camera pitch rotation this frame
     * @param actionFlags  uint8 packed  see bit layout in class javadoc
     * @param hotbarSlot   0-8 = select slot, -1 = no change
     */
    public static void executeAction(float moveForward, float moveStrafe,
                                     float yawDelta,    float pitchDelta,
                                     byte  actionFlags, int   hotbarSlot) {
        Minecraft   mc     = Minecraft.getInstance();
        LocalPlayer player = mc.player;
        if (player == null) return;

        if (attackUseCooldownTicks > 0) attackUseCooldownTicks--;
        if (inventoryCooldownTicks > 0) inventoryCooldownTicks--;

        int     flags    = actionFlags & 0xFF;
        boolean jump     = (flags & 0b10000000) != 0;
        boolean sneak    = (flags & 0b01000000) != 0;
        boolean attack   = (flags & 0b00100000) != 0;
        boolean use      = (flags & 0b00010000) != 0;
        boolean drop     = (flags & 0b00001000) != 0;
        boolean openInv  = (flags & 0b00000100) != 0;
        boolean swapHand = (flags & 0b00000010) != 0;
        boolean sprint   = (flags & 0b00000001) != 0;

        // ── Camera rotation ───────────────────────────────────────────────
        if (yawDelta != 0f || pitchDelta != 0f) {
            player.turn(yawDelta, pitchDelta);
        }

        // ── Movement keys ─────────────────────────────────────────────────
        // KeyMapping.setDown() is Forge's API for programmatically pressing
        // vanilla key bindings. It updates the internal pressed state that
        // LocalPlayer.input (KeyboardInput) reads every tick.
        // This works correctly in Forge 1.20.1 / Parchment 47.4.10.
        mc.options.keyUp.setDown(moveForward >  0.3f);
        mc.options.keyDown.setDown(moveForward < -0.3f);
        mc.options.keyLeft.setDown(moveStrafe  < -0.3f);
        mc.options.keyRight.setDown(moveStrafe >  0.3f);
        mc.options.keyJump.setDown(jump);
        mc.options.keyShift.setDown(sneak);
        mc.options.keySprint.setDown(sprint);

        // ── Hotbar selection ──────────────────────────────────────────────
        if (hotbarSlot >= 0 && hotbarSlot <= 8) {
            player.getInventory().selected = hotbarSlot;
        }

        // ── Attack / Use (rate-limited) ───────────────────────────────────
        if (attackUseCooldownTicks == 0) {
            if (attack && mc.hitResult != null
                    && mc.hitResult.getType() == HitResult.Type.ENTITY) {
                net.minecraft.world.entity.Entity target =
                        ((EntityHitResult) mc.hitResult).getEntity();
                mc.gameMode.attack(player, target);
                attackUseCooldownTicks = ATTACK_USE_COOLDOWN;
            } else if (use) {
                mc.gameMode.useItem(player, InteractionHand.MAIN_HAND);
                attackUseCooldownTicks = ATTACK_USE_COOLDOWN;
            }
        }

        // ── Drop ──────────────────────────────────────────────────────────
        if (drop) {
            player.drop(false);
        }

        // ── Open inventory (rate-limited) ─────────────────────────────────
        // In Forge 1.20.1 the correct way is mc.setScreen(new InventoryScreen(player)).
        if (openInv && inventoryCooldownTicks == 0) {
            if (mc.screen == null) {
                mc.setScreen(new InventoryScreen(player));
            }
            inventoryCooldownTicks = INVENTORY_COOLDOWN;
        }

        // ── Swap hand ─────────────────────────────────────────────────────
        if (swapHand) {
            player.swing(InteractionHand.OFF_HAND);
        }
    }

    // =========================================================================
    // Inventory slot interaction
    // =========================================================================

    /**
     * Execute an inventory slot click in the currently open container.
     *
     * Called by TCPServer when the ability string starts with "inv:".
     * The string format is:  "inv:SLOT,BUTTON,CLICK_TYPE"
     *
     * Uses MultiPlayerGameMode.handleInventoryMouseClick() which:
     *   1. Calls the container's slotClick() for local prediction.
     *   2. Sends ServerboundContainerClickPacket to the server.
     *   3. Server validates and applies; ClientboundContainerSetSlotPacket
     *      corrects any prediction error.
     *
     * This is identical to what happens when the player manually clicks
     * a slot with a real mouse — fully server-authoritative.
     *
     * Forge 1.20.1 / Parchment 47.4.10:
     *   MultiPlayerGameMode.handleInventoryMouseClick(int, int, int, ClickType, Player)
     */
    public static void executeInventoryAction(String actionString) {
        if (actionString == null || !actionString.startsWith("inv:")) return;

        Minecraft   mc     = Minecraft.getInstance();
        LocalPlayer player = mc.player;
        if (player == null || mc.gameMode == null) return;

        try {
            String   payload = actionString.substring(4);
            String[] parts   = payload.split(",");
            if (parts.length < 1) return;

            int slotId   = Integer.parseInt(parts[0].trim());
            int button   = parts.length > 1 ? Integer.parseInt(parts[1].trim()) : 0;
            int ctOrd    = parts.length > 2 ? Integer.parseInt(parts[2].trim()) : 0;

            // Guard: valid ClickType ordinal
            ClickType[] types = ClickType.values();
            ClickType clickType = types[Math.max(0, Math.min(ctOrd, types.length - 1))];

            // containerId from the currently open container menu.
            // For the player inventory: InventoryMenu with containerId = 0.
            // For external containers (CraftingTable, etc.): the id assigned
            // by the server when it sent ClientboundOpenScreenPacket.
            int containerId = player.containerMenu.containerId;

            mc.gameMode.handleInventoryMouseClick(
                containerId, slotId, button, clickType, player);

            DWClientMod.LOGGER.debug(
                "[ActionExecutor] inv click — container={} slot={} btn={} type={}",
                containerId, slotId, button, clickType);

        } catch (NumberFormatException | ArrayIndexOutOfBoundsException e) {
            DWClientMod.LOGGER.debug(
                "[ActionExecutor] Invalid inv action '{}': {}", actionString, e.getMessage());
        } catch (Exception e) {
            DWClientMod.LOGGER.warn(
                "[ActionExecutor] inv action failed: {}", e.getMessage());
        }
    }

    // =========================================================================
    // Screen control actions
    // =========================================================================

    /**
     * Handle screen control actions dispatched by TCPServer.
     * String format:  "screen:COMMAND"
     *
     *   screen:close   — closes any open GUI (sends close packet to server).
     *   screen:inv     — opens the player inventory screen.
     */
    public static void executeScreenAction(String actionString) {
        if (actionString == null || !actionString.startsWith("screen:")) return;

        Minecraft   mc     = Minecraft.getInstance();
        LocalPlayer player = mc.player;
        if (player == null) return;

        String cmd = actionString.substring(7).trim().toLowerCase();
        switch (cmd) {
            case "close" -> {
                if (mc.screen != null) {
                    // mc.setScreen(null) closes the screen AND sends
                    // ServerboundContainerClosePacket to the server automatically.
                    mc.setScreen(null);
                    DWClientMod.LOGGER.debug("[ActionExecutor] Screen closed");
                }
            }
            case "inv" -> {
                if (mc.screen == null && inventoryCooldownTicks == 0) {
                    mc.setScreen(new InventoryScreen(player));
                    inventoryCooldownTicks = INVENTORY_COOLDOWN;
                    DWClientMod.LOGGER.debug("[ActionExecutor] Inventory opened");
                }
            }
            default -> DWClientMod.LOGGER.debug(
                "[ActionExecutor] Unknown screen command: {}", cmd);
        }
    }
}