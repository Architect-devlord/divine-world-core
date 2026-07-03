// src/main/java/com/divineworld/client/render/GodHumanoidGeoRenderer.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.render;

import com.divineworld.client.entity.gods.BaseGodEntity;
import com.divineworld.client.model.GodHumanoidGeoModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.MultiBufferSource;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.cache.object.BakedGeoModel;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/**
 * Renderer for gods in HUMANOID form.
 *
 * Uses GodHumanoidGeoModel which reads god_{type}.geo.json /
 * god_{type}.png / god_{type}.animation.json for every god type,
 * including creaking (god_creaking.* for its humanoid appearance,
 * which is separate from ai_creaking.* used by its real boss body).
 *
 * Registered for each god's custom EntityType in ClientSetup alongside
 * the existing GodEntityRenderer — but GodEntityRenderer is kept as the
 * initially-registered renderer; this renderer is used as a DELEGATE
 * within GodEntityRenderer.render() when dw_form=humanoid, rather than
 * being registered separately (see GodEntityRenderer for the composition).
 *
 * Scale: always 1.0× in humanoid form regardless of god type — same as
 * the Steve/Alex disguise form.  The imposing god-form scale only applies
 * to the real boss body entity, not the humanoid puppet.
 *
 * Ability animations: the animation names in god_*.animation.json match
 * the ability names used in god form exactly (attack, burrow, tentacles_out
 * etc.) plus the standard player movement set (walk, run, idle, swim, sneak,
 * hit, mount).  BaseGodEntity.registerControllers() fires the same triggerable
 * names regardless of form — the animation.json just provides humanoid-shaped
 * keyframes for each of those shared names.
 */
@OnlyIn(Dist.CLIENT)
public class GodHumanoidGeoRenderer<T extends BaseGodEntity>
        extends GeoEntityRenderer<T> {

    public GodHumanoidGeoRenderer(EntityRendererProvider.Context context) {
        super(context, new GodHumanoidGeoModel<>());
        this.shadowRadius = 0.5f;
    }

    @Override
    public void scaleModelForRender(float widthScale, float heightScale,
                                       PoseStack poseStack,
                                       T animatable,
                                       BakedGeoModel model,
                                       boolean isReRender,
                                       float partialTick,
                                       int packedLight,
                                       int packedOverlay) {
        // No scaling needed
        // Humanoid form always renders at 1.0× scale — the god body entity
        // carries the large scale, not this puppet form.
        // No poseStack.scale() call needed; GeoEntityRenderer defaults to 1×.
    }

    /**
     * Called as a delegate from GodEntityRenderer.render() when dw_form=humanoid.
     * The caller handles visibility (player puppet must be setInvisible(false)
     * server-side when entering humanoid form) and form detection; this method
     * just drives the GeckoLib render pipeline for the puppet entity.
     */
    public void renderAsHumanoid(T entity, float entityYaw, float partialTick,
                                  PoseStack poseStack, MultiBufferSource bufferSource,
                                  int packedLight) {
        super.render(entity, entityYaw, partialTick, poseStack, bufferSource, packedLight);
    }
}