// src/main/java/com/divineworld/commands/GodCommand.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;

/**
 * God Commands - Toggle disguise form for god entities
 * Fixed for Forge 1.20.1 with Parchment mappings
 */
public class GodCommand {

    /**
     * Register the /godtoggle command
     */
    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        // /godtoggle - Toggle disguise for the executing god player
        dispatcher.register(Commands.literal("godtoggle")
                .requires(source -> source.hasPermission(2))
                .executes(GodCommand::toggleSelfDisguise)
        );

        // /godtoggle <agent_id> - Toggle disguise for a specific god agent
        dispatcher.register(Commands.literal("godtoggle")
                .requires(source -> source.hasPermission(2))
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .executes(GodCommand::toggleTargetDisguise)
                )
        );

        DWMod.LOGGER.info("[GodCommand] Registered /godtoggle command");
    }

    /**
     * Toggle disguise for the command executor
     */
    private static int toggleSelfDisguise(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();

            // Check if player is a god
            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only gods may use this command!"
                ));
                return 0;
            }

            String agentId = DWNPCManager.getAgentId(player);
            if (agentId == null) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Failed to retrieve your agent ID"
                ));
                return 0;
            }

            // Get current disguise state from NBT
            boolean currentlyDisguised = player.getPersistentData().getBoolean("dw_disguised");

            // Toggle disguise via Python backend
            PythonBackendClient.godTransform(
                    agentId,
                    currentlyDisguised ? "god_form" : "villager" // Toggle between forms
            );

            // Update NBT state
            player.getPersistentData().putBoolean("dw_disguised", !currentlyDisguised);

            String message = currentlyDisguised
                    ? "§a[God Toggle] You have returned to your divine form"
                    : "§a[God Toggle] You have assumed mortal disguise";

            player.sendSystemMessage(Component.literal(message));

            DWMod.LOGGER.info("God {} toggled disguise: {} -> {}",
                    agentId, currentlyDisguised, !currentlyDisguised);

            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God toggle command failed", e);
            ctx.getSource().sendFailure(Component.literal(
                    "§c[God Toggle] Command failed: " + e.getMessage()
            ));
            return 0;
        }
    }

    /**
     * Toggle disguise for a target god agent
     */
    private static int toggleTargetDisguise(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor = ctx.getSource().getPlayerOrException();
            String targetAgentId = StringArgumentType.getString(ctx, "agent_id");

            // Find the target god player
            ServerPlayer targetGod = DWNPCManager.findPlayerByAgentId(
                    ctx.getSource().getLevel(),
                    targetAgentId
            );

            if (targetGod == null) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Agent not found: " + targetAgentId
                ));
                return 0;
            }

            if (!DWNPCManager.isGodPlayer(targetGod)) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] " + targetAgentId + " is not a god"
                ));
                return 0;
            }

            // Get current disguise state
            boolean currentlyDisguised = targetGod.getPersistentData().getBoolean("dw_disguised");

            // Toggle disguise via Python backend
            PythonBackendClient.godTransform(
                    targetAgentId,
                    currentlyDisguised ? "god_form" : "villager"
            );

            // Update NBT state
            targetGod.getPersistentData().putBoolean("dw_disguised", !currentlyDisguised);

            String message = currentlyDisguised
                    ? "§a[God Toggle] " + targetAgentId + " returned to divine form"
                    : "§a[God Toggle] " + targetAgentId + " assumed mortal disguise";

            executor.sendSystemMessage(Component.literal(message));

            // Notify the target god
            targetGod.sendSystemMessage(Component.literal(
                    currentlyDisguised
                            ? "§d[Divine] You return to your true form"
                            : "§7[Divine] You assume mortal guise"
            ));

            DWMod.LOGGER.info("God {} disguise toggled by {}",
                    targetAgentId, executor.getName().getString());

            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God toggle target command failed", e);
            ctx.getSource().sendFailure(Component.literal(
                    "§c[God Toggle] Command failed: " + e.getMessage()
            ));
            return 0;
        }
    }
}