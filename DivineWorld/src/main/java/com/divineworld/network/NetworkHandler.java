// com/divineworld/network/NetworkHandler.java
package com.divineworld.network;

import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.simple.SimpleChannel;

public class NetworkHandler {
    private static final String PROTOCOL_VERSION = "1";
    public static final SimpleChannel INSTANCE = NetworkRegistry.newSimpleChannel(
        new ResourceLocation("divineworld", "main"),
        () -> PROTOCOL_VERSION,
        PROTOCOL_VERSION::equals,
        PROTOCOL_VERSION::equals
    );
    
    private static int packetId = 0;
    
    private static int id() {
        return packetId++;
    }
    
public static void register() {
    INSTANCE.registerMessage(
        id(),
        ChatPacket.class,           // Server → Client
        ChatPacket::encode,          // Serialize
        ChatPacket::new,             // Deserialize
        ChatPacket::handle           // Handle on client
    );
    
    INSTANCE.registerMessage(
        id(),
        ChatSayPacket.class,         // Client → Server
        ChatSayPacket::encode,
        ChatSayPacket::decode,
        ChatSayPacketHandler::handle // Handle on server
    );
  }
}


