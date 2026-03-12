// src/main/java/com/divineworld/client/DWClientMod.java
package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.network.ClientNetworkHandler;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Divine World Client Mod - PRODUCTION VERSION WITH RENDERING
 *
 * Features:
 * - WebSocket communication with Python backend
 * - Vision capture for AI perception
 * - God entity rendering with transformations
 * - Custom Creaking entity with full model
 * - Player abilities for all agents
 * - Chat bubbles for AI speech
 *
 * UPDATED:
 * - Added rendering system initialization
 * - Added transformation tracking
 * - Added god ability visual effects
 */
@Mod(DWClientMod.MOD_ID)
public class DWClientMod {
    public static final String MOD_ID = "dwclient";
    public static final Logger LOGGER = LogManager.getLogger();

    // Configuration from system properties
    private static String agentId;
    private static String backendUrl;
    private static int backendPort = 11400;
    private static boolean isGodAgent = false;
    private static String godType = null;

    public DWClientMod() {
        IEventBus modEventBus = FMLJavaModLoadingContext.get().getModEventBus();

        // Load configuration early
        loadConfiguration();

        // Register common setup
        modEventBus.addListener(this::commonSetup);
        modEventBus.addListener(this::clientSetup);

        // Register entities
        ModEntities.ENTITIES.register(modEventBus);

        // Register to event bus
        MinecraftForge.EVENT_BUS.register(this);

        // Register client-side event handlers
        MinecraftForge.EVENT_BUS.register(ClientEventHandler.class);
        MinecraftForge.EVENT_BUS.register(TransformationHandler.class);
        MinecraftForge.EVENT_BUS.register(GodAbilityVisualHandler.class);
        MinecraftForge.EVENT_BUS.register(ClientChatEventHandler.class);

        LOGGER.info("=".repeat(60));
        LOGGER.info("  Divine World Client Mod v2.2 (CLIENT-SIDE)");
        LOGGER.info("=".repeat(60));
        LOGGER.info("Agent Configuration:");
        LOGGER.info("  Agent ID: {}", agentId);
        LOGGER.info("  Mode: {}", isGodAgent ? "GOD (" + godType + ")" : "NORMAL");
        LOGGER.info("  Backend: {}:{}", backendUrl, backendPort);
        LOGGER.info("=".repeat(60));
        LOGGER.info("Features:");
        LOGGER.info("  ✅ WebSocket Communication");
        LOGGER.info("  ✅ Vision Capture System");
        LOGGER.info("  ✅ God Entity Rendering");
        LOGGER.info("  ✅ Custom Creaking Model");
        LOGGER.info("  ✅ Transformation System");
        LOGGER.info("  ✅ Player Abilities");
        LOGGER.info("  ✅ Chat Bubbles");
        LOGGER.info("=".repeat(60));
    }

    private void commonSetup(final FMLCommonSetupEvent event) {
        LOGGER.info("[CommonSetup] Initializing network handlers...");

        // Register network handlers
        ClientNetworkHandler.register();

        LOGGER.info("[CommonSetup] ✅ Network handlers registered");
    }

    private void clientSetup(final FMLClientSetupEvent event) {
        LOGGER.info("[ClientSetup] Initializing client components...");

        event.enqueueWork(() -> {
            // Client components are registered via @Mod.EventBusSubscriber
            // See: ClientSetup.java for entity renderers
            // See: ClientEventHandler.java for game events

            LOGGER.info("[ClientSetup] ✅ Client components initialized");
        });
    }

    private void loadConfiguration() {
        // Load from system properties (passed by Python launcher)
        agentId = System.getProperty("dw.agent.id");
        backendUrl = System.getProperty("dw.backend.url", "ws://127.0.0.1");

        String portStr = System.getProperty("dw.backend.port", "11400");
        try {
            backendPort = Integer.parseInt(portStr);
        } catch (NumberFormatException e) {
            LOGGER.warn("Invalid backend port: {}, using default 11400", portStr);
            backendPort = 11400;
        }

        // Check if god agent
        godType = System.getProperty("dw.god.type");
        if (godType != null && !godType.isEmpty()) {
            isGodAgent = true;
            LOGGER.info("Configured as GOD agent: {}", godType);
        }

        // Validate configuration
        if (agentId == null || agentId.isEmpty()) {
            LOGGER.error("No agent ID provided! Using fallback.");
            agentId = "DW_AGENT_" + System.currentTimeMillis();
        }
    }

    // Public getters
    public static String getAgentId() {
        return agentId;
    }

    public static String getBackendUrl() {
        return backendUrl;
    }

    public static int getBackendPort() {
        return backendPort;
    }

    public static boolean isGodAgent() {
        return isGodAgent;
    }

    public static String getGodType() {
        return godType;
    }

    public static ResourceLocation id(String path) {
        return new ResourceLocation(MOD_ID, path);
    }

    /**
     * Check if an entity is a god entity (client-side helper)
     */
    public static boolean isGodEntity(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().contains("dw_god");
    }

    /**
     * Check if a god is disguised (client-side helper)
     */
    public static boolean isDisguised(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().getBoolean("dw_disguised");
    }

    /**
     * Get god type from entity (client-side helper)
     */
    public static String getEntityGodType(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().getString("dw_god_type");
    }
}