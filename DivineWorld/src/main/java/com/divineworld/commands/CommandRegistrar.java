// src/main/java/com/divineworld/commands/CommandRegistrar.java
// DivineWorld server mod
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.oracle.LLMOracleBrain;
import com.divineworld.oracle.OracleSystem;
import com.divineworld.utils.AgentConfigLoader;
import net.minecraftforge.event.RegisterCommandsEvent;

/**
 * Command Registrar — single entry point for every Divine World command.
 *
 * FIX (consolidation): this class previously only registered NPCCommand and
 * GodCommand, and — separately — was never actually called from anywhere;
 * DWMod.onRegisterCommands() called DivineCommands, NPCCommand, GodCommand,
 * and OracleCommandRegistrar directly, one by one, making this class fully
 * dead code despite being imported. All five command groups (Divine, God,
 * NPC, Oracle, Breed) are now registered from this single place, and
 * DWMod.onRegisterCommands() calls only CommandRegistrar.register(...).
 *
 * Adding a new command group going forward only requires one new line here
 * — DWMod.java itself never needs to change again for that purpose.
 *
 * OracleCommandRegistrar needs live OracleSystem/LLMOracleBrain instances
 * (constructed in DWMod's initializeOracle(), not available until then) —
 * passed straight through rather than this class reaching into DWMod's
 * private state itself.
 */
public class CommandRegistrar {

    /**
     * Register every command group. Call once from
     * DWMod.onRegisterCommands(), passing that event's dispatcher and the
     * already-initialised Oracle instances.
     */
    public static void register(RegisterCommandsEvent event,
                                  OracleSystem oracleSystem,
                                  LLMOracleBrain oracleBrain) {
        var dispatcher = event.getDispatcher();

        DWMod.LOGGER.info("[CommandRegistrar] Registering all commands...");

        // Pre-load agent configuration so agents.json is confirmed
        // accessible before any command tries to read it.
        AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
        DWMod.LOGGER.info("[CommandRegistrar] Agent configuration loaded: "
                + "{} male NPCs, {} female NPCs, {} god types",
                config.getMaleNPCNames().size(),
                config.getFemaleNPCNames().size(),
                config.getGodTypes().size());

        // /genesis, /divine_reset, /clear_memories, /spawn_god, /god_ability,
        // /god_transform, /list_agents
        DivineCommands.register(dispatcher);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ Divine commands registered");

        // /dw npc spawn|list|remove|info
        NPCCommand.register(dispatcher);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ NPC commands registered");

        // /godtoggle (no-arg: cycle own form | <god_name>: cycle target |
        //             <agent_id> <mob>: mob transform)
        GodCommand.register(dispatcher);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ God commands registered");

        // /oracle spawn|despawn|teach|stop_teach|set_model|...
        OracleCommandRegistrar.registerCommands(dispatcher, oracleSystem, oracleBrain);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ Oracle commands registered");

        // /breed <agent_a> <agent_b>
        BreedCommand.register(dispatcher);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ Breed command registered");

        // /craft minecraft:<item> <agent>
        CraftCommand.register(dispatcher);
        DWMod.LOGGER.info("[CommandRegistrar] ✅ Craft command registered");

        DWMod.LOGGER.info("[CommandRegistrar] All commands registered successfully");
    }
}