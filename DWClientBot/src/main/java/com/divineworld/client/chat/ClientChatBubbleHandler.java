// src/main/java/com/divineworld/client/chat/ClientChatBubbleHandler.java
package com.divineworld.client.chat;

import com.divineworld.client.DWClientMod;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Client-side chat bubble handler
 * Receives ChatPacket from server and stores messages for rendering
 */
@OnlyIn(Dist.CLIENT)
public class ClientChatBubbleHandler {

    private static final Map<UUID, ChatBubble> ACTIVE_BUBBLES = new ConcurrentHashMap<>();
    private static final Map<UUID, Integer> ENTITY_ID_CACHE = new ConcurrentHashMap<>();

    /**
     * Called when ChatPacket is received from server
     */
    public static void showMessage(UUID entityId, String message) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;

        // Try cached entity ID first (fast path)
        Integer cachedId = ENTITY_ID_CACHE.get(entityId);
        Entity entity = null;

        if (cachedId != null) {
            entity = mc.level.getEntity(cachedId);

            // Verify UUID still matches (entity might have been replaced)
            if (entity != null && !entity.getUUID().equals(entityId)) {
                entity = null;
                ENTITY_ID_CACHE.remove(entityId);
            }
        }

        // Slow path: search for entity by UUID
        if (entity == null) {
            entity = findEntityByUUID(mc.level, entityId);

            if (entity != null) {
                // Cache the entity ID for faster future lookups
                ENTITY_ID_CACHE.put(entityId, entity.getId());
            } else {
                DWClientMod.LOGGER.warn("Entity not found for chat bubble: {}", entityId);
                return;
            }
        }

        // Create chat bubble
        ChatBubble bubble = new ChatBubble(message, System.currentTimeMillis() + 3000);
        ACTIVE_BUBBLES.put(entityId, bubble);

        DWClientMod.LOGGER.debug("Chat bubble added for {}: {}", entity.getName().getString(), message);
    }

    /**
     * Find entity by UUID - optimized to check players first
     */
    private static Entity findEntityByUUID(ClientLevel level, UUID uuid) {
        // Check players first (AI agents are players)
        for (Player player : level.players()) {
            if (player.getUUID().equals(uuid)) {
                return player;
            }
        }

        // Fallback: check all entities
        for (Entity entity : level.entitiesForRendering()) {
            if (entity.getUUID().equals(uuid)) {
                return entity;
            }
        }

        return null;
    }

    /**
     * Tick to clean up expired bubbles
     */
    public static void tick() {
        long now = System.currentTimeMillis();

        // Remove expired bubbles
        ACTIVE_BUBBLES.entrySet().removeIf(entry -> {
            boolean expired = entry.getValue().expireTime < now;

            // Also clear cache for expired entities
            if (expired) {
                ENTITY_ID_CACHE.remove(entry.getKey());
            }

            return expired;
        });

        // Periodically clean up entity ID cache (every 5 seconds)
        if (now % 5000 < 50) {
            cleanupEntityCache();
        }
    }

    /**
     * Clean up stale entity ID cache entries
     */
    private static void cleanupEntityCache() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;

        ENTITY_ID_CACHE.entrySet().removeIf(entry -> {
            Entity entity = mc.level.getEntity(entry.getValue());
            return entity == null || !entity.getUUID().equals(entry.getKey());
        });
    }

    public static String getMessage(UUID entityId) {
        ChatBubble bubble = ACTIVE_BUBBLES.get(entityId);
        return bubble != null ? bubble.message : null;
    }

    public static boolean hasMessage(UUID entityId) {
        return ACTIVE_BUBBLES.containsKey(entityId);
    }

    public static void clearMessage(UUID entityId) {
        ACTIVE_BUBBLES.remove(entityId);
        ENTITY_ID_CACHE.remove(entityId);
    }

    public static void clearAll() {
        ACTIVE_BUBBLES.clear();
        ENTITY_ID_CACHE.clear();
    }

    private static class ChatBubble {
        final String message;
        final long expireTime;

        ChatBubble(String message, long expireTime) {
            this.message = message;
            this.expireTime = expireTime;
        }
    }
}