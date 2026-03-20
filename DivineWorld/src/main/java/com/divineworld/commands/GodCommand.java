package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.events.GodDisguiseHandler;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

/**
 * God Commands — toggle disguise form for god entities.
 *
 * FIX S-02: The original code only called PythonBackendClient.godTransform()
 * and flipped the dw_disguised NBT flag, but never called
 * GodDisguiseHandler.applyTransform() / removeTransform().  The actual body
 * swap (replaceGodBody) and MorphSyncPacket broadcast never happened —
 * visually nothing changed for other players.
 *
 * Now both sub-commands delegate entirely to GodDisguiseHandler, which owns
 * the full transform pipeline (body swap, NBT update, particle burst, packet).
 */
public class GodCommand {

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        // /godtoggle
        dispatcher.register(Commands.literal("godtoggle")
                .requires(source -> source.hasPermission(2))
                .executes(GodCommand::toggleSelfDisguise)
        );

        // /godtoggle <agent_id>
        dispatcher.register(Commands.literal("godtoggle")
                .requires(source -> source.hasPermission(2))
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .executes(GodCommand::toggleTargetDisguise)
                )
        );

        DWMod.LOGGER.info("[GodCommand] Registered /godtoggle command");
    }

    private static int toggleSelfDisguise(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();

            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only gods may use this command!"));
                return 0;
            }

            ServerLevel level = ctx.getSource().getLevel();
            boolean currentlyDisguised = GodDisguiseHandler.isTransformed(player);

            if (currentlyDisguised) {
                // Revert to original god form
                GodDisguiseHandler.removeTransform(player);
            } else {
                // Transform into player-like disguise (villager)
                GodDisguiseHandler.applyTransform(player, "villager", level);
            }

            DWMod.LOGGER.info("God {} toggled disguise: {} → {}",
                    DWNPCManager.getAgentId(player), currentlyDisguised, !currentlyDisguised);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God toggle command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] Command failed: " + e.getMessage()));
            return 0;
        }
    }

    private static int toggleTargetDisguise(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor     = ctx.getSource().getPlayerOrException();
            String       targetAgentId = StringArgumentType.getString(ctx, "agent_id");

            ServerPlayer targetGod = DWNPCManager.findPlayerByAgentId(
                    ctx.getSource().getLevel(), targetAgentId);

            if (targetGod == null) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Agent not found: " + targetAgentId));
                return 0;
            }

            if (!DWNPCManager.isGodPlayer(targetGod)) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] " + targetAgentId + " is not a god"));
                return 0;
            }

            ServerLevel level = targetGod.serverLevel();
            boolean currentlyDisguised = GodDisguiseHandler.isTransformed(targetGod);

            if (currentlyDisguised) {
                GodDisguiseHandler.removeTransform(targetGod);
            } else {
                GodDisguiseHandler.applyTransform(targetGod, "villager", level);
            }

            executor.sendSystemMessage(Component.literal(
                    currentlyDisguised
                            ? "§a[God Toggle] " + targetAgentId + " returned to divine form"
                            : "§a[God Toggle] " + targetAgentId + " assumed mortal disguise"));

            DWMod.LOGGER.info("God {} disguise toggled by {}", targetAgentId,
                    executor.getName().getString());
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God toggle target command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] Command failed: " + e.getMessage()));
            return 0;
        }
    }
}