// src/main/java/com/divineworld/client/render/ChatBubbleRenderer.java
package com.divineworld.client.render;

import com.divineworld.client.chat.ClientChatBubbleHandler;
import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.world.entity.Entity;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.RenderLivingEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Renders chat bubbles above entities
 * Subscribes to RenderLivingEvent to draw text above AI agents
 */
@Mod.EventBusSubscriber(value = Dist.CLIENT, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ChatBubbleRenderer {

    @SubscribeEvent
    public static void onRenderEntity(RenderLivingEvent.Post<?, ?> event) {
        Entity entity = event.getEntity();

        // Check if this entity has a chat bubble
        String message = ClientChatBubbleHandler.getMessage(entity.getUUID());
        if (message == null || message.isEmpty()) {
            return;
        }

        PoseStack poseStack = event.getPoseStack();
        MultiBufferSource bufferSource = event.getMultiBufferSource();
        int packedLight = event.getPackedLight();

        renderChatBubble(entity, message, poseStack, bufferSource, packedLight);
    }

    private static void renderChatBubble(
            Entity entity,
            String message,
            PoseStack poseStack,
            MultiBufferSource bufferSource,
            int packedLight
    ) {
        Minecraft mc = Minecraft.getInstance();
        Font font = mc.font;

        poseStack.pushPose();

        // Position above entity's head
        float yOffset = entity.getBbHeight() + 0.5f;
        poseStack.translate(0, yOffset, 0);

        // Billboard effect (face camera)
        poseStack.mulPose(mc.getEntityRenderDispatcher().cameraOrientation());
        poseStack.mulPose(Axis.ZP.rotationDegrees(180.0F));

        // Scale text
        float scale = 0.025f;
        poseStack.scale(-scale, -scale, scale);

        // Measure text width
        int textWidth = font.width(message);
        float x = -textWidth / 2.0f;

        // Draw background
        int backgroundColor = 0x80000000; // Semi-transparent black
        int padding = 2;

        font.drawInBatch(
                message,
                x,
                0,
                0xFFFFFFFF, // White text
                false,
                poseStack.last().pose(),
                bufferSource,
                Font.DisplayMode.NORMAL,
                backgroundColor,
                packedLight
        );

        poseStack.popPose();
    }
}