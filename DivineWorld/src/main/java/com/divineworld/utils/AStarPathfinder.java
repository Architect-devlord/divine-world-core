// src/main/java/com/divineworld/utils/AStarPathfinder.java
// DivineWorld server mod
package com.divineworld.utils;

import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.level.material.FluidState;

import java.util.*;

/**
 * Self-contained grid-based A* pathfinder over a ServerLevel's block grid.
 *
 * Why this exists rather than reusing vanilla's PathNavigation:
 * Vanilla's PathNavigation / WalkNodeEvaluator (the system every Mob uses for
 * movement) is built around Mob — NodeEvaluator.prepare(LevelReader, Mob)
 * requires a live Mob reference for size/AI-sensing data. The DivineWorld
 * agents being pathfound here (BreedingWalkManager's bed-walk sequence) are
 * ServerPlayer instances, not Mob subclasses — Player has no PathNavigation
 * at all. Rather than spawn a throwaway invisible Mob purely to borrow its
 * navigator (extra entity, extra edge cases), this is a standalone A*
 * implementation operating directly on the block grid, usable for any
 * Player-based or Mob-based entity alike.
 *
 * Scope/limits (intentional, not oversights):
 *   - 4-directional + diagonal horizontal movement, single-block step-up/
 *     step-down (matches typical mob movement capability, not full vanilla
 *     parkour/ladder/door logic).
 *   - Bounded search: maxRadius caps how far from the start the search may
 *     explore, maxNodes caps total node expansions. Both exist so a search
 *     in a complex area can't hang the server thread — this runs synchronously
 *     on the calling thread, so callers should keep maxNodes modest for
 *     anything invoked from a tick handler (a one-off command-triggered
 *     search wants accuracy more than speed, since it's a single call).
 *   - On failure (no path within budget), returns null. Callers should
 *     decide their own fallback (e.g. straight-line walk, or fail the task).
 */
public final class AStarPathfinder {

    private AStarPathfinder() {}

    /** One candidate step. dx/dz in {-1,0,1} (8-directional), dy in {-1,0,1} (step up/down/level). */
    private static final int[][] NEIGHBOR_OFFSETS = {
            {1,0,0},{-1,0,0},{0,0,1},{0,0,-1},
            {1,0,1},{1,0,-1},{-1,0,1},{-1,0,-1},
            // step up and step down variants for each horizontal direction
            {1,1,0},{-1,1,0},{0,1,1},{0,1,-1},
            {1,-1,0},{-1,-1,0},{0,-1,1},{0,-1,-1},
    };

    private static final class Node implements Comparable<Node> {
        final BlockPos pos;
        final double   gScore;
        final double   fScore;
        final Node     parent;

        Node(BlockPos pos, double gScore, double fScore, Node parent) {
            this.pos = pos; this.gScore = gScore; this.fScore = fScore; this.parent = parent;
        }

        @Override
        public int compareTo(Node o) { return Double.compare(this.fScore, o.fScore); }
    }

    /**
     * Find a walkable path from start to goal.
     *
     * @param level     the level to read block states from
     * @param start     starting block position (caller's feet position, floor()'d)
     * @param goal      target block position (also floor()'d feet position)
     * @param maxRadius search is abandoned once a node further than this
     *                  many blocks from start (Chebyshev distance) is reached
     * @param maxNodes  hard cap on node expansions — safety valve against
     *                  pathological search spaces
     * @return ordered list of waypoints from (just after start) to goal
     *         inclusive, or null if no path was found within budget
     */
    public static List<BlockPos> findPath(ServerLevel level, BlockPos start, BlockPos goal,
                                            int maxRadius, int maxNodes) {
        if (start.equals(goal)) return Collections.singletonList(goal);

        PriorityQueue<Node> open = new PriorityQueue<>();
        Map<BlockPos, Double> bestG = new HashMap<>();
        Set<BlockPos> closed = new HashSet<>();

        Node startNode = new Node(start, 0.0, heuristic(start, goal), null);
        open.add(startNode);
        bestG.put(start, 0.0);

        int expansions = 0;

        while (!open.isEmpty() && expansions < maxNodes) {
            Node current = open.poll();
            if (closed.contains(current.pos)) continue;
            closed.add(current.pos);
            expansions++;

            if (current.pos.equals(goal)) {
                return reconstructPath(current);
            }

            // Abandon branches that have wandered too far from the start —
            // keeps the search bounded even if the goal is unreachable.
            if (chebyshev(start, current.pos) > maxRadius) continue;

            for (int[] off : NEIGHBOR_OFFSETS) {
                BlockPos next = current.pos.offset(off[0], off[1], off[2]);
                if (closed.contains(next)) continue;
                if (!isWalkable(level, next, current.pos)) continue;

                // Diagonal moves cost more than orthogonal; vertical steps cost
                // a little extra too (discourages unnecessary stair-stepping
                // when a flat detour is available).
                double stepCost = (off[0] != 0 && off[2] != 0) ? 1.4142 : 1.0;
                if (off[1] != 0) stepCost += 0.5;

                double tentativeG = current.gScore + stepCost;
                Double knownG = bestG.get(next);
                if (knownG != null && tentativeG >= knownG) continue;

                bestG.put(next, tentativeG);
                double f = tentativeG + heuristic(next, goal);
                open.add(new Node(next, tentativeG, f, current));
            }
        }

        return null;   // no path found within budget
    }

    private static List<BlockPos> reconstructPath(Node end) {
        LinkedList<BlockPos> path = new LinkedList<>();
        Node cur = end;
        while (cur != null && cur.parent != null) {   // exclude the start node itself
            path.addFirst(cur.pos);
            cur = cur.parent;
        }
        return path;
    }

    private static double heuristic(BlockPos a, BlockPos b) {
        // Euclidean — admissible for this neighbor set (diagonal cost ≥ √2 exactly)
        double dx = a.getX() - b.getX();
        double dy = a.getY() - b.getY();
        double dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    private static int chebyshev(BlockPos a, BlockPos b) {
        return Math.max(Math.abs(a.getX() - b.getX()),
               Math.max(Math.abs(a.getY() - b.getY()), Math.abs(a.getZ() - b.getZ())));
    }

    /**
     * A position is walkable when:
     *   - the block at the position itself is passable (air, or a non-solid
     *     fluid-free space) — actual ground tolerance for shallow water,
     *   - the block one above has enough headroom (also passable),
     *   - the block one below is solid (something to stand on) UNLESS this
     *     is a step-down move FROM a position that itself had solid ground
     *     (handled implicitly — see fromPos parameter).
     *
     * fromPos lets a step-down move succeed even when descending onto a
     * ledge whose own "floor" is what we're stepping onto, rather than
     * requiring a full extra solid block below the destination too.
     */
    private static boolean isWalkable(ServerLevel level, BlockPos pos, BlockPos fromPos) {
        boolean selfPassable  = isPassable(level, pos);
        boolean aboveHeadroom = isPassable(level, pos.above());
        if (!selfPassable || !aboveHeadroom) return false;

        boolean hasFloor = level.getBlockState(pos.below()).isSolidRender(level, pos.below())
                || !level.getFluidState(pos.below()).isEmpty();
        return hasFloor;
    }

    private static boolean isPassable(ServerLevel level, BlockPos pos) {
        var state = level.getBlockState(pos);
        if (state.isAir()) return true;
        FluidState fluid = level.getFluidState(pos);
        if (!fluid.isEmpty() && !fluid.is(net.minecraft.tags.FluidTags.LAVA)) return true;   // shallow water OK
        return !state.isSolidRender(level, pos) && state.getCollisionShape(level, pos).isEmpty();
    }
}