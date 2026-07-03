// src/main/java/com/divineworld/client/DWClientMod.java
package com.divineworld.client;

import com.divineworld.client.entity.ModEntities;
import com.divineworld.client.network.ClientNetworkHandler;
import com.divineworld.client.network.TCPServer;
import com.divineworld.client.utils.AgentsJsonReader;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.IEventBus;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.event.lifecycle.FMLCommonSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

/**
 * Divine World Client Mod — PORT RESOLUTION via agents.json
 *
 * Port resolution order (most reliable first):
 *
 *   1. agents.json lookup by player display name  (~/Documents/agents.json)
 *      Called by ClientEventHandler.onPlayerLogin() once the Minecraft
 *      session is live and getUser().getName() returns "Alice" etc.
 *      This is the PRIMARY path — works even when JVM -D properties are not
 *      delivered by the launcher.
 *
 *   2. JVM system properties  (-Ddw.tcp.port, -Ddw.backend.port)
 *      Set via instance.cfg JvmArgs by the Python launcher.
 *      Used as a pre-login hint when available.
 *
 *   3. Hard-coded defaults  (TCP=11401, WS=21401)
 *      Last resort, only during the brief window before player login.
 *
 * Why agents.json is primary
 * --------------------------
 * UltimMC's INST_JAVA env var is the Java executable path — if -D flags are
 * placed there, UltimMC ignores them and launches system Java with no
 * properties.  agents.json is always on disk at ~/Documents/agents.json
 * regardless of launcher behaviour.
 */
@Mod(DWClientMod.MOD_ID)
public class DWClientMod {

    public static final String MOD_ID = "dwclient";
    public static final Logger LOGGER = LogManager.getLogger();

    private static String  agentId;
    private static String  backendUrl          = "ws://127.0.0.1";
    private static int     tcpPort             = AgentsJsonReader.DEFAULT_TCP_PORT;
    private static int     backendPort         = AgentsJsonReader.DEFAULT_WS_PORT;
    private static boolean portsFromAgentsJson = false;
    private static boolean isGodAgent          = false;
    private static String  godType             = null;

