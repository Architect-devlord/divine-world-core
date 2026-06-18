// src/main/java/com/divineworld/utils/TaggedEntitySystem.java
// DivineWorld server mod
package com.divineworld.utils;

import com.divineworld.DWMod;
import net.minecraft.world.entity.Entity;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Tagged Entity System
 * ====================
 * Central registry for all DW-agent entities (NPCs and gods).
 *
 * Tagging strategy
 * ----------------
 * All DW agents are ServerPlayer instances whose Minecraft username is
 * EXACTLY the clean name stored in agents.json — no prefixes, no suffixes.
 *
 *   "Adam"  → NPCs.male         → NPC_MALE
 *   "Eve"   → NPCs.female       → NPC_FEMALE
 *   "Zeus"  → GODs.dual.oracle  → GOD  (godType = "oracle")
 *   "Mortis"→ GODs.dual.wither  → GOD  (godType = "wither")
 *
 * Detection order in detectAgentType():
 *   1. agents.json lookup by raw username            → NPC_MALE / NPC_FEMALE / GOD
 *   2. NBT cache from a prior session                → restore from NBT
 *   3. Not found in JSON, no NBT                     → REAL_PLAYER
 *
 * Gender and godType are cached in NBT ("dw_gender", "dw_god_type") on the
 * first call so all subsequent isAIPlayer() / isGodPlayer() checks are O(1)
 * NBT reads with no JSON I/O.
 */
public class TaggedEntitySystem {

    // NBT / persistent-data keys shared across the whole mod
    public static final String TAG_DW_NPC        = "dw_npc";
    public static final String TAG_DW_GOD        = "dw_god";
    public static final String TAG_GOD_TYPE      = "dw_god_type";
    public static final String TAG_AI_ID         = "dw_ai_id";
    public static final String TAG_DIVINE_POWER  = "dw_divine_power";
    public static final String TAG_GENESIS_IMMUNE= "dw_genesis_immune";

    private static final Map<UUID, TaggedEntity> TRACKED        = new ConcurrentHashMap<>();
    private static final Map<String, Set<UUID>>  TAG_INDEX      = new ConcurrentHashMap<>();

    // =========================================================================
    // Core tagging
    // =========================================================================

    public static void tagEntity(Entity entity, String... tags) {
        CompoundTag nbt = entity.getPersistentData();
        for (String tag : tags) {
            nbt.putBoolean(tag, true);
            TAG_INDEX.computeIfAbsent(tag, k -> ConcurrentHashMap.newKeySet()).add(entity.getUUID());
        }
        TaggedEntity te = TRACKED.computeIfAbsent(entity.getUUID(),
                id -> new TaggedEntity(id, entity.getType().toString()));
        te.tags.addAll(Arrays.asList(tags));
    }

    public static void setAIID(Entity entity, String aiId) {
        entity.getPersistentData().putString(TAG_AI_ID, aiId);
        TaggedEntity te = TRACKED.get(entity.getUUID());
        if (te != null) te.aiId = aiId;
    }

    public static String getAIID(Entity entity) {
        return entity.getPersistentData().getString(TAG_AI_ID);
    }

    public static boolean hasTag(Entity entity, String tag) {
        return entity.getPersistentData().getBoolean(tag);
    }

    public static void setGodType(Entity entity, String godType) {
        entity.getPersistentData().putString(TAG_GOD_TYPE, godType);
        TaggedEntity te = TRACKED.get(entity.getUUID());
        if (te != null) te.godType = godType;
    }

    public static String getGodType(Entity entity) {
        return entity.getPersistentData().getString(TAG_GOD_TYPE);
    }

    public static void setDivinePower(Entity entity, int power) {
        entity.getPersistentData().putInt(TAG_DIVINE_POWER, power);
        TaggedEntity te = TRACKED.get(entity.getUUID());
        if (te != null) te.divinePower = power;
    }

    public static int getDivinePower(Entity entity) {
        return entity.getPersistentData().getInt(TAG_DIVINE_POWER);
    }

    public static void makeGenesisImmune(Entity entity) {
        tagEntity(entity, TAG_GENESIS_IMMUNE);
    }

    // =========================================================================
    // World queries
    // =========================================================================

    public static List<Entity> getEntitiesWithTag(ServerLevel world, String tag) {
        Set<UUID> ids = TAG_INDEX.getOrDefault(tag, Collections.emptySet());
        List<Entity> result = new ArrayList<>();
        for (UUID id : ids) {
            Entity e = world.getEntity(id);
            if (e != null && !e.isRemoved()) result.add(e);
        }
        return result;
    }

    public static List<Entity> getAllNPCs(ServerLevel world)  { return getEntitiesWithTag(world, TAG_DW_NPC); }
    public static List<Entity> getAllGods(ServerLevel world)  { return getEntitiesWithTag(world, TAG_DW_GOD); }
    public static List<Entity> getGenesisImmuneEntities(ServerLevel world) { return getEntitiesWithTag(world, TAG_GENESIS_IMMUNE); }

    public static void cleanupRemovedEntities(ServerLevel world) {
        Iterator<Map.Entry<UUID, TaggedEntity>> it = TRACKED.entrySet().iterator();
        while (it.hasNext()) {
            Map.Entry<UUID, TaggedEntity> e = it.next();
            Entity entity = world.getEntity(e.getKey());
            if (entity == null || entity.isRemoved()) {
                for (String t : e.getValue().tags) {
                    Set<UUID> s = TAG_INDEX.get(t);
                    if (s != null) s.remove(e.getKey());
                }
                it.remove();
            }
        }
    }

