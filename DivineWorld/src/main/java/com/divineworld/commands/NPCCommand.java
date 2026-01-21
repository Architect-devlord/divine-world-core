// src/main/java/com/divineworld/commands/NPCCommand.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.integration.PythonBackendClient;
import com.divineworld.utils.TaggedEntitySystem;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.List;

/**
 * NPC Management Commands - FIXED to use single agent spawn endpoint
 */
public class NPCCommand {

    /**
     * Register all NPC commands under /dw npc
     */
    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("dw")
                .then(Commands.literal("npc")

                        // /dw npc spawn <name>
                        .then(Commands.literal("spawn")
                                .then(Commands.argument("name", StringArgumentType.string())
                                        .executes(NPCCommand::spawnNPC)
                                )
                        )

                        // /dw npc list
                        .then(Commands.literal("list")
                                .executes(NPCCommand::listNPCs)
                        )

                        // /dw npc remove <name>
                        .then(Commands.literal("remove")
                                .then(Commands.argument("name", StringArgumentType.string())
                                        .executes(NPCCommand::removeNPC)
                                )
                        )

                        // /dw npc info <name>
                        .then(Commands.literal("info")
                                .then(Commands.argument("name", StringArgumentType.string())
                                        .executes(NPCCommand::getNPCInfo)
                                )
                        )
                )
        );

        DWMod.LOGGER.info("[NPCCommand] Registered /dw npc commands");
    }

    /**
     * Spawn a new NPC agent via Python backend - FIXED
     */
    private static int spawnNPC(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String name = StringArgumentType.getString(ctx, "name");

            // Calculate spawn position (in front of player)
            BlockPos spawnPos = player.blockPosition().relative(player.getDirection(), 3);
            spawnPos = getSafeSpawnPosition(level, spawnPos);

            player.sendSystemMessage(Component.literal("§d[DW] §eSpawning NPC: " + name));

            // ✅ FIX: Use new single agent spawn endpoint instead of genesis
            PythonBackendClient.spawnSingleAgent(
                    name,
                    player.getName().getString(),
                    level.dimension().location().toString(),
                    spawnPos
            );

            player.sendSystemMessage(Component.literal("§a[DW] Agent system initializing..."));
            player.sendSystemMessage(Component.literal("§7The NPC will connect shortly."));

            DWMod.LOGGER.info("Spawning NPC '{}' at {} for player {}",
                    name, spawnPos, player.getName().getString());

            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("NPC spawn command failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[DW] Spawn failed: " + e.getMessage()));
            return 0;
        }
    }

    /**
     * List all AI-controlled NPCs in the world
     */
    private static int listNPCs(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();

            List<ServerPlayer> npcs = DWNPCManager.getAIPlayers(level);
            List<ServerPlayer> gods = DWNPCManager.getGodPlayers(level);

            int regularNPCs = npcs.size() - gods.size();

            player.sendSystemMessage(Component.literal("§5[DW] §eNPCs in world: " + regularNPCs));

            for (ServerPlayer npc : npcs) {
                if (DWNPCManager.isGodPlayer(npc)) {
                    continue; // Skip gods
                }

                String agentId = DWNPCManager.getAgentId(npc);
                String displayName = npc.getName().getString();
                BlockPos pos = npc.blockPosition();

                player.sendSystemMessage(Component.literal(
                        "§7- " + displayName + " §8(ID: " + agentId + ") §7at " + pos.toShortString()
                ));
            }

            if (regularNPCs == 0) {
                player.sendSystemMessage(Component.literal("§7No NPCs found. Use §b/dw npc spawn <name>"));
            }

            return regularNPCs;

        } catch (Exception e) {
            DWMod.LOGGER.error("List NPCs command failed", e);
            return 0;
        }
    }

    /**
     * Remove an NPC by name
     */
    private static int removeNPC(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String name = StringArgumentType.getString(ctx, "name");

            List<ServerPlayer> npcs = DWNPCManager.getAIPlayers(level);

            for (ServerPlayer npc : npcs) {
                if (npc.getName().getString().equalsIgnoreCase(name)) {

                    // Skip if it's a god
                    if (DWNPCManager.isGodPlayer(npc)) {
                        player.sendSystemMessage(Component.literal(
                                "§c[DW] Cannot remove gods via this command. Use /divine_reset instead."
                        ));
                        return 0;
                    }

                    String agentId = DWNPCManager.getAgentId(npc);

                    // Disconnect the NPC (Python backend will be notified via player disconnect event)
                    npc.connection.disconnect(Component.literal("§c[DW] Removed by administrator"));

                    player.sendSystemMessage(Component.literal("§a[DW] Removed NPC: " + name));

                    DWMod.LOGGER.info("NPC '{}' (Agent: {}) removed by {}",
                            name, agentId, player.getName().getString());

                    return 1;
                }
            }

            player.sendSystemMessage(Component.literal("§c[DW] NPC not found: " + name));
            player.sendSystemMessage(Component.literal("§7Use §b/dw npc list §7to see all NPCs"));

            return 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("Remove NPC command failed", e);
            return 0;
        }
    }

    /**
     * Get detailed information about an NPC
     */
    private static int getNPCInfo(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            ServerLevel level = ctx.getSource().getLevel();
            String name = StringArgumentType.getString(ctx, "name");

            List<ServerPlayer> npcs = DWNPCManager.getAIPlayers(level);

            for (ServerPlayer npc : npcs) {
                if (npc.getName().getString().equalsIgnoreCase(name)) {

                    String agentId = DWNPCManager.getAgentId(npc);
                    boolean isGod = DWNPCManager.isGodPlayer(npc);
                    BlockPos pos = npc.blockPosition();

                    player.sendSystemMessage(Component.literal("§5[DW] §eNPC Information:"));
                    player.sendSystemMessage(Component.literal("§7Name: " + name));
                    player.sendSystemMessage(Component.literal("§7Agent ID: " + agentId));
                    player.sendSystemMessage(Component.literal("§7Position: " + pos.toShortString()));
                    player.sendSystemMessage(Component.literal("§7Type: " + (isGod ? "§cGod" : "§aNPC")));

                    if (isGod) {
                        String godType = TaggedEntitySystem.getGodType(npc);
                        int divinePower = TaggedEntitySystem.getDivinePower(npc);
                        player.sendSystemMessage(Component.literal("§7God Type: §d" + godType));
                        player.sendSystemMessage(Component.literal("§7Divine Power: §d" + divinePower));
                    }

                    player.sendSystemMessage(Component.literal("§7Health: §c" +
                            String.format("%.1f", npc.getHealth()) + "/" +
                            String.format("%.1f", npc.getMaxHealth())));

                    return 1;
                }
            }

            player.sendSystemMessage(Component.literal("§c[DW] NPC not found: " + name));
            player.sendSystemMessage(Component.literal("§7Use §b/dw npc list §7to see all NPCs"));

            return 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("Get NPC info command failed", e);
            return 0;
        }
    }

    /**
     * Find a safe spawn position (solid ground, air above)
     */
    private static BlockPos getSafeSpawnPosition(ServerLevel level, BlockPos pos) {
        for (int i = 0; i < 10; i++) {
            if (level.getBlockState(pos).isAir() &&
                    level.getBlockState(pos.above()).isAir() &&
                    level.getBlockState(pos.below()).isSolid()) {
                return pos;
            }
            pos = pos.above();
        }
        return pos; // Fallback
    }
}