// src/main/java/com/divineworld/commands/BreedCommand.java
// DivineWorld server mod
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.events.BreedingEventHandler;
import com.divineworld.events.BreedingWalkManager;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.level.block.BedBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.BedPart;

import java.util.ArrayList;
import java.util.List;

/**
 * /breed <agent_a> <agent_b> — guided breeding sequence.
 *
 * Distinct from the ambient proximity-based breeding system
 * (BreedingEventHandler.onServerTick) — this is an explicitly-triggered
 * sequence intended to teach early/new agents the bed-breeding mechanic by
 * walking them there directly, rather than waiting for them to discover it
 * by wandering near beds on their own.
 *
 * Validation order (matches the original spec exactly):
 *   1. Both names resolve to online AI agents (NPC or god)
 *   2. Gender/god compatibility — reuses BreedingEventHandler.areGendersCompatible(),
 *      the same predicate the ambient system already uses. Exact role
 *      resolution (including the dual-god random-assignment / role-flip
 *      logic) is NOT duplicated here — that already lives in, and is
 *      correctly handled by, breeding_system.py's initiate_breeding(),
 *      which BreedingWalkManager triggers once both agents are asleep.
 *   3. Two ADJACENT beds exist within 20 blocks of the search anchor
 *      (anchor = agent A's position at the moment the command is issued —
 *      see findAdjacentBedPair() for why "adjacent" means two complete,
 *      separate beds positioned next to each other, not just "two bed
 *      blocks somewhere in the area").
 *   4. Both agents within 20 blocks of that same anchor.
 *   5. It's night or a thunderstorm (Level.isDay() already accounts for
 *      both — see comment on the check below).
 *   6. Hand off to BreedingWalkManager for the actual A*-pathfind-and-sleep
 *      sequence; death-during-walk and conditions-changed-during-walk are
 *      both handled there, not here.
 */
public class BreedCommand {

