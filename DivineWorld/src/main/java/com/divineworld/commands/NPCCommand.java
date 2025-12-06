package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCWithChat;
import com.divineworld.utils.TaggedEntitySystem;
import com.google.gson.JsonObject;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.world.entity.EntityType;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.network.chat.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.Random;
import java.util.concurrent.CompletableFuture;

public class NPCCommand {
    
    private static final HttpClient HTTP_CLIENT = HttpClient.newHttpClient();
    private static final String PYTHON_BACKEND = "http://127.0.0.1:11400";
    private static final Random RANDOM = new Random();
    
    public static void register(CommandDispatcher dispatcher) {
        dispatcher.register(Commands.literal("dw")
            .requires(src -> src.hasPermission(2))
            .then(Commands.literal("npc")
                .then(Commands.literal("spawn")
                    .then(Commands.argument("name", StringArgumentType.string())
                        .executes(NPCCommand::spawnNPC)
                    )
                )
                .then(Commands.literal("list")
                    .executes(NPCCommand::listNPCs)
                )
                .then(Commands.literal("remove")
                    .then(Commands.argument("name", StringArgumentType.string())
                        .executes(NPCCommand::removeNPC)
                    )
                )
                .then(Commands.literal("info")
                    .then(Commands.argument("name", StringArgumentType.string())
                        .executes(NPCCommand::getNPCInfo)
                    )
                )
            )
        );
    }
    
    private static int spawnNPC(CommandContext ctx) {
        try {
            CommandSourceStack source = ctx.getSource();
            ServerPlayer player = source.getPlayerOrException();
            ServerLevel world = source.getLevel();
            String name = StringArgumentType.getString(ctx, "name");
            
            String agentId = "npc_" + name.toLowerCase() + "_" + System.currentTimeMillis();
            
            BlockPos playerPos = player.blockPosition();
            BlockPos spawnPos = playerPos.relative(player.getDirection(), 2);
            
            source.sendSuccess(
                () -> Component.literal("§6[DW] §eSpawning NPC: " + name),
                false
            );
            
            JsonObject personality = new JsonObject();
            personality.addProperty("curiosity", RANDOM.nextDouble() * 2 - 1);
            personality.addProperty("boldness", RANDOM.nextDouble() * 2 - 1);
            personality.addProperty("sociability", RANDOM.nextDouble() * 2 - 1);
            personality.addProperty("agreeableness", RANDOM.nextDouble() * 2 - 1);
            personality.addProperty("conscientiousness", RANDOM.nextDouble() * 2 - 1);
            
            CompletableFuture.runAsync(() -> {
                try {
                    spawnNPCAI(agentId, name, personality, world, spawnPos, player);
                } catch (Exception e) {
                    DWMod.LOGGER.error("Failed to spawn NPC AI: " + e.getMessage());
                }
            });
            
            source.sendSuccess(
                () -> Component.literal("§6[DW] §aAI system initializing for: " + name),
                false
            );
            source.sendSuccess(
                () -> Component.literal("§7Agent ID: " + agentId),
                false
            );
            
            return 1;
            
        } catch (Exception e) {
            DWMod.LOGGER.error("NPC spawn failed", e);
            return 0;
        }
    }
    
    private static void spawnNPCAI(String agentId, String name, JsonObject personality,
                                   ServerLevel world, BlockPos pos, ServerPlayer spawner) 
            throws IOException, InterruptedException {
        
        JsonObject request = new JsonObject();
        request.addProperty("agent_id", agentId);
        request.addProperty("spawn_type", "command");
        request.add("persona_traits", personality);
        request.addProperty("server", "127.0.0.1:25565");
        
        JsonObject metadata = new JsonObject();
        metadata.addProperty("spawned_by", spawner.getName().getString());
        metadata.addProperty("spawn_location", pos.toShortString());
        metadata.addProperty("world", world.dimension().location().toString());
        metadata.addProperty("display_name", name);
        request.add("metadata", metadata);
        
        HttpRequest httpRequest = HttpRequest.newBuilder()
            .uri(URI.create(PYTHON_BACKEND + "/api/agents/spawn"))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(request.toString()))
            .build();
        
        HttpResponse response = HTTP_CLIENT.send(
            httpRequest,
            HttpResponse.BodyHandlers.ofString()
        );
        
