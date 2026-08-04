// src/main/java/com/divineworld/model/GodHumanoidGeoModel.java
// DivineWorld server mod — client-dist only, GeckoLib 4.4.x, Forge 1.20.1
package com.divineworld.model;

import com.divineworld.DWMod;
import com.divineworld.entity.gods.BaseGodEntity;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import software.bernie.geckolib.model.GeoModel;

/**
 * GeoModel for the god body entities spawned by GodSpawnHandler.
 *
 * This is DivineWorld's own copy of the equivalent class in DWClientBot
 * (com.divineworld.client.model.GodHumanoidGeoModel), adapted to use
 * DivineWorld's own asset namespace instead of DWClientBot's. The actual
 * geo/texture/animation files already exist under both mods' resources
 * (assets/divineworld/... and assets/dwclient/...), so this stays fully
 * self-contained rather than reaching across to DWClientBot's mod id —
 * DivineWorld has no build dependency on DWClientBot.
 *
 * Assets (one trio per god type, under DivineWorld's own resources):
 *   geo/entity/god_{type}.geo.json
 *   textures/entity/god_{type}.png
 *   animations/entity/god_{type}.animation.json
 *
 * Animation names match BaseGodEntity.registerControllers()'s triggerable
 * names exactly (attack, hit, mount, plus the shared movement set) — see
 * that class for the full list.
 */
@OnlyIn(Dist.CLIENT)
public class GodHumanoidGeoModel<T extends BaseGodEntity> extends GeoModel<T> {

    @Override
    public ResourceLocation getModelResource(T entity) {
        return new ResourceLocation(DWMod.MOD_ID,
                "geo/entity/god_" + entity.getGodType() + ".geo.json");
    }

    @Override
    public ResourceLocation getTextureResource(T entity) {
        return new ResourceLocation(DWMod.MOD_ID,
                "textures/entity/god_" + entity.getGodType() + ".png");
    }

    @Override
    public ResourceLocation getAnimationResource(T entity) {
        return new ResourceLocation(DWMod.MOD_ID,
                "animations/entity/god_" + entity.getGodType() + ".animation.json");
    }
}