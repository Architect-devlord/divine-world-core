// src/main/java/com/divineworld/model/CreakingGeoModel.java
// DivineWorld server mod — GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.model;

import com.divineworld.DWMod;
import com.divineworld.entity.AICreakingEntity;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.model.GeoModel;

/**
 * GeckoLib model for the Creaking god entity.
 *
 * Resource paths (place your exported BBmodel files here):
 *   assets/divineworld/geo/entity/ai_creaking.geo.json        ← BBmodel geo export
 *   assets/divineworld/textures/entity/ai_creaking.png        ← texture atlas
 *   assets/divineworld/animations/entity/ai_creaking.animation.json  ← BBmodel animation export
 *
 * BBmodel export checklist:
 *   1. File → Export Model → GeckoLib Model → save as ai_creaking.geo.json
 *   2. File → Export Animations → GeckoLib Animations → save as ai_creaking.animation.json
 *   3. Texture PNG goes to the textures/entity/ folder
 *
 * Animation names in the .animation.json MUST exactly match:
 *   walk, run, attack, tentacles_out, tentacles_retract,
 *   grab_eat, tentacles_wall_climb, tentacle_jump, burrow,
 *   tentacle_run, tentacle_attack, dig_out
 */
@OnlyIn(Dist.CLIENT)
public class CreakingGeoModel extends GeoModel<AICreakingEntity> {

    private static final ResourceLocation MODEL =
            new ResourceLocation(DWMod.MOD_ID, "geo/entity/ai_creaking.geo.json");
    private static final ResourceLocation TEXTURE =
            new ResourceLocation(DWMod.MOD_ID, "textures/entity/ai_creaking.png");
    private static final ResourceLocation ANIMATION =
            new ResourceLocation(DWMod.MOD_ID, "animations/entity/ai_creaking.animation.json");

    @Override
    public ResourceLocation getModelResource(AICreakingEntity entity) {
        return MODEL;
    }

    @Override
    public ResourceLocation getTextureResource(AICreakingEntity entity) {
        return TEXTURE;
    }

    @Override
    public ResourceLocation getAnimationResource(AICreakingEntity entity) {
        return ANIMATION;
    }
}