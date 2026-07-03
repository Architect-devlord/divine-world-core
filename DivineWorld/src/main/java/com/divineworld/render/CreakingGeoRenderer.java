// src/main/java/com/divineworld/render/CreakingGeoRenderer.java
// DivineWorld server mod — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.render;

import com.divineworld.DWMod;
import com.divineworld.entity.AICreakingEntity;
import com.divineworld.model.CreakingGeoModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/**
 * GeckoLib renderer for the Creaking god entity.
 *
 * GeoEntityRenderer handles:
 *   - Loading the GeckoLib model from the geo.json
 *   - Playing animations from the animation.json
 *   - Rendering the texture
 *   - Shadow, name tag, held items (inherited from LivingEntityRenderer)
 *
 * Registered in DivineClientSetup via EntityRenderers.register().
 */
@OnlyIn(Dist.CLIENT)
public class CreakingGeoRenderer extends GeoEntityRenderer<AICreakingEntity> {

    private static final ResourceLocation TEXTURE =
            new ResourceLocation(DWMod.MOD_ID, "textures/entity/ai_creaking.png");

    public CreakingGeoRenderer(EntityRendererProvider.Context context) {
        super(context, new CreakingGeoModel());
        // Shadow radius — Creaking is tall (3.5 blocks), so a wide shadow
        this.shadowRadius = 0.7f;
    }

    @Override
    public ResourceLocation getTextureLocation(AICreakingEntity entity) {
        return TEXTURE;
    }

    /**
     * Scale the Creaking god to 1.5× normal Creaking size to reflect its
     * divine-tier power. Override this to adjust per-entity if needed.
     */
    @Override
    public void scaleModelForRender(
            float widthScale,
            float heightScale,
            PoseStack poseStack,
            AICreakingEntity animatable,
            software.bernie.geckolib.cache.object.BakedGeoModel model,
            boolean isReRender,
            float partialTick,
            int packedLight,
            int packedOverlay) {

        poseStack.scale(1.5f, 1.5f, 1.5f);
    }
    @Override
    public void render(AICreakingEntity entity, float entityYaw, float partialTick,
                       PoseStack poseStack, MultiBufferSource bufferSource, int packedLight) {
        // While underground the entity is invisible — skip rendering entirely
        if (entity.isUnderground()) return;
        super.render(entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
    }
}