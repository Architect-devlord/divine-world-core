package com.divineworld.network;

import com.divineworld.client.network.ChatSayPacket;
import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.SimpleChannel;


public class ClientNetworkHandler {
    private static final String PROTOCOL_VERSION = "1";
    public static final SimpleChannel INSTANCE = NetworkRegistry.newSimpleChannel(
        new ResourceLocation("dwclientbot", "main"),
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
        ChatSayPacket.class,         // Client → Server
        ChatSayPacket::encode,
        ChatSayPacket::decode,
        ChatSayPacket::handle        // No-op on client
    );
        System.out.println("[DWClientBot] Network handler registered");
    }
}