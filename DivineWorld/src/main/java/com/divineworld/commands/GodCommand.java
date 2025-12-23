/**package com.divineworld.commands;

import com.mojang.brigadier.Command;
import com.mojang.brigadier.CommandDispatcher;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.world.entity.Entity;

public class GodCommand {

    // Registers /godtoggle command
    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("godtoggle")
                .requires(source -> source.hasPermission(2))
                .executes(ctx -> {
                    CommandSourceStack source = ctx.getSource();
                    Entity entity = source.getEntity();

                    if (entity instanceof DWGodEntity godEntity) {
                        godEntity.toggleDisguiseForm();
                        String msg = godEntity.isInMortalDisguise()
                                ? "You have assumed mortal disguise."
                                : "You have returned to your divine form.";
                        source.sendSuccess(() -> net.minecraft.network.chat.Component.literal(msg), true);
                        return Command.SINGLE_SUCCESS;
                    } else {
                        source.sendFailure(net.minecraft.network.chat.Component.literal("This command only applies to Divine World gods."));
                        return 0;
                    }
                })
        );
    }
}
**/