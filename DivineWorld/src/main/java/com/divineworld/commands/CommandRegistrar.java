package com.divineworld.commands;

import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.core.BlockPos;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.SubscribeEvent;

import java.net.HttpURLConnection;
import java.net.URL;

/**
 * Registers actionable commands (e.g., /npcspawn).
 */
public class CommandRegistrar {

    public static void register() {
        MinecraftForge.EVENT_BUS.register(new CommandRegistrar());
        //MinecraftForge.EVENT_BUS.addListener((RegisterCommandsEvent e) -> GodCommand.register(e.getDispatcher()));

    }

    @SubscribeEvent
    public void onRegisterCommands(RegisterCommandsEvent evt) {
        CommandDispatcher<CommandSourceStack> disp = evt.getDispatcher();
        // In CommandRegistrar.java
        disp.register(
                Commands.literal("spawnai")
                        .then(Commands.argument("agentId", StringArgumentType.string())
                                .executes(ctx -> {
                                    String agentId = StringArgumentType.getString(ctx, "agentId");
                                    ServerPlayer player = ctx.getSource().getPlayerOrException();

                                    // Call Python backend to spawn
                                    try {
                                        URL url = new URL("http://127.0.0.1:11400/api/spawn_npc");
                                        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                                        conn.setRequestMethod("POST");
                                        conn.setDoOutput(true);

                                        String data = "agent_id=" + agentId +
                                                "&server=127.0.0.1:25565" +
                                                "&curiosity=0.7&boldness=0.5";

                                        conn.getOutputStream().write(data.getBytes());

                                        int code = conn.getResponseCode();
                                        if (code == 200) {
                                            player.sendSystemMessage(Component.literal("§aSpawning AI agent: " + agentId));
                                        }

                                        conn.disconnect();
                                    } catch (Exception e) {
                                        player.sendSystemMessage(Component.literal("§cFailed to spawn: " + e.getMessage()));
                                    }

                                    return 1;
                                })
                        )
        );

        /* Add to onRegisterCommands method:

        disp.register(
                Commands.literal("npcsay")
                        .requires(src -> src.hasPermission(2))
                        .then(Commands.argument("message", StringArgumentType.greedyString())
                                .executes(ctx -> {
                                    String message = StringArgumentType.getString(ctx, "message");
                                    ServerPlayer player = ctx.getSource().getPlayerOrException();

                                    // Find nearest DWFakePlayer
                                    var level = player.level();
                                    var nearest = level.getEntitiesOfClass(
                                            DWNPCWithChat.class,
                                            player.getBoundingBox().inflate(10.0),
                                            e -> true
                                    ).stream().findFirst();

                                    if (nearest.isPresent()) {
                                        nearest.get().say(message);
                                        player.sendSystemMessage(Component.literal("§aMessage sent!"));
                                    } else {
                                        player.sendSystemMessage(Component.literal("§cNo NPC nearby"));
                                    }

                                    return 1;
                                })
                        )
        );
    */
    }
}