    private static final double SEARCH_RADIUS = 20.0;

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("breed")
                .requires(src -> src.hasPermission(2))
                .then(Commands.argument("agent_a", StringArgumentType.string())
                        .then(Commands.argument("agent_b", StringArgumentType.string())
                                .executes(BreedCommand::executeBreed)
                        )
                )
        );
        DWMod.LOGGER.info("[BreedCommand] Registered /breed <agent_a> <agent_b>");
    }

    private static int executeBreed(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack source = ctx.getSource();
        String nameA = StringArgumentType.getString(ctx, "agent_a");
        String nameB = StringArgumentType.getString(ctx, "agent_b");

        try {
            ServerLevel level = source.getLevel();

            // ── Step 1: resolve both names to online AI agents ───────────
            ServerPlayer a = findAgentByName(level, nameA);
            ServerPlayer b = findAgentByName(level, nameB);

            if (a == null) {
                source.sendFailure(Component.literal("§cAgent not found or not online: " + nameA));
                return 0;
            }
            if (b == null) {
                source.sendFailure(Component.literal("§cAgent not found or not online: " + nameB));
                return 0;
            }
            if (a == b) {
                source.sendFailure(Component.literal("§cAn agent cannot breed with itself."));
                return 0;
            }
            if (a.level() != b.level()) {
                source.sendFailure(Component.literal(
                        "§c" + nameA + " and " + nameB + " are too far away (different dimensions)."));
                return 0;
            }

            // ── Step 2: gender / god compatibility ───────────────────────
            String genderA = a.getPersistentData().getString("dw_gender");
            String genderB = b.getPersistentData().getString("dw_gender");
            boolean validGenderTags =
                    ("male".equals(genderA) || "female".equals(genderA) || "dual".equals(genderA)) &&
                    ("male".equals(genderB) || "female".equals(genderB) || "dual".equals(genderB));

            if (!validGenderTags || !BreedingEventHandler.areGendersCompatible(genderA, genderB)) {
                source.sendSuccess(() -> Component.literal(
                        "§e" + nameA + " and " + nameB + " can't breed."), false);
                return 0;
            }

            // Already mid-walk, pregnant, on cooldown, etc. — those are all
            // re-validated authoritatively by Python's check_can_breed() once
            // triggered; we only need to avoid double-starting a walk here.
            if (BreedingWalkManager.isWalkActive(a) || BreedingWalkManager.isWalkActive(b)) {
                source.sendFailure(Component.literal(
                        "§e" + nameA + " or " + nameB + " is already in the middle of a breeding sequence."));
                return 0;
            }

            // ── Step 3: two ADJACENT beds within 20 blocks ───────────────
            // Anchor = agent A's position — see class doc for rationale
            // (simple, deterministic, standard "radius around an entity"
            // idiom; B's distance to this same anchor is the meaningful
            // half of the check below).
            BlockPos anchor = a.blockPosition();
            BedPair beds = findAdjacentBedPair(level, anchor, SEARCH_RADIUS);

            if (beds == null) {
                source.sendSuccess(() -> Component.literal(
                        "§eNo two adjacent beds are available within " + (int) SEARCH_RADIUS
                                + " blocks of " + nameA + "."), false);
                return 0;
            }

            // ── Step 4: both agents within the same 20-block radius ──────
            double distA = a.position().distanceTo(net.minecraft.world.phys.Vec3.atCenterOf(anchor));
            double distB = b.position().distanceTo(net.minecraft.world.phys.Vec3.atCenterOf(anchor));
            if (distA > SEARCH_RADIUS || distB > SEARCH_RADIUS) {
                String farName = distB > SEARCH_RADIUS ? nameB : nameA;
                source.sendSuccess(() -> Component.literal(
                        "§e" + farName + " is too far away."), false);
                return 0;
            }

            // ── Step 5: night or thunderstorm ────────────────────────────
            // Level.isDay() == skyDarken < 4, and skyDarken already rises
            // during rain/thunder — so !isDay() is true during BOTH actual
            // night AND a thunderstorm during the day, exactly matching the
            // vanilla bed-sleeping eligibility rule and exactly what was
            // asked for, with no separate weather check needed.
            if (level.isDay()) {
                source.sendSuccess(() -> Component.literal(
                        "§eAgents can only breed at night or during a thunderstorm."), false);
                return 0;
            }

            // ── Step 6: assign beds (closer bed to closer agent) and start ──
            BlockPos bedForA = beds.head1;
            BlockPos bedForB = beds.head2;
            double directDistSq   = a.distanceToSqr(bedForA.getX(), bedForA.getY(), bedForA.getZ())
                                   + b.distanceToSqr(bedForB.getX(), bedForB.getY(), bedForB.getZ());
            double swappedDistSq  = a.distanceToSqr(bedForB.getX(), bedForB.getY(), bedForB.getZ())
                                   + b.distanceToSqr(bedForA.getX(), bedForA.getY(), bedForA.getZ());
            if (swappedDistSq < directDistSq) {
                BlockPos tmp = bedForA; bedForA = bedForB; bedForB = tmp;
            }

            boolean started = BreedingWalkManager.startWalk(a, b, bedForA, bedForB);
            if (!started) {
                source.sendFailure(Component.literal(
                        "§cFound adjacent beds, but " + nameA + " or " + nameB
                                + " could not find a walkable path to them."));
                return 0;
            }

            source.sendSuccess(() -> Component.literal(
                    "§a" + nameA + " and " + nameB + " are making their way to bed..."), true);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("[BreedCommand] /breed failed", e);
            source.sendFailure(Component.literal("§c[Breed] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // Agent lookup
    // =========================================================================

    private static ServerPlayer findAgentByName(ServerLevel level, String name) {
        for (ServerPlayer p : level.getServer().getPlayerList().getPlayers()) {
            if (!p.getName().getString().equalsIgnoreCase(name)) continue;
            if (DWNPCManager.isAIPlayer(p) || DWNPCManager.isGodPlayer(p)) return p;
        }
        return null;
    }

    // =========================================================================
    // Adjacent-bed-pair detection
    // =========================================================================

    private record BedPair(BlockPos head1, BlockPos head2) {}

    /**
     * Find two DISTINCT, separate beds positioned next to each other within
     * radius blocks of anchor — e.g. a bunk-style or side-by-side bedroom
     * layout, not just "two bed blocks somewhere in the area" (which could
     * be the head+foot of a SINGLE bed, or two unrelated beds far apart).
     *
     * Search box is capped to ±8 vertically (vs. the full ±20 horizontally)
     * — a realistic "nearby bedroom" is very unlikely to be 20 blocks
     * straight up or down, and this keeps the scan (~41×41×17 ≈ 28k block
     * reads) fast for a single on-demand command call.
     *
     * Returns the HEAD position of each bed (the position vanilla's own
     * BedBlock.use() always resolves to before calling
     * Player.startSleepInBed() — see method doc on BreedingWalkManager.trySleep()),
     * or null if no adjacent pair was found.
     */
    private static BedPair findAdjacentBedPair(ServerLevel level, BlockPos anchor, double radius) {
        int rH = (int) Math.ceil(radius);
        int rV = 8;
        double rSq = radius * radius;

        List<BlockPos> headPositions = new ArrayList<>();

        for (int dx = -rH; dx <= rH; dx++) {
            for (int dz = -rH; dz <= rH; dz++) {
                if (dx * dx + dz * dz > rSq) continue;
                for (int dy = -rV; dy <= rV; dy++) {
                    BlockPos pos = anchor.offset(dx, dy, dz);
                    BlockState state = level.getBlockState(pos);
                    if (!(state.getBlock() instanceof BedBlock)) continue;

                    BlockPos headPos = resolveHeadPos(state, pos);
                    if (!headPositions.contains(headPos)) {
                        headPositions.add(headPos);
                    }
                }
            }
        }

        if (headPositions.size() < 2) return null;

        // Find the first pair where any block of bed1 (head or foot) is
        // horizontally adjacent (distance 1, same Y) to any block of bed2.
        for (int i = 0; i < headPositions.size(); i++) {
            BlockPos head1 = headPositions.get(i);
            BlockPos foot1 = resolveFootPos(level, head1);
            for (int j = i + 1; j < headPositions.size(); j++) {
                BlockPos head2 = headPositions.get(j);
                BlockPos foot2 = resolveFootPos(level, head2);

                if (isHorizontallyAdjacent(head1, head2) || isHorizontallyAdjacent(head1, foot2)
                        || isHorizontallyAdjacent(foot1, head2) || isHorizontallyAdjacent(foot1, foot2)) {
                    return new BedPair(head1, head2);
                }
            }
        }
        return null;
    }

    /** Resolve any bed block (head or foot) to its HEAD position. */
    private static BlockPos resolveHeadPos(BlockState state, BlockPos pos) {
        if (state.getValue(BedBlock.PART) == BedPart.HEAD) return pos;
        return pos.relative(state.getValue(BedBlock.FACING));
    }

    /** Given a known HEAD position, resolve the corresponding FOOT position. */
    private static BlockPos resolveFootPos(ServerLevel level, BlockPos headPos) {
        BlockState headState = level.getBlockState(headPos);
        return headPos.relative(headState.getValue(BedBlock.FACING).getOpposite());
    }

    private static boolean isHorizontallyAdjacent(BlockPos p1, BlockPos p2) {
        if (p1.getY() != p2.getY()) return false;
        int dx = Math.abs(p1.getX() - p2.getX());
        int dz = Math.abs(p1.getZ() - p2.getZ());
        return (dx + dz) == 1;   // exactly one step, one axis — orthogonal neighbor
    }
}