package com.divineworld.client.network;

import net.minecraft.network.FriendlyByteBuf;
import net.minecraftforge.network.NetworkEvent;

import java.util.function.Supplier;

/**
 * Client-side packet for sending chat messages from AI to server
 */
public class ChatSayPacket {
    public final String agentId;
    public final String message;

    public ChatSayPacket(String agentId, String message) {
        this.agentId = agentId;
        this.message = message;
    }

    public static void encode(ChatSayPacket pkt, FriendlyByteBuf buf) {
        buf.writeUtf(pkt.agentId, 256);
        buf.writeUtf(pkt.message, 512);
    }

    public static ChatSayPacket decode(FriendlyByteBuf buf) {
        String id = buf.readUtf(256);
        String msg = buf.readUtf(512);
        return new ChatSayPacket(id, msg);
    }

    public static void handle(ChatSayPacket pkt, Supplier ctx) {
        ctx.get().enqueueWork(() -> {
            // Client->Server: Server will handle this in its own handler
            // Nothing to do here on client side
        });
        ctx.get().setPacketHandled(true);
    }
}