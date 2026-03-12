package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.integration.PythonBackendClient;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.event.ServerChatEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Proximity Chat Handler — Server-side (DivineWorld mod)
 * ======================================================
 * Replaces Minecraft's global broadcast with proximity-based delivery:
 *
 *   • All chat is intercepted before the default broadcast fires.
 *   • The message is delivered only to players/agents within
 *     {@value #PROXIMITY_RADIUS} blocks in the same dimension.
 *   • For every NPC/GOD agent recipient, the Python backend is notified
 *     via PythonBackendClient.notifyChatHeard() so the agent's
 *     cognitive loop can process what it "overheard".
 *
 * Lives in the server mod (com.divineworld.events) because it uses
 * ServerChatEvent and ServerPlayer — pure server-side APIs.
 * No client-mod imports anywhere.
 *
 * Register in DWMod constructor:
 *   forgeBus.register(ProximityChatHandler.class);
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ProximityChatHandler {

    /** Players must be within this many blocks (3D Euclidean) to receive a message. */
    public static final double PROXIMITY_RADIUS = 10.0;

    /**
     * Intercept every outgoing server chat message.
     * Cancelling ServerChatEvent suppresses the vanilla broadcast;
     * we do our own targeted delivery and backend notification.
     */
    @SubscribeEvent
    public static void onServerChat(ServerChatEvent event) {
        event.setCanceled(true);

        ServerPlayer sender  = event.getPlayer();
        String       rawMsg  = event.getMessage().getString();
        Component    display = buildMessage(sender, rawMsg);

        // Always deliver to the sender so they see their own message
        sender.sendSystemMessage(display);

        // Deliver to every nearby player; notify backend for each agent recipient
        for (ServerPlayer recipient : sender.getServer().getPlayerList().getPlayers()) {
            if (recipient == sender) continue;
            if (!sameDimension(sender, recipient)) continue;
            if (distanceBetween(sender, recipient) > PROXIMITY_RADIUS) continue;

            recipient.sendSystemMessage(display);

            // HTTP-notify ONLY god agents (oracle brains etc.) that overheard this.
            // NPC agents (DWClientBot instances) receive the same message via their
            // own ClientChatReceivedEvent → WebSocket path, so notifying them here
            // too would cause the cognitive loop to process the same chat twice.
            TaggedEntitySystem.AgentType type = TaggedEntitySystem.detectAgentType(recipient);
            if (type == TaggedEntitySystem.AgentType.GOD) {
                PythonBackendClient.notifyChatHeard(
                        recipient.getName().getString(),
                        sender.getName().getString(),
                        rawMsg
                );
            }
        }

        DWMod.LOGGER.debug("[ProximityChat] {} said '{}' (radius={})",
                sender.getName().getString(), rawMsg, PROXIMITY_RADIUS);
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    /** Build the chat Component shown to recipients. Matches vanilla format. */
    private static Component buildMessage(ServerPlayer sender, String rawMessage) {
        return Component.literal("<" + sender.getName().getString() + "> " + rawMessage);
    }

    /** 3D Euclidean distance between two players. */
    private static double distanceBetween(Player a, Player b) {
        double dx = a.getX() - b.getX();
        double dy = a.getY() - b.getY();
        double dz = a.getZ() - b.getZ();
        return Math.sqrt(dx * dx + dy * dy + dz * dz);
    }

    /** Both players must be in the same server-level dimension. */
    private static boolean sameDimension(ServerPlayer a, ServerPlayer b) {
        return a.serverLevel().dimension().equals(b.serverLevel().dimension());
    }
}