    public static List<TaggedEntity> getAllTrackedEntities() {
        return new ArrayList<>(TRACKED.values());
    }

    // =========================================================================
    // Agent-type detection  (primary public API for DWEventHandler / DWNPCManager)
    // =========================================================================

    /**
     * Agent type as resolved from agents.json.
     */
    public enum AgentType {
        NPC_MALE,
        NPC_FEMALE,
        GOD,
        REAL_PLAYER
    }

    /**
     * Determine the full agent type for a connecting player.
     *
     * The Minecraft username IS the clean name from agents.json — no prefix.
     * "Adam" → NPCs.male → NPC_MALE.  "Zeus" → GODs.dual.oracle → GOD.
     *
     * This is the SINGLE source of truth.  Call it from DWEventHandler.onPlayerJoin()
     * and cache the result in NBT — every other system reads the NBT tags.
     *
     * Side effects:
     *  - Stores "dw_gender" and "dw_god_type" in NBT so all subsequent
     *    isAIPlayer() / isGodPlayer() checks are O(1) NBT reads.
     */
    public static AgentType detectAgentType(ServerPlayer player) {
        String username = player.getName().getString();

        // ── 1. Look up username directly in agents.json ──────────────────────
        // Fast-path: if NBT already tagged from a previous login, skip JSON I/O
        CompoundTag nbt = player.getPersistentData();

        // Re-use cached NBT if available (avoids JSON read on every re-join)
        if (nbt.getBoolean(TAG_DW_GOD)) {
            // FIX B-03: ensure dw_gender="dual" is always present for gods
            // (may be absent on pre-fix saves that didn't write it).
            if (!"dual".equals(nbt.getString("dw_gender"))) {
                nbt.putString("dw_gender", "dual");
            }
            return AgentType.GOD;
        }
        if (nbt.getBoolean(TAG_DW_NPC)) {
            return "female".equals(nbt.getString("dw_gender"))
                    ? AgentType.NPC_FEMALE : AgentType.NPC_MALE;
        }

        // Fresh join — consult agents.json
        AgentConfigLoader.AgentType jsonType = AgentConfigLoader.getAgentTypeForName(username);

        if (jsonType == AgentConfigLoader.AgentType.GOD) {
            String godType = AgentConfigLoader.getGodTypeForName(username);
            if (godType == null) godType = "oracle"; // safe fallback
            nbt.putString("dw_god_type", godType);
            // FIX B-03: set dw_gender="dual" for gods so BreedingEventHandler
            // can include them in proximity scans, and Python breeding_system
            // can resolve their reproductive role per-partner.
            nbt.putString("dw_gender", "dual");
            return AgentType.GOD;
        }

        if (jsonType == AgentConfigLoader.AgentType.NPC_FEMALE) {
            nbt.putString("dw_gender", "female");
            return AgentType.NPC_FEMALE;
        }

        if (jsonType == AgentConfigLoader.AgentType.NPC_MALE) {
            nbt.putString("dw_gender", "male");
            return AgentType.NPC_MALE;
        }

        // ── 2. Not in agents.json → real player ──────────────────────────────
        return AgentType.REAL_PLAYER;
    }

    // ─── convenience helpers ────────────────────────────────────────────────

    /**
     * True if this player is any kind of DW agent (NPC or god).
     * Relies on NBT set by detectAgentType(); falls back to JSON if NBT absent.
     */
    public static boolean isAnyAgent(ServerPlayer p) {
        CompoundTag nbt = p.getPersistentData();
        if (nbt.getBoolean(TAG_DW_NPC) || nbt.getBoolean(TAG_DW_GOD)) return true;
        return AgentConfigLoader.getAgentTypeForName(p.getName().getString()) != null;
    }

    /**
     * The display name of an agent IS their Minecraft username.
     * This method exists for API compatibility — it simply returns the username.
     */
    public static String extractDisplayName(ServerPlayer player) {
        return player.getName().getString();
    }

    /**
     * Return the entity-type god key for a god agent player.
     * Reads from cached "dw_god_type" NBT first; falls back to agents.json.
     * Returns null for non-god players.
     */
    public static String extractGodType(ServerPlayer player) {
        CompoundTag nbt = player.getPersistentData();
        // Prefer NBT cache
        if (nbt.contains("dw_god_type")) {
            String cached = nbt.getString("dw_god_type");
            if (!cached.isEmpty()) return cached;
        }
        // Fallback: look up in agents.json
        return AgentConfigLoader.getGodTypeForName(player.getName().getString());
    }

    // =========================================================================
    // TaggedEntity record
    // =========================================================================

    public static class TaggedEntity {
        public UUID        entityId;
        public String      entityType;
        public String      aiId;
        public String      godType;
        public int         divinePower;
        public Set<String> tags;
        public long        trackedSince;

        public TaggedEntity(UUID id, String type) {
            this.entityId    = id;
            this.entityType  = type;
            this.tags        = new HashSet<>();
            this.trackedSince= System.currentTimeMillis();
        }

        public boolean isNPC()          { return tags.contains(TAG_DW_NPC); }
        public boolean isGod()          { return tags.contains(TAG_DW_GOD); }
        public boolean isGenesisImmune(){ return tags.contains(TAG_GENESIS_IMMUNE); }
    }
}
