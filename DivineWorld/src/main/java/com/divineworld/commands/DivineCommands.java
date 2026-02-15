// src/main/java/com/divineworld/commands/DivineCommands.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import com.divineworld.utils.AgentConfigLoader;
import com.divineworld.utils.GenesisManager;
import com.divineworld.utils.TaggedEntitySystem;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.commands.arguments.EntityArgument;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

/**
 * Complete Divine World command system
 * Synced with AgentConfigLoader.java for agent registry (agents.json)
 *
 * Commands:
 * - /genesis - Spawn 2 AI agents
 * - /divine_reset - Kill all AI agents + delete memories
 * - /clear_memories <all|agent_id> [exceptions...] - Clear agent memories
 * - /spawn_god <type> - Spawn god agent
 * - /god_ability <agent_id> <ability> [params...] - Use god ability
 * - /god_transform <agent_id> <mob> - Transform god
 * - /list_agents - List all AI agents
 */
public class DivineCommands {

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        // /genesis - Spawn 2 AI agents
        dispatcher.register(Commands.literal("genesis")
                .executes(ctx -> executeGenesis(ctx))
        );

        // /divine_reset - Kill all AI agents
        dispatcher.register(Commands.literal("divine_reset")
                .executes(ctx -> executeDivineReset(ctx))
        );

        // /clear_memories <all|agent_id> [exceptions...]
        dispatcher.register(Commands.literal("clear_memories")
                .then(Commands.argument("target", StringArgumentType.string())
                        .executes(ctx -> executeClearMemories(ctx, new ArrayList<>()))
                        .then(Commands.argument("exceptions", EntityArgument.players())
                                .executes(ctx -> executeClearMemoriesWithExceptions(ctx))
                        )
                )
        );

        // /spawn_god <type>
        dispatcher.register(Commands.literal("spawn_god")
                .then(Commands.argument("type", StringArgumentType.string())
                        .suggests((ctx, builder) -> {
                            // Suggest god types from agents.json config
                            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
                            for (String godType : config.getGodTypes()) {
                                builder.suggest(godType.toLowerCase());
                            }
                            // Also suggest common god types
                            builder.suggest("ender_dragon");
                            builder.suggest("wither");
                            builder.suggest("warden");
                            builder.suggest("elder_guardian");
                            builder.suggest("oracle");
                            builder.suggest("creaking");
                            return builder.buildFuture();
                        })
                        .executes(ctx -> executeSpawnGod(ctx))
                )
        );

