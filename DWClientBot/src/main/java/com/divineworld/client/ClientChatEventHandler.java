package com.divineworld.client;

import com.divineworld.client.network.WebSocketManager;
import net.minecraft.client.Minecraft;
import net.minecraft.network.chat.Component;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.client.event.ClientChatReceivedEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Client Chat Event Handler — DWClientBot
 * ========================================
 * Intercepts every chat message that arrives at this client and forwards
 * it to the Python agent via WebSocket so the cognitive loop can hear it.
 *
 * Flow:
 *   Server ProximityChatHandler  (DivineWorld mod)
 *     → sendSystemMessage() to nearby players
 *       → ClientChatReceivedEvent fires on DWClientBot
 *         → WebSocketManager.sendChatObservation()
 *           → Python /ws/agent receives JSON text frame
 *
 * Zero imports from the server mod — fully self-contained in DWClientBot.
 *
 * Register in DWClientMod constructor:
 *   MinecraftForge.EVENT_BUS.register(ClientChatEventHandler.class);
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public class ClientChatEventHandler {

    @SubscribeEvent
    public static void onChatReceived(ClientChatReceivedEvent event) {
        if (!WebSocketManager.isConnected()) return;

        String rawText = event.getMessage().getString();

        // Only forward proximity chat (format "<SpeakerName> message")
        // Ignore system/server messages that don't match that pattern
        if (!rawText.startsWith("<")) return;

        // Parse speaker and body out of "<Speaker> message"
        int closeAngle = rawText.indexOf('>');
        if (closeAngle < 2) return; // malformed

        String speaker = rawText.substring(1, closeAngle);
        String body    = rawText.substring(closeAngle + 2); // skip "> "

        // Don't forward messages the agent itself sent (echo suppression)
        String selfName = Minecraft.getInstance().player != null
                ? Minecraft.getInstance().player.getName().getString()
                : "";
        if (speaker.equals(selfName)) return;

        WebSocketManager.sendChatObservation(speaker, body);
    }
}