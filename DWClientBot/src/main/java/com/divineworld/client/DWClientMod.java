package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.network.NetworkHandler;
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
 * Divine World Client Mod - PRODUCTION VERSION
 *
 * Integrates with Python backend via binary WebSocket protocol.
 * Supports both normal agents and god entities.
 *
 * FIXED:
 * - Proper entity registration
 * - Thread-safe WebSocket
 * - Vision capture optimization
 * - God entity spawning
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

        LOGGER.info("Divine World Client Mod initializing for: {}", agentId);
        LOGGER.info("  Mode: {}", isGodAgent ? "GOD (" + godType + ")" : "NORMAL");
        LOGGER.info("  Backend: {}:{}", backendUrl, backendPort);
    }

    private void commonSetup(final FMLCommonSetupEvent event) {
        LOGGER.info("Common setup phase");

        // Register network handlers
        NetworkHandler.register();
    }

    private void clientSetup(final FMLClientSetupEvent event) {
        LOGGER.info("Client setup phase");

        event.enqueueWork(() -> {
            // Post-setup initialization
            initializeClientComponents();
        });
    }

    private void initializeClientComponents() {
        LOGGER.info("Initializing client components...");

        // Components will be initialized when player joins world
        // See ClientEventHandler.onPlayerJoinWorld

        LOGGER.info("Client components registered");
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

        LOGGER.info("Configuration loaded:");
        LOGGER.info("  Agent ID: {}", agentId);
        LOGGER.info("  Backend: {}:{}", backendUrl, backendPort);
        LOGGER.info("  God Type: {}", godType != null ? godType : "N/A");
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
}