// src/main/java/com/divineworld/DWMod.java
// DivineWorld server mod
package com.divineworld;

import com.divineworld.commands.CommandRegistrar;
import com.divineworld.entity.ModEntities;
import com.divineworld.events.BreedingEventHandler;
import com.divineworld.events.ProximityChatHandler;
import com.divineworld.network.NetworkHandler;
import com.divineworld.oracle.LLMOracleBrain;
import com.divineworld.oracle.OllamaManager;
import com.divineworld.oracle.OracleSystem;
import com.divineworld.utils.Config;
import com.divineworld.utils.GenesisManager;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.event.server.ServerStartingEvent;
import net.minecraftforge.event.server.ServerStoppingEvent;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import net.minecraftforge.common.MinecraftForge;
import net.minecraft.server.MinecraftServer;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Mod(DWMod.MOD_ID)
public class DWMod {
    public static final String MOD_ID = "divineworld";
    private static DWMod instance;
    public static final Logger LOGGER = LogManager.getLogger();

    private OracleSystem oracleSystem;
    private LLMOracleBrain oracleBrain;
    private MinecraftServer server;
    private final ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2);

    public DWMod() {
        instance = this;

        IEventBus modBus = FMLJavaModLoadingContext.get().getModEventBus();
        IEventBus forgeBus = MinecraftForge.EVENT_BUS;

        // Load config
        Config.load();

        // CRITICAL: Initialize Oracle BEFORE any events
        initializeOracle();

        // Register custom entities (server + client entity type registry)
        ModEntities.ENTITIES.register(modBus);
        // NOTE: EntityAttributeRegistrar is @Mod.EventBusSubscriber(Bus.MOD) — auto-registered

        // Setup method for mod lifecycle
        modBus.addListener(this::setup);

        // Register Forge event handlers
        forgeBus.register(BreedingEventHandler.class);
        forgeBus.register(TaggedEntitySystem.class);
        forgeBus.register(GenesisManager.class);
        forgeBus.register(ProximityChatHandler.class);
        forgeBus.register(this);

        LOGGER.info("=".repeat(60));
        LOGGER.info("  Divine World Mod v2.2 Loading (1.20.1)");
        LOGGER.info("=".repeat(60));
        LOGGER.info("Features:");
        LOGGER.info("  ✅ NPC Breeding System");
        LOGGER.info("  ✅ Auto-Packaging Support");
        LOGGER.info("  ✅ Tag-Based Entity Tracking");
        LOGGER.info("  ✅ Genesis & Divine Reset");
        LOGGER.info("  ✅ God Entity System");
        LOGGER.info("  ✅ GeckoLib Creaking God (divineworld:ai_creaking)");
        LOGGER.info("  ✅ Oracle System (ENHANCED)");
        LOGGER.info("  ✅ AI Player Management");
        LOGGER.info("=".repeat(60));
    }

    /**
     * ENHANCED: Initialize Oracle with better error handling
     * Assumes Ollama daemon is already running
     */
    private void initializeOracle() {
        try {
            String model = Config.getOracleModel();
            String endpoint = Config.getOracleEndpoint();

            LOGGER.info("[DivineWorld] ╔════════════════════════════════════╗");
            LOGGER.info("[DivineWorld] Initializing Oracle System");
            LOGGER.info("[DivineWorld]   Model: {}", model);
            LOGGER.info("[DivineWorld]   Endpoint: {}", endpoint);
            LOGGER.info("[DivineWorld] ╚════════════════════════════════════╝");

            // Initialize Ollama connection (assumes daemon is running)
            OllamaManager.initialize(model);

            // Check if Ollama is accessible
            if (!OllamaManager.isOllamaRunning()) {
                LOGGER.error("[DivineWorld] ❌ Cannot connect to Ollama!");
                LOGGER.error("[DivineWorld] Make sure Ollama daemon is running");
                LOGGER.error("[DivineWorld] Oracle features will be LIMITED");
                LOGGER.error("[DivineWorld] Use /oracle restart to reconnect");

                // Create Oracle with warning
                oracleBrain = new LLMOracleBrain(model, endpoint, false);
                oracleSystem = new OracleSystem(oracleBrain);
                return;
            }

            // Check model availability
            OllamaManager.ModelStatus status = OllamaManager.checkModelStatus(model);

            switch (status) {
                case AVAILABLE:
                    LOGGER.info("[DivineWorld] ✅ Model '{}' verified and ready", model);
                    break;

                case NOT_DOWNLOADED:
                    LOGGER.warn("[DivineWorld] ⚠️ Model '{}' is NOT downloaded!", model);
                    LOGGER.warn("[DivineWorld] ");
                    LOGGER.warn("[DivineWorld] Oracle will NOT work until you download it:");
                    LOGGER.warn("[DivineWorld]   In-game: /oracle pull {}", model);
                    LOGGER.warn("[DivineWorld]   Or terminal: ollama pull {}", model);
                    LOGGER.warn("[DivineWorld] ");
                    LOGGER.warn("[DivineWorld] Available models: /oracle list_models");
                    break;

                case OLLAMA_NOT_RUNNING:
                    LOGGER.error("[DivineWorld] ❌ Cannot verify model - Ollama not responding");
                    break;

                case ERROR:
                    LOGGER.error("[DivineWorld] ❌ Error checking model status");
                    break;
            }

            // Create Oracle Brain and System
            oracleBrain = new LLMOracleBrain(model, endpoint, false);
            oracleSystem = new OracleSystem(oracleBrain);

            LOGGER.info("[DivineWorld] ✅ Oracle System initialized");
            LOGGER.info("[DivineWorld] ╚════════════════════════════════════╝");

        } catch (Exception e) {
            LOGGER.error("[DivineWorld] ❌ Failed to initialize Oracle System", e);

            // Create fallback
            oracleBrain = new LLMOracleBrain("phi3:mini", "http://localhost:11434", false);
            oracleSystem = new OracleSystem(oracleBrain);

            LOGGER.warn("[DivineWorld] Using fallback Oracle configuration");
        }
    }

    public static DWMod getInstance() {
        return instance;
    }

    private boolean oracleSystemRegistered = false;  // FIX M-09: prevent double-registration on server restart

    @SubscribeEvent
    public void onServerStarting(ServerStartingEvent evt) {
        this.server = evt.getServer();
        LOGGER.info("[DivineWorld] Server starting - registering Oracle handlers");

        if (!oracleSystemRegistered) {
            MinecraftForge.EVENT_BUS.register(oracleSystem);
            oracleSystemRegistered = true;
        }

        LOGGER.info("[DivineWorld] Oracle handlers registered");
    }

    @SubscribeEvent
    public void onRegisterCommands(RegisterCommandsEvent event) {
        LOGGER.info("[DivineWorld] Registering commands...");

        // Verify Oracle is initialized
        if (oracleSystem == null || oracleBrain == null) {
            LOGGER.error("[DivineWorld] ❌ Oracle not initialized! Reinitializing...");
            initializeOracle();
        }

        LOGGER.info("[DivineWorld] Oracle status - System: {}, Brain: {}",
                (oracleSystem != null ? "✅" : "❌"),
                (oracleBrain != null ? "✅" : "❌"));

        // FIX (command-registrar consolidation): CommandRegistrar.java existed
        // but was dead code — every command group was registered directly
        // from here instead. All five groups (Divine, NPC, God, Oracle, Breed)
        // are now registered from CommandRegistrar.register() in one place;
        // adding a new command group going forward only needs a line added
        // there, not here.
        CommandRegistrar.register(event, oracleSystem, oracleBrain);
        LOGGER.info("[DivineWorld] ✅ All commands registered via CommandRegistrar");
    }

    @SubscribeEvent
    public void onServerStopping(ServerStoppingEvent evt) {
        shutdown();
    }

    private void setup(FMLCommonSetupEvent event) {
        LOGGER.info("[DivineWorld] Running common setup phase");

        // Initialize network handler
        NetworkHandler.register();

        // Commands are NOT registered here. CommandRegistrar.register() needs
        // the live OracleSystem/LLMOracleBrain instances and the
        // RegisterCommandsEvent's dispatcher, neither of which exist at this
        // point in the mod lifecycle — both are only available inside
        // onRegisterCommands() below, which is this mod's sole command
        // registration point.

        LOGGER.info("[DivineWorld] Common setup complete");
    }

    public void shutdown() {
        LOGGER.info("[DivineWorld] Shutting down mod...");

        // Shutdown Ollama connection
        OllamaManager.shutdown();

        scheduler.shutdownNow();
        LOGGER.info("[DivineWorld] Shutdown complete");
    }

    public void scheduleTask(Runnable task, long delayTicks) {
        scheduler.schedule(() -> {
            if (server != null) {
                server.execute(task);
            }
        }, delayTicks * 50L, TimeUnit.MILLISECONDS);
    }

    public void scheduleRepeatingTask(java.util.function.BooleanSupplier task, long delayTicks, long periodTicks) {
        // We need to capture the future so we can cancel it when the task signals done.
        // ScheduledFuture is assigned after scheduleAtFixedRate returns, so we wrap it
        // in a single-element array to allow the lambda to reference it.
        java.util.concurrent.ScheduledFuture<?>[] futureRef = new java.util.concurrent.ScheduledFuture<?>[1];

        futureRef[0] = scheduler.scheduleAtFixedRate(() -> {
            if (server != null) {
                server.execute(() -> {
                    boolean continueTask = task.getAsBoolean();
                    if (!continueTask) {
                        // Cancel the repeating task from outside the scheduler thread
                        // (mayInterruptIfRunning=false so the current execution is not
                        //  interrupted — we just stop future invocations).
                        if (futureRef[0] != null) {
                            futureRef[0].cancel(false);
                        }
                    }
                });
            }
        }, delayTicks * 50L, periodTicks * 50L, TimeUnit.MILLISECONDS);
    }

    // Getters and setters
    public OracleSystem getOracleSystem() {
        if (oracleSystem == null) {
            LOGGER.warn("[DivineWorld] Oracle system accessed before initialization!");
            initializeOracle();
        }
        return oracleSystem;
    }

    public LLMOracleBrain getOracleBrain() {
        if (oracleBrain == null) {
            LOGGER.warn("[DivineWorld] Oracle brain accessed before initialization!");
            initializeOracle();
        }
        return oracleBrain;
    }

    public void setOracleBrain(LLMOracleBrain brain) {
        this.oracleBrain = brain;
        if (oracleSystem != null) {
            oracleSystem.setOracleBrain(brain);
        }
    }

    public MinecraftServer getServer() { return server; }
}