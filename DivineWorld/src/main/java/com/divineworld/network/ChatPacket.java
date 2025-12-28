// src/main/java/com/divineworld/network/ChatPacket.java
package com.divineworld.network;

import com.divineworld.DWMod;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraftforge.network.NetworkEvent;

import java.util.UUID;
import java.util.function.Supplier;

/**
 * Network packet for syncing chat bubbles from server to client
 * Server sends this when AI agent "speaks"
 *
 * FIXED: No client-side execution - safe for dedicated servers
 */
public class ChatPacket {
    private final UUID entityId;
    private final String message;

    public ChatPacket(UUID entityId, String message) {
        this.entityId = entityId;
        this.message = message;
    }

    public ChatPacket(FriendlyByteBuf buf) {
        this.entityId = buf.readUUID();
        this.message = buf.readUtf(256);
    }

    public void encode(FriendlyByteBuf buf) {
        buf.writeUUID(entityId);
        buf.writeUtf(message, 256);
    }

    public void handle(Supplier<NetworkEvent.Context> ctx) {
        ctx.get().enqueueWork(() -> {
            // SERVER-SIDE FALLBACK: Store message for potential client mod support
            // This runs on the SERVER thread (not client)
            ServerChatHandler.showMessage(entityId, message);

            DWMod.LOGGER.debug("Chat packet handled for entity: {}", entityId);
        });
        ctx.get().setPacketHandled(true);
    }
}