package com.dwclient;

import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;

import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.io.IOException;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.List;

/**
 * Manages auto-connection for AI clients (1.21.x compatible)
 */
@Mod.EventBusSubscriber(modid = "dwclientbot")
public class AutoConnectManager {

    private static final Path AGENTS_FOLDER = Paths.get("dw_agents");
    private static final int RETRY_INTERVAL = 100;
    
    private final List pendingAgents = new ArrayList<>();
    private final Minecraft mc;
    private int ticksSinceLastAttempt = 0;
    private boolean autoConnectEnabled = true;
    
    public AutoConnectManager() {
        this.mc = Minecraft.getInstance();
        MinecraftForge.EVENT_BUS.register(this);
        
        try {
            Files.createDirectories(AGENTS_FOLDER);
        } catch (IOException e) {
            System.err.println("Failed to create agents folder: " + e.getMessage());
        }
        
        startFolderWatcher();
    }
    
    private void startFolderWatcher() {
        Thread watcherThread = new Thread(() -> {
            try {
                WatchService watcher = FileSystems.getDefault().newWatchService();
                AGENTS_FOLDER.register(watcher,
                    StandardWatchEventKinds.ENTRY_CREATE,
                    StandardWatchEventKinds.ENTRY_DELETE);
                
                while (true) {
                    WatchKey key = watcher.take();
                    
                    for (WatchEvent event : key.pollEvents()) {
                        WatchEvent.Kind kind = event.kind();
                        Path filename = (Path) event.context();
                        
                        if (kind == StandardWatchEventKinds.ENTRY_CREATE) {
                            System.out.println("New agent detected: " + filename);
                            synchronized (pendingAgents) {
                                pendingAgents.add(filename.toString());
                            }
                        }
                    }
                    
                    if (!key.reset()) break;
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        });
        
        watcherThread.setDaemon(true);
        watcherThread.start();
    }
    
    @SubscribeEvent
    public void onClientTick(TickEvent.ClientTickEvent event) {
        if (!autoConnectEnabled || event.phase != TickEvent.Phase.END) {
            return;
        }
        
        ticksSinceLastAttempt++;
        if (ticksSinceLastAttempt < RETRY_INTERVAL) {
            return;
        }
        
        ticksSinceLastAttempt = 0;
        
        // Check if we're already connected (1.21.x API)
        ClientPacketListener connection = mc.getConnection();
        if (connection != null && connection.getConnection().isConnected()) {
            return;
        }
        
        synchronized (pendingAgents) {
            if (pendingAgents.isEmpty()) return;
            
            for (String agent : new ArrayList<>(pendingAgents)) {
                System.out.println("Attempting to connect agent: " + agent);
                
                try {
                    if (tryConnect()) {
                        System.out.println("Successfully connected agent: " + agent);
                        pendingAgents.remove(agent);
                    }
                } catch (Exception e) {
                    e.printStackTrace();
                }
            }
        }
    }
    
    private boolean tryConnect() {
        try {
            ServerAddress serverAddress = ServerAddress.parseString("127.0.0.1:25565");
            
            mc.execute(() -> {
                ConnectScreen.startConnecting(
                    mc.screen,
                    mc,
                    serverAddress,
                    null,
                    false,
                    null
                );
            });
            
            return true;
        } catch (Exception e) {
            e.printStackTrace();
            return false;
        }
    }
}