package com.divineworld.client;

import com.divineworld.client.entity.GodEntityManager;
import com.divineworld.client.network.TCPServer;
import com.divineworld.client.network.WebSocketManager;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Client Event Handler
 *
 * Handles the client-side lifecycle events: first world join, respawn, logout.
 * On first join it starts the TCP server (primary action channel) and the
 * WebSocket connection (perception + fallback actions).
 *
 * Fix Bug G — NPE on respawn:
 *   onPlayerRespawn previously called initializeGodEntity() without checking
 *   mc.level.  During respawn Minecraft replaces the level reference; if the
 *   event fires before the new level is assigned, GodEntityManager constructors
 *   (AIEnderDragon, AIWither, …) receive null and crash with NullPointerException.
 *
 *   Fix: guard both player and level non-null before calling initializeGodEntity().
 *   This mirrors the existing guard in onClientTick (line: mc.player != null &&
 *   mc.level != null) and is the correct pattern for all client entity creation.
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ClientEventHandler {

    private static boolean initialized  = false;
    private static int     tickCounter  = 0;

    // -------------------------------------------------------------------------
    // Client tick — one-time init + periodic status logging
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();

        // Initialize once when both player and level are available
        if (!initialized && mc.player != null && mc.level != null) {
            onPlayerJoinedWorld(mc.player);
            initialized = true;
        }

        tickCounter++;

        if (tickCounter % 20 == 0) {
            performPeriodicUpdates();
        }
    }

    private static void onPlayerJoinedWorld(LocalPlayer player) {
        DWClientMod.LOGGER.info("[ClientEventHandler] Player joined world: {}",
                player.getName().getString());

        // Start TCP server (primary low-latency action channel)
        TCPServer.start(8765);

        // Initialize WebSocket (perception loop + fallback action channel)
        try {
            WebSocketManager.initialize(
                    DWClientMod.getBackendUrl(),
                    DWClientMod.getBackendPort(),
                    DWClientMod.getAgentId());
        } catch (Exception e) {
            DWClientMod.LOGGER.error("[ClientEventHandler] Failed to initialize WebSocket", e);
        }

        // Spawn client-side god entity if this is a god agent
        if (DWClientMod.isGodAgent()) {
            initializeGodEntity(player);
        }
    }

    private static void initializeGodEntity(LocalPlayer player) {
        String godType = DWClientMod.getGodType();
        DWClientMod.LOGGER.info("[ClientEventHandler] Initializing god entity: {}", godType);
        try {
            GodEntityManager.initializeGodEntity(godType);
        } catch (Exception e) {
            DWClientMod.LOGGER.error("[ClientEventHandler] Failed to initialize god entity", e);
        }
    }

    // -------------------------------------------------------------------------
    // Periodic status logging
    // -------------------------------------------------------------------------

    private static void performPeriodicUpdates() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return;

        if (tickCounter % 100 == 0) {
            logAgentStatus();
        }
    }

    private static void logAgentStatus() {
        Minecraft mc = Minecraft.getInstance();
        if (mc.player == null) return;

        LocalPlayer player = mc.player;
        DWClientMod.LOGGER.debug("[ClientEventHandler] Agent Status:");
        DWClientMod.LOGGER.debug("  Position: {}, {}, {}",
                player.getX(), player.getY(), player.getZ());
        DWClientMod.LOGGER.debug("  Health: {}/{}", player.getHealth(), player.getMaxHealth());
        DWClientMod.LOGGER.debug("  TCP:       {}",
                com.divineworld.client.network.TCPServer.isConnected() ? "Connected" : "Disconnected");
        DWClientMod.LOGGER.debug("  WebSocket: {}",
                WebSocketManager.isConnected() ? "Connected" : "Disconnected");
        if (DWClientMod.isGodAgent()) {
            DWClientMod.LOGGER.debug("  God Type: {}", DWClientMod.getGodType());
        }
    }

    // -------------------------------------------------------------------------
    // Respawn
    // -------------------------------------------------------------------------

    /**
     * Re-initialize the god entity after a respawn.
     *
     * FIX Bug G: During respawn the client level is temporarily null while
     * Minecraft swaps the level reference.  All god entity constructors
     * (AIEnderDragon, AIWither, etc.) call new Entity(level) — passing null
     * crashes with NPE inside Minecraft internals.
     *
     * Guard: only proceed when BOTH mc.player and mc.level are non-null.
     * This is the same guard used in onClientTick for the initial join.
     */
    @SubscribeEvent
    public static void onPlayerRespawn(PlayerEvent.PlayerRespawnEvent event) {
        if (!(event.getEntity() instanceof LocalPlayer)) return;

        DWClientMod.LOGGER.info("[ClientEventHandler] Player respawned");

        if (DWClientMod.isGodAgent()) {
            Minecraft mc = Minecraft.getInstance();
            // FIX Bug G: guard both player and level before god entity construction
            if (mc.player != null && mc.level != null) {
                initializeGodEntity((LocalPlayer) event.getEntity());
            } else {
                DWClientMod.LOGGER.warn(
                        "[ClientEventHandler] Respawn: mc.level is null — " +
                        "deferring god entity init to next tick");
                // Cleared initialized flag so onClientTick will retry on the
                // next tick when mc.level is non-null again.
                initialized = false;
            }
        }
    }

    // -------------------------------------------------------------------------
    // Logout
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        DWClientMod.LOGGER.info("[ClientEventHandler] Player logged out");
        initialized = false;
        WebSocketManager.shutdown();
    }
}