        if (response.statusCode() == 200) {
            DWMod.LOGGER.info("✅ NPC AI spawned: " + agentId);
            
            DWNPCWithChat npcEntity = new DWNPCWithChat(
                EntityType.VILLAGER, 
                world
            );
            npcEntity.setPos(pos.getX(), pos.getY(), pos.getZ());
            npcEntity.setCustomName(Component.literal(name));
            
            TaggedEntitySystem.tagEntity(npcEntity, TaggedEntitySystem.TAG_DW_NPC);
            TaggedEntitySystem.setAIID(npcEntity, agentId);
            
            world.addFreshEntity(npcEntity);
            
            DWMod.LOGGER.info("✅ NPC entity created and tagged: " + name);
        } else {
            DWMod.LOGGER.error("❌ Failed to spawn NPC AI: " + response.body());
        }
    }
    
    private static int listNPCs(CommandContext ctx) {
        try {
            CommandSourceStack source = ctx.getSource();
            ServerLevel world = source.getLevel();
            
            List npcs = TaggedEntitySystem.getAllNPCs(world);
            
            source.sendSuccess(
                () -> Component.literal("§6[DW] §eNPCs in world: " + npcs.size()),
                false
            );
            
            for (net.minecraft.world.entity.Entity npc : npcs) {
                String aiId = TaggedEntitySystem.getAIID(npc);
                String displayName = npc.hasCustomName() ? 
                    npc.getCustomName().getString() : 
                    "Unknown";
                
                source.sendSuccess(
                    () -> Component.literal(
                        "§7- " + displayName + " §8(AI: " + aiId + ")"
                    ),
                    false
                );
            }
            
            return npcs.size();
            
        } catch (Exception e) {
            DWMod.LOGGER.error("List NPCs failed", e);
            return 0;
        }
    }
    
    private static int removeNPC(CommandContext ctx) {
        try {
            CommandSourceStack source = ctx.getSource();
            ServerLevel world = source.getLevel();
            String name = StringArgumentType.getString(ctx, "name");
            
            List npcs = TaggedEntitySystem.getAllNPCs(world);
            
            for (net.minecraft.world.entity.Entity npc : npcs) {
                if (npc.hasCustomName() && 
                    npc.getCustomName().getString().equalsIgnoreCase(name)) {
                    
                    String aiId = TaggedEntitySystem.getAIID(npc);
                    
                    npc.remove(net.minecraft.world.entity.Entity.RemovalReason.DISCARDED);
                    
                    CompletableFuture.runAsync(() -> {
                        try {
                            despawnNPCAI(aiId);
                        } catch (Exception e) {
                            DWMod.LOGGER.error("Failed to despawn AI: " + e.getMessage());
                        }
                    });
                    
                    source.sendSuccess(
                        () -> Component.literal("§6[DW] §aRemoved NPC: " + name),
                        false
                    );
                    
                    return 1;
                }
            }
            
            source.sendFailure(
                Component.literal("§6[DW] §cNPC not found: " + name)
            );
            
            return 0;
            
        } catch (Exception e) {
            DWMod.LOGGER.error("Remove NPC failed", e);
            return 0;
        }
    }
    
    private static void despawnNPCAI(String agentId) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create(PYTHON_BACKEND + "/api/agents/" + agentId))
            .DELETE()
            .build();
        
        HttpResponse response = HTTP_CLIENT.send(
            request,
            HttpResponse.BodyHandlers.ofString()
        );
        
        if (response.statusCode() == 200) {
            DWMod.LOGGER.info("✅ NPC AI despawned: " + agentId);
        } else {
            DWMod.LOGGER.error("❌ Failed to despawn NPC AI: " + response.body());
        }
    }
    
    private static int getNPCInfo(CommandContext ctx) {
        try {
            CommandSourceStack source = ctx.getSource();
            ServerLevel world = source.getLevel();
            String name = StringArgumentType.getString(ctx, "name");
            
            List npcs = TaggedEntitySystem.getAllNPCs(world);
            
            for (net.minecraft.world.entity.Entity npc : npcs) {
                if (npc.hasCustomName() && 
                    npc.getCustomName().getString().equalsIgnoreCase(name)) {
                    
                    String aiId = TaggedEntitySystem.getAIID(npc);
                    BlockPos pos = npc.blockPosition();
                    
                    source.sendSuccess(
                        () -> Component.literal("§6[DW] §eNPC Information:"),
                        false
                    );
                    source.sendSuccess(
                        () -> Component.literal("§7Name: " + name),
                        false
                    );
                    source.sendSuccess(
                        () -> Component.literal("§7AI ID: " + aiId),
                        false
                    );
                    source.sendSuccess(
                        () -> Component.literal("§7Position: " + pos.toShortString()),
                        false
                    );
                    source.sendSuccess(
                        () -> Component.literal("§7Type: NPC"),
                        false
                    );
                    
                    return 1;
                }
            }
            
            source.sendFailure(
                Component.literal("§6[DW] §cNPC not found: " + name)
            );
            
            return 0;
            
        } catch (Exception e) {
            DWMod.LOGGER.error("Get NPC info failed", e);
            return 0;
        }
    }
}