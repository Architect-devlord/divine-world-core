package com.divineworld.client;

import com.divineworld.client.entity.GodEntityManager;
import com.divineworld.client.network.TCPServer;
import com.divineworld.client.network.WebSocketManager;
import com.divineworld.client.utils.AgentsJsonReader;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Client Event Handler
 *
 * Handles the client-side lifecycle: first world join, respawn, logout.
 *
 * Port resolution (onPlayerJoinedWorld)
 * -------------------------------------
 * The Minecraft player profile is fully available once the client enters
 * a world.  Minecraft.getInstance().getUser().getName() reliably returns
 * the account display name ("Alice", "Zeus", …) at that point.
 *
 * We use that name to look up the agent's ports in agents.json
 * via DWClientMod.resolvePortsFromPlayerName().  This is the PRIMARY
 * resolution path and works regardless of whether the JVM -D properties
 * were delivered by the launcher.
 *
 *   TCP port  = agents.json["Alice"]          e.g. 11471
 *   WS  port  = TCP + WS_PORT_OFFSET          e.g. 21471
 *
 * Services are started AFTER resolution so they always bind the right port.
 *
 * Fix Bug G — NPE on respawn:
 *   Guard both player and level non-null before calling initializeGodEntity().
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ClientEventHandler {

    private static boolean initialized = false;
    private static int     tickCounter = 0;

    // -------------------------------------------------------------------------
    // Client tick — one-time init
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();

        if (!initialized && mc.player != null && mc.level != null) {
            onPlayerJoinedWorld(mc.player);
            initialized = true;
        }

        tickCounter++;
        if (tickCounter % 100 == 0) {
            logAgentStatus();
        }
    }

    // -------------------------------------------------------------------------
    // World join — port resolution + service startup
    // -------------------------------------------------------------------------

    private static void onPlayerJoinedWorld(LocalPlayer player) {
        // getUser().getName() is the Minecraft account name ("Alice")
        // player.getName().getString() is the in-game entity name (same in offline mode)
        String sessionName = Minecraft.getInstance().getUser().getName();
        String entityName  = player.getName().getString();
        DWClientMod.LOGGER.info("[CEH] Joined world: session='{}' entity='{}'",
                sessionName, entityName);

        // ── Primary: resolve ports from agents.json by player name ─────────
        // Try session name first, fall back to entity name.
        boolean resolved = DWClientMod.resolvePortsFromPlayerName(sessionName);
        if (!resolved && !sessionName.equals(entityName)) {
            resolved = DWClientMod.resolvePortsFromPlayerName(entityName);
        }

        int tcpPort = DWClientMod.getTcpPort();
        int wsPort  = DWClientMod.getBackendPort();
        String src  = DWClientMod.isPortsFromAgentsJson() ? "agents.json" : "fallback default";
        DWClientMod.LOGGER.info("[CEH] Ports ({}): TCP={} WS={}", src, tcpPort, wsPort);

        // ── Start TCP action server on the resolved port ────────────────────
        TCPServer.start(tcpPort);

        // ── Connect WebSocket perception channel ────────────────────────────
        try {
            WebSocketManager.initialize(
                DWClientMod.getBackendUrl(),
                wsPort,
                DWClientMod.getAgentId()
            );
        } catch (Exception e) {
            DWClientMod.LOGGER.error("[CEH] WebSocket init failed: {}", e.getMessage());
        }

        // ── Spawn god entity if applicable ──────────────────────────────────
        if (DWClientMod.isGodAgent()) {
            initializeGodEntity(player);
        }
    }

    private static void initializeGodEntity(LocalPlayer player) {
        String gt = DWClientMod.getGodType();
        DWClientMod.LOGGER.info("[CEH] Initializing god entity: {}", gt);
        try {
            GodEntityManager.initializeGodEntity(gt);
        } catch (Exception e) {
            DWClientMod.LOGGER.error("[CEH] God entity init failed: {}", e.getMessage());
        }
    }

    // -------------------------------------------------------------------------
    // Periodic status
    // -------------------------------------------------------------------------

    private static void logAgentStatus() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return;
        LocalPlayer p = mc.player;
        // FIX B-16: Log4j2 uses {} not {:.0f} — use String.format for numeric formatting
        DWClientMod.LOGGER.debug("[Status] agent='{}' tcp={} ws={} pos=({},{},{}) hp={}",
            DWClientMod.getAgentId(), TCPServer.getPort(), DWClientMod.getBackendPort(),
            String.format("%.0f", p.getX()),
            String.format("%.0f", p.getY()),
            String.format("%.0f", p.getZ()),
            String.format("%.0f", p.getHealth()));
    }

    // -------------------------------------------------------------------------
    // Respawn  (Bug G)
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onPlayerRespawn(PlayerEvent.PlayerRespawnEvent event) {
        if (!(event.getEntity() instanceof LocalPlayer)) return;
        DWClientMod.LOGGER.info("[CEH] Player respawned");
        if (DWClientMod.isGodAgent()) {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player != null && mc.level != null) {
                initializeGodEntity((LocalPlayer) event.getEntity());
            } else {
                DWClientMod.LOGGER.warn("[CEH] Respawn: mc.level null — deferring to next tick");
                initialized = false;
            }
        }
    }

    // -------------------------------------------------------------------------
    // Logout
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        DWClientMod.LOGGER.info("[CEH] Player logged out — stopping services");
        initialized = false;
        TCPServer.stop();
        WebSocketManager.shutdown();
        AgentsJsonReader.invalidateCache();
    }
}