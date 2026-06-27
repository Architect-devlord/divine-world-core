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
import java.util.function.Predicate;

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

        // FIX (plan.md §8.3): the predicate previously only accepted an
        // EXACT protocol-version match on both sides (PROTOCOL_VERSION::
        // equals), with no allowance for a connection where the other side
        // has no channel at all. NetworkRegistry.ABSENT is the documented
        // sentinel value Forge passes into these predicates precisely for
        // that case (confirmed across multiple Forge 1.20.x Javadoc
        // versions) — accepting it here is what lets a vanilla client (or
        // any client without this mod) complete the login handshake instead
        // of being rejected outright. ChannelBuilder/.optional() migration
        // is NOT needed for this Forge version (that's a 1.20.4+ networking
        // rewrite) — NetworkRegistry.newSimpleChannel(...) below is already
        // the correct, current, non-deprecated API for 1.20.1; only the
        // predicate arguments needed to change.
        Predicate<String> versionCheck = v ->
            PROTOCOL_VERSION.equals(v) || NetworkRegistry.ABSENT.equals(v);

        INSTANCE = NetworkRegistry.newSimpleChannel(
                new ResourceLocation("divineworld", "main"),
                () -> PROTOCOL_VERSION,
                versionCheck,
                versionCheck
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
                // FIX (plan.md §8.3): don't assume INSTANCE.send() silently
                // no-ops for a player whose client has no channel registered
                // — nothing in Forge's documentation states that, so it
                // shouldn't be relied on as free. SimpleChannel exposes a
                // documented isRemotePresent(Connection) method for exactly
                // this check. In practice this channel's strict version
                // predicates (now accepting NetworkRegistry.ABSENT, fixed
                // above) mean any player who completes the login handshake
                // at all already has the channel, so this is a narrow edge
                // case — but a cheap, correct guard regardless of how narrow.
                if (INSTANCE.isRemotePresent(nearby.connection.getConnection())) {
                    INSTANCE.send(PacketDistributor.PLAYER.with(() -> nearby), pkt);
                }
            }
        }
    }
}