    public DWClientMod() {
        IEventBus modEventBus = FMLJavaModLoadingContext.get().getModEventBus();

        loadConfiguration();

        modEventBus.addListener(this::commonSetup);
        modEventBus.addListener(this::clientSetup);

        ModEntities.ENTITIES.register(modEventBus);

        // NOTE: ClientEventHandler, TransformationHandler, GodAbilityVisualHandler,
        // and ClientChatEventHandler are all annotated with @Mod.EventBusSubscriber
        // so Forge auto-registers them at mod load — manual register() calls here
        // would cause every event to fire twice.  Do NOT re-register them.
        MinecraftForge.EVENT_BUS.register(this);

        LOGGER.info("=".repeat(60));
        LOGGER.info("  Divine World Client Mod v2.3");
        LOGGER.info("=".repeat(60));
        LOGGER.info("  Agent ID  : {}", agentId != null ? agentId : "<pending player login>");
        LOGGER.info("  TCP port  : {} (provisional)", tcpPort);
        LOGGER.info("  WS port   : {} (provisional)", backendPort);
        LOGGER.info("  Backend   : {}", backendUrl);
        LOGGER.info("  Mode      : {}", isGodAgent ? "GOD (" + godType + ")" : "NPC");
        LOGGER.info("  Ports will be confirmed from agents.json after player login");
        LOGGER.info("=".repeat(60));
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Setup events
    // ─────────────────────────────────────────────────────────────────────────

    private void commonSetup(final FMLCommonSetupEvent event) {
        ClientNetworkHandler.register();
        LOGGER.info("[CommonSetup] Network handlers registered");
    }

    private void clientSetup(final FMLClientSetupEvent event) {
        event.enqueueWork(() ->
            LOGGER.info("[ClientSetup] Client components initialised")
        );
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Phase 1  — mod construction (JVM properties, no player name yet)
    // ─────────────────────────────────────────────────────────────────────────

    private void loadConfiguration() {
        backendUrl = System.getProperty("dw.backend.url", "ws://127.0.0.1");
        godType    = System.getProperty("dw.god.type");
        if (godType != null && !godType.isEmpty()) isGodAgent = true;

        // Agent ID from JVM property — may be null/stale if launcher didn't deliver it
        String jvmAgentId = System.getProperty("dw.agent.id");
        if (jvmAgentId != null && !jvmAgentId.isEmpty()
                && !jvmAgentId.startsWith("DW_AGENT_")) {
            agentId = jvmAgentId;
        }

        // TCP port from JVM property (highest priority override)
        String tcpProp = System.getProperty("dw.tcp.port");
        if (tcpProp != null && !tcpProp.isEmpty()) {
            try {
                int p = Integer.parseInt(tcpProp.trim());
                if (p > 0 && p < 65536) {
                    tcpPort     = p;
                    backendPort = p + AgentsJsonReader.WS_PORT_OFFSET;
                    LOGGER.info("[Config] Ports from -Ddw.tcp.port: TCP {} / WS {}", tcpPort, backendPort);
                    return;
                }
            } catch (NumberFormatException ignored) {}
        }

        // WS port from JVM property
        String wsProp = System.getProperty("dw.backend.port");
        if (wsProp != null && !wsProp.isEmpty()) {
            try {
                int p = Integer.parseInt(wsProp.trim());
                if (p > 0 && p < 65536) {
                    backendPort = p;
                    tcpPort     = Math.max(AgentsJsonReader.PORT_START,
                                           p - AgentsJsonReader.WS_PORT_OFFSET);
                    LOGGER.info("[Config] Ports from -Ddw.backend.port: TCP {} / WS {}", tcpPort, backendPort);
                    return;
                }
            } catch (NumberFormatException ignored) {}
        }

        // Early agents.json lookup if we already have a usable agent ID
        if (agentId != null && !agentId.isEmpty()) {
            AgentsJsonReader.PortPair pp = AgentsJsonReader.lookupPorts(agentId);
            if (pp != null) {
                tcpPort            = pp.tcpPort;
                backendPort        = pp.wsPort;
                portsFromAgentsJson = true;
                LOGGER.info("[Config] Early agents.json lookup for '{}': TCP {} / WS {}",
                        agentId, tcpPort, backendPort);
                return;
            }
        }

        LOGGER.info("[Config] Using default ports TCP {} / WS {} — will re-resolve after login",
                tcpPort, backendPort);
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Phase 2  — called by ClientEventHandler.onPlayerLogin()
    // ─────────────────────────────────────────────────────────────────────────

    /**
     * Re-resolve ports from agents.json using the live Minecraft player name.
     *
     * Called by ClientEventHandler.onPlayerLogin() once the session is active
     * and Minecraft.getInstance().getUser().getName() is reliable.
     *
     * @param playerName  Minecraft display name (e.g. "Alice")
     * @return true if ports were successfully resolved from agents.json
     */
    public static boolean resolvePortsFromPlayerName(String playerName) {
        if (playerName == null || playerName.isEmpty()) return false;

        // Update agent ID to the actual player name if we didn't get it from JVM props
        if (agentId == null || agentId.isEmpty() || agentId.startsWith("DW_AGENT_")) {
            agentId = playerName;
            LOGGER.info("[Config] Agent ID set from player name: '{}'", agentId);
        }

        AgentsJsonReader.PortPair pp = AgentsJsonReader.lookupPorts(playerName);
        if (pp == null) {
            LOGGER.warn("[Config] '{}' not found in agents.json — using TCP {} / WS {}",
                    playerName, tcpPort, backendPort);
            return false;
        }

        int oldTcp = tcpPort;
        int oldWs  = backendPort;
        tcpPort            = pp.tcpPort;
        backendPort        = pp.wsPort;
        portsFromAgentsJson = true;

        LOGGER.info("[Config] ✅ agents.json resolved '{}': TCP {} / WS {}",
                playerName, tcpPort, backendPort);

        if (oldTcp != tcpPort || oldWs != backendPort) {
            LOGGER.info("[Config] Ports changed ({}/{} → {}/{}) — TCPServer + WebSocket will reinit",
                    oldTcp, oldWs, tcpPort, backendPort);
        }
        return true;
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Public getters
    // ─────────────────────────────────────────────────────────────────────────

    public static String  getAgentId()             { return agentId != null ? agentId : "unknown"; }
    public static String  getBackendUrl()          { return backendUrl; }
    public static int     getBackendPort()         { return backendPort; }
    public static int     getTcpPort()             { return tcpPort; }
    public static boolean isGodAgent()             { return isGodAgent; }
    public static String  getGodType()             { return godType; }
    public static boolean isPortsFromAgentsJson()  { return portsFromAgentsJson; }

    /** Full WebSocket URL the agent's Python backend listens on. */
    public static String getWebSocketUrl() {
        return backendUrl + ":" + backendPort + "/ws/agent";
    }

    // ─────────────────────────────────────────────────────────────────────────
    // Entity helpers
    // ─────────────────────────────────────────────────────────────────────────

    public static ResourceLocation id(String path) {
        return new ResourceLocation(MOD_ID, path);
    }

    public static boolean isGodEntity(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().contains("dw_god");
    }

    public static boolean isDisguised(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().getBoolean("dw_disguised");
    }

    public static String getEntityGodType(net.minecraft.world.entity.Entity entity) {
        return entity.getPersistentData().getString("dw_god_type");
    }
}