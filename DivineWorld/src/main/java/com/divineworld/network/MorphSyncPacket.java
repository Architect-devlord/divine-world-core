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
 * FIX: this used to be one half of a parallel-class design — DivineWorld
 * defined this class and registered it on "divineworld:main" with a no-op
 * handle(), while DWClientBot separately defined an identical
 * ClientMorphSyncPacket and registered *its own* channel of the same name to
 * do the real client-side work. That only worked when exactly one of the two
 * mods was loaded in a given JVM — Forge's NetworkRegistry rejects a second
 * newSimpleChannel() call for a name that's already taken, so having both
 * mods loaded together (as DWClientBot now requires, as of the mods.toml
 * dependency below) crashed at startup.
 *
 * Now that DWClientBot has a real compile-time dependency on DivineWorld
 * (compileOnly against DivineWorld's built jar — see DWClientBot's
 * build.gradle and mods.toml), there's exactly one channel and one packet
 * class, owned here. CLIENT_HANDLER is the extension point: DivineWorld
 * itself only knows how to leave it null (a plain server has no reason to
 * ever set it, and runs standalone with no problem — that requirement is
 * unchanged). DWClientBot's ClientNetworkHandler sets it during client
 * setup to actually update the puppet-disguise renderer's state. This is a
 * one-directional dependency by design: DivineWorld has zero knowledge of
 * DWClientBot or this callback's contents, it just exposes the hook.
 */
public class MorphSyncPacket {

    /**
     * Set by DWClientBot's ClientNetworkHandler during client setup, if and
     * only if DWClientBot is present. Left null on a dedicated server (or a
     * client running DivineWorld without DWClientBot) — handle() below
     * checks for that and no-ops safely either way.
     */
    public static java.util.function.Consumer<MorphSyncPacket> CLIENT_HANDLER = null;

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

    // ── Handler ────────────────────────────────────────────────────────────

    /**
     * This packet is only ever sent server → client. On a pure dedicated
     * server it should never arrive at all (nothing sends it to itself), so
     * the warning path below is defensive, not expected. On a client, this
     * runs CLIENT_HANDLER if DWClientBot registered one; otherwise it's a
     * silent no-op — a client with only DivineWorld installed (no
     * DWClientBot) simply doesn't have puppet-disguise rendering to update.
     */
    public void handle(Supplier<NetworkEvent.Context> ctx) {
        NetworkEvent.Context context = ctx.get();
        context.enqueueWork(() -> {
            if (CLIENT_HANDLER != null) {
                CLIENT_HANDLER.accept(this);
            } else if (context.getDirection().getReceptionSide() == net.minecraftforge.fml.LogicalSide.SERVER) {
                DWMod.LOGGER.warn("[MorphSyncPacket] Unexpected server-side receipt — discarded.");
            }
            // else: client with no CLIENT_HANDLER registered — nothing to do.
        });
        context.setPacketHandled(true);
    }

    // ── Accessors ──────────────────────────────────────────────────────────

    public UUID   getPlayerUUID() { return playerUUID; }
    public String getMobType()    { return mobType; }
    public String getGodType()    { return godType; }
}