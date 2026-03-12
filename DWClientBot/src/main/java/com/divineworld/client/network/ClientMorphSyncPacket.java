package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraftforge.network.NetworkEvent;

import java.util.UUID;
import java.util.function.Supplier;

/**
 * ClientMorphSyncPacket — DWClientBot side handler for morph sync
 * ================================================================
 * Registered by DWClientBot's NetworkHandler as packet ID 1 on the
 * "divineworld:main" channel — same ID and wire format as the server
 * mod's MorphSyncPacket, so the bytes decode correctly.
 *
 * On receipt, pushes the event into MorphStateCache.
 * TransformationHandler drains the cache each ClientTickEvent.
 *
 * Zero imports from the server mod — fully independent.
 *
 * Wire format (must match server-mod MorphSyncPacket exactly):
 *   UUID   playerUUID
 *   String mobType  (max 64 chars)  — "" means revert
 *   String godType  (max 32 chars)
 */
public class ClientMorphSyncPacket {

    private final UUID   playerUUID;
    private final String mobType;
    private final String godType;

    // ── Deserialisation constructor — called by Forge on packet receipt ────

    public ClientMorphSyncPacket(FriendlyByteBuf buf) {
        this.playerUUID = buf.readUUID();
        this.mobType    = buf.readUtf(64);
        this.godType    = buf.readUtf(32);
    }

    /** Encode is required by Forge even for receive-only packets. */
    public void encode(FriendlyByteBuf buf) {
        buf.writeUUID(playerUUID);
        buf.writeUtf(mobType.length() > 64 ? mobType.substring(0, 64) : mobType, 64);
        buf.writeUtf(godType.length() > 32 ? godType.substring(0, 32) : godType, 32);
    }

    // ── Handler ────────────────────────────────────────────────────────────

    public void handle(Supplier<NetworkEvent.Context> ctx) {
        ctx.get().enqueueWork(() -> {
            MorphStateCache.push(playerUUID, mobType, godType);
            DWClientMod.LOGGER.debug("[MorphSync] {} → {}",
                    playerUUID, mobType.isEmpty() ? "REVERTED" : mobType);
        });
        ctx.get().setPacketHandled(true);
    }
}