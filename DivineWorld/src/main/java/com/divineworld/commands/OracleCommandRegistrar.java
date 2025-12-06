package com.divineworld.commands;

import com.divineworld.oracle.LLMOracleBrain;
import com.divineworld.oracle.OracleSystem;
import com.divineworld.DWMod;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.suggestion.SuggestionProvider;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.SharedSuggestionProvider;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;


import java.util.Arrays;
import java.util.List;

public class OracleCommandRegistrar {
    
    private final OracleSystem oracleSystem;
    private LLMOracleBrain oracleBrain;
    
    private static final List<String> AVAILABLE_MODELS = Arrays.asList("gemma3:1b", "deepseek-r1:8b");
    
    private static final SuggestionProvider<CommandSourceStack> MODEL_SUGGESTIONS = (ctx, builder) ->
        SharedSuggestionProvider.suggest(AVAILABLE_MODELS, builder);
    
    public OracleCommandRegistrar(OracleSystem oracleSystem, LLMOracleBrain oracleBrain) {
        this.oracleSystem = oracleSystem;
        this.oracleBrain = oracleBrain;
    }
    
    @SubscribeEvent
    public void onRegisterCommands(RegisterCommandsEvent evt) {
        CommandDispatcher<CommandSourceStack> disp = evt.getDispatcher();
        
        disp.register(Commands.literal("oracle")
            .requires(src -> src.hasPermission(2))
            .then(Commands.literal("spawn")
                .executes(ctx -> {
                    ServerPlayer player = ctx.getSource().getPlayerOrException();
                    oracleSystem.spawnOracle(player);
                    player.sendSystemMessage(Component.literal("§aOracle spawned using model: §b" + oracleBrain.getModelName()));
                    return 1;
                })
            )
            .then(Commands.literal("despawn")
                .executes(ctx -> {
                    ServerPlayer player = ctx.getSource().getPlayerOrException();
                    oracleSystem.despawnOracle(player);
                    player.sendSystemMessage(Component.literal("§cOracle despawned."));
                    return 1;
                })
            )
            .then(Commands.literal("setmodel")
                .then(Commands.argument("model", StringArgumentType.string())
                    .suggests(MODEL_SUGGESTIONS)
                    .executes(ctx -> {
                        String newModel = StringArgumentType.getString(ctx, "model");
                        if (!AVAILABLE_MODELS.contains(newModel)) {
                            ctx.getSource().sendFailure(Component.literal("§cModel not available. Options: " + String.join(", ", AVAILABLE_MODELS)));
                            return 0;
                        }
                        
                        String endpoint = "http://localhost:11434";
                        this.oracleBrain = new LLMOracleBrain(newModel, endpoint);
                        DWMod.getInstance().setOracleBrain(this.oracleBrain);
                        oracleSystem.setOracleBrain(this.oracleBrain);
                        
                        ctx.getSource().sendSuccess(() -> Component.literal("§aOracle model changed to: §b" + newModel), true);
                        return 1;
                    })
                )
            )
            .then(Commands.literal("listmodels")
                .executes(ctx -> {
                    ctx.getSource().sendSuccess(() -> Component.literal("§eAvailable Oracle Models:"), false);
                    String activeModel = oracleBrain.getModelName();
                    for (String model : AVAILABLE_MODELS) {
                        if (model.equals(activeModel)) {
                            ctx.getSource().sendSuccess(() -> Component.literal("§a - " + model + " §7(active)"), false);
                        } else {
                            ctx.getSource().sendSuccess(() -> Component.literal("§b - " + model), false);
                        }
                    }
                    return 1;
                })
            )
        );
    }
}
