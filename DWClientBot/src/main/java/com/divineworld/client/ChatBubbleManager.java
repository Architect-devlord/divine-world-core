// com/divineworld/client/ChatBubbleManager.java
package com.divineworld.client;

import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.client.event.RenderLevelStageEvent;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.event.TickEvent;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Manages overhead chat bubbles for AI agents in Minecraft.
 * Shows messages above entity heads with automatic fading.
 */
public class ChatBubbleManager {

    private static final Map<UUID, ChatBubble> activeBubbles = new ConcurrentHashMap<>();
    private static final int MAX_BUBBLE_AGE_TICKS = 200; // 10 seconds
    private static final int FADE_START_TICKS = 160; // Start fading at 8 seconds
    private static final float BUBBLE_HEIGHT_OFFSET = 0.5f;
    private static final int MAX_MESSAGE_LENGTH = 50;
    
    /**
     * Show a chat message above an entity
     */
    public static void showMessage(UUID entityId, String message) {
        if (message == null || message.isEmpty()) return;
        
        // Truncate long messages
        if (message.length() > MAX_MESSAGE_LENGTH) {
            message = message.substring(0, MAX_MESSAGE_LENGTH - 3) + "...";
        }
        
        ChatBubble bubble = new ChatBubble(entityId, message);
        activeBubbles.put(entityId, bubble);
    }
    
    /**
     * Show message for agent by agent ID
     */
    public static void showAgentMessage(String agentId, String message) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;
        
        // Find entity with matching agent ID (stored in persistent data)
        for (Entity entity : mc.level.entitiesForRendering()) {
            if (entity.getPersistentData().contains("dw_agent_id")) {
                String entityAgentId = entity.getPersistentData().getString("dw_agent_id");
                if (entityAgentId.equals(agentId)) {
                    showMessage(entity.getUUID(), message);
                    return;
                }
            }
        }
    }
    
    /**
     * Update bubble lifetimes (call every tick)
     */
    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        
        // Update all bubbles
        List<UUID> toRemove = new ArrayList<>();
        
        for (Map.Entry<UUID, ChatBubble> entry : activeBubbles.entrySet()) {
            ChatBubble bubble = entry.getValue();
            bubble.age++;
            
            if (bubble.age > MAX_BUBBLE_AGE_TICKS) {
                toRemove.add(entry.getKey());
            }
        }
        
        // Remove expired bubbles
        toRemove.forEach(activeBubbles::remove);
    }
    
    /**
     * Render all active chat bubbles
     */
    @SubscribeEvent
    public static void onRenderLevel(RenderLevelStageEvent event) {
        if (event.getStage() != RenderLevelStageEvent.Stage.AFTER_ENTITIES) return;
        
        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null || mc.player == null) return;
        
        PoseStack poseStack = event.getPoseStack();
        MultiBufferSource.BufferSource bufferSource = mc.renderBuffers().bufferSource();
        Font font = mc.font;
        
        Vec3 cameraPos = mc.gameRenderer.getMainCamera().getPosition();
        
        for (ChatBubble bubble : activeBubbles.values()) {
            // Find entity
            Entity entity = mc.level.getEntity(bubble.entityId.hashCode());
            if (entity == null) continue;
            
            // Calculate alpha based on age
            float alpha = 1.0f;
            if (bubble.age > FADE_START_TICKS) {
                float fadeProgress = (float)(bubble.age - FADE_START_TICKS) / 
                                   (MAX_BUBBLE_AGE_TICKS - FADE_START_TICKS);
                alpha = 1.0f - fadeProgress;
            }
            
            // Don't render if too far or fully transparent
            double distSq = entity.position().distanceToSqr(cameraPos);
            if (distSq > 64 * 64 || alpha <= 0.01f) continue;
            
            // Calculate position above entity
            Vec3 entityPos = entity.position();
            double x = entityPos.x - cameraPos.x;
            double y = entityPos.y + entity.getBbHeight() + BUBBLE_HEIGHT_OFFSET - cameraPos.y;
            double z = entityPos.z - cameraPos.z;
            
            poseStack.pushPose();
            poseStack.translate(x, y, z);
            
            // Billboard effect (face camera)
            poseStack.mulPose(mc.gameRenderer.getMainCamera().rotation());
            
            float scale = 0.025f;
            poseStack.scale(-scale, -scale, scale);
            
            // Render background
            Component text = Component.literal(bubble.message);
            int textWidth = font.width(text);
            int bgColor = (int)(alpha * 128) << 24; // Semi-transparent black
            
            font.drawInBatch(
                text,
                -textWidth / 2f,
                0,
                0xFFFFFF | ((int)(alpha * 255) << 24),
                false,
                poseStack.last().pose(),
                bufferSource,
                Font.DisplayMode.SEE_THROUGH,
                bgColor,
                15728880
            );
            
            poseStack.popPose();
        }
        
        bufferSource.endBatch();
    }
    
    /**
     * Clear all bubbles
     */
    public static void clearAll() {
        activeBubbles.clear();
    }
    
    /**
     * Clear bubble for specific entity
     */
    public static void clearBubble(UUID entityId) {
        activeBubbles.remove(entityId);
    }
    
    /**
     * Internal bubble data class
     */
    private static class ChatBubble {
        final UUID entityId;
        final String message;
        int age = 0;
        
        ChatBubble(UUID entityId, String message) {
            this.entityId = entityId;
            this.message = message;
        }
    }
}

