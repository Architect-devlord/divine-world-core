// src/main/java/com/divineworld/client/render/CreakingGeoRenderer.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.render;

import com.divineworld.client.entity.gods.AICreaking;
import com.divineworld.client.model.CreakingGeoModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.cache.object.BakedGeoModel;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/**
 * GeckoLib renderer for DWClientBot's AICreaking.
 *
 * Handles all three forms for the Creaking god:
 *
 *   god form      — Creaking is special: its real boss entity uses ai_creaking.*
 *                   assets (GeckoLib boss geometry/animations), same as
 *                   DivineWorld's server-side AICreakingEntity.  This is what
 *                   this renderer's GeoEntityRenderer path provides.  The
 *                   player puppet is invisible (setInvisible(true) on server).
 *
 *   humanoid form — Delegate to the lazily-initialised GodEntityRenderer instance
 *                   (same pattern GodEntityRenderer uses for the humanoid path).
 *                   GodEntityRenderer.renderHumanoidForm() calls GeckoLib's
 *                   GodHumanoidGeoRenderer with god_creaking.* assets.
 *
 *   disguise form — Delegate to GodEntityRenderer for Steve/Alex rendering.
 *
 * This delegation pattern (store a GodEntityRenderer as a field, call its
 * form-specific methods in render()) avoids the EntityType registration
 * constraint: a single EntityType can only have one registered renderer, so
 * we make CreakingGeoRenderer that single renderer and have it dispatch to
 * GodEntityRenderer's helpers when the form is not "god".
 */
@OnlyIn(Dist.CLIENT)
public class CreakingGeoRenderer extends GeoEntityRenderer<AICreaking> {

    @SuppressWarnings("rawtypes")
    private GodEntityRenderer godDelegate;
    private final EntityRendererProvider.Context savedContext;

    private static final String FORM_GOD = "god";

    public CreakingGeoRenderer(EntityRendererProvider.Context context) {
        super(context, new CreakingGeoModel());
        this.savedContext  = context;
        this.shadowRadius  = 0.7f;
    }

    @Override
    public void scaleModelForRender(float widthScale, float heightScale,
                                       PoseStack poseStack,
                                       AICreaking animatable,
                                       BakedGeoModel model,
                                       boolean isReRender, float partialTick,
                                       int packedLight, int packedOverlay) {
        String form = animatable.getPersistentData().getString("dw_form");

        if (form == null || form.isEmpty() || FORM_GOD.equals(form)) {
            poseStack.scale(1.2f, 1.2f, 1.2f);
        }
    }

    @Override
    @SuppressWarnings("unchecked")
    public void render(AICreaking entity, float entityYaw, float partialTick,
                       PoseStack poseStack, MultiBufferSource bufferSource, int packedLight) {
        if (entity.isUnderground()) return;

        String form = entity.getPersistentData().getString("dw_form");
        if (form == null || form.isEmpty()) form = FORM_GOD;

        switch (form) {
            case "humanoid" -> {
                // Humanoid form — delegate to GodEntityRenderer's humanoid path
                // which calls GodHumanoidGeoRenderer with god_creaking.* assets.
                ensureDelegate();
                godDelegate.renderHumanoidFormPublic(
                        entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
            }
            case "disguise" -> {
                // Disguise form — delegate to GodEntityRenderer's Steve/Alex path
                ensureDelegate();
                godDelegate.renderDisguiseFormPublic(
                        entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
            }
            default ->
                // God form — Creaking's own GeckoLib ai_creaking.* assets
                super.render(entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
        }
    }

    @SuppressWarnings("rawtypes")
    private void ensureDelegate() {
        if (godDelegate == null) {
            godDelegate = new GodEntityRenderer(savedContext);
        }
    }
}