package com.divineworld.client;

import com.divineworld.client.network.WebSocketManager;
import com.divineworld.client.entity.GodEntityManager;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Client Event Handler - FIXED VERSION
 */

@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ClientEventHandler {

    private static boolean initialized = false;
    private static int tickCounter = 0;

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();

        // FIXED: Initialize once player exists
        if (!initialized && mc.player != null && mc.level != null) {
            onPlayerJoinedWorld(mc.player);
            initialized = true;
        }

        tickCounter++;

        // Periodic updates
        if (tickCounter % 20 == 0) {
            performPeriodicUpdates();
        }
    }

    private static void onPlayerJoinedWorld(LocalPlayer player) {
        DWClientMod.LOGGER.info("Player joined world: {}", player.getName().getString());

        // FIXED: Initialize WebSocket after player spawns
        try {
            WebSocketManager.initialize(
                    DWClientMod.getBackendUrl(),
                    DWClientMod.getBackendPort(),
                    DWClientMod.getAgentId()
            );
        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to initialize WebSocket", e);
        }

        // Initialize god entity if needed
        if (DWClientMod.isGodAgent()) {
            initializeGodEntity(player);
        }
    }

    private static void initializeGodEntity(LocalPlayer player) {
        String godType = DWClientMod.getGodType();
        DWClientMod.LOGGER.info("Initializing god entity: {}", godType);

        try {
            GodEntityManager.initializeGodEntity(godType);
        } catch (Exception e) {
            DWClientMod.LOGGER.error("Failed to initialize god entity", e);
        }
    }

    private static void performPeriodicUpdates() {
        Minecraft mc = Minecraft.getInstance();

        if (mc.player == null) return;

        // Check WebSocket connection
        if (!WebSocketManager.isConnected()) {
            // Reconnection handled automatically
        }

        // Log status every 5 seconds
        if (tickCounter % 100 == 0) {
            logAgentStatus();
        }
    }

    private static void logAgentStatus() {
        Minecraft mc = Minecraft.getInstance();

        if (mc.player != null) {
            LocalPlayer player = mc.player;

            DWClientMod.LOGGER.debug("Agent Status:");
            DWClientMod.LOGGER.debug("  Position: {}, {}, {}",
                    player.getX(), player.getY(), player.getZ());
            DWClientMod.LOGGER.debug("  Health: {}/{}",
                    player.getHealth(), player.getMaxHealth());
            DWClientMod.LOGGER.debug("  WebSocket: {}",
                    WebSocketManager.isConnected() ? "Connected" : "Disconnected");

            if (DWClientMod.isGodAgent()) {
                DWClientMod.LOGGER.debug("  God Type: {}", DWClientMod.getGodType());
            }
        }
    }

    @SubscribeEvent
    public static void onPlayerRespawn(PlayerEvent.PlayerRespawnEvent event) {
        if (event.getEntity() instanceof LocalPlayer) {
            DWClientMod.LOGGER.info("Player respawned");

            if (DWClientMod.isGodAgent()) {
                LocalPlayer player = (LocalPlayer) event.getEntity();
                initializeGodEntity(player);
            }
        }
    }

    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        DWClientMod.LOGGER.info("Player logged out");
        initialized = false;
        WebSocketManager.shutdown();
    }
}