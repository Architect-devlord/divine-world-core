// src/main/java/com/divineworld/network/NetworkHandler.java
// DivineWorld server mod
package com.divineworld.network;

import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.network.NetworkRegistry;
import net.minecraftforge.network.PacketDistributor;
import net.minecraftforge.network.simple.SimpleChannel;

import java.util.UUID;

import com.divineworld.DWMod;

/**
 * DivineWorld server-mod network handler.
 *
 * Chat bubble system removed — proximity chat handles all agent speech.
 *
 * Packet table (must match DWClientBot ClientNetworkHandler IDs exactly):
 *   ID 0 — MorphSyncPacket  (server → client)
 */
public class NetworkHandler {

    private static final String PROTOCOL_VERSION = "2";
    private static SimpleChannel INSTANCE;
    private static boolean registered = false;

    public static void register() {
        if (registered){
            DWMod.LOGGER.warn("[NetworkHandler] Already registered — skipping duplicate call.");
            return;  // Prevent double registration (causes crashes)
        }
        registered = true;

        INSTANCE = NetworkRegistry.newSimpleChannel(
                new ResourceLocation("divineworld", "main"),
                () -> PROTOCOL_VERSION,
                PROTOCOL_VERSION::equals,
                PROTOCOL_VERSION::equals
        );

        // ID 0 — Morph sync (server → client)
        INSTANCE.registerMessage(
                id(),
                MorphSyncPacket.class,
                MorphSyncPacket::encode,
                MorphSyncPacket::new,
                MorphSyncPacket::handle
        );
    }

    private static int packetId = 0;
    private static int id() { return packetId++; }

    /**
     * Broadcast a MorphSyncPacket to all players within 64 blocks.
     * Called by GodDisguiseHandler after a successful /god_transform.
     */
    public static void broadcastMorph(ServerPlayer transformedPlayer,
                                      ServerLevel level,
                                      String newMobType) {
        UUID   uuid    = transformedPlayer.getUUID();
        String godType = transformedPlayer.getPersistentData().getString("dw_god_type");
        MorphSyncPacket pkt = new MorphSyncPacket(uuid, newMobType, godType);

        for (ServerPlayer nearby : level.players()) {
            if (nearby.distanceToSqr(transformedPlayer) < 64 * 64) {
                INSTANCE.send(PacketDistributor.PLAYER.with(() -> nearby), pkt);
            }
        }
    }
}
