// src/main/java/com/divineworld/client/render/CreakingRenderer.java

package com.divineworld.client.render;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.AICreaking;
import com.divineworld.client.model.CreakingModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.geom.ModelLayerLocation;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

/**
 * Creaking Renderer - FIXED VERSION
 * Now extends LivingEntityRenderer for Player-based entities
 */
@OnlyIn(Dist.CLIENT)
public class CreakingRenderer extends LivingEntityRenderer<AICreaking, CreakingModel<AICreaking>> {

    private static final ResourceLocation CREAKING_TEXTURE =
            new ResourceLocation(DWClientMod.MOD_ID, "textures/entity/ai_creaking.png");

    public static final ModelLayerLocation CREAKING_LAYER = new ModelLayerLocation(
            new ResourceLocation(DWClientMod.MOD_ID, "creaking"),
            "main"
    );

    public CreakingRenderer(EntityRendererProvider.Context context) {
        super(context, new CreakingModel<>(context.bakeLayer(CREAKING_LAYER)), 0.5F);
    }

    @Override
    public ResourceLocation getTextureLocation(AICreaking entity) {
        // Check if transformed/disguised
        if (entity.getPersistentData().getBoolean("dw_disguised")) {
            // Use player skin when disguised
            return new ResourceLocation("textures/entity/player/wide/steve.png");
        }
        return CREAKING_TEXTURE;
    }

    @Override
    public void render(AICreaking entity, float entityYaw, float partialTicks,
                       PoseStack poseStack, MultiBufferSource buffer, int packedLight) {

        poseStack.pushPose();

        // Apply scaling for creaking.
        // Entity.getScale() was added in MC 1.20.4 — does not exist in 1.20.1 (Forge 47.x).
        // AICreaking always uses 1.2f, so hardcode it here.
        final float scale = 1.2f;
        poseStack.scale(scale, scale, scale);

        super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);

        poseStack.popPose();
    }
}