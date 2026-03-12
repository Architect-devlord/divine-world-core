// src/main/java/com/divineworld/client/control/ActionExecutor.java
package com.divineworld.client.control;

import com.divineworld.client.DWClientMod;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.InteractionHand;

/**
 * ActionExecutor — applies a decoded action frame to the local Minecraft player.
 *
 * CALL CONVENTION (critical):
 * ───────────────────────────
 * executeAction() MUST be called on the Minecraft main thread.
 * Both callers (TCPServer, WebSocketManager) already wrap the call inside
 * Minecraft.getInstance().execute(() -> { ... }), so this method applies
 * inputs synchronously without any further scheduling.
 *
 * God ability dispatch is handled by the callers, not here:
 *   TCPServer     → reads god_ability section, calls GodEntityManager.executeGodAbility()
 *   WebSocketManager → reads god_ability section, calls GodEntityManager.executeGodAbility()
 * This keeps ActionExecutor single-responsibility: movement + boolean inputs only.
 *
 * FIX Bug A (compile crash):
 * ──────────────────────────
 * The previous version declared executeAction(byte[] data) and attempted to
 * parse the full binary frame internally. Both callers (TCPServer and
 * WebSocketManager) parse frames themselves and call with individual values,
 * making the byte[] signature a compile error at every call-site.
 *
 * Fix: changed to the 6-parameter flat signature both callers already expect.
 * Frame parsing responsibility stays in the caller, which is the correct
 * design: TCPServer reads a TCP stream (no MAGIC header); WebSocketManager
 * reads a WebSocket message (has MAGIC+FRAME_ACTION header). Each format
 * differs — ActionExecutor should not handle both.
 *
 * Action flags byte layout (bit 7 = MSB):
 *   bit 7  jump
 *   bit 6  sneak
 *   bit 5  attack
 *   bit 4  use
 *   bit 3  drop
 *   bit 2  open_inv
 *   bit 1  swap_hand
 *   bit 0  sprint
 * Matches Python: communication_protocol.BinaryProtocol.dict_to_action_flags()
 *             and actuators.ForgeIPCClient.send_action() flags packing.
 */
public class ActionExecutor {

    /** Minimum ticks between attack or use actions — prevents spam clicks. */
    private static final int ATTACK_USE_COOLDOWN = 4;
    /** Minimum ticks between inventory-open actions. */
    private static final int INVENTORY_COOLDOWN  = 20;

    private static int attackUseCooldownTicks = 0;
    private static int inventoryCooldownTicks = 0;

    // -------------------------------------------------------------------------
    // Public entry point
    // -------------------------------------------------------------------------

    /**
     * Apply one decoded action frame to the local player.
     *
     * Must be called on the Minecraft main thread.
     * Callers (TCPServer, WebSocketManager) schedule this inside
     * Minecraft.getInstance().execute() — do NOT add further scheduling here.
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

        Minecraft mc = Minecraft.getInstance();
        LocalPlayer player = mc.player;
        if (player == null) return;

        // ── Cooldown tick ─────────────────────────────────────────────────────
        if (attackUseCooldownTicks > 0) attackUseCooldownTicks--;
        if (inventoryCooldownTicks > 0) inventoryCooldownTicks--;

        // Expand packed flags byte — treat as unsigned to avoid sign-bit issues
        int flags    = actionFlags & 0xFF;
        boolean jump     = (flags & 0b10000000) != 0;
        boolean sneak    = (flags & 0b01000000) != 0;
        boolean attack   = (flags & 0b00100000) != 0;
        boolean use      = (flags & 0b00010000) != 0;
        boolean drop     = (flags & 0b00001000) != 0;
        boolean openInv  = (flags & 0b00000100) != 0;
        boolean swapHand = (flags & 0b00000010) != 0;
        boolean sprint   = (flags & 0b00000001) != 0;

        // ── Camera rotation ───────────────────────────────────────────────────
        if (yawDelta != 0f || pitchDelta != 0f) {
            player.turn(yawDelta, pitchDelta);
        }

        // ── Movement keys ─────────────────────────────────────────────────────
        // Drive vanilla key bindings so physics (gravity, collisions, sprinting)
        // work exactly as for a real player.
        mc.options.keyUp.setDown(moveForward >  0.3f);
        mc.options.keyDown.setDown(moveForward < -0.3f);
        mc.options.keyLeft.setDown(moveStrafe  < -0.3f);
        mc.options.keyRight.setDown(moveStrafe >  0.3f);
        mc.options.keyJump.setDown(jump);
        mc.options.keyShift.setDown(sneak);
        mc.options.keySprint.setDown(sprint);

        // ── Hotbar selection ──────────────────────────────────────────────────
        if (hotbarSlot >= 0 && hotbarSlot <= 8) {
            player.getInventory().selected = hotbarSlot;
        }

        // ── Attack / Use (rate-limited) ───────────────────────────────────────
        if (attackUseCooldownTicks == 0) {
            if (attack && mc.hitResult != null) {
                mc.gameMode.attack(player, player);
                attackUseCooldownTicks = ATTACK_USE_COOLDOWN;
            } else if (use) {
                mc.gameMode.useItem(player, InteractionHand.MAIN_HAND);
                attackUseCooldownTicks = ATTACK_USE_COOLDOWN;
            }
        }

        // ── Drop ──────────────────────────────────────────────────────────────
        if (drop) {
            player.drop(false);
        }

        // ── Open inventory (rate-limited) ─────────────────────────────────────
        // FIX: LocalPlayer does not have openInventory() in Forge 1.20.1.
        // The correct approach is to call mc.setScreen() with a new InventoryScreen.
        // This is exactly what vanilla does internally when the player presses 'E'.
        if (openInv && inventoryCooldownTicks == 0) {
            if (mc.screen == null) {
                mc.setScreen(new InventoryScreen(player));
            }
            inventoryCooldownTicks = INVENTORY_COOLDOWN;
        }

        // ── Swap hand ─────────────────────────────────────────────────────────
        if (swapHand) {
            player.swing(InteractionHand.OFF_HAND);
        }
    }
}