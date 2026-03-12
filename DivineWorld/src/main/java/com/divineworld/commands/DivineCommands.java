// src/main/java/com/divineworld/commands/DivineCommands.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import com.divineworld.utils.AgentConfigLoader;
import com.divineworld.events.GodDisguiseHandler;
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
 *
 * FIX Bug #6 — executeGodAbility now runs server-side effects
 * -----------------------------------------------------------
 * Previously executeGodAbility() only called PythonBackendClient.godUseAbility()
 * which POSTed to the Python backend. The ability effects (damage, particles,
 * knockback, status effects) never ran in the Minecraft world.
 *
 * Now it calls ServerGodAbilityExecutor.execute() which runs all effects
 * directly server-side. Python is also still notified (fire-and-forget) so the
 * AI cognitive loop can record the ability as an action taken.
 */
public class DivineCommands {

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        // /genesis
        dispatcher.register(Commands.literal("genesis")
                .executes(ctx -> executeGenesis(ctx))
        );

        // /divine_reset
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
                            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
                            for (String godType : config.getGodTypes()) builder.suggest(godType.toLowerCase());
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

        // /god_ability <agent_id> <ability>
        dispatcher.register(Commands.literal("god_ability")
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .then(Commands.argument("ability", StringArgumentType.string())
                                .suggests((ctx, builder) -> {
                                    // Suggest common ability names across all god types
                                    String[] abilities = {
                                        "sonic_boom","darkness","sniff","burrow","emerge",
                                        "wither_skull","explosion","summon_wither_skeletons","dash",
                                        "dragon_breath","fireball","perch",
                                        "mining_fatigue","laser_beam","guardian_spikes","thorn_attack",
                                        "wisdom_aura","teleport","healing_wave","knowledge_beam",
                                        "tentacle_whip","life_steal","toggle_underground","toggle_ceiling"
                                    };
                                    for (String a : abilities) builder.suggest(a);
                                    return builder.buildFuture();
                                })
                                .executes(ctx -> executeGodAbility(ctx))
                        )
                )
        );

        // /god_transform <mob>              — caller transforms themselves
        // /god_transform <agent_id> <mob>   — admin transforms a god agent
        // /god_transform <agent_id> revert  — restore original form
        dispatcher.register(Commands.literal("god_transform")
                .requires(src -> src.hasPermission(2))
                .then(Commands.argument("mob", StringArgumentType.string())
                        .suggests((ctx, builder) -> { suggestMobTypes(builder); return builder.buildFuture(); })
                        .executes(ctx -> executeGodTransformSelf(ctx))
                )
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .then(Commands.argument("mob", StringArgumentType.string())
                                .suggests((ctx, builder) -> { suggestMobTypes(builder); return builder.buildFuture(); })
                                .executes(ctx -> executeGodTransform(ctx))
                        )
                )
        );

        // /list_agents
        dispatcher.register(Commands.literal("list_agents")
                .executes(ctx -> executeListAgents(ctx))
        );
    }

    // =========================================================================

    private static int executeGenesis(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            if (!GenesisManager.canUseGenesis(player)) {
                long remaining = GenesisManager.getGenesisCooldown(player);
                player.sendSystemMessage(Component.literal(
                        "§c[Genesis] Cooldown: " + remaining + " seconds remaining"));
                return 0;
            }

            AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
            player.sendSystemMessage(Component.literal("§5[Genesis] §eAvailable agents in registry:"));
            player.sendSystemMessage(Component.literal("  §7Male: " + String.join(", ", config.getMaleNPCNames())));
            player.sendSystemMessage(Component.literal("  §7Female: " + String.join(", ", config.getFemaleNPCNames())));

            BlockPos playerPos = player.blockPosition();
            BlockPos spawn1 = playerPos.relative(player.getDirection(), 3).offset(2, 0, 0);
            BlockPos spawn2 = playerPos.relative(player.getDirection(), 3).offset(-2, 0, 0);

            player.sendSystemMessage(Component.literal("§5[Genesis] §eCreating first beings..."));

            PythonBackendClient.spawnGenesisAgents(
                    player.getName().getString(),
                    level.dimension().location().toString(),
                    spawn1, spawn2);

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

            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[Divine Reset] Only gods may invoke the Divine Reset!"));
                return 0;
            }

            GenesisManager.triggerDivineReset(level, player);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("Divine reset command failed", e);
            return 0;
        }
    }

    private static int executeClearMemories(CommandContext<CommandSourceStack> ctx,
                                             List<String> exceptions) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String target = StringArgumentType.getString(ctx, "target");

            List<String> agentIds = new ArrayList<>();
            if (target.equalsIgnoreCase("all")) {
                for (ServerPlayer agent : DWNPCManager.getAIPlayers(level)) {
                    String agentId = DWNPCManager.getAgentId(agent);
                    if (agentId != null && !exceptions.contains(agentId)) agentIds.add(agentId);
                }
            } else {
                if (!exceptions.contains(target)) agentIds.add(target);
            }

            if (agentIds.isEmpty()) {
                player.sendSystemMessage(Component.literal(
                        "§c[Clear Memories] No agents to clear (all in exception list)"));
                return 0;
            }

            PythonBackendClient.clearAgentMemories(agentIds, exceptions);
            player.sendSystemMessage(Component.literal(
                    "§a[Clear Memories] Clearing memories for " + agentIds.size() + " agents..."));
            if (!exceptions.isEmpty()) {
                player.sendSystemMessage(Component.literal(
                        "§7Exceptions: " + String.join(", ", exceptions)));
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
                    if (agentId != null) exceptions.add(agentId);
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

            if (!AgentConfigLoader.isValidGodType(godType)) {
                AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
                player.sendSystemMessage(Component.literal("§c[Spawn God] Unknown god type: " + godType));
                player.sendSystemMessage(Component.literal("§7Available: " + String.join(", ", config.getGodTypes())));
                return 0;
            }

            BlockPos spawnPos = player.blockPosition().relative(player.getDirection(), 3);
            player.sendSystemMessage(Component.literal("§d[Spawn God] §eCreating " + godType + " god..."));
            PythonBackendClient.spawnGodAgent(godType, player.getName().getString(),
                    level.dimension().location().toString(), spawnPos);
            DWMod.LOGGER.info("{} spawning god: {}", player.getName().getString(), godType);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("Spawn god command failed", e);
            return 0;
        }
    }

    /**
     * FIX Bug #6: Now calls ServerGodAbilityExecutor.execute() which runs ability
     * effects directly in the Minecraft world (damage, particles, status effects).
     * Python is still notified so the AI's cognitive loop can record the action.
     */
    private static int executeGodAbility(CommandContext<CommandSourceStack> ctx) {
        try {
            String agentId = StringArgumentType.getString(ctx, "agent_id");
            String ability  = StringArgumentType.getString(ctx, "ability");
            ServerLevel level = ctx.getSource().getLevel();

            ServerPlayer godPlayer = DWNPCManager.findPlayerByAgentId(level, agentId);
            if (godPlayer == null) {
                ctx.getSource().sendFailure(Component.literal("§c[God Ability] Agent not found: " + agentId));
                return 0;
            }
            if (!DWNPCManager.isGodPlayer(godPlayer)) {
                ctx.getSource().sendFailure(Component.literal("§c[God Ability] " + agentId + " is not a god"));
                return 0;
            }

            // Execute ability effects server-side
            ServerGodAbilityExecutor.execute(godPlayer, ability, level);

            // Notify Python (fire-and-forget — a failure here must not block the ability)
            try {
                PythonBackendClient.godUseAbility(agentId, ability);
            } catch (Exception pyEx) {
                DWMod.LOGGER.warn("[god_ability] Backend notify failed for {}/{}: {}",
                        agentId, ability, pyEx.getMessage());
            }

            DWMod.LOGGER.info("[god_ability] {} used {}", agentId, ability);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("God ability command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Ability] " + e.getMessage()));
            return 0;
        }
    }

    private static int executeGodTransformSelf(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            String mobType = StringArgumentType.getString(ctx, "mob");

            if ("revert".equalsIgnoreCase(mobType)) {
                GodDisguiseHandler.removeTransform(player);
                return 1;
            }
            GodDisguiseHandler.applyTransform(player, mobType, ctx.getSource().getLevel());
            return 1;
        } catch (Exception e) {
            DWMod.LOGGER.error("[god_transform] self command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Transform] " + e.getMessage()));
            return 0;
        }
    }

    private static int executeGodTransform(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor = ctx.getSource().getPlayerOrException();
            String agentId = StringArgumentType.getString(ctx, "agent_id");
            String mobType  = StringArgumentType.getString(ctx, "mob");

            ServerPlayer target = null;
            if (agentId.equalsIgnoreCase("self") ||
                agentId.equals(executor.getName().getString())) {
                target = executor;
            } else {
                target = DWNPCManager.findPlayerByAgentId(ctx.getSource().getLevel(), agentId);
            }

            if (target == null) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Transform] Agent not found: " + agentId));
                return 0;
            }

            if ("revert".equalsIgnoreCase(mobType)) {
                GodDisguiseHandler.removeTransform(target);
                executor.sendSystemMessage(Component.literal("§d[God Transform] " + agentId + " reverted."));
                return 1;
            }

            boolean ok = GodDisguiseHandler.applyTransform(target, mobType, target.serverLevel());
            if (ok && target != executor) {
                executor.sendSystemMessage(Component.literal(
                        "§a[God Transform] " + agentId + " is now: §b" + mobType));
            }
            return ok ? 1 : 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("[god_transform] command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Transform] " + e.getMessage()));
            return 0;
        }
    }

    private static void suggestMobTypes(com.mojang.brigadier.suggestion.SuggestionsBuilder builder) {
        builder.suggest("revert");
        String[] godTypes = {"oracle","warden","ender_dragon","wither","elder_guardian","creaking"};
        for (String t : godTypes) builder.suggest(t);
        String[] common = {
            "zombie","skeleton","creeper","spider","enderman","blaze","ghast",
            "witch","villager","pillager","vindicator","evoker","ravager",
            "iron_golem","snow_golem","horse","wolf","fox","bee","drowned",
            "husk","stray","wither_skeleton","cave_spider","slime","magma_cube",
            "shulker","guardian","phantom","piglin","hoglin","zoglin",
            "piglin_brute","goat","axolotl","frog","sniffer","camel",
            "cat","rabbit","cow","pig","sheep","chicken","mooshroom",
            "bat","squid","glow_squid","dolphin","turtle","pufferfish",
            "salmon","cod","tropical_fish","polar_bear","panda","ocelot",
            "llama","parrot","mule","donkey","strider","trader_llama",
            "wandering_trader","allay","vex"
        };
        for (String m : common) builder.suggest(m);
        for (String t : AgentConfigLoader.getGodTypes()) builder.suggest(t);
    }

    private static int executeListAgents(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            List<ServerPlayer> aiAgents  = DWNPCManager.getAIPlayers(level);
            List<ServerPlayer> godAgents = DWNPCManager.getGodPlayers(level);

            player.sendSystemMessage(Component.literal(
                    "§d[AI Agents] §eTotal: " + aiAgents.size()));
            player.sendSystemMessage(Component.literal(
                    "§7Normal Agents: " + (aiAgents.size() - godAgents.size())));
            player.sendSystemMessage(Component.literal(
                    "§7God Agents: " + godAgents.size()));

            for (ServerPlayer agent : aiAgents) {
                String agentId  = DWNPCManager.getAgentId(agent);
                boolean isGod   = DWNPCManager.isGodPlayer(agent);
                String godType  = isGod ? TaggedEntitySystem.getGodType(agent) : null;
                String display  = isGod
                        ? "§c[GOD-" + godType + "] " + agentId
                        : "§a[NPC] " + agentId;
                player.sendSystemMessage(Component.literal("  " + display));
            }

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