package com.divineworld.client.network;

import java.util.Queue;
import java.util.UUID;
import java.util.concurrent.ConcurrentLinkedQueue;

/**
 * MorphStateCache — DWClientBot (com.divineworld.client.network)
 * ==============================================================
 * Holds pending morph events delivered by the client-side MorphSyncPacket
 * handler.  TransformationHandler drains this queue each ClientTickEvent.
 *
 * Lives entirely in DWClientBot — zero imports from the server mod.
 * The server mod has no reference to this class.
 */
public class MorphStateCache {

    public record MorphEvent(UUID playerUUID, String mobType, String godType) {}

    // Thread-safe: packet handler writes on Netty thread, TransformationHandler
    // reads on the Minecraft client thread.
    private static final Queue<MorphEvent> PENDING = new ConcurrentLinkedQueue<>();

    public static void push(UUID playerUUID, String mobType, String godType) {
        PENDING.add(new MorphEvent(playerUUID, mobType, godType));
    }

    public static MorphEvent poll() {
        return PENDING.poll();
    }

    public static void clear() {
        PENDING.clear();
    }
}