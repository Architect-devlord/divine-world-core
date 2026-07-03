// src/main/java/com/divineworld/client/ClientSetup.java
package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.render.CreakingGeoRenderer;
import com.divineworld.client.render.GodEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRenderers;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;

/**
 * Client Setup — entity renderer registrations.
 *
 * FIX (Creaking GeckoLib conversion): removed CreakingModel / CREAKING_LAYER /
 * registerLayerDefinitions entirely.  GeckoLib 4.x does NOT use Forge's
 * ModelLayerLocation system — it reads geometry from .geo.json resources at
 * runtime via GeoModel, not from baked LayerDefinitions registered at startup.
 * Keeping the old event listener and ModelLayerLocation around caused a
 * confusing log entry ("Registering model layers...") and registered a baked
 * layer that nothing ever read, but was otherwise harmless.  Removed for
 * clarity; if a future non-GeckoLib entity is added, add it back then.
 *
 * God entity renderers (GodEntityRenderer):
 *   All god types except Creaking share GodEntityRenderer, which handles all
 *   three forms internally:
 *     god form      — nameplate only (puppet is invisible, boss body renders)
 *     humanoid form — delegates to GodHumanoidGeoRenderer (GeckoLib)
 *                     reads god_<type>.geo.json / .png / .animation.json
 *     disguise form — PlayerModel with Steve or Alex vanilla skin at 1.0×
 *
 * Creaking (AI_CREAKING):
 *   Uses CreakingGeoRenderer for its GOD form (ai_creaking.geo.json etc.).
 *   Its HUMANOID form is handled by the same GodEntityRenderer delegate
 *   path as every other god — GodHumanoidGeoModel reads god_creaking.geo.json
 *   regardless of god type.
 *
 *   NOTE: ModEntities.AI_CREAKING entity class (AICreaking / AICreakingEntity)
 *   is a BaseGodEntity subclass — so it satisfies GodEntityRenderer's
 *   BaseGodEntity type check AND CreakingGeoRenderer's GeoEntity bound.
 *   However, a single EntityType can only have one registered renderer.
 *   The chosen renderer for AI_CREAKING is CreakingGeoRenderer (its god-form
 *   appearance).  Humanoid/disguise form dispatch for Creaking works the same
 *   way as the other gods — GodEntityRenderer.render() is called from inside
 *   CreakingGeoRenderer.render() when dw_form ≠ "god".  See CreakingGeoRenderer
 *   for the override.
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public class ClientSetup {

    @SubscribeEvent
    public static void onClientSetup(FMLClientSetupEvent event) {
        DWClientMod.LOGGER.info("[ClientSetup] Registering entity renderers...");

        event.enqueueWork(() -> {
            // ── Non-Creaking gods — GodEntityRenderer handles all three forms ──
            EntityRenderers.register(ModEntities.AI_ORACLE.get(),         GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_ENDER_DRAGON.get(),   GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_WITHER.get(),         GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_WARDEN.get(),         GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_ELDER_GUARDIAN.get(), GodEntityRenderer::new);

            // ── Creaking — CreakingGeoRenderer for god form; it calls the
            //    GodEntityRenderer delegate path for humanoid/disguise forms ──
            EntityRenderers.register(ModEntities.AI_CREAKING.get(), CreakingGeoRenderer::new);

            DWClientMod.LOGGER.info("[ClientSetup] ✅ Entity renderers registered");
        });
    }
    // No registerLayerDefinitions override — GeckoLib does not use LayerDefinitions.
}