// src/main/java/com/divineworld/client/render/GodEntityRenderer.java
package com.divineworld.client.render;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.*;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.PlayerModel;
import net.minecraft.client.model.geom.ModelLayers;
import net.minecraft.client.player.AbstractClientPlayer;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.client.renderer.entity.layers.*;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;

/**
 * God Entity Renderer
 * Renders god entities as players with special effects
 * Handles transformations and visual indicators
 */
@OnlyIn(Dist.CLIENT)
public class GodEntityRenderer extends LivingEntityRenderer<Player, PlayerModel<Player>> {

    private static final ResourceLocation DEFAULT_GOD_SKIN =
            new ResourceLocation(DWClientMod.MOD_ID, "textures/entity/god_default.png");

    public GodEntityRenderer(EntityRendererProvider.Context context) {
        super(context, new PlayerModel<>(context.bakeLayer(ModelLayers.PLAYER), false), 0.5F);

        // Add standard player layers
        this.addLayer(new HumanoidArmorLayer<>(this,
                new PlayerModel<>(context.bakeLayer(ModelLayers.PLAYER_INNER_ARMOR), true),
                new PlayerModel<>(context.bakeLayer(ModelLayers.PLAYER_OUTER_ARMOR), false),
                context.getModelManager()));

        this.addLayer(new ItemInHandLayer<>(this, context.getItemInHandRenderer()));
        this.addLayer(new ArrowLayer<>(context, this));
        this.addLayer(new CustomHeadLayer<>(this, context.getModelSet(), context.getItemInHandRenderer()));
        this.addLayer(new ElytraLayer<>(this, context.getModelSet()));

        // Add god-specific glow layer
        this.addLayer(new GodGlowLayer(this));
    }

    @Override
    public ResourceLocation getTextureLocation(Player entity) {
        // Check if transformed
        if (entity.getPersistentData().contains("dw_god") &&
                entity.getPersistentData().getBoolean("dw_disguised")) {
            // Use player skin when disguised
            if (entity instanceof AbstractClientPlayer clientPlayer) {
                return clientPlayer.getSkinTextureLocation();
            }
        }

        // Use god-specific skin based on type
        String godType = entity.getPersistentData().getString("dw_god_type");
        if (godType != null && !godType.isEmpty()) {
            return new ResourceLocation(DWClientMod.MOD_ID,
                    "textures/entity/god_" + godType + ".png");
        }

        return DEFAULT_GOD_SKIN;
    }

    @Override
    public void render(Player entity, float entityYaw, float partialTicks,
                       PoseStack poseStack, MultiBufferSource buffer, int packedLight) {

        // Apply god-specific scaling
        if (entity.getPersistentData().contains("dw_god")) {
            float scale = getGodScale(entity);

            poseStack.pushPose();
            poseStack.scale(scale, scale, scale);

            super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);

            poseStack.popPose();
        } else {
            super.render(entity, entityYaw, partialTicks, poseStack, buffer, packedLight);
        }

        // Render god nameplate
        renderGodNameplate(entity, poseStack, buffer, packedLight);
    }

    private float getGodScale(Player entity) {
        String godType = entity.getPersistentData().getString("dw_god_type");

        // If disguised, use normal scale
        if (entity.getPersistentData().getBoolean("dw_disguised")) {
            return 1.0f;
        }

        return switch (godType) {
            case "ender_dragon" -> 4.0f;
            case "wither" -> 1.8f;
            case "warden" -> 1.5f;
            case "elder_guardian" -> 2.0f;
            case "creaking" -> 1.2f;
            case "oracle" -> 1.0f;
            default -> 1.0f;
        };
    }

    private void renderGodNameplate(Player entity, PoseStack poseStack,
                                    MultiBufferSource buffer, int packedLight) {
        if (!entity.getPersistentData().contains("dw_god")) return;

        String godType = entity.getPersistentData().getString("dw_god_type");
        if (godType == null || godType.isEmpty()) return;

        // Render "[GOD]" prefix above name
        poseStack.pushPose();

        // Position above entity
        poseStack.translate(0.0D, entity.getBbHeight() + 0.5D, 0.0D);

        // Billboard rotation
        poseStack.mulPose(this.entityRenderDispatcher.cameraOrientation());

        // Scale text
        float scale = 0.025f;
        poseStack.scale(-scale, -scale, scale);

        // Render text
        var font = this.getFont();
        String text = "§5[" + godType.toUpperCase() + " GOD]";

        float x = -font.width(text) / 2.0f;

        font.drawInBatch(text, x, 0, 0xFFFFFF, false,
                poseStack.last().pose(), buffer,
                net.minecraft.client.gui.Font.DisplayMode.NORMAL,
                0, packedLight);

        poseStack.popPose();
    }

    /**
     * Custom glow layer for gods
     */
    private static class GodGlowLayer extends RenderLayer<Player, PlayerModel<Player>> {

        public GodGlowLayer(GodEntityRenderer renderer) {
            super(renderer);
        }

        @Override
        public void render(PoseStack poseStack, MultiBufferSource buffer, int packedLight,
                           Player entity, float limbSwing, float limbSwingAmount,
                           float partialTicks, float ageInTicks, float netHeadYaw, float headPitch) {

            if (!entity.getPersistentData().contains("dw_god")) return;
            if (entity.getPersistentData().getBoolean("dw_disguised")) return;

            // Add subtle glow effect
            // Implementation depends on your visual preferences
            // Could use emissive textures, particles, etc.
        }
    }
}