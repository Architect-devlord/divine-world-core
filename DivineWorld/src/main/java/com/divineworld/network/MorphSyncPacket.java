// src/main/java/com/divineworld/network/MorphSyncPacket.java
// DivineWorld server mod
package com.divineworld.network;

import com.divineworld.DWMod;
import net.minecraft.network.FriendlyByteBuf;
import net.minecraftforge.network.NetworkEvent;

import java.util.UUID;
import java.util.function.Supplier;

/**
 * MorphSyncPacket — Server → Client  (DivineWorld server mod)
 * ============================================================
 * Broadcast by NetworkHandler.broadcastMorph() when a god/player transforms.
 *
 * This class lives in the server mod and is ONLY responsible for:
 *   1. Encoding the packet to send (encode / constructor-from-fields)
 *   2. Decoding incoming bytes (constructor-from-buf) — needed by Forge registry
 *   3. handle() — this packet is server→client only; if somehow received
 *      server-side it is a no-op.
 *
 * The client-side handling is done entirely by DWClientBot's own
 * com.divineworld.client.network.MorphSyncPacket which is registered
 * on the same channel/ID by DWClientBot's NetworkHandler.
 * The two mods are fully independent — no cross-mod imports.
 *
 * Wire format (must match DWClientBot's MorphSyncPacket exactly):
 *   UUID   playerUUID
 *   String mobType  (max 64 chars)  — "" means revert
 *   String godType  (max 32 chars)
 */
public class MorphSyncPacket {

    private final UUID   playerUUID;
    private final String mobType;
    private final String godType;

    public MorphSyncPacket(UUID playerUUID, String mobType, String godType) {
        this.playerUUID = playerUUID;
        this.mobType    = mobType;
        this.godType    = godType;
    }

    // ── Serialisation ──────────────────────────────────────────────────────

    /** Deserialisation constructor — used by Forge when registering the message. */
    public MorphSyncPacket(FriendlyByteBuf buf) {
        this.playerUUID = buf.readUUID();
        this.mobType    = buf.readUtf(64);
        this.godType    = buf.readUtf(32);
    }

    public void encode(FriendlyByteBuf buf) {
        buf.writeUUID(playerUUID);
        buf.writeUtf(mobType.length() > 64 ? mobType.substring(0, 64) : mobType, 64);
        buf.writeUtf(godType.length() > 32 ? godType.substring(0, 32) : godType, 32);
    }

    // ── Handler — no-op on server side ─────────────────────────────────────

    /**
     * This is a server→client packet. It should never arrive at the server.
     * If it somehow does, discard it safely.
     * Client-side handling is done by DWClientBot's own MorphSyncPacket.
     */
    public void handle(Supplier<NetworkEvent.Context> ctx) {
        ctx.get().setPacketHandled(true);
        DWMod.LOGGER.warn("[MorphSyncPacket] Unexpected server-side receipt — discarded.");
    }

    // ── Accessors ──────────────────────────────────────────────────────────

    public UUID   getPlayerUUID() { return playerUUID; }
    public String getMobType()    { return mobType; }
    public String getGodType()    { return godType; }
}
