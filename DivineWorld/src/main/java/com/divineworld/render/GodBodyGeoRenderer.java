// src/main/java/com/divineworld/render/GodBodyGeoRenderer.java
// DivineWorld server mod — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.render;

import com.divineworld.entity.gods.BaseGodEntity;
import com.divineworld.model.GodHumanoidGeoModel;
import com.mojang.blaze3d.vertex.PoseStack;
import net.minecraft.client.renderer.entity.EntityRendererProvider;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.cache.object.BakedGeoModel;
import software.bernie.geckolib.renderer.GeoEntityRenderer;

/**
 * GeckoLib renderer for the actual spawned god body entities
 * (AIWarden/AIWither/AIOracle/AIElderGuardian/AIEnderDragon — everything
 * GodSpawnHandler.getGodEntityType() maps to a com.divineworld.entity.gods.*
 * class rather than a vanilla EntityType).
 *
 * This is deliberately NOT the same renderer as DWClientBot's
 * GodEntityRenderer. That one is built around the invisible ServerPlayer
 * puppet's "god / humanoid / disguise" form-cycling system (dispatching on
 * dw_form NBT) and always renders its humanoid delegate at a flat 1.0x scale
 * — by its own doc comment, "the imposing god-form scale only applies to the
 * real boss body entity, not the humanoid puppet." This class IS that real
 * boss body's renderer: no form-dispatch needed (the body doesn't have a
 * dw_form concept, it just always looks like its god), and it applies the
 * imposing per-type scale that nothing else currently does for these five
 * god types (Creaking already gets this from CreakingGeoRenderer).
 *
 * One renderer, shared across all five god types via the generic T — the
 * model resolves geo/texture/animation dynamically per entity through
 * entity.getGodType(), same as GodHumanoidGeoModel already does.
 *
 * Registered once per god type in DivineClientSetup via EntityRenderers.register().
 */
@OnlyIn(Dist.CLIENT)
public class GodBodyGeoRenderer<T extends BaseGodEntity> extends GeoEntityRenderer<T> {

    public GodBodyGeoRenderer(EntityRendererProvider.Context context) {
        super(context, new GodHumanoidGeoModel<>());
        this.shadowRadius = 1.0f;
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
        float scale = switch (animatable.getGodType()) {
            case "ender_dragon"   -> 4.0f;
            case "wither"         -> 1.8f;
            case "warden"         -> 1.5f;
            case "elder_guardian" -> 2.0f;
            case "oracle"         -> 1.0f;
            default               -> 1.0f;
        };
        poseStack.scale(scale, scale, scale);
    }
}