        // /god_ability <agent_id> <ability> [params...]
        dispatcher.register(Commands.literal("god_ability")
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .then(Commands.argument("ability", StringArgumentType.string())
                                .executes(ctx -> executeGodAbility(ctx))
                        )
                )
        );

        // /god_transform <agent_id> <mob>
        dispatcher.register(Commands.literal("god_transform")
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .then(Commands.argument("mob", StringArgumentType.string())
                                .suggests((ctx, builder) -> {
                                    builder.suggest("player");
                                    builder.suggest("villager");
                                    builder.suggest("pig");
                                    builder.suggest("cow");
                                    builder.suggest("zombie");
                                    builder.suggest("skeleton");
                                    return builder.buildFuture();
                                })
                                .executes(ctx -> executeGodTransform(ctx))
                        )
                )
        );

        // /list_agents - List all AI agents
        dispatcher.register(Commands.literal("list_agents")
                .executes(ctx -> executeListAgents(ctx))
        );
    }

    private static int executeGenesis(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            // Check cooldown
            if (!GenesisManager.canUseGenesis(player)) {
                long remaining = GenesisManager.getGenesisCooldown(player);
                player.sendSystemMessage(Component.literal(
                        "§c[Genesis] Cooldown: " + remaining + " seconds remaining"
                ));
                return 0;
            }

            // Load and display available agents from agents.json
            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
            player.sendSystemMessage(Component.literal("§5[Genesis] §eAvailable agents in registry:"));
            player.sendSystemMessage(Component.literal("  §7Male: " + String.join(", ", config.getMaleNPCNames())));
            player.sendSystemMessage(Component.literal("  §7Female: " + String.join(", ", config.getFemaleNPCNames())));

            // Trigger genesis (spawns 2 agents via Python)
            BlockPos playerPos = player.blockPosition();
            BlockPos spawn1 = playerPos.relative(player.getDirection(), 3).offset(2, 0, 0);
            BlockPos spawn2 = playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0);

            player.sendSystemMessage(Component.literal("§5[Genesis] §eCreating first beings..."));

            PythonBackendClient.spawnGenesisAgents(
                    player.getName().getString(),
                    level.dimension().location().toString(),
                    spawn1,
                    spawn2
            );

            DWMod.LOGGER.info("Genesis invoked by {}", player.getName().getString());
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("Genesis command failed", e);
            return 0;
        }
    }

    private static int executeDivineReset(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            // Check if player is a god (optional restriction)
            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[Divine Reset] Only gods may invoke the Divine Reset!"
                ));
                return 0;
            }

            GenesisManager.triggerDivineReset(level, player);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("Divine reset command failed", e);
            return 0;
        }
    }

    private static int executeClearMemories(CommandContext<CommandSourceStack> ctx, List<String> exceptions) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String target = StringArgumentType.getString(ctx, "target");

            List<String> agentIds = new ArrayList<>();

            if (target.equalsIgnoreCase("all")) {
                // Clear all AI agents
                List<ServerPlayer> agents = DWNPCManager.getAIPlayers(level);
                for (ServerPlayer agent : agents) {
                    String agentId = DWNPCManager.getAgentId(agent);
                    if (agentId != null && !exceptions.contains(agentId)) {
                        agentIds.add(agentId);
                    }
                }
            } else {
                // Clear specific agent
                if (!exceptions.contains(target)) {
                    agentIds.add(target);
                }
            }

            if (agentIds.isEmpty()) {
                player.sendSystemMessage(Component.literal(
                        "§c[Clear Memories] No agents to clear (all in exception list)"
                ));
                return 0;
            }

            PythonBackendClient.clearAgentMemories(agentIds, exceptions);

            player.sendSystemMessage(Component.literal(
                    "§a[Clear Memories] Clearing memories for " + agentIds.size() + " agents..."
            ));

            if (!exceptions.isEmpty()) {
                player.sendSystemMessage(Component.literal(
                        "§7Exceptions: " + String.join(", ", exceptions)
                ));
            }

            return agentIds.size();

        } catch (Exception e) {
            DWMod.LOGGER.error("Clear memories command failed", e);
            return 0;
        }
    }

    private static int executeClearMemoriesWithExceptions(CommandContext<CommandSourceStack> ctx) {
        try {
            Collection<ServerPlayer> exceptionPlayers = EntityArgument.getPlayers(ctx, "exceptions");
            List<String> exceptions = new ArrayList<>();

            for (ServerPlayer p : exceptionPlayers) {
                if (DWNPCManager.isAIPlayer(p)) {
                    String agentId = DWNPCManager.getAgentId(p);
                    if (agentId != null) {
                        exceptions.add(agentId);
                    }
                }
            }

            return executeClearMemories(ctx, exceptions);

        } catch (Exception e) {
            return executeClearMemories(ctx, new ArrayList<>());
        }
    }

    private static int executeSpawnGod(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String godType = StringArgumentType.getString(ctx, "type");

            // Validate god type against config
            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
            boolean isValidType = AgentConfigLoader.isValidGodType(godType);
            
            if (!isValidType) {
                player.sendSystemMessage(Component.literal(
                        "§c[Spawn God] Unknown god type: " + godType
                ));
                player.sendSystemMessage(Component.literal(
                        "§7Available: " + String.join(", ", config.getGodTypes())
                ));
                return 0;
            }

            BlockPos spawnPos = player.blockPosition().relative(player.getDirection(), 3);

            player.sendSystemMessage(Component.literal(
                    "§d[Spawn God] §eCreating " + godType + " god..."
            ));

            PythonBackendClient.spawnGodAgent(
                    godType,
                    player.getName().getString(),
                    level.dimension().location().toString(),
                    spawnPos
            );

            DWMod.LOGGER.info("{} spawning god: {}", player.getName().getString(), godType);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("Spawn god command failed", e);
            return 0;
        }
    }

    private static int executeGodAbility(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            String agentId = StringArgumentType.getString(ctx, "agent_id");
            String ability = StringArgumentType.getString(ctx, "ability");

            // Verify agent exists and is a god
            ServerPlayer godPlayer = DWNPCManager.findPlayerByAgentId(ctx.getSource().getLevel(), agentId);

            if (godPlayer == null) {
                player.sendSystemMessage(Component.literal("§c[God Ability] Agent not found: " + agentId));
                return 0;
            }

            if (!DWNPCManager.isGodPlayer(godPlayer)) {
                player.sendSystemMessage(Component.literal("§c[God Ability] " + agentId + " is not a god"));
                return 0;
            }

            PythonBackendClient.godUseAbility(agentId, ability);

            player.sendSystemMessage(Component.literal(
                    "§a[God Ability] Commanding " + agentId + " to use: " + ability
            ));

            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God ability command failed", e);
            return 0;
        }
    }

    private static int executeGodTransform(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            String agentId = StringArgumentType.getString(ctx, "agent_id");
            String targetMob = StringArgumentType.getString(ctx, "mob");

            // Verify agent exists and is a god
            ServerPlayer godPlayer = DWNPCManager.findPlayerByAgentId(ctx.getSource().getLevel(), agentId);

            if (godPlayer == null) {
                player.sendSystemMessage(Component.literal("§c[God Transform] Agent not found: " + agentId));
                return 0;
            }

            if (!DWNPCManager.isGodPlayer(godPlayer)) {
                player.sendSystemMessage(Component.literal("§c[God Transform] " + agentId + " is not a god"));
                return 0;
            }

            PythonBackendClient.godTransform(agentId, targetMob);

            player.sendSystemMessage(Component.literal("§a[God Transform] Commanding " + agentId + " to transform into: " + targetMob));

            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God transform command failed", e);
            return 0;
        }
    }

    private static int executeListAgents(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            List<ServerPlayer> aiAgents = DWNPCManager.getAIPlayers(level);
            List<ServerPlayer> godAgents = DWNPCManager.getGodPlayers(level);

            player.sendSystemMessage(Component.literal("§d[AI Agents] §eTotal: " + aiAgents.size()));
            player.sendSystemMessage(Component.literal("§7Normal Agents: " + (aiAgents.size() - godAgents.size())));
            player.sendSystemMessage(Component.literal("§7God Agents: " + godAgents.size()));

            for (ServerPlayer agent : aiAgents) {
                String agentId = DWNPCManager.getAgentId(agent);
                boolean isGod = DWNPCManager.isGodPlayer(agent);
                String godType = isGod ? TaggedEntitySystem.getGodType(agent) : null;

                String display = isGod
                        ? "§c[GOD-" + godType + "] " + agentId
                        : "§a[NPC] " + agentId;

                player.sendSystemMessage(Component.literal("  " + display));
            }

            // Show registry info
            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
            player.sendSystemMessage(Component.literal("§d[Agent Registry] (agents.json)"));
            player.sendSystemMessage(Component.literal("  §7Male NPCs: " + config.getMaleNPCNames().size()));
            player.sendSystemMessage(Component.literal("  §7Female NPCs: " + config.getFemaleNPCNames().size()));
            player.sendSystemMessage(Component.literal("  §7Gods: " + config.getGodTypes().size()));

            return aiAgents.size();

        } catch (Exception e) {
            DWMod.LOGGER.error("List agents command failed", e);
            return 0;
        }
    }
}