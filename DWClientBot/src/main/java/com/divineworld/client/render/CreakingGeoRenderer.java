// src/main/java/com/divineworld/client/render/CreakingGeoRenderer.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.render;

import com.divineworld.client.entity.gods.AICreaking;
import com.divineworld.client.model.CreakingGeoModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/**
 * GeckoLib renderer for DWClientBot's AICreaking.
 *
 * FIX (plan-creaking-geckolib-and-oracle-teach.md, Part 1, Step 3):
 * The previous CreakingRenderer extended LivingEntityRenderer<AICreaking,
 * CreakingModel<AICreaking>> — the vanilla renderer path, which drives
 * geometry from the now-deleted HierarchicalModel and has no concept of
 * GeckoLib .geo.json or .animation.json. This class replaces it with
 * GeoEntityRenderer, which hands rendering fully to GeckoLib.
 *
 * What GeoEntityRenderer gives for free vs. the old renderer:
 *   - Reads geometry from geo/entity/ai_creaking.geo.json
 *   - Runs animations from animations/entity/ai_creaking.animation.json
 *   - Renders the texture atlas ai_creaking.png with the correct UV map
 *   - Inherits shadow, name tag, held items from LivingEntityRenderer
 *     (GeoEntityRenderer extends it) — no manual re-implementation needed
 *
 * Registration: replace EntityRenderers.register(ModEntities.AI_CREAKING,
 *   ctx -> new CreakingRenderer(ctx))  with
 *   ctx -> new CreakingGeoRenderer(ctx)  in DWClientSetup.
 *
 * The old ModelLayerLocation registration (CREAKING_LAYER in
 * CreakingRenderer + EntityModelLayers / event registration) is no
 * longer needed — GeoEntityRenderer uses GeoModel, not LayeredModel.
 * Remove those registrations from your entity layer event handler.
 */
@OnlyIn(Dist.CLIENT)
public class CreakingGeoRenderer extends GeoEntityRenderer<AICreaking> {

    public CreakingGeoRenderer(EntityRendererProvider.Context context) {
        super(context, new CreakingGeoModel());
        // Shadow radius — Creaking is tall; 0.7 matches DivineWorld's value
        this.shadowRadius = 0.7f;
    }

    /**
     * Scale to 1.2× to match AICreaking.getScale() == 1.2f.
     *
     * In 1.20.1 Entity.getScale() doesn't exist (added in 1.20.4), so
     * GeoEntityRenderer doesn't call it — we override scaleModelForRender()
     * instead, which is the GeckoLib-idiomatic way to apply entity-level
     * scaling. The previous renderer applied this via a poseStack.scale()
     * in render(); moving it here keeps the same effective output size.
     */
    @Override
    protected void scaleModelForRender(float widthScale, float heightScale,
                                        PoseStack poseStack,
                                        AICreaking animatable,
                                        ModelPart rootPart,
                                        boolean isReRender, float partialTick,
                                        int packedLight, int packedOverlay) {
        poseStack.scale(1.2f, 1.2f, 1.2f);
    }

    @Override
    public void render(AICreaking entity, float entityYaw, float partialTick,
                       PoseStack poseStack, MultiBufferSource bufferSource, int packedLight) {
        // While underground, entity is invisible — skip rendering entirely.
        // Same check as DivineWorld's CreakingGeoRenderer and the old
        // CreakingRenderer's disguise check, consolidated here.
        if (entity.isUnderground()) return;
        super.render(entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
    }
}