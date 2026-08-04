// src/main/java/com/divineworld/client/DivineClientSetup.java
// DivineWorld server mod — client-dist only
package com.divineworld.client;

import com.divineworld.DWMod;
import com.divineworld.entity.ModEntities;
import com.divineworld.render.CreakingGeoRenderer;
import com.divineworld.render.GodBodyGeoRenderer;
import net.minecraft.client.renderer.entity.EntityRenderers;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;

/**
 * Client-side setup for the DivineWorld server mod.
 *
 * Separating client registration here keeps DWMod.java free of @OnlyIn code
 * and prevents crashes on dedicated servers that call FMLClientSetupEvent handlers.
 *
 * Registered in DWMod constructor:
 *   modBus.addListener(DivineClientSetup::onClientSetup)
 * — NOT via @Mod.EventBusSubscriber (the Dist.CLIENT guard on that annotation
 *   works, but an explicit addListener in DWMod is equally clear and avoids
 *   accidental double-registration).
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID,
        bus    = Mod.EventBusSubscriber.Bus.MOD,
        value  = Dist.CLIENT)
public class DivineClientSetup {

    @SubscribeEvent
    public static void onClientSetup(FMLClientSetupEvent event) {
        event.enqueueWork(() -> {
            // Register GeckoLib renderer for divineworld:ai_creaking
            EntityRenderers.register(ModEntities.AI_CREAKING.get(),
                    CreakingGeoRenderer::new);

            // Register GeckoLib renderers for the remaining five god bodies —
            // one shared GodBodyGeoRenderer type, applying each god's own
            // scale via BaseGodEntity.getGodType() at render time.
            EntityRenderers.register(ModEntities.AI_WARDEN.get(), GodBodyGeoRenderer::new);
            EntityRenderers.register(ModEntities.AI_WITHER.get(), GodBodyGeoRenderer::new);
            EntityRenderers.register(ModEntities.AI_ORACLE.get(), GodBodyGeoRenderer::new);
            EntityRenderers.register(ModEntities.AI_ELDER_GUARDIAN.get(), GodBodyGeoRenderer::new);
            EntityRenderers.register(ModEntities.AI_ENDER_DRAGON.get(), GodBodyGeoRenderer::new);

            DWMod.LOGGER.info("[DivineClientSetup] ✅ All 6 god body GeckoLib renderers registered");
        });
    }
}