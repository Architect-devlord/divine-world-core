// src/main/java/com/divineworld/client/model/GodHumanoidGeoModel.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.model;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.BaseGodEntity;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.model.GeoModel;

/**
 * GeoModel for gods in their HUMANOID form.
 *
 * Assets (one trio per god type, must exist in DWClientBot's resources):
 *   geo/entity/god_{type}.geo.json
 *   textures/entity/god_{type}.png
 *   animations/entity/god_{type}.animation.json
 *
 * Animation names match the god form exactly by design — gods use the same
 * ability names (attack, burrow, tentacles_out …) in every form, so the
 * animation controller code in BaseGodEntity.registerControllers() fires the
 * same triggerable animation names regardless of which form is active.  The
 * humanoid .animation.json just provides humanoid-shaped keyframes for those
 * same names, plus the standard player movement set (walk, run, idle, swim,
 * sneak, hit, mount) that vanilla PlayerModel handles automatically for the
 * player-form render but must be explicitly keyframed here since GeckoLib
 * drives the geometry from scratch.
 *
 * Creaking is special: in ITS god form the real boss uses ai_creaking.* assets
 * (CreakingGeoModel / CreakingGeoRenderer, separately registered).  This model
 * only handles the HUMANOID form, so it uses god_creaking.* for creaking too.
 */
@OnlyIn(Dist.CLIENT)
public class GodHumanoidGeoModel<T extends BaseGodEntity> extends GeoModel<T> {

    @Override
    public ResourceLocation getModelResource(T entity) {
        return new ResourceLocation(DWClientMod.MOD_ID,
                "geo/entity/god_" + entity.getGodType() + ".geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(T entity) {
        return new ResourceLocation(DWClientMod.MOD_ID,
                "textures/entity/god_" + entity.getGodType() + ".png");
    }

    @Override
    public ResourceLocation getAnimationResource(T entity) {
        return new ResourceLocation(DWClientMod.MOD_ID,
                "animations/entity/god_" + entity.getGodType() + ".animation.json");
    }
}