// src/main/java/com/divineworld/utils/DivineMagicCircle.java
package com.divineworld.utils;

import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;

/**
 * DivineMagicCircle
 *
 * Renders an animated, layered 5-block-radius magic circle of particles
 * on the ground and in the air around a given origin.
 *
 * Used when Genesis or Divine Reset fires.
 * Call spawnGenesisCircle() or spawnDivineResetCircle() on the server thread.
 * Each call spawns one "frame" of the animation – schedule it to repeat for
 * the full effect (e.g. every 5 ticks for ~10 seconds = 40 calls).
 *
 * Particle types used (all available in 1.20.1):
 *   Genesis      – END_ROD (white), PORTAL (purple swirl), ENCHANT (golden),
 *                  DRAGON_BREATH (purple mist), TOTEM_OF_UNDYING (green burst)
 *   Divine Reset – SOUL_FIRE_FLAME (blue), FLAME (orange), SMOKE (grey),
 *                  ASH (grey drift), SCULK_SOUL (cyan)
 */
public class DivineMagicCircle {

    private static final double RADIUS       = 5.0;
    private static final double INNER_RADIUS = 2.5;
    // Number of points around the full circle
    private static final int    RING_POINTS  = 48;

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Spawn a single animated frame of the Genesis magic circle.
     *
     * @param level   the server level
     * @param center  origin block position (ground level)
     * @param tick    current animation tick (0-based, used for rotation)
     */
    public static void spawnGenesisCircle(ServerLevel level, BlockPos center, int tick) {
        double cx = center.getX() + 0.5;
        double cy = center.getY();           // ground level
        double cz = center.getZ() + 0.5;

        double angleOffset = Math.toRadians(tick * 3);   // rotate 3°/tick

        // --- Outer ring (END_ROD – bright white)
        spawnRing(level, cx, cy + 0.05, cz, RADIUS, RING_POINTS,
                angleOffset, ParticleTypes.END_ROD, 1);

        // --- Inner ring (PORTAL – purple swirl)
        spawnRing(level, cx, cy + 0.05, cz, INNER_RADIUS, RING_POINTS / 2,
                -angleOffset * 1.5, ParticleTypes.PORTAL, 1);

        // --- Pentagrams / star points at outer ring (ENCHANT)
        for (int i = 0; i < 5; i++) {
            double a = angleOffset + Math.toRadians(i * 72.0);
            double px = cx + RADIUS * Math.cos(a);
            double pz = cz + RADIUS * Math.sin(a);
            level.sendParticles(ParticleTypes.ENCHANT,
                    px, cy + 0.1, pz, 5, 0.1, 0.3, 0.1, 0.05);
        }

        // --- Vertical pillars at the five pentagram points (DRAGON_BREATH)
        for (int i = 0; i < 5; i++) {
            double a = angleOffset + Math.toRadians(i * 72.0);
            double px = cx + RADIUS * Math.cos(a);
            double pz = cz + RADIUS * Math.sin(a);
            for (double h = 0; h <= 2.0; h += 0.4) {
                level.sendParticles(ParticleTypes.DRAGON_BREATH,
                        px, cy + h, pz, 1, 0.05, 0.05, 0.05, 0.01);
            }
        }

        // --- Upward burst at center every 10 ticks (TOTEM_OF_UNDYING)
        if (tick % 10 == 0) {
            level.sendParticles(ParticleTypes.TOTEM_OF_UNDYING,
                    cx, cy + 0.5, cz, 60, 0.3, 1.0, 0.3, 0.2);
            level.playSound(null, center, SoundEvents.AMETHYST_CLUSTER_HIT,
                    SoundSource.AMBIENT, 0.6f, 0.8f + (tick % 4) * 0.1f);
        }

        // --- Ambient mist filling the circle (PORTAL, low density)
        for (int i = 0; i < 4; i++) {
            double a = Math.random() * Math.PI * 2;
            double r = Math.random() * RADIUS;
            level.sendParticles(ParticleTypes.PORTAL,
                    cx + r * Math.cos(a), cy + Math.random() * 1.5,
                    cz + r * Math.sin(a), 1, 0, 0, 0, 0.02);
        }
    }

    /**
     * Spawn a single animated frame of the Divine Reset magic circle.
     *
     * @param level   the server level
     * @param center  origin block position (ground level)
     * @param tick    current animation tick (0-based, used for rotation)
     */
    public static void spawnDivineResetCircle(ServerLevel level, BlockPos center, int tick) {
        double cx = center.getX() + 0.5;
        double cy = center.getY();
        double cz = center.getZ() + 0.5;

        double angleOffset = Math.toRadians(tick * 4);   // faster rotation for reset

        // --- Outer ring (SOUL_FIRE_FLAME – eerie blue)
        spawnRing(level, cx, cy + 0.05, cz, RADIUS, RING_POINTS,
                angleOffset, ParticleTypes.SOUL_FIRE_FLAME, 1);

        // --- Counter-rotating inner ring (FLAME – orange)
        spawnRing(level, cx, cy + 0.05, cz, INNER_RADIUS, RING_POINTS / 2,
                -angleOffset * 2, ParticleTypes.FLAME, 1);

        // --- Ash drifting upward across the whole circle
        for (int i = 0; i < 6; i++) {
            double a = Math.random() * Math.PI * 2;
            double r = Math.random() * RADIUS;
            level.sendParticles(ParticleTypes.ASH,
                    cx + r * Math.cos(a), cy + Math.random() * 2.5,
                    cz + r * Math.sin(a), 1, 0, 0.02, 0, 0.01);
        }

        // --- Smoke at hexagram points
        for (int i = 0; i < 6; i++) {
            double a = angleOffset + Math.toRadians(i * 60.0);
            double px = cx + RADIUS * Math.cos(a);
            double pz = cz + RADIUS * Math.sin(a);
            level.sendParticles(ParticleTypes.LARGE_SMOKE,
                    px, cy + 0.1, pz, 3, 0.1, 0.2, 0.1, 0.01);
            // Vertical column
            for (double h = 0; h <= 3.0; h += 0.5) {
                level.sendParticles(ParticleTypes.SOUL_FIRE_FLAME,
                        px, cy + h, pz, 1, 0.05, 0.05, 0.05, 0.01);
            }
        }

        // --- Shockwave burst every 20 ticks
        if (tick % 20 == 0) {
            level.sendParticles(ParticleTypes.EXPLOSION_EMITTER,
                    cx, cy + 0.5, cz, 1, 0, 0, 0, 0);
            level.playSound(null, center, SoundEvents.WITHER_AMBIENT,
                    SoundSource.AMBIENT, 0.5f, 0.5f);
        }

        // --- SCULK_SOUL creeping outward (using tick-based radius)
        double wave = (tick % 20) / 20.0 * RADIUS;
        spawnRing(level, cx, cy + 0.02, cz, wave, 20, angleOffset,
                ParticleTypes.SCULK_SOUL, 1);
    }

    // -------------------------------------------------------------------------
    // Helpers
    // -------------------------------------------------------------------------

    /**
     * Spawn particles evenly distributed around a horizontal ring.
     *
     * @param level       server level
     * @param cx, cy, cz  ring center world coordinates
     * @param radius      ring radius in blocks
     * @param points      number of particle positions around the ring
     * @param angleOffset starting angle offset in radians (for rotation)
     * @param particle    particle type
     * @param count       particles per position
     */
    private static void spawnRing(
            ServerLevel level,
            double cx, double cy, double cz,
            double radius, int points, double angleOffset,
            net.minecraft.core.particles.SimpleParticleType particle,
            int count) {

        for (int i = 0; i < points; i++) {
            double angle = angleOffset + (2.0 * Math.PI * i) / points;
            double px = cx + radius * Math.cos(angle);
            double pz = cz + radius * Math.sin(angle);
            level.sendParticles(particle, px, cy, pz, count,
                    0.02, 0.02, 0.02, 0.001);
        }
    }
}