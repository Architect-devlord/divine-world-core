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
 *     via PythonBackendClient.notifyChatHeard().
 *
 * FIX — Oracle chat interception:
 *   ProximityChatHandler used to call event.setCanceled(true) immediately,
 *   which prevented OracleSystem.onPlayerChat() from ever seeing the event
 *   (Forge skips cancelled-event listeners unless receiveCancelled=true).
 *
 *   Fix: OracleSystem registers a static hook via setChatHook(). This handler
 *   invokes the hook FIRST, before cancelling. If the hook signals it consumed
 *   the message (sender has an active oracle), the message is still cancelled
 *   for vanilla broadcast but the oracle received it.
 *
 * Lives in the server mod (com.divineworld.events) because it uses
 * ServerChatEvent and ServerPlayer — pure server-side APIs.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class ProximityChatHandler {

    /** Players must be within this many blocks (3D Euclidean) to receive a message. */
    public static final double PROXIMITY_RADIUS = 10.0;

    /**
     * Optional hook called before the proximity broadcast runs.
     * OracleSystem sets this so it can intercept messages directed at the Oracle
     * even after the event is cancelled.
     *
     * The hook receives (sender, rawMessage). It returns true if it consumed the
     * message (oracle handled it) — the proximity broadcast still runs normally
     * but the oracle's LLM response replaces/augments the chat output.
     */
    @FunctionalInterface
    public interface ChatHook {
        boolean onChat(ServerPlayer sender, String rawMessage);
    }

    private static ChatHook chatHook = null;

    /** Register a chat hook (called by OracleSystem on startup). */
    public static void setChatHook(ChatHook hook) {
        chatHook = hook;
    }

    /**
     * Intercept every outgoing server chat message.
     * Cancelling ServerChatEvent suppresses the vanilla broadcast;
     * we do our own targeted delivery and backend notification.
     */
    @SubscribeEvent
    public static void onServerChat(ServerChatEvent event) {
        ServerPlayer sender  = event.getPlayer();
        String       rawMsg  = event.getMessage().getString().trim();

        // ── Step 1: Oracle hook runs BEFORE cancel so it always sees the message ──
        boolean oracleConsumed = false;
        if (chatHook != null) {
            try {
                oracleConsumed = chatHook.onChat(sender, rawMsg);
            } catch (Exception e) {
                DWMod.LOGGER.warn("[ProximityChat] Oracle chat hook error: {}", e.getMessage());
            }
        }

        // ── Step 2: Cancel vanilla broadcast ──────────────────────────────────────
        event.setCanceled(true);

        // If oracle fully consumed this message (it was a tutorial/llm command),
        // suppress the proximity echo too — oracle sends its own response messages.
        if (oracleConsumed) {
            DWMod.LOGGER.debug("[ProximityChat] Oracle consumed message from {}",
                sender.getName().getString());
            return;
        }

        // ── Step 3: Proximity broadcast ───────────────────────────────────────────
        Component display = buildMessage(sender, rawMsg);
        sender.sendSystemMessage(display);

        for (ServerPlayer recipient : sender.getServer().getPlayerList().getPlayers()) {
            if (recipient == sender) continue;
            if (!sameDimension(sender, recipient)) continue;
            if (distanceBetween(sender, recipient) > PROXIMITY_RADIUS) continue;

            recipient.sendSystemMessage(display);

            // HTTP-notify god agents that overheard this.
            // NPC agents receive it via ClientChatReceivedEvent → WebSocket.
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