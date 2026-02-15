// src/main/java/com/divineworld/commands/CommandRegistrar.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.utils.AgentConfigLoader;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.SubscribeEvent;

/**
 * Command Registrar - Registers all Divine World commands
 * UPDATED with GodCommand and NPCCommand
 * Synced with AgentConfigLoader for agent name validation
 */
public class CommandRegistrar {

    public static void register() {
        MinecraftForge.EVENT_BUS.register(new CommandRegistrar());
        
        // Pre-load agent configuration to ensure agents.json is accessible
        AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
        DWMod.LOGGER.info("[CommandRegistrar] Agent Configuration loaded:");
        DWMod.LOGGER.info("  - Male NPCs: {}", config.getMaleNPCNames().size());
        DWMod.LOGGER.info("  - Female NPCs: {}", config.getFemaleNPCNames().size());
        DWMod.LOGGER.info("  - Gods: {}", config.getGodTypes().size());
        
        DWMod.LOGGER.info("[CommandRegistrar] Registered to event bus");
    }

    @SubscribeEvent
    public void onRegisterCommands(RegisterCommandsEvent event) {
        DWMod.LOGGER.info("[CommandRegistrar] Registering commands...");

        // Register NPC management commands (/dw npc ...)
        NPCCommand.register(event.getDispatcher());
        DWMod.LOGGER.info("[CommandRegistrar] ✅ NPC commands registered");

        // Register God disguise toggle command (/godtoggle)
        GodCommand.register(event.getDispatcher());
        DWMod.LOGGER.info("[CommandRegistrar] ✅ God commands registered");

        DWMod.LOGGER.info("[CommandRegistrar] All commands registered successfully");
    }
}