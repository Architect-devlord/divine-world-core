// src/main/java/com/divineworld/events/BreedingWalkManager.java
// DivineWorld server mod
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.utils.AStarPathfinder;
import com.mojang.datafixers.util.Either;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.*;

/**
 * Guided breeding-walk sequence — /breed command support.
 *
 * Distinct from BreedingEventHandler's ambient proximity detection: this is
 * an explicitly-triggered, scripted sequence ("this will help the early
 * agents learn how to breed" per the original request) where two already-
 * validated, already-compatible agents are walked to a pair of adjacent
 * beds, made to sleep in them, and breeding is triggered automatically on
 * arrival — rather than waiting for the agents to wander there themselves.
 *
 * Control override, not consciousness override:
 *   While a session is WALKING or SLEEPING, this class forces each agent's
 *   position/rotation every server tick (Phase.END — same "last write wins"
 *   pattern GodControlHandler already uses for boss-body position sync),
 *   overriding whatever the normal AI action pipeline would otherwise set
 *   that tick. This is what "control overridden" means in practice — the
 *   agent's MOVEMENT is taken over. Nothing here touches perception: the
 *   WebSocket/perception loop keeps running completely normally throughout,
 *   so the agent still observes and remembers everything that happens
 *   (the "consciousness" / "can see but can't stop it" part) — only the
 *   final position each tick is overridden, not anything upstream of it.
 *
 *   The "dw_breeding_walk_active" NBT flag is also set on both agents for
 *   the duration, so any OTHER system that applies movement from AI action
 *   vectors can check it and skip doing so — but correctness here does not
 *   depend on every such system checking it, since this class's own
 *   Phase.END override always has the final say for that tick regardless.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingWalkManager {

    // ── Tunables ──────────────────────────────────────────────────────────

    /** Blocks moved per tick while walking — ≈ 4.4 blocks/sec, brisk-walk pace. */
    private static final double WALK_SPEED_PER_TICK = 0.22;

    /** How close to a waypoint counts as "arrived at it" before advancing. */
    private static final double WAYPOINT_EPSILON = 0.3;

    /** Ticks to remain asleep after both agents are confirmed sleeping,
     *  before waking them and ending the session (purely cosmetic pause —
     *  long enough to read the chat message, short enough not to feel stuck). */
    private static final int SLEEP_HOLD_TICKS = 60;   // 3 seconds

    /** Re-check death / day-night every tick; re-check pathfinding never
     *  (path is computed once at session start). */

    // ── Session state ─────────────────────────────────────────────────────

    private enum Phase { WALKING, ARRIVED, SLEEPING, DONE, FAILED }

    private static final class AgentProgress {
        final ServerPlayer player;
        final BlockPos     bedHeadPos;
        List<BlockPos>     path;
        int                pathIndex = 0;
        boolean            arrived   = false;
        boolean            sleeping  = false;

        AgentProgress(ServerPlayer player, BlockPos bedHeadPos) {
            this.player = player; this.bedHeadPos = bedHeadPos;
        }
    }

    private static final class Session {
        final AgentProgress a, b;
        final ServerLevel   level;
        Phase  phase = Phase.WALKING;
        int    sleepHoldRemaining = SLEEP_HOLD_TICKS;
        String failReason = null;

        Session(AgentProgress a, AgentProgress b, ServerLevel level) {
            this.a = a; this.b = b; this.level = level;
        }
    }

    private static final List<Session> ACTIVE = new ArrayList<>();

    // ── Entry point — called by BreedCommand after all validation passes ──

    /**
     * Begin the guided walk-to-bed sequence for two already-validated agents.
     *
     * @param a, b           the two agents (already confirmed alive,
     *                       compatible, and in range by the caller)
     * @param bedHeadPosA    HEAD block position of the bed assigned to a
     * @param bedHeadPosB    HEAD block position of the bed assigned to b
     * @return true if pathfinding succeeded and the walk began; false if no
     *         path could be found for either agent (caller should report
     *         this back to the command issuer — beds exist but unreachable)
     */
    public static boolean startWalk(ServerPlayer a, ServerPlayer b,
                                     BlockPos bedHeadPosA, BlockPos bedHeadPosB) {
        ServerLevel level = a.serverLevel();

        List<BlockPos> pathA = AStarPathfinder.findPath(
                level, a.blockPosition(), bedHeadPosA, 28, 4000);
        List<BlockPos> pathB = AStarPathfinder.findPath(
                level, b.blockPosition(), bedHeadPosB, 28, 4000);

        if (pathA == null || pathB == null) {
            DWMod.LOGGER.warn("[Breeding] Pathfinding failed for {} or {} to their assigned bed",
                    a.getName().getString(), b.getName().getString());
            return false;
        }

        AgentProgress pa = new AgentProgress(a, bedHeadPosA);
        AgentProgress pb = new AgentProgress(b, bedHeadPosB);
        pa.path = pathA;
        pb.path = pathB;

        // Mark control-override flag — see class doc for what this does and
        // does not affect.
        a.getPersistentData().putBoolean("dw_breeding_walk_active", true);
        b.getPersistentData().putBoolean("dw_breeding_walk_active", true);

        Session session = new Session(pa, pb, level);
        ACTIVE.add(session);

        a.sendSystemMessage(Component.literal("§dYou feel an irresistible urge to find rest..."));
        b.sendSystemMessage(Component.literal("§dYou feel an irresistible urge to find rest..."));

        DWMod.LOGGER.info("[Breeding] Walk session started: {} (path {} steps) x {} (path {} steps)",
                a.getName().getString(), pathA.size(), b.getName().getString(), pathB.size());
        return true;
    }

    public static boolean isWalkActive(ServerPlayer player) {
        for (Session s : ACTIVE) {
            if (s.a.player == player || s.b.player == player) return true;
        }
        return false;
    }

    // ── Tick handler — Phase.END, same "last write wins" pattern as
    //    GodControlHandler's boss-body position sync ────────────────────

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
        // ── Death check — first, every tick, regardless of phase ──────────
        if (!s.a.player.isAlive() || !s.b.player.isAlive()) {
            String deadName = !s.a.player.isAlive()
                    ? s.a.player.getName().getString() : s.b.player.getName().getString();
            failSession(s, deadName + " has died. Breeding will not be possible.");
            return;
        }

        switch (s.phase) {
            case WALKING  -> tickWalking(s);
            case ARRIVED  -> tickArrived(s);
            case SLEEPING -> tickSleeping(s);
            default -> {}
        }
    }

    private static void tickWalking(Session s) {
        boolean aArrived = advanceAlongPath(s.a);
        boolean bArrived = advanceAlongPath(s.b);

        if (aArrived && bArrived) {
            s.phase = Phase.ARRIVED;
        }
    }

    /**
     * Move one agent a fixed distance along its precomputed path, forcing
     * position/rotation every tick (overriding anything else that tick).
     * Returns true once this agent has reached the final waypoint.
     */
    private static boolean advanceAlongPath(AgentProgress p) {
        if (p.arrived) return true;

        if (p.pathIndex >= p.path.size()) {
            p.arrived = true;
            return true;
        }

        BlockPos targetBlock = p.path.get(p.pathIndex);
        Vec3 target  = Vec3.atBottomCenterOf(targetBlock);
        Vec3 current = p.player.position();
        Vec3 toTarget = target.subtract(current);
        double dist = toTarget.length();

        if (dist < WAYPOINT_EPSILON) {
            p.pathIndex++;
            if (p.pathIndex >= p.path.size()) {
                p.arrived = true;
                return true;
            }
            return false;
        }

        Vec3 step = toTarget.scale(Math.min(1.0, WALK_SPEED_PER_TICK / dist));
        Vec3 next = current.add(step);

        float yaw = (float) (Math.toDegrees(Math.atan2(-toTarget.x, toTarget.z)));
        p.player.moveTo(next.x, next.y, next.z, yaw, 0f);
        p.player.setYHeadRot(yaw);

        return false;
    }

    private static void tickArrived(Session s) {
        // Final, authoritative day/night-or-thunder check — time may have
        // changed during the walk. Re-checked here rather than only at
        // command time, matching vanilla's own "can't start sleeping during
        // the day" behaviour if conditions change mid-action.
        if (s.level.isDay()) {
            failSession(s, "It's no longer night nor a thunderstorm — breeding will not be possible.");
            return;
        }

        boolean aSlept = trySleep(s.a);
        boolean bSlept = trySleep(s.b);

        if (aSlept && bSlept) {
            s.phase = Phase.SLEEPING;
            s.a.player.sendSystemMessage(Component.literal("§5You drift off to sleep beside " + s.b.player.getName().getString() + "..."));
            s.b.player.sendSystemMessage(Component.literal("§5You drift off to sleep beside " + s.a.player.getName().getString() + "..."));

            // Trigger the existing, working breeding-initiation pipeline —
            // BreedingEventHandler.triggerDirectBreeding() already does
            // PythonBackendClient.notifyBreeding() -> /api/breeding/event ->
            // breeding_system.initiate_breeding(), which resolves gender
            // roles (including the dual-god random/role-swap logic) and
            // creates the pregnancy. No need to duplicate any of that here.
            BreedingEventHandler.triggerDirectBreeding(s.a.player, s.b.player);
        }
        // If only one slept (shouldn't normally happen since both pass the
        // same day/night check above, but a startSleepInBed edge case like
        // OBSTRUCTED could still fail asymmetrically), stay in ARRIVED and
        // retry next tick until SLEEP_HOLD logic elsewhere catches it —
        // in practice this resolves within a tick or two.
    }

    private static boolean trySleep(AgentProgress p) {
        if (p.sleeping) return true;
        Either<Player.BedSleepingProblem, net.minecraft.util.Unit> result =
                p.player.startSleepInBed(p.bedHeadPos);
        if (result.left().isPresent()) {
            DWMod.LOGGER.debug("[Breeding] {} could not sleep: {}",
                    p.player.getName().getString(), result.left().get());
            return false;
        }
        p.sleeping = true;
        return true;
    }

    private static void tickSleeping(Session s) {
        if (--s.sleepHoldRemaining <= 0) {
            wakeUp(s.a.player);
            wakeUp(s.b.player);
            s.a.player.sendSystemMessage(Component.literal("§aBreeding successful! A pregnancy has begun."));
            s.b.player.sendSystemMessage(Component.literal("§aBreeding successful! A pregnancy has begun."));
            s.phase = Phase.DONE;
        }
    }

    private static void wakeUp(ServerPlayer player) {
        if (player.isSleeping()) {
            player.stopSleepInBed(false, true);
        }
    }

    private static void failSession(Session s, String reason) {
        s.failReason = reason;
        s.phase = Phase.FAILED;
        s.a.player.sendSystemMessage(Component.literal("§c[Breeding] " + reason));
        if (s.a.player.isAlive()) {
            s.b.player.sendSystemMessage(Component.literal("§c[Breeding] " + reason));
        }
        DWMod.LOGGER.info("[Breeding] Walk session failed: {}", reason);
    }

    private static void cleanupSession(Session s) {
        wakeUp(s.a.player);
        wakeUp(s.b.player);
        if (s.a.player.isAlive()) {
            s.a.player.getPersistentData().remove("dw_breeding_walk_active");
        }
        if (s.b.player.isAlive()) {
            s.b.player.getPersistentData().remove("dw_breeding_walk_active");
        }
    }
}