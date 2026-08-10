package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.network.MorphSyncPacket;

/**
 * DWClientBot network handler.
 *
 * Chat bubble system removed — proximity chat handles all agent speech.
 *
 * FIX: this used to create its own "divineworld:main" SimpleChannel and
 * register a parallel ClientMorphSyncPacket class on it — identical
 * ResourceLocation to DivineWorld's own NetworkHandler, which crashed the
 * game with "NetworkDirection Channel (divineworld:main) already
 * registered" the moment both mods were loaded in the same JVM (Forge's
 * NetworkRegistry only allows one newSimpleChannel() call per channel name,
 * globally per JVM — there's no way for two independently-registered
 * channels of the same name to coexist).
 *
 * DWClientBot now has a real compile-time dependency on DivineWorld
 * (compileOnly against DivineWorld's built jar in build.gradle, declared as
 * a mandatory dependency in mods.toml) — since both mods are always
 * installed together on the client side, there's no reason to duplicate the
 * channel at all. DivineWorld owns the one and only "divineworld:main"
 * channel; this class just plugs into its MorphSyncPacket.CLIENT_HANDLER
 * extension point instead. DivineWorld itself has zero knowledge of this
 * class or DWClientBot in general — the dependency is one-directional, so
 * DivineWorld keeps running standalone on a dedicated server with no
 * problem, exactly as before.
 */
public class ClientNetworkHandler {

    private static boolean registered = false;

    public static void register() {
        if (registered) {
            DWClientMod.LOGGER.warn("[ClientNetworkHandler] Already registered — skipping duplicate call.");
            return;
        }
        registered = true;

        MorphSyncPacket.CLIENT_HANDLER = pkt -> {
            MorphStateCache.push(pkt.getPlayerUUID(), pkt.getMobType(), pkt.getGodType());
            DWClientMod.LOGGER.debug("[MorphSync] {} → {}",
                    pkt.getPlayerUUID(), pkt.getMobType().isEmpty() ? "REVERTED" : pkt.getMobType());
        };

        DWClientMod.LOGGER.info("[ClientNetworkHandler] Hooked into DivineWorld's MorphSyncPacket.CLIENT_HANDLER");
    }
}