package com.divineworld.client;

import com.google.gson.JsonObject;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.MultiPlayerGameMode;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.InteractionHand;
import net.minecraft.client.gui.screens.inventory.InventoryScreen;

// remove ambiguous/wrong imports if present:
// import net.minecraft.client.player.ClientInput;
// import net.minecraft.world.entity.player.Input;

import net.minecraft.client.player.ClientInput; // Parchment name for client input
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.player.Input;


import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public class ActionExecutor {
    private static final Minecraft mc = Minecraft.getInstance();

    // Inside ActionExecutor
    public static void applyAction(String action) {
        queueSimpleAction(action, 1); // default 1 tick
    }

    public static void applyActionJson(JsonObject action) {
        queueAction(action);
    }

    public enum ActionKey {
        FORWARD, BACKWARD, LEFT, RIGHT, JUMP, SNEAK, SPRINT
    }

    private static final Map<ActionKey, Integer> keyHoldTicks = new EnumMap<>(ActionKey.class);
    static {
        for (ActionKey k : ActionKey.values()) keyHoldTicks.put(k, 0);
    }

    private static int leftClickTicks = 0;
    private static int rightClickTicks = 0;

    private static final List<JsonObject> actionQueue = new ArrayList<>();

    /** Queue a JSON action for processing */
    public static void queueAction(JsonObject action) {
        synchronized (actionQueue) {
            actionQueue.add(action);
        }
    }

    /** Queue a simple string action with optional hold ticks */
    public static void queueSimpleAction(String action, int ticks) {
        JsonObject json = new JsonObject();
        switch (action.toUpperCase()) {
            case "W": json.addProperty("move_forward", 1f); break;
            case "S": json.addProperty("move_forward", -1f); break;
            case "A": json.addProperty("move_strafe", -1f); break;
            case "D": json.addProperty("move_strafe", 1f); break;
            case "SPACE":
            case "JUMP": json.addProperty("jump", true); break;
            case "SHIFT": json.addProperty("sneak", true); break;
            case "LEFT_CLICK": json.addProperty("left_click_duration", ticks); break;
            case "RIGHT_CLICK": json.addProperty("right_click_duration", ticks); break;
            case "OPEN_INV": json.addProperty("open_inv", true); break;
            case "DROP": json.addProperty("drop", true); break;
            default: return;
        }

        if (ticks > 0) {
            switch (action.toUpperCase()) {
                case "W": json.addProperty("forward_ticks", ticks); break;
                case "S": json.addProperty("backward_ticks", ticks); break;
                case "A": json.addProperty("left_ticks", ticks); break;
                case "D": json.addProperty("right_ticks", ticks); break;
                case "SPACE":
                case "JUMP": json.addProperty("jump_ticks", ticks); break;
                case "SHIFT": json.addProperty("sneak_ticks", ticks); break;
            }
        }

        queueAction(json);
    }

    /** Process all queued actions (call once per tick) */
    public static void processQueuedActions() {
        LocalPlayer player = mc.player;
        if (player == null) return;

        mc.execute(() -> {
            ClientInput input = player.input;

            synchronized (actionQueue) {
                for (JsonObject action : actionQueue) {
                    // Movement keys with duration
                    keyHoldTicks.put(ActionKey.FORWARD, Math.max(keyHoldTicks.get(ActionKey.FORWARD), action.has("forward_ticks") ? action.get("forward_ticks").getAsInt() : 0));
                    keyHoldTicks.put(ActionKey.BACKWARD, Math.max(keyHoldTicks.get(ActionKey.BACKWARD), action.has("backward_ticks") ? action.get("backward_ticks").getAsInt() : 0));
                    keyHoldTicks.put(ActionKey.LEFT, Math.max(keyHoldTicks.get(ActionKey.LEFT), action.has("left_ticks") ? action.get("left_ticks").getAsInt() : 0));
                    keyHoldTicks.put(ActionKey.RIGHT, Math.max(keyHoldTicks.get(ActionKey.RIGHT), action.has("right_ticks") ? action.get("right_ticks").getAsInt() : 0));
                    keyHoldTicks.put(ActionKey.JUMP, Math.max(keyHoldTicks.get(ActionKey.JUMP), action.has("jump_ticks") ? action.get("jump_ticks").getAsInt() : 0));
                    keyHoldTicks.put(ActionKey.SNEAK, Math.max(keyHoldTicks.get(ActionKey.SNEAK), action.has("sneak_ticks") ? action.get("sneak_ticks").getAsInt() : 0));

                    // Clicks
                    if (action.has("left_click_duration")) leftClickTicks = Math.max(leftClickTicks, action.get("left_click_duration").getAsInt());
                    if (action.has("right_click_duration")) rightClickTicks = Math.max(rightClickTicks, action.get("right_click_duration").getAsInt());

                    // Rotation
                    if (action.has("yaw_delta") || action.has("pitch_delta")) {
                        float yaw = action.has("yaw_delta") ? action.get("yaw_delta").getAsFloat() : 0f;
                        float pitch = action.has("pitch_delta") ? action.get("pitch_delta").getAsFloat() : 0f;
                        player.setYRot(player.getYRot() + yaw);
                        player.setXRot(player.getXRot() + pitch);
                    }

                    // Inventory / drop
                    if (action.has("open_inv") && action.get("open_inv").getAsBoolean()) mc.setScreen(new InventoryScreen(player));
                    if (action.has("drop") && action.get("drop").getAsBoolean()) player.drop(true);
                }
                actionQueue.clear();
            }

            // Apply movement based on ticks
            input.keyPresses = new Input(
                    keyHoldTicks.get(ActionKey.FORWARD) > 0,
                    keyHoldTicks.get(ActionKey.BACKWARD) > 0,
                    keyHoldTicks.get(ActionKey.LEFT) > 0,
                    keyHoldTicks.get(ActionKey.RIGHT) > 0,
                    keyHoldTicks.get(ActionKey.JUMP) > 0,
                    keyHoldTicks.get(ActionKey.SNEAK) > 0,
                    false
            );

            // Decrement key ticks
            keyHoldTicks.replaceAll((k, v) -> Math.max(0, v - 1));

            // Process clicks
            tickClicks(player);
        });
    }

    /** Properly handle left/right clicks */
    private static void tickClicks(LocalPlayer player) {
        MultiPlayerGameMode gameMode = mc.gameMode;
        if (gameMode == null) return;

        double reach = 4.5; // Default attack / interaction range

        // LEFT CLICK
        if (leftClickTicks > 0) {
            var hitResult = player.pick(reach, 0f, false);

            switch (hitResult.getType()) {
                case ENTITY -> {
                    // Attack entity under crosshair
                    var entityTarget = ((net.minecraft.world.phys.EntityHitResult) hitResult).getEntity();
                    if (entityTarget != null) {
                        gameMode.attack(player, entityTarget);
                    }
                }
                case BLOCK -> {
                    // Mine block under crosshair
                    var blockHit = (net.minecraft.world.phys.BlockHitResult) hitResult;
                    var pos = blockHit.getBlockPos();
                    var direction = blockHit.getDirection();

                    // Start or continue mining
                    if (!player.level().isEmptyBlock(pos)) {
                        gameMode.startDestroyBlock(pos, direction);
                        gameMode.continueDestroyBlock(pos, direction); // Keeps mining while held
                    }
                }
                default -> {}
            }

            leftClickTicks--;
        }

        // RIGHT CLICK
        if (rightClickTicks > 0) {
            gameMode.useItem(player, InteractionHand.MAIN_HAND);
            rightClickTicks--;
            if (rightClickTicks == 0) {
                gameMode.releaseUsingItem(player); // Stop using item when done
            }
        }
    }

}

