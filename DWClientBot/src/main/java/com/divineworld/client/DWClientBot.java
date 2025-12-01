// com/divineworld/client/DWClientBot.java - FIXED
package com.divineworld.client;

import com.divineworld.client.network.ClientNetworkHandler;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.resolver.ServerAddress;
import net.minecraft.client.gui.screens.ConnectScreen;
import com.mojang.authlib.GameProfile;

import java.util.UUID;

@Mod(DWClientBot.MODID)
@Mod.EventBusSubscriber(modid = DWClientBot.MODID, bus = Mod.EventBusSubscriber.Bus.MOD)
public class DWClientBot {
    public static final String MODID = "dwclientbot";
    public static String AGENT_ID = null;
    public static String AGENT_TYPE = null;
    public static String SERVER = null;
    public static String BACKEND = null;

    public DWClientBot(FMLJavaModLoadingContext context) {
        AGENT_ID = System.getProperty("dw.agentId");
        AGENT_TYPE = System.getProperty("dw.agentType", "npc");
        SERVER = System.getProperty("dw.server");
        BACKEND = System.getProperty("dw.backend", "http://127.0.0.1:11400");

        // Set username based on agent type
        setMinecraftUsername();

        // Register client network handler FIRST
        ClientNetworkHandler.register();

        // Register other event listeners
        MinecraftForge.EVENT_BUS.register(new AudioCapture());
        MinecraftForge.EVENT_BUS.register(new FrameCaptureHandler());
        MinecraftForge.EVENT_BUS.register(ChatBubbleManager.class);
    }

    /**
     * Set Minecraft username based on agent type.
     * Format:
     * - NPCs: "AI_<agentId>"
     * - Gods: "GOD_<type>_<agentId>"
     */
    private void setMinecraftUsername() {
        if (AGENT_ID == null) {
            System.err.println("[DWClientBot] ERROR: No agent ID provided!");
            return;
        }

        String username;

        if (AGENT_TYPE.startsWith("god_")) {
            // God entity: GOD_wither_agent123
            String godType = AGENT_TYPE.substring(4); // Remove "god_" prefix
            username = "GOD_" + godType + "_" + AGENT_ID;
        } else {
            // Regular NPC: AI_agent123
            username = "AI_" + AGENT_ID;
        }

        // Ensure username length <= 16 characters (Minecraft limit)
        if (username.length() > 16) {
            // Truncate agent ID to fit
            int maxIdLength = 16 - (username.length() - AGENT_ID.length());
            String truncatedId = AGENT_ID.substring(0, Math.max(1, maxIdLength));

            if (AGENT_TYPE.startsWith("god_")) {
                String godType = AGENT_TYPE.substring(4);
                username = "GOD_" + godType + "_" + truncatedId;
            } else {
                username = "AI_" + truncatedId;
            }
        }

        System.out.println("[DWClientBot] Setting username: " + username);

        // Set the username via reflection (Minecraft's Session)
        try {
            Minecraft mc = Minecraft.getInstance();

            // Get current session
            var sessionField = Minecraft.class.getDeclaredField("user");
            sessionField.setAccessible(true);
            var currentSession = sessionField.get(mc);

            // Create new session with AI username
            var sessionClass = currentSession.getClass();
            var usernameField = sessionClass.getDeclaredField("name");
            usernameField.setAccessible(true);
            usernameField.set(currentSession, username);

            System.out.println("[DWClientBot] Username set successfully: " + username);

        } catch (Exception e) {
            System.err.println("[DWClientBot] Failed to set username: " + e.getMessage());
            e.printStackTrace();
        }
    }

    @SubscribeEvent
    public static void onClientSetup(FMLClientSetupEvent evt) {
        System.out.println("[DWClientBot] Client setup - agent=" + AGENT_ID +
                " type=" + AGENT_TYPE + " server=" + SERVER + " backend=" + BACKEND);

        if (AGENT_ID != null && BACKEND != null) {
            WSActionClient.start(AGENT_ID, BACKEND.replaceFirst("^http", "ws") + "/ws");
        }

        if (SERVER != null && !SERVER.isEmpty()) {
            Minecraft.getInstance().execute(DWClientBot::connectToServer);
        }
    }

    private static void connectToServer() {
        try {
            ServerAddress address = ServerAddress.parseString(SERVER);

            ConnectScreen.startConnecting(
                    Minecraft.getInstance().screen,
                    Minecraft.getInstance(),
                    address,
                    null,
                    false,
                    null
            );
        } catch (Exception ex) {
            ex.printStackTrace();
        }
    }
}