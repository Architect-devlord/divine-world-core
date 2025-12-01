// com/divineworld/client/ClientModInitializer.java
package com.divineworld.client;

import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

@Mod.EventBusSubscriber(modid = "divineworld", bus = Mod.EventBusSubscriber.Bus.MOD)
public class ClientModInitializer {

    public static void init() {
        // Register the ChatBubbleManager to Forge's EVENT_BUS
        FMLJavaModLoadingContext.get().getModEventBus().addListener(ClientModInitializer::setup);
    }

    private static void setup(final FMLClientSetupEvent event) {
        // Register client-side events
        net.minecraftforge.common.MinecraftForge.EVENT_BUS.register(ChatBubbleManager.class);
    }
}
