package com.divineworld.client.network;

import net.minecraft.resources.ResourceLocation;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.simple.SimpleChannel;

/**
 * DWClientBot network handler.
 *
 * Chat bubble system removed — proximity chat handles all agent speech.
 *
 * Packet table:
 *   ID 0 — ClientMorphSyncPacket  (server → client)
 *
 * Protocol version "2" must match the server mod's MorphSyncPacket encoding.
 */
public class ClientNetworkHandler {

    private static final String PROTOCOL_VERSION = "2";

    public static final SimpleChannel INSTANCE = NetworkRegistry.newSimpleChannel(
            new ResourceLocation("divineworld", "main"),
            () -> PROTOCOL_VERSION,
            PROTOCOL_VERSION::equals,
            PROTOCOL_VERSION::equals
    );

    private static int packetId = 0;
    private static int id() { return packetId++; }

    public static void register() {
        // ID 0 — Morph sync (server → client)
        INSTANCE.registerMessage(
                id(),
                ClientMorphSyncPacket.class,
                ClientMorphSyncPacket::encode,
                ClientMorphSyncPacket::new,
                ClientMorphSyncPacket::handle
        );
    }
}