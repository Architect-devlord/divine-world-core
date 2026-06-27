// src/main/java/com/divineworld/client/model/CreakingGeoModel.java
// DWClientBot — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.client.model;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.gods.AICreaking;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.model.GeoModel;

/**
 * GeckoLib GeoModel for DWClientBot's AICreaking.
 *
 * FIX (plan-creaking-geckolib-and-oracle-teach.md, Part 1, Step 2):
 * The previous CreakingModel<T> extended HierarchicalModel<T> — a hand-
 * coded box model with vanilla texOffs() UV coordinates. The new
 * ai_creaking.png texture uses a UV layout from the GeckoLib .geo.json
 * export, NOT the old box model's UV layout — rendering against the old
 * model would produce garbled textures. This class replaces the entire
 * model with GeoModel, which reads geometry from the .geo.json instead.
 *
 * Resource paths (DWClientBot's own resource pack):
 *   assets/{MOD_ID}/geo/entity/ai_creaking.geo.json
 *   assets/{MOD_ID}/textures/entity/ai_creaking.png
 *   assets/{MOD_ID}/animations/entity/ai_creaking.animation.json
 *
 * These three files were already present in DWClientBot's resources
 * before this fix — they just were never connected to any Java class.
 * This class is the connection.
 */
@OnlyIn(Dist.CLIENT)
public class CreakingGeoModel extends GeoModel<AICreaking> {

    private static final ResourceLocation MODEL =
            new ResourceLocation(DWClientMod.MOD_ID, "geo/entity/ai_creaking.geo.json");
    private static final ResourceLocation TEXTURE =
            new ResourceLocation(DWClientMod.MOD_ID, "textures/entity/ai_creaking.png");
    private static final ResourceLocation ANIMATION =
            new ResourceLocation(DWClientMod.MOD_ID, "animations/entity/ai_creaking.animation.json");

    @Override
    public ResourceLocation getModelResource(AICreaking entity) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AICreaking entity) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AICreaking entity) {
        return ANIMATION;
    }
}