package com.divineworld.commands;

import com.divineworld.utils.GenesisManager;
import com.mojang.brigadier.Command;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;

public class DivineCommand {

    public static void register(net.minecraftforge.event.RegisterCommandsEvent event) {
        event.getDispatcher().register(
                Commands.literal("divine")
                        .requires(src -> src.hasPermission(2))
                        .then(Commands.literal("genesis")
                                .executes(ctx -> executeGenesis(ctx)))
                        .then(Commands.literal("reset")
                                .executes(ctx -> executeReset(ctx)))
        );
    }

    private static int executeGenesis(CommandContext<CommandSourceStack> ctx) {
        var player = ctx.getSource().getPlayer();
        if (player != null) {
            GenesisManager.onGenesisUse(player, player.level(), InteractionHand.MAIN_HAND);
        }
        return Command.SINGLE_SUCCESS;
    }

    private static int executeReset(CommandContext<CommandSourceStack> ctx) {
        var player = ctx.getSource().getPlayer();
        if (player != null && !player.level().isClientSide()) {
            GenesisManager.onGenesisUse(player, player.level(), InteractionHand.MAIN_HAND);
        }
        return Command.SINGLE_SUCCESS;
    }
}
