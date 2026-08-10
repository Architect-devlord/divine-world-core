// src/main/java/com/divineworld/clientsetup/DivineClientSetup.java
// DivineWorld server mod — client-dist only
package com.divineworld.clientsetup;
// FIX: this class used to live in package com.divineworld.client — the exact
// same package name DWClientBot's own classes (DWClientMod, ClientSetup,
// ClientEventHandler, etc.) use. Two separate mod jars both containing the
// same package name is illegal under the Java Platform Module System once
// both are loaded together as named modules — Forge's
// ModuleLayerHandler.buildLayer() throws java.lang.module.ResolutionException
// ("Module divineworld contains package com.divineworld.client, module
// dwclient exports package com.divineworld.client to divineworld") and the
// game fails to launch at all with both mods installed. This was the only
// DivineWorld file in that package; moving it to its own package resolves
// the collision without touching DWClientBot. Nothing else in DivineWorld
// referenced this class directly (it self-registers via
// @Mod.EventBusSubscriber), so no other import needed updating.

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
 * Self-registers via the @Mod.EventBusSubscriber annotation below (with
 * value = Dist.CLIENT, so Forge skips it entirely on a dedicated server) —
 * nothing in DWMod.java needs to reference this class directly.
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