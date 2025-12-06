// com/divineworld/network/ChatSayPacketHandler.java
package com.divineworld.network;

import com.divineworld.entity.DWNPCManager;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraftforge.network.NetworkEvent;

import java.util.function.Supplier;

/**
 * Server-side handler for chat bubble packets from AI clients.
 * Receives ChatSayPacket from DWClientBot and displays overhead bubbles.
 */
public class ChatSayPacketHandler {

    public static void handle(ChatSayPacket packet, Supplier<NetworkEvent.Context> ctx) {
        ServerPlayer sender = ctx.get().getSender();

        if (sender == null) {
            ctx.get().setPacketHandled(true);
            return;
        }

        // Verify sender is AI-controlled
        if (!DWNPCManager.isAIPlayer(sender)) {
            // Not an AI player, ignore
            ctx.get().setPacketHandled(true);
            return;
        }

        // Verify agent ID matches
        String senderAgentId = DWNPCManager.getAgentId(sender);
        if (senderAgentId == null || !senderAgentId.equals(packet.agentId)) {
            // Agent ID mismatch, ignore
            ctx.get().setPacketHandled(true);
            return;
        }

        // Process on server thread
        ctx.get().enqueueWork(() -> {
            ServerLevel level = sender.serverLevel();

            // Send chat bubble to nearby players (NOT global chat)
            DWNPCManager.sendChatBubble(level, packet.agentId, packet.message);
        });

        ctx.get().setPacketHandled(true);
    }
}