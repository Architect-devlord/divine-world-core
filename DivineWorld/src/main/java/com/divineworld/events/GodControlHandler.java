// src/main/java/com/divineworld/events/GodControlHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.boss.enderdragon.EnderDragon;
import net.minecraft.world.entity.boss.wither.WitherBoss;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * GodControlHandler — synchronises the god body entity with the invisible
 * player puppet every server tick, and vice-versa when the body drifts.
 *
 * Data-flow
 * ---------
 * 1. Python backend → TCPServer (port 8765, client side).
 * 2. ActionExecutor sets player input flags on the client.
 * 3. Vanilla netcode sends the updated position to the server.
 * 4. THIS handler reads the server-side player position every tick and
 *    pushes it to the boss entity so it visually follows the agent.
 *
 * Previously fixed (Bugs 2 & 9):
 *   - Removed player.moveTo(godEntity.Y + 100) that caused flying gods to
 *     rocket to the sky ceiling.
 *   - Ground gods only teleport when displacement > GROUND_MOVE_SQ, avoiding
 *     per-tick position spam while the agent stands still.
 *
 * FIX Bug 11 — one-directional sync causes drift after ability knockback
 * -----------------------------------------------------------------------
 * Vanilla knockback, explosion blasts, and ability effects (sonic boom,
 * wither skull hits) physically displace the boss body entity each tick.
 * The old code only synced puppet → body, never the reverse, so:
 *
 *   Frame N  : body at (0, 64, 0), puppet at (0, 64, 0)  — in sync
 *   Ability  : sonic boom knocks body to (5, 64, 0)
 *   Frame N+1: handler sees puppet at (0,64,0), body at (5,64,0)
 *              → teleports body back to (0,64,0)           ← fights physics
 *              → body snaps back every tick, looks wrong
 *
 * Fix: after the primary puppet→body sync, measure how far the body has
 * moved relative to the puppet. If the gap exceeds REVERSE_SYNC_SQ the
 * puppet is pulled to the body's new position. On the next tick the puppet
 * and body are co-located again, so the primary sync does nothing and the
 * vanilla knockback / physics are respected.
 *
 * We use teleportTo() (not moveTo()) so no Forge movement events fire and
 * no position packet is broadcast for the invisible puppet player.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GodControlHandler {

    /** Lerp fraction per tick for flying gods. Higher = snappier. */
    private static final double FLY_LERP = 0.35;

    /** Hard-snap distance² for flying gods — handles first-tick & lag spikes. */
    private static final double FLY_HARD_SNAP_SQ = 8.0 * 8.0;

    /** Min displacement² before a ground god teleports (avoids idle packet spam). */
    private static final double GROUND_MOVE_SQ = 0.25 * 0.25;

    /**
     * FIX Bug 11: if the body has drifted this far from the puppet (due to
     * knockback, explosion, etc.) we pull the puppet to the body's position
     * so the next tick's primary sync doesn't fight vanilla physics.
     */
    private static final double REVERSE_SYNC_SQ = 0.5 * 0.5;

    // ─────────────────────────────────────────────────────────────────────────

    @SubscribeEvent
    public static void onPlayerTick(TickEvent.PlayerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        if (!(event.player instanceof ServerPlayer player)) return;
        if (!DWNPCManager.isGodPlayer(player)) return;

        Entity godEntity = GodSpawnHandler.getGodEntity(player.getUUID());
        if (godEntity == null || godEntity.isRemoved()) return;

        syncGodWithPlayer(player, godEntity);
    }

    // ─────────────────────────────────────────────────────────────────────────

    private static void syncGodWithPlayer(ServerPlayer player, Entity godEntity) {

        // Always mirror look direction.
        godEntity.setYRot(player.getYRot());
        godEntity.setXRot(player.getXRot());
        godEntity.setYHeadRot(player.getYHeadRot());

        // ── Primary sync: puppet → body ───────────────────────────────────
        boolean isFlying = (godEntity instanceof EnderDragon)
                        || (godEntity instanceof WitherBoss);

        if (isFlying) {
            syncFlyingGod(player, godEntity);
        } else {
            syncGroundGod(player, godEntity);
        }

        // ── Reverse sync: body → puppet (FIX Bug 11) ─────────────────────
        // After the primary sync vanilla physics may have moved the body
        // (knockback, sonic boom blast, explosion impulse). If the body is
        // now more than REVERSE_SYNC_SQ from the puppet, snap the puppet to
        // the body so the next frame the agent's reference position is updated.
        double rdx = godEntity.getX() - player.getX();
        double rdy = godEntity.getY() - player.getY();
        double rdz = godEntity.getZ() - player.getZ();

        if (rdx * rdx + rdy * rdy + rdz * rdz > REVERSE_SYNC_SQ) {
            // teleportTo: no position broadcast, no Forge movement events.
            // Safe because the puppet is invisible with noPhysics = true.
            player.teleportTo(godEntity.getX(), godEntity.getY(), godEntity.getZ());
        }
    }

    // ── Flying gods (EnderDragon / WitherBoss) ────────────────────────────────

    private static void syncFlyingGod(ServerPlayer player, Entity godEntity) {
        double dx = player.getX() - godEntity.getX();
        double dy = player.getY() - godEntity.getY();
        double dz = player.getZ() - godEntity.getZ();
        double distSq = dx * dx + dy * dy + dz * dz;

        if (distSq < 0.01) {
            godEntity.setDeltaMovement(Vec3.ZERO);
            return;
        }

        if (distSq > FLY_HARD_SNAP_SQ) {
            // Too far — hard teleport then zero velocity.
            godEntity.moveTo(player.getX(), player.getY(), player.getZ(),
                             player.getYRot(), player.getXRot());
            godEntity.setDeltaMovement(Vec3.ZERO);
            return;
        }

        // Smooth lerp toward player position.
        godEntity.setDeltaMovement(dx * FLY_LERP, dy * FLY_LERP, dz * FLY_LERP);
    }

    // ── Ground gods (Warden, Elder Guardian, Oracle, Creaking …) ─────────────

    private static void syncGroundGod(ServerPlayer player, Entity godEntity) {
        double dx = player.getX() - godEntity.getX();
        double dy = player.getY() - godEntity.getY();
        double dz = player.getZ() - godEntity.getZ();

        if (dx * dx + dy * dy + dz * dz > GROUND_MOVE_SQ) {
            godEntity.moveTo(player.getX(), player.getY(), player.getZ(),
                             player.getYRot(), player.getXRot());
        }
    }
}