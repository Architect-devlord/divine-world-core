package com.divineworld;

import com.divineworld.commands.CommandRegistrar;
import com.divineworld.commands.OracleCommandRegistrar;
import com.divineworld.events.BreedingDetector;
import com.divineworld.entity.ModEntities;
import com.divineworld.network.NetworkHandler;
import com.divineworld.oracle.LLMOracleBrain;
import com.divineworld.oracle.OracleSystem;
import com.divineworld.utils.Config;
import com.divineworld.utils.GenesisManager;
import com.divineworld.utils.TaggedEntitySystem;
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

        // Register entities
        ModEntities.ENTITIES.register(modBus);

        // Setup method for mod lifecycle
        modBus.addListener(this::setup);

        // Register Forge event handlers
        forgeBus.register(BreedingDetector.class);
        forgeBus.register(TaggedEntitySystem.class);
        forgeBus.register(GenesisManager.class);
        forgeBus.register(this);

        LOGGER.info("=".repeat(60));
        LOGGER.info("  Divine World Mod v2.1 Loading (1.20.1)");
        LOGGER.info("=".repeat(60));
        LOGGER.info("Features:");
        LOGGER.info("  ✅ NPC Breeding System");
        LOGGER.info("  ✅ Auto-Packaging Support");
        LOGGER.info("  ✅ Tag-Based Entity Tracking");
        LOGGER.info("  ✅ Genesis Divine Reset");
        LOGGER.info("  ✅ God Entity System");
        LOGGER.info("  ✅ Oracle System");
        LOGGER.info("  ✅ AI Player Management");
        LOGGER.info("=".repeat(60));
    }

    public static DWMod getInstance() {
        return instance;
    }

    @SubscribeEvent
    public void onServerStarting(ServerStartingEvent evt) {
        this.server = evt.getServer();
        LOGGER.info("[DivineWorld] Server starting - initializing Oracle System");

        // Initialize oracle brain and system
        oracleBrain = new LLMOracleBrain("gemma3:1b", "http://127.0.0.1:11434", false);
        oracleSystem = new OracleSystem(oracleBrain);
        MinecraftForge.EVENT_BUS.register(oracleSystem);

        // Register Oracle commands
        MinecraftForge.EVENT_BUS.register(new OracleCommandRegistrar(oracleSystem, oracleBrain));

        // Register standard commands
        CommandRegistrar.register();

        LOGGER.info("[DivineWorld] Oracle System initialized successfully");
    }

    @SubscribeEvent
    public void onServerStopping(ServerStoppingEvent evt) {
        shutdown();
    }

    private void setup(FMLCommonSetupEvent event) {
        LOGGER.info("[DivineWorld] Running common setup phase");

        // Initialize network handler
        NetworkHandler.register();

        // Commands registration can be deferred to server start
        event.enqueueWork(() -> {
            CommandRegistrar.register();
            LOGGER.info("[DivineWorld] Commands registered in setup");
        });

        LOGGER.info("[DivineWorld] Common setup complete");
    }

    public void shutdown() {
        LOGGER.info("[DivineWorld] Shutting down mod...");
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
        scheduler.scheduleAtFixedRate(() -> {
            if (server != null) {
                server.execute(() -> {
                    if (!task.getAsBoolean()) {
                        // Stop repeating if the task returns false
                    }
                });
            }
        }, delayTicks * 50L, periodTicks * 50L, TimeUnit.MILLISECONDS);
    }

    // Getters and setters
    public OracleSystem getOracleSystem() { return oracleSystem; }
    public LLMOracleBrain getOracleBrain() { return oracleBrain; }
    public void setOracleBrain(LLMOracleBrain brain) { this.oracleBrain = brain; }
    public MinecraftServer getServer() { return server; }
}