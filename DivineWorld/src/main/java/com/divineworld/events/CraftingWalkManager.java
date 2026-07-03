// src/main/java/com/divineworld/events/CraftingWalkManager.java
// DivineWorld server mod — Forge 1.20.1
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.utils.AStarPathfinder;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.CraftingRecipe;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.*;

/**
 * Guided crafting sequence — /craft command support.
 *
 * Same "control overridden, not consciousness" principle as
 * BreedingWalkManager (see that class's doc for the full rationale): while
 * a session is WALKING, this class forces the agent's position/rotation
 * every server tick, but nothing here touches the perception pipeline — the
 * agent keeps observing and remembering everything normally throughout.
 *
 * Two modes:
 *   INVENTORY  — no walk needed (recipe fits the player's own 2×2 grid).
 *                Craft executes immediately on the same tick /craft was run.
 *   TABLE      — walk to a pre-located crafting table (found by CraftCommand
 *                via the same 20-block-radius search idiom BreedCommand
 *                uses for beds), then craft on arrival.
 *
 * VERSION NOTE: targets Forge 1.20.1. See CraftCommand.java's class doc for
 * the RecipeHolder/RegistryAccess version details this file's CraftingRecipe
 * usage depends on.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class CraftingWalkManager {

    private static final double WALK_SPEED_PER_TICK = 0.22;
    private static final double WAYPOINT_EPSILON    = 0.3;
    /** How close to the table counts as "arrived" — close enough to interact. */
    private static final double TABLE_ARRIVAL_RADIUS = 2.0;

    private enum Phase { WALKING, ARRIVED, DONE, FAILED }
    private enum Mode  { INVENTORY, TABLE }

    private static final class Session {
        final ServerPlayer     player;
        final Mode             mode;
        final CraftingRecipe   recipe;
        final ItemStack        result;
        final Map<Integer, ItemStack[]> slotAssignments;
        final BlockPos         tablePos;     // null for INVENTORY mode
        List<BlockPos>         path;
        int                    pathIndex = 0;
        Phase                  phase = Phase.WALKING;

        Session(ServerPlayer player, Mode mode, CraftingRecipe recipe, ItemStack result,
                Map<Integer, ItemStack[]> slotAssignments, BlockPos tablePos) {
            this.player = player; this.mode = mode; this.recipe = recipe;
            this.result = result; this.slotAssignments = slotAssignments;
            this.tablePos = tablePos;
        }
    }

    private static final List<Session> ACTIVE = new ArrayList<>();

    // =========================================================================
    // Entry points — called by CraftCommand after all validation passes
    // =========================================================================

    /**
     * Craft immediately using the player's 2×2 inventory grid — no walk
     * needed since this recipe already fits it.
     */
    public static boolean startInventoryCraft(ServerPlayer player, CraftingRecipe recipe,
                                                ItemStack result,
                                                Map<Integer, ItemStack[]> slotAssignments) {
        Session session = new Session(player, Mode.INVENTORY, recipe, result, slotAssignments, null);
        // No walk phase at all for inventory crafting — execute right away.
        executeCraft(session);
        player.sendSystemMessage(Component.literal(
                "§aYou craft §e" + result.getHoverName().getString() + "§a using your own inventory."));
        DWMod.LOGGER.info("[Crafting] {} inventory-crafted {}",
                player.getName().getString(), result.getItem());
        return true;
    }

    /**
     * Walk to a pre-located crafting table, then craft on arrival.
     */
    public static boolean startTableCraft(ServerPlayer player, BlockPos tablePos,
                                            CraftingRecipe recipe, ItemStack result,
                                            Map<Integer, ItemStack[]> slotAssignments) {
        ServerLevel level = player.serverLevel();
        List<BlockPos> path = AStarPathfinder.findPath(
                level, player.blockPosition(), tablePos, 28, 4000);

        if (path == null) {
            DWMod.LOGGER.warn("[Crafting] Pathfinding failed for {} to crafting table at {}",
                    player.getName().getString(), tablePos);
            return false;
        }

        Session session = new Session(player, Mode.TABLE, recipe, result, slotAssignments, tablePos);
        session.path = path;

        player.getPersistentData().putBoolean("dw_crafting_walk_active", true);
        ACTIVE.add(session);

        player.sendSystemMessage(Component.literal(
                "§dYou feel drawn toward a crafting table..."));

        DWMod.LOGGER.info("[Crafting] Walk session started: {} -> table at {} (path {} steps)",
                player.getName().getString(), tablePos, path.size());
        return true;
    }

    public static boolean isCraftActive(ServerPlayer player) {
        for (Session s : ACTIVE) {
            if (s.player == player) return true;
        }
        return false;
    }

    // =========================================================================
    // Tick handler — Phase.END, same pattern as BreedingWalkManager
    // =========================================================================

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        if (ACTIVE.isEmpty()) return;

        Iterator<Session> it = ACTIVE.iterator();
        while (it.hasNext()) {
            Session s = it.next();
            tickSession(s);
            if (s.phase == Phase.DONE || s.phase == Phase.FAILED) {
                cleanupSession(s);
                it.remove();
            }
        }
    }

    private static void tickSession(Session s) {
        if (!s.player.isAlive()) {
            failSession(s, s.player.getName().getString() + " has died. Crafting will not be possible.");
            return;
        }

        switch (s.phase) {
            case WALKING -> tickWalking(s);
            case ARRIVED -> tickArrived(s);
            default -> {}
        }
    }

    private static void tickWalking(Session s) {
        BlockPos targetBlock = s.path.get(Math.min(s.pathIndex, s.path.size() - 1));
        Vec3 target  = Vec3.atBottomCenterOf(targetBlock);
        Vec3 current = s.player.position();
        Vec3 toTarget = target.subtract(current);
        double dist = toTarget.length();

        if (dist < WAYPOINT_EPSILON) {
            s.pathIndex++;
            if (s.pathIndex >= s.path.size()) {
                s.phase = Phase.ARRIVED;
                return;
            }
        } else {
            Vec3 step = toTarget.scale(Math.min(1.0, WALK_SPEED_PER_TICK / dist));
            Vec3 next = current.add(step);
            float yaw = (float) (Math.toDegrees(Math.atan2(-toTarget.x, toTarget.z)));
            s.player.moveTo(next.x, next.y, next.z, yaw, 0f);
            s.player.setYHeadRot(yaw);
        }

        // Table may have been broken mid-walk — check every tick, fail early
        // rather than arriving at an empty space.
        if (s.tablePos != null &&
                !(s.player.serverLevel().getBlockState(s.tablePos).getBlock()
                        instanceof net.minecraft.world.level.block.CraftingTableBlock)) {
            failSession(s, "The crafting table is no longer there.");
        }
    }

    private static void tickArrived(Session s) {
        double distSq = s.player.position().distanceTo(Vec3.atCenterOf(s.tablePos));
        if (distSq > TABLE_ARRIVAL_RADIUS) {
            // Shouldn't normally happen (path ends adjacent to the table),
            // but guard against an edge case where the last waypoint wasn't
            // quite close enough — nudge one more step rather than failing.
            s.phase = Phase.WALKING;
            return;
        }

        executeCraft(s);
        s.player.sendSystemMessage(Component.literal(
                "§aYou craft §e" + s.result.getHoverName().getString() + "§a at the crafting table."));
        DWMod.LOGGER.info("[Crafting] {} table-crafted {}",
                s.player.getName().getString(), s.result.getItem());
        s.phase = Phase.DONE;
    }

    // =========================================================================
    // Actual craft execution — consume ingredients, produce result
    // =========================================================================

    /**
     * Directly manipulates the agent's inventory: removes the required
     * ingredient counts (matching CraftCommand.checkInventory()'s own
     * counting logic exactly, so what was validated is what gets consumed),
     * then adds the crafted result.
     *
     * This is server-authoritative inventory manipulation — the same
     * category of operation vanilla's own /give command performs — rather
     * than simulating a client GUI click sequence. We've already resolved
     * the exact recipe and confirmed ingredient availability in
     * CraftCommand, so there's nothing left for a live CraftingContainer/
     * Menu simulation to determine that we don't already know.
     */
    private static void executeCraft(Session s) {
        var inventory = s.player.getInventory();

        // Re-derive required counts per canonical item (mirrors
        // CraftCommand.buildIngredientMap's collapsing logic) so we consume
        // exactly what was validated, not a slot-by-slot removal that could
        // double-remove a shared ingredient appearing in multiple slots.
        Map<String, Integer> toConsume = new LinkedHashMap<>();
        Map<String, ItemStack[]> candidatesByKey = new LinkedHashMap<>();
        for (ItemStack[] candidates : s.slotAssignments.values()) {
            if (candidates.length == 0) continue;
            String key = keyOf(candidates[0]);
            toConsume.merge(key, 1, Integer::sum);
            candidatesByKey.put(key, candidates);
        }

        for (Map.Entry<String, Integer> entry : toConsume.entrySet()) {
            int remaining = entry.getValue();
            ItemStack[] candidates = candidatesByKey.get(entry.getKey());

            for (int i = 0; i < inventory.items.size() && remaining > 0; i++) {
                ItemStack stack = inventory.items.get(i);
                if (stack.isEmpty()) continue;
                boolean matches = false;
                for (ItemStack candidate : candidates) {
                    if (keyOf(stack).equals(keyOf(candidate))) { matches = true; break; }
                }
                if (!matches) continue;

                int take = Math.min(remaining, stack.getCount());
                stack.shrink(take);
                remaining -= take;
            }
        }

        boolean added = inventory.add(s.result.copy());
        if (!added) {
            // Inventory was full — drop the result at the agent's feet
            // rather than silently discarding it.
            s.player.level().addFreshEntity(new net.minecraft.world.entity.item.ItemEntity(
                    s.player.level(), s.player.getX(), s.player.getY(), s.player.getZ(), s.result.copy()));
        }
    }

    private static String keyOf(ItemStack stack) {
        var rl = net.minecraftforge.registries.ForgeRegistries.ITEMS.getKey(stack.getItem());
        return rl != null ? rl.toString() : "minecraft:air";
    }

    private static void failSession(Session s, String reason) {
        s.phase = Phase.FAILED;
        if (s.player.isAlive()) {
            s.player.sendSystemMessage(Component.literal("§c[Crafting] " + reason));
        }
        DWMod.LOGGER.info("[Crafting] Walk session failed: {}", reason);
    }

    private static void cleanupSession(Session s) {
        if (s.player.isAlive()) {
            s.player.getPersistentData().remove("dw_crafting_walk_active");
        }
    }
}