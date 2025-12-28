// src/main/java/com/divineworld/commands/CommandRegistrar.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import net.minecraftforge.event.RegisterCommandsEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.eventbus.api.SubscribeEvent;

/**
 * Command Registrar - Registers all Divine World commands
 * UPDATED with GodCommand and NPCCommand
 */
public class CommandRegistrar {

    public static void register() {
        MinecraftForge.EVENT_BUS.register(new CommandRegistrar());
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