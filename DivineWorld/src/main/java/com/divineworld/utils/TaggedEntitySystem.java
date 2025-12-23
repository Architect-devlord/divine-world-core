// src/main/java/com/divineworld/utils/TaggedEntitySystem.java
package com.divineworld.utils;

import com.divineworld.DWMod;
import net.minecraft.world.entity.Entity;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.entity.EntityJoinLevelEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Tagged Entity System - FIXED
 * No references to custom god entities
 * All agents are ServerPlayer with tags
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class TaggedEntitySystem {

    public static final String TAG_DW_NPC = "dw_npc";
    public static final String TAG_DW_GOD = "dw_god";
    public static final String TAG_GOD_TYPE = "dw_god_type";
    public static final String TAG_AI_ID = "dw_ai_id";
    public static final String TAG_DIVINE_POWER = "dw_divine_power";
    public static final String TAG_GENESIS_IMMUNE = "dw_genesis_immune";

    private static final Map<UUID, TaggedEntity> TRACKED_ENTITIES = new ConcurrentHashMap<>();
    private static final Map<String, Set<UUID>> TAG_INDEX = new ConcurrentHashMap<>();

    public static void tagEntity(Entity entity, String... tags) {
        CompoundTag nbt = entity.getPersistentData();

        for (String tag : tags) {
            nbt.putBoolean(tag, true);

            TAG_INDEX.computeIfAbsent(tag, k -> ConcurrentHashMap.newKeySet())
                    .add(entity.getUUID());
        }

        TaggedEntity tracked = new TaggedEntity(entity.getUUID(), entity.getType().toString());
        tracked.tags.addAll(Arrays.asList(tags));
        TRACKED_ENTITIES.put(entity.getUUID(), tracked);

        DWMod.LOGGER.debug("Tagged entity {} with: {}", entity.getUUID(), String.join(", ", tags));
    }

    public static void setAIID(Entity entity, String aiId) {
        CompoundTag nbt = entity.getPersistentData();
        nbt.putString(TAG_AI_ID, aiId);

        TaggedEntity tracked = TRACKED_ENTITIES.get(entity.getUUID());
        if (tracked != null) {
            tracked.aiId = aiId;
        }

        DWMod.LOGGER.info("Linked entity {} to AI: {}", entity.getUUID(), aiId);
    }

    public static String getAIID(Entity entity) {
        CompoundTag nbt = entity.getPersistentData();
        return nbt.getString(TAG_AI_ID);
    }

    public static boolean hasTag(Entity entity, String tag) {
        return entity.getPersistentData().getBoolean(tag);
    }

    public static List<Entity> getEntitiesWithTag(ServerLevel world, String tag) {
        Set<UUID> entityIds = TAG_INDEX.getOrDefault(tag, Collections.emptySet());
        List<Entity> result = new ArrayList<>();

        for (UUID id : entityIds) {
            Entity entity = world.getEntity(id);
            if (entity != null && !entity.isRemoved()) {
                result.add(entity);
            }
        }

        return result;
    }

    public static List<Entity> getAllNPCs(ServerLevel world) {
        return getEntitiesWithTag(world, TAG_DW_NPC);
    }

    public static List<Entity> getAllGods(ServerLevel world) {
        return getEntitiesWithTag(world, TAG_DW_GOD);
    }

    public static List<Entity> getGenesisImmuneEntities(ServerLevel world) {
        return getEntitiesWithTag(world, TAG_GENESIS_IMMUNE);
    }

    public static void setGodType(Entity entity, String godType) {
        CompoundTag nbt = entity.getPersistentData();
        nbt.putString(TAG_GOD_TYPE, godType);

        TaggedEntity tracked = TRACKED_ENTITIES.get(entity.getUUID());
        if (tracked != null) {
            tracked.godType = godType;
        }
    }

    public static String getGodType(Entity entity) {
        return entity.getPersistentData().getString(TAG_GOD_TYPE);
    }

    public static void setDivinePower(Entity entity, int power) {
        CompoundTag nbt = entity.getPersistentData();
        nbt.putInt(TAG_DIVINE_POWER, power);

        TaggedEntity tracked = TRACKED_ENTITIES.get(entity.getUUID());
        if (tracked != null) {
            tracked.divinePower = power;
        }
    }

    public static int getDivinePower(Entity entity) {
        return entity.getPersistentData().getInt(TAG_DIVINE_POWER);
    }

    public static void makeGenesisImmune(Entity entity) {
        tagEntity(entity, TAG_GENESIS_IMMUNE);
    }

    // REMOVED: onEntityJoin event (no custom god entities to auto-tag)

    public static void cleanupRemovedEntities(ServerLevel world) {
        Iterator<Map.Entry<UUID, TaggedEntity>> it = TRACKED_ENTITIES.entrySet().iterator();

        while (it.hasNext()) {
            Map.Entry<UUID, TaggedEntity> entry = it.next();
            Entity entity = world.getEntity(entry.getKey());

            if (entity == null || entity.isRemoved()) {
                for (String tag : entry.getValue().tags) {
                    Set<UUID> tagSet = TAG_INDEX.get(tag);
                    if (tagSet != null) {
                        tagSet.remove(entry.getKey());
                    }
                }

                it.remove();
                DWMod.LOGGER.debug("Cleaned up tracked entity: {}", entry.getKey());
            }
        }
    }

    public static List<TaggedEntity> getAllTrackedEntities() {
        return new ArrayList<>(TRACKED_ENTITIES.values());
    }

    public static class TaggedEntity {
        public UUID entityId;
        public String entityType;
        public String aiId;
        public String godType;
        public int divinePower;
        public Set<String> tags;
        public long trackedSince;

        public TaggedEntity(UUID entityId, String entityType) {
            this.entityId = entityId;
            this.entityType = entityType;
            this.tags = new HashSet<>();
            this.trackedSince = System.currentTimeMillis();
        }

        public boolean isNPC() {
            return tags.contains(TAG_DW_NPC);
        }

        public boolean isGod() {
            return tags.contains(TAG_DW_GOD);
        }

        public boolean isGenesisImmune() {
            return tags.contains(TAG_GENESIS_IMMUNE);
        }
    }
}