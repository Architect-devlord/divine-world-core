// src/main/java/com/divineworld/client/ClientSetup.java
package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.model.CreakingModel;
import com.divineworld.client.render.CreakingRenderer;
import com.divineworld.client.render.GodEntityRenderer;
import net.minecraft.client.model.geom.ModelLayerLocation;
import net.minecraft.client.renderer.entity.EntityRenderers;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.EntityRenderersEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;

/**
 * Client Setup - COMPLETE
 * Registers all entity renderers and models
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.MOD, value = Dist.CLIENT)
public class ClientSetup {

    public static final ModelLayerLocation CREAKING_LAYER = new ModelLayerLocation(
            new ResourceLocation(DWClientMod.MOD_ID, "creaking"), "main");

    @SubscribeEvent
    public static void onClientSetup(FMLClientSetupEvent event) {
        DWClientMod.LOGGER.info("[ClientSetup] Registering entity renderers...");

        event.enqueueWork(() -> {
            // Register god entity renderers (all use GodEntityRenderer)
            EntityRenderers.register(ModEntities.AI_ORACLE.get(), GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_ENDER_DRAGON.get(), GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_WITHER.get(), GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_WARDEN.get(), GodEntityRenderer::new);
            EntityRenderers.register(ModEntities.AI_ELDER_GUARDIAN.get(), GodEntityRenderer::new);

            // Register custom Creaking renderer
            EntityRenderers.register(ModEntities.AI_CREAKING.get(), CreakingRenderer::new);

            DWClientMod.LOGGER.info("[ClientSetup] ✅ Entity renderers registered");
        });
    }

    @SubscribeEvent
    public static void registerLayerDefinitions(EntityRenderersEvent.RegisterLayerDefinitions event) {
        DWClientMod.LOGGER.info("[ClientSetup] Registering model layers...");

        // Register Creaking model layer
        event.registerLayerDefinition(CREAKING_LAYER, CreakingModel::createBodyLayer);

        DWClientMod.LOGGER.info("[ClientSetup] ✅ Model layers registered");
    }
}