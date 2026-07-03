// src/main/java/com/divineworld/events/BreedingEventHandler.java
// DivineWorld server mod
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

/**
 * Breeding Event Handler — proximity + adjacent-bed detection.
 *
 * Why BabyEntitySpawnEvent was wrong
 * -----------------------------------
 * BabyEntitySpawnEvent fires only for Animal subclasses (Cow, Pig, etc.).
 * AI agents are ServerPlayer instances, not Animals, so it NEVER fires for
 * them.  The breeding system was entirely non-functional.
 *
 * Correct detection  (matches Python breeding_system.check_can_breed())
 * -----------------------------------------------------------------------
 * On every BREED_CHECK_INTERVAL tick we scan all male/female NPC pairs in
 * each ServerLevel.  A pair triggers when:
 *   1. Both are NPC agents (not gods)
 *   2. One is male, the other female  (from dw_gender NBT)
 *   3. Within PROXIMITY_RADIUS blocks of each other
 *   4. At least two bed blocks exist within BED_SEARCH_RADIUS of their midpoint
 *      (Python's breeding_system requires beds_adjacent=true for NPCs)
 *   5. Not suppressed by the Java-side per-pair cooldown
 *
 * Python checks all remaining conditions (pregnancy, cooldown, gender compat)
 * via /api/breeding/event → breeding_system.check_can_breed().
 *
 * Flow:
 *   ServerTickEvent → checkBreedingInLevel()
 *     → PythonBackendClient.notifyBreeding()  (fire-and-forget HTTP)
 *       → /api/breeding/event
 *         → breeding_system.initiate_breeding()
 *           → pregnancy → child agent packaged and launched by Python
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class BreedingEventHandler {

    // ── Configuration ──────────────────────────────────────────────────────

    /** Max 3D distance between agents for breeding to trigger. */
    private static final double PROXIMITY_RADIUS    = 4.0;

    /** Radius around the pair midpoint within which two beds must exist. */
    private static final double BED_SEARCH_RADIUS   = 5.0;

    /** Check interval in server ticks (20 ticks/s → check once per second). */
    private static final int    BREED_CHECK_INTERVAL = 20;

    /**
     * After notifying Python, suppress re-notification for this pair for
     * this many ticks to avoid flooding before Python processes the event.
     * 240 ticks = 12 seconds.
     */
    private static final int    JAVA_COOLDOWN_TICKS  = 240;

    // ── State ───────────────────────────────────────────────────────────────

    private static int ticksSinceLastCheck = 0;

    /** Pair key → ticks remaining until pair may be re-notified. */
    private static final Map<String, Integer> PAIR_COOLDOWNS = new HashMap<>();

    // ── Tick handler ────────────────────────────────────────────────────────

    @SubscribeEvent
    public static void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        // Tick down all cooldowns every server tick
        PAIR_COOLDOWNS.replaceAll((k, v) -> Math.max(0, v - 1));
        PAIR_COOLDOWNS.entrySet().removeIf(e -> e.getValue() == 0);

        if (++ticksSinceLastCheck < BREED_CHECK_INTERVAL) return;
        ticksSinceLastCheck = 0;

        if (event.getServer() == null) return;
        for (ServerLevel level : event.getServer().getAllLevels()) {
            checkBreedingInLevel(level);
        }
    }

    // ── Level scan ───────────────────────────────────────────────────────────

    /**
     * FIX B-02: Gods (dw_gender="dual") are now included in proximity scans.
     *
     * A pair is compatible when genders are complementary:
     *   male  × female  — standard NPC pair
     *   dual  × male    — god acts as female (god is pregnant)
     *   dual  × female  — god acts as male   (NPC is pregnant)
     *   dual  × dual    — both gods; first player alphabetically is "female"
     *
     * Gods waive the adjacent-beds requirement; NPC×NPC still requires beds.
     * Python breeding_system.initiate_breeding() resolves the exact role.
     */
    private static void checkBreedingInLevel(ServerLevel level) {
        // FIX: DWNPCManager.getAIPlayers() only returns NPC-tagged players (TAG_DW_NPC).
        // Gods are tagged TAG_DW_GOD, not TAG_DW_NPC, so they were excluded.
        // Union both lists so god×npc and god×god pairs are detected.
        List<ServerPlayer> npcPlayers = DWNPCManager.getAIPlayers(level);
        List<ServerPlayer> godPlayers = DWNPCManager.getGodPlayers(level);
        List<ServerPlayer> aiPlayers  = new java.util.ArrayList<>(npcPlayers);
        for (ServerPlayer gp : godPlayers) {
            if (!aiPlayers.contains(gp)) aiPlayers.add(gp);
        }
        if (aiPlayers.size() < 2) return;

        for (int i = 0; i < aiPlayers.size(); i++) {
            ServerPlayer a    = aiPlayers.get(i);
            String genderA    = a.getPersistentData().getString("dw_gender");
            boolean isGodA    = "dual".equals(genderA);
            // Skip players that have no gender tag yet (real players, untagged)
            if (!isGodA && !"male".equals(genderA) && !"female".equals(genderA)) continue;

            for (int j = i + 1; j < aiPlayers.size(); j++) {
                ServerPlayer b = aiPlayers.get(j);
                String genderB = b.getPersistentData().getString("dw_gender");
                boolean isGodB = "dual".equals(genderB);
                if (!isGodB && !"male".equals(genderB) && !"female".equals(genderB)) continue;

                // Gender compatibility check — rejects same non-dual genders
                if (!areGendersCompatible(genderA, genderB)) continue;

                String idA = DWNPCManager.getAgentId(a);
                String idB = DWNPCManager.getAgentId(b);
                if (idA == null || idB == null) continue;

                // Java-side cooldown — prevents flooding Python before it processes
                String pairKey = pairKey(a.getUUID(), b.getUUID());
                if (PAIR_COOLDOWNS.getOrDefault(pairKey, 0) > 0) continue;

                // Proximity check
                double distSq = a.distanceToSqr(b);
                if (distSq > PROXIMITY_RADIUS * PROXIMITY_RADIUS) continue;

                // Beds check — waived when either agent is a god (dual gender)
                boolean needsBeds = !isGodA && !isGodB;
                if (needsBeds && !hasTwoBedsNearby(level, a.blockPosition(), b.blockPosition())) {
                    continue;
                }

                // All spatial conditions met — notify Python with agent types
                String typeA = isGodA ? "god" : "npc";
                String typeB = isGodB ? "god" : "npc";
                PythonBackendClient.notifyBreeding(idA, idB, typeA, typeB);
                PAIR_COOLDOWNS.put(pairKey, JAVA_COOLDOWN_TICKS);

                // FIX HF-1: Log4j2 uses {} not {:.1f} — format distance with String.format
                DWMod.LOGGER.info(
                        "[Breeding] Pair detected: {} ({}/{}) x {} ({}/{}) dist={}m",
                        idA, genderA, typeA, idB, genderB, typeB,
                        String.format("%.1f", Math.sqrt(distSq)));
            }
        }
    }

    /**
     * True when two gender strings form a compatible breeding pair.
     *
     * Compatible combinations:
     *   male   × female  ✅
     *   female × male    ✅
     *   dual   × male    ✅  (god acts as female)
     *   dual   × female  ✅  (god acts as male)
     *   male   × dual    ✅
     *   female × dual    ✅
     *   dual   × dual    ✅  (god × god)
     *
     * Incompatible:
     *   male   × male    ❌
     *   female × female  ❌
     *
     * FIX (widened to public): single source of truth for gender-compatibility,
     * now also reused by BreedCommand.java's /breed command for its upfront
     * "can these two even breed" check — avoids a second, possibly-drifting
     * copy of this exact predicate.
     */
    public static boolean areGendersCompatible(String a, String b) {
        if ("dual".equals(a) || "dual".equals(b)) return true;
        return ("male".equals(a) && "female".equals(b))
                || ("female".equals(a) && "male".equals(b));
    }

    // ── Bed detection ─────────────────────────────────────────────────────────

    /**
     * True when at least two distinct bed blocks are within BED_SEARCH_RADIUS
     * of the midpoint between posA and posB.
     * Uses the "minecraft:beds" block tag — matches all colours and mod beds.
     */
    private static boolean hasTwoBedsNearby(ServerLevel level, BlockPos posA, BlockPos posB) {
        BlockPos mid = new BlockPos(
                (posA.getX() + posB.getX()) / 2,
                (posA.getY() + posB.getY()) / 2,
                (posA.getZ() + posB.getZ()) / 2
        );

        int r    = (int) Math.ceil(BED_SEARCH_RADIUS);
        int beds = 0;
        double rSq = BED_SEARCH_RADIUS * BED_SEARCH_RADIUS;

        outer:
        for (int dx = -r; dx <= r; dx++) {
            for (int dy = -r; dy <= r; dy++) {
                for (int dz = -r; dz <= r; dz++) {
                    if (dx * dx + dy * dy + dz * dz > rSq) continue;
                    BlockState state = level.getBlockState(mid.offset(dx, dy, dz));
                    if (state.is(BlockTags.BEDS)) {
                        if (++beds >= 2) break outer;
                    }
                }
            }
        }

        return beds >= 2;
    }

    // ── Helpers ───────────────────────────────────────────────────────────────

    /**
     * Canonical pair key: lower UUID first so (A,B) and (B,A) share the
     * same cooldown entry.
     */
    private static String pairKey(UUID a, UUID b) {
        return a.compareTo(b) <= 0 ? a + ":" + b : b + ":" + a;
    }

    /**
     * Directly trigger a breeding notification for two specific agents.
     * Use this from commands or when the Python backend requests it via a
     * WebSocket/HTTP signal rather than waiting for proximity detection.
     */
    public static void triggerDirectBreeding(ServerPlayer playerA, ServerPlayer playerB) {
        if (!DWNPCManager.isAIPlayer(playerA) || !DWNPCManager.isAIPlayer(playerB)) {
            DWMod.LOGGER.warn("[Breeding] triggerDirectBreeding: not both AI agents");
            return;
        }
        String idA   = DWNPCManager.getAgentId(playerA);
        String idB   = DWNPCManager.getAgentId(playerB);
        if (idA == null || idB == null) return;

        String typeA = DWNPCManager.isGodPlayer(playerA) ? "god" : "npc";
        String typeB = DWNPCManager.isGodPlayer(playerB) ? "god" : "npc";

        PythonBackendClient.notifyBreeding(idA, idB, typeA, typeB);
        PAIR_COOLDOWNS.put(pairKey(playerA.getUUID(), playerB.getUUID()), JAVA_COOLDOWN_TICKS);

        DWMod.LOGGER.info("Direct breeding triggered: {} x {}", idA, idB);
    }
}