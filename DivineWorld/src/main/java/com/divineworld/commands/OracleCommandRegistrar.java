package com.divineworld.commands;

import com.divineworld.oracle.LLMOracleBrain;
import com.divineworld.oracle.OllamaManager;
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

import java.util.Arrays;
import java.util.List;

/**
 * COMPLETE Oracle Command Registration
 * All commands properly registered
 */
public class OracleCommandRegistrar {

    private static final List<String> AVAILABLE_MODELS = Arrays.asList(
            "phi3:mini",
            "gemma3:1b",
            "deepseek-r1:8b",
            "llama2",
            "mistral"
    );

    private static final SuggestionProvider<CommandSourceStack> MODEL_SUGGESTIONS = (ctx, builder) ->
            SharedSuggestionProvider.suggest(AVAILABLE_MODELS, builder);

    /**
     * Register all Oracle commands
     */
    public static void registerCommands(CommandDispatcher<CommandSourceStack> dispatcher,
                                        OracleSystem oracleSystem,
                                        LLMOracleBrain oracleBrain) {

        DWMod.LOGGER.info("[OracleCommandRegistrar] Registering Oracle commands...");

        dispatcher.register(Commands.literal("oracle")
                // ===== SPAWN =====
                .then(Commands.literal("spawn")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();
                                oracleSystem.spawnOracle(player);
                                player.sendSystemMessage(Component.literal("§aOracle spawned using model: §b" + oracleBrain.getModelName()));
                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Oracle spawn command failed", e);
                                ctx.getSource().sendFailure(Component.literal("§cFailed to spawn Oracle: " + e.getMessage()));
                                return 0;
                            }
                        })
                )

                // ===== DESPAWN =====
                .then(Commands.literal("despawn")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();
                                oracleSystem.despawnOracle(player);
                                player.sendSystemMessage(Component.literal("§cOracle despawned."));
                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Oracle despawn command failed", e);
                                ctx.getSource().sendFailure(Component.literal("§cFailed to despawn Oracle: " + e.getMessage()));
                                return 0;
                            }
                        })
                )

                // ===== SET_MODEL =====
                .then(Commands.literal("set_model")
                        .then(Commands.argument("model", StringArgumentType.greedyString())
                                .suggests(MODEL_SUGGESTIONS)
                                .executes(ctx -> {
                                    try {
                                        String newModel = StringArgumentType.getString(ctx, "model");

                                        if (newModel.trim().isEmpty()) {
                                            ctx.getSource().sendFailure(Component.literal("§cModel name cannot be empty"));
                                            return 0;
                                        }

                                        ServerPlayer player = ctx.getSource().getPlayerOrException();

                                        String endpoint = "http://localhost:11434";
                                        LLMOracleBrain newBrain = new LLMOracleBrain(newModel, endpoint, false);

                                        DWMod.getInstance().setOracleBrain(newBrain);
                                        oracleSystem.setOracleBrain(newBrain);

                                        player.sendSystemMessage(Component.literal("§aOracle model changed to: §b" + newModel));
                                        player.sendSystemMessage(Component.literal("§7Endpoint: " + endpoint));

                                        DWMod.LOGGER.info("Oracle model changed to: {} by {}", newModel, player.getName().getString());

                                        return 1;
                                    } catch (Exception e) {
                                        DWMod.LOGGER.error("Set model command failed", e);
                                        ctx.getSource().sendFailure(Component.literal("§cFailed to change model: " + e.getMessage()));
                                        return 0;
                                    }
                                })
                        )
                )

                // ===== LIST_MODELS =====
                .then(Commands.literal("list_models")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§e━━━━━ Available Oracle Models ━━━━━"));
                                String activeModel = oracleBrain.getModelName();

                                for (String model : AVAILABLE_MODELS) {
                                    if (model.equals(activeModel)) {
                                        player.sendSystemMessage(Component.literal("§a✓ " + model + " §7(active)"));
                                    } else {
                                        player.sendSystemMessage(Component.literal("§7  " + model));
                                    }
                                }

                                player.sendSystemMessage(Component.literal("§e━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"));
                                player.sendSystemMessage(Component.literal("§7Usage: §b/oracle set_model <name>"));

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("List models command failed", e);
                                return 0;
                            }
                        })
                )

                // ===== TEST =====
                .then(Commands.literal("test")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§e[Oracle Test] Starting diagnostic test..."));
                                player.sendSystemMessage(Component.literal("§7=".repeat(40)));
                                player.sendSystemMessage(Component.literal("§7Model: " + oracleBrain.getModelName()));
                                player.sendSystemMessage(Component.literal("§7Host: " + OllamaManager.getHost()));
                                player.sendSystemMessage(Component.literal("§7Initialized: " + (OllamaManager.isInitialized() ? "§aYES" : "§cNO")));

                                // Check connection
                                boolean connected = OllamaManager.isOllamaRunning();
                                player.sendSystemMessage(Component.literal("§7Connection: " + (connected ? "§aOK" : "§cFAILED")));

                                if (!connected) {
                                    player.sendSystemMessage(Component.literal("§7=".repeat(40)));
                                    player.sendSystemMessage(Component.literal("§c[Oracle Test] Connection failed - cannot proceed"));
                                    return 0;
                                }

                                player.sendSystemMessage(Component.literal("§7=".repeat(40)));
                                player.sendSystemMessage(Component.literal("§e[Oracle Test] Sending test query..."));
                                player.sendSystemMessage(Component.literal("§7Query: 'Say hello in one word'"));

                                // Test the connection with timer
                                long startTime = System.currentTimeMillis();

                                oracleBrain.queryAsync(
                                        DWMod.getInstance().getServer(),
                                        "Say 'hello' in one word. Reply with only one word.",
                                        response -> {
                                            long elapsed = System.currentTimeMillis() - startTime;

                                            player.sendSystemMessage(Component.literal("§7=".repeat(40)));

                                            if (response.contains("Error") || response.contains("failed")) {
                                                player.sendSystemMessage(Component.literal("§c[Oracle Test] ❌ FAILED"));
                                                player.sendSystemMessage(Component.literal("§7Error: " + response));
                                            } else {
                                                player.sendSystemMessage(Component.literal("§a[Oracle Test] ✅ SUCCESS"));
                                                player.sendSystemMessage(Component.literal("§7Response time: " + elapsed + "ms"));
                                                player.sendSystemMessage(Component.literal("§7Response: §f" + response));
                                            }

                                            player.sendSystemMessage(Component.literal("§7=".repeat(40)));
                                            player.sendSystemMessage(Component.literal("§a[Oracle Test] Test complete!"));
                                        }
                                );

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Oracle test failed", e);
                                ctx.getSource().sendFailure(Component.literal("§cTest failed: " + e.getMessage()));
                                return 0;
                            }
                        })
                )

                // ===== STATUS =====
                .then(Commands.literal("status")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§e━━━━━ Oracle Status ━━━━━"));
                                player.sendSystemMessage(Component.literal("§7Active Model: §b" + oracleBrain.getModelName()));
                                player.sendSystemMessage(Component.literal("§7Endpoint: §bhttp://localhost:11434"));

                                String status = com.divineworld.oracle.OllamaManager.getStatus();
                                player.sendSystemMessage(Component.literal("§7Ollama: " + status));

                                boolean connected = oracleBrain.testConnection();
                                if (connected) {
                                    player.sendSystemMessage(Component.literal("§7Connection: §aOK"));
                                } else {
                                    player.sendSystemMessage(Component.literal("§7Connection: §cFAILED"));
                                    player.sendSystemMessage(Component.literal("§cTry: /oracle test for details"));
                                }

                                player.sendSystemMessage(Component.literal("§e━━━━━━━━━━━━━━━━━━━━━━━"));

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Status command failed", e);
                                return 0;
                            }
                        })
                )

                // ===== REFRESH =====
                .then(Commands.literal("refresh")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§e[Ollama] Refreshing connection..."));

                                boolean success = com.divineworld.oracle.OllamaManager.refresh();

                                if (success) {
                                    player.sendSystemMessage(Component.literal("§a[Ollama] ✅ Connection OK"));
                                } else {
                                    player.sendSystemMessage(Component.literal("§c[Ollama] ❌ Connection failed"));
                                    player.sendSystemMessage(Component.literal("§7Make sure 'ollama serve' is running"));
                                }

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Refresh command failed", e);
                                return 0;
                            }
                        })
                )

                // ===== PULL =====
                .then(Commands.literal("pull")
                        .then(Commands.argument("model", StringArgumentType.greedyString())
                                .suggests(MODEL_SUGGESTIONS)
                                .executes(ctx -> {
                                    try {
                                        String modelName = StringArgumentType.getString(ctx, "model");
                                        ServerPlayer player = ctx.getSource().getPlayerOrException();

                                        player.sendSystemMessage(Component.literal("§e[Ollama] Pulling model: " + modelName));
                                        player.sendSystemMessage(Component.literal("§7This may take several minutes..."));

                                        // Run async
                                        new Thread(() -> {
                                            boolean success = com.divineworld.oracle.OllamaManager.pullModel(modelName);

                                            DWMod.getInstance().getServer().execute(() -> {
                                                if (success) {
                                                    player.sendSystemMessage(Component.literal("§a[Ollama] ✅ Model pulled: " + modelName));
                                                    player.sendSystemMessage(Component.literal("§7Use: §b/oracle set_model " + modelName));
                                                } else {
                                                    player.sendSystemMessage(Component.literal("§c[Ollama] ❌ Failed to pull model"));
                                                    player.sendSystemMessage(Component.literal("§7Check server logs for details"));
                                                }
                                            });
                                        }, "Ollama-Pull-" + modelName).start();

                                        return 1;
                                    } catch (Exception e) {
                                        DWMod.LOGGER.error("Pull command failed", e);
                                        return 0;
                                    }
                                })
                        )
                )

                // ===== RESTART =====
                .then(Commands.literal("restart")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§e[Ollama] Reconnecting..."));

                                boolean success = com.divineworld.oracle.OllamaManager.refresh();

                                if (success) {
                                    player.sendSystemMessage(Component.literal("§a[Ollama] ✅ Reconnected"));
                                } else {
                                    player.sendSystemMessage(Component.literal("§c[Ollama] ❌ Cannot connect"));
                                    player.sendSystemMessage(Component.literal("§7Run: §bollama serve"));
                                }

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Restart command failed", e);
                                return 0;
                            }
                        })
                )

                // ===== HELP =====
                .then(Commands.literal("help")
                        .executes(ctx -> {
                            try {
                                ServerPlayer player = ctx.getSource().getPlayerOrException();

                                player.sendSystemMessage(Component.literal("§d━━━━━ Oracle Commands ━━━━━"));
                                player.sendSystemMessage(Component.literal("§b/oracle spawn §7- Summon the Oracle"));
                                player.sendSystemMessage(Component.literal("§b/oracle despawn §7- Dismiss the Oracle"));
                                player.sendSystemMessage(Component.literal("§b/oracle set_model <n> §7- Change AI model"));
                                player.sendSystemMessage(Component.literal("§b/oracle list_models §7- Show available models"));
                                player.sendSystemMessage(Component.literal("§b/oracle test §7- Test LLM connection"));
                                player.sendSystemMessage(Component.literal("§b/oracle status §7- Check Ollama status"));
                                player.sendSystemMessage(Component.literal("§b/oracle refresh §7- Kill stale processes"));
                                player.sendSystemMessage(Component.literal("§b/oracle restart §7- Restart Ollama server"));
                                player.sendSystemMessage(Component.literal("§b/oracle help §7- Show this help"));
                                player.sendSystemMessage(Component.literal("§d━━━━━━━━━━━━━━━━━━━━━━━━━"));

                                return 1;
                            } catch (Exception e) {
                                DWMod.LOGGER.error("Help command failed", e);
                                return 0;
                            }
                        })
                )
        ); // <-- CLOSING PARENTHESIS FOR THE WHOLE COMMAND TREE

        DWMod.LOGGER.info("[OracleCommandRegistrar] ✅ Oracle commands registered successfully");
        DWMod.LOGGER.info("[OracleCommandRegistrar] Available: spawn, despawn, set_model, list_models, test, status, refresh, restart, help");
    }
}