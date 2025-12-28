// src/main/java/com/divineworld/network/ServerChatHandler.java
package com.divineworld.network;

import com.divineworld.DWMod;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;

import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * SERVER-SIDE ONLY Chat Handler
 * Manages chat bubbles without any client-side code
 * For dedicated servers - no client references
 */
public class ServerChatHandler {

    private static final Map<UUID, ChatBubble> ACTIVE_BUBBLES = new ConcurrentHashMap<>();

    /**
     * Show chat message above entity (by UUID - for packet handler)
     */
    public static void showMessage(UUID entityId, String message) {
        if (entityId == null || message == null || message.isEmpty()) {
            return;
        }

        ChatBubble bubble = new ChatBubble(message, System.currentTimeMillis() + 3000);
        ACTIVE_BUBBLES.put(entityId, bubble);

        DWMod.LOGGER.debug("Chat bubble stored for entity: {}", entityId);
    }

    /**
     * Show chat message above entity (direct entity reference)
     */
    public static void showMessage(Entity entity, String message) {
        if (entity == null || message == null || message.isEmpty()) {
            return;
        }

        ChatBubble bubble = new ChatBubble(message, System.currentTimeMillis() + 3000);
        ACTIVE_BUBBLES.put(entity.getUUID(), bubble);

        // Send to nearby players as system message (fallback for server-only)
        if (entity.level() instanceof net.minecraft.server.level.ServerLevel serverLevel) {
            for (ServerPlayer player : serverLevel.players()) {
                double distSq = player.distanceToSqr(entity);
                if (distSq < 64 * 64) { // Within 64 blocks
                    player.sendSystemMessage(Component.literal(
                            "§7[" + entity.getName().getString() + "] §f" + message
                    ));
                }
            }
        }

        DWMod.LOGGER.debug("Chat bubble: {} says '{}'", entity.getName().getString(), message);
    }

    /**
     * Tick to clean up expired bubbles
     */
    public static void tick() {
        long now = System.currentTimeMillis();
        ACTIVE_BUBBLES.entrySet().removeIf(entry -> entry.getValue().expireTime < now);
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
    }

    public static void clearAll() {
        ACTIVE_BUBBLES.clear();
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