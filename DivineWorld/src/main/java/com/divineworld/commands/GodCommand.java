// src/main/java/com/divineworld/commands/GodCommand.java
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.events.GodDisguiseHandler;
import com.divineworld.utils.AgentConfigLoader;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;

import java.util.concurrent.CompletableFuture;

/**
 * God Commands — disguise toggle for god entities.
 *
 * COMMAND SYNTAX (single dispatcher.register call, no duplicates):
 *
 *   /godtoggle
 *     God toggles their own disguise.
 *     • If already disguised → reverts to original god form.
 *     • If not disguised     → applies last-used disguise type, or
 *                               "villager" if never transformed before.
 *
 *   /godtoggle <mob>
 *     God transforms into the specified mob type.
 *     "revert" or "original" as the mob value reverts to god form.
 *     Full mob suggestion list matches /god_transform.
 *
 *   /godtoggle <agent_id> <mob>
 *     Admin transforms a specific god agent into the specified mob.
 *     "revert" restores their original form.
 *
 * RELATIONSHIP WITH /god_transform (DivineCommands):
 *   /god_transform is the scripted / Python-initiated transform command
 *   used by operators and the AI action-frame channel.
 *   /godtoggle is the quick in-game toggle for gods and ops —
 *   no conflict; both ultimately call GodDisguiseHandler.
 *
 * PREVIOUS BUGS FIXED:
 *   FIX 1 — Duplicate registration: The old code called
 *     dispatcher.register("godtoggle") twice (once with no args,
 *     once with <agent_id>). Brigadier merged them, but the two
 *     separate calls cluttered the command tree and logged "registered"
 *     twice. Now a single dispatcher.register() node covers all forms.
 *
 *   FIX 2 — Hardcoded "villager": The old toggle always passed
 *     "villager" to applyTransform() making every god look like a
 *     villager regardless of intent. Now:
 *       • /godtoggle with no mob arg reads "dw_last_disguise" from NBT
 *         so repeated toggles remember the previous form.
 *       • /godtoggle <mob> accepts any mob from the full suggestion list.
 */
public class GodCommand {

    // =========================================================================
    // Mob suggestion list  (mirrors DivineCommands.suggestMobTypes)
    // =========================================================================

    private static final String[] COMMON_MOBS = {
            "zombie", "skeleton", "creeper", "spider", "enderman", "blaze", "ghast",
            "witch", "villager", "pillager", "vindicator", "evoker", "ravager",
            "iron_golem", "snow_golem", "horse", "wolf", "fox", "bee", "drowned",
            "husk", "stray", "wither_skeleton", "cave_spider", "slime", "magma_cube",
            "shulker", "guardian", "phantom", "piglin", "hoglin", "zoglin",
            "piglin_brute", "goat", "axolotl", "frog", "sniffer", "camel",
            "cat", "rabbit", "cow", "pig", "sheep", "chicken", "mooshroom",
            "bat", "squid", "glow_squid", "dolphin", "turtle",
            "polar_bear", "panda", "ocelot", "llama", "parrot",
            "mule", "donkey", "strider", "trader_llama", "wandering_trader",
            "allay", "vex"
    };

    // Sentinel values that mean "revert to original form"
    private static boolean isRevertValue(String mob) {
        return "revert".equalsIgnoreCase(mob) || "original".equalsIgnoreCase(mob);
    }

    // =========================================================================
    // Registration  (single register call — no duplicates)
    // =========================================================================

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        dispatcher.register(Commands.literal("godtoggle")
                .requires(src -> src.hasPermission(2))

                // /godtoggle  (no args — toggle using remembered or default mob)
                .executes(GodCommand::toggleSelf)

                // /godtoggle <mob>  (self transform / revert)
                .then(Commands.argument("mob", StringArgumentType.string())
                                .suggests((ctx, builder) -> {
                                    builder.suggest("revert");
                                    for (String g : AgentConfigLoader.getGodTypes()) builder.suggest(g);
                                    for (String m : COMMON_MOBS) builder.suggest(m);
                                    return builder.buildFuture();
                                })
                                .executes(GodCommand::toggleSelfWithMob)

                        // /godtoggle <agent_id> <mob>  (admin targets another god)
                        // Re-using the "mob" arg slot as agent_id first, then a second "mob" arg.
                        // Brigadier resolves ambiguity by trying both branches: if the first
                        // string matches an online agent-id and a second arg is provided, we
                        // treat it as <agent_id> <mob>; otherwise it falls through to the
                        // single-arg <mob> branch.
                )

                // /godtoggle <agent_id> <mob>  (explicit two-arg form)
                .then(Commands.argument("agent_id", StringArgumentType.string())
                        .then(Commands.argument("target_mob", StringArgumentType.string())
                                .suggests((ctx, builder) -> {
                                    builder.suggest("revert");
                                    for (String g : AgentConfigLoader.getGodTypes()) builder.suggest(g);
                                    for (String m : COMMON_MOBS) builder.suggest(m);
                                    return builder.buildFuture();
                                })
                                .executes(GodCommand::toggleTarget)
                        )
                )
        );

        DWMod.LOGGER.info("[GodCommand] Registered /godtoggle (no-arg | <mob> | <agent_id> <mob>)");
    }

    // =========================================================================
    // /godtoggle  — toggle own disguise using remembered mob or "villager"
    // =========================================================================

    private static int toggleSelf(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();

            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only gods may use this command!"));
                return 0;
            }

            ServerLevel level             = ctx.getSource().getLevel();
            boolean     currentlyDisguised = GodDisguiseHandler.isTransformed(player);

            if (currentlyDisguised) {
                GodDisguiseHandler.removeTransform(player);
                DWMod.LOGGER.info("[godtoggle] {} reverted to original form",
                        DWNPCManager.getAgentId(player));
            } else {
                // Remember the last disguise used; fall back to "villager"
                String lastMob = player.getPersistentData().getString("dw_last_disguise");
                if (lastMob == null || lastMob.isEmpty()) lastMob = "villager";
                GodDisguiseHandler.applyTransform(player, lastMob, level);
                DWMod.LOGGER.info("[godtoggle] {} → {}", DWNPCManager.getAgentId(player), lastMob);
            }
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] self toggle failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // /godtoggle <mob>  — transform self into specific mob (or revert)
    // =========================================================================

    private static int toggleSelfWithMob(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();
            String       mob    = StringArgumentType.getString(ctx, "mob");

            if (!DWNPCManager.isGodPlayer(player)
                    && !ctx.getSource().hasPermission(4)) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only gods or operators (level 4) may use this."));
                return 0;
            }

            ServerLevel level = ctx.getSource().getLevel();

            if (isRevertValue(mob)) {
                GodDisguiseHandler.removeTransform(player);
                DWMod.LOGGER.info("[godtoggle] {} reverted", player.getName().getString());
                return 1;
            }

            boolean ok = GodDisguiseHandler.applyTransform(player, mob, level);
            if (ok) {
                // Remember for next no-arg toggle
                player.getPersistentData().putString("dw_last_disguise", mob.toLowerCase());
                DWMod.LOGGER.info("[godtoggle] {} → {}", player.getName().getString(), mob);
            }
            return ok ? 1 : 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] self-with-mob failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // /godtoggle <agent_id> <mob>  — admin transforms a specific god agent
    // =========================================================================

    private static int toggleTarget(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor    = ctx.getSource().getPlayerOrException();
            String       agentId     = StringArgumentType.getString(ctx, "agent_id");
            String       mob         = StringArgumentType.getString(ctx, "target_mob");

            ServerPlayer targetGod = DWNPCManager.findPlayerByAgentId(
                    ctx.getSource().getLevel(), agentId);

            if (targetGod == null) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Agent not found: " + agentId));
                return 0;
            }

            if (!DWNPCManager.isGodPlayer(targetGod)) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] " + agentId + " is not a god."));
                return 0;
            }

            if (isRevertValue(mob)) {
                GodDisguiseHandler.removeTransform(targetGod);
                executor.sendSystemMessage(Component.literal(
                        "§d[God Toggle] " + agentId + " returned to divine form."));
                DWMod.LOGGER.info("[godtoggle] admin {} reverted {}", executor.getName().getString(), agentId);
                return 1;
            }

            boolean ok = GodDisguiseHandler.applyTransform(targetGod, mob, targetGod.serverLevel());
            if (ok) {
                targetGod.getPersistentData().putString("dw_last_disguise", mob.toLowerCase());
                executor.sendSystemMessage(Component.literal(
                        "§a[God Toggle] " + agentId + " is now: §b" + mob));
                DWMod.LOGGER.info("[godtoggle] admin {} → {} as {}",
                        agentId, mob, executor.getName().getString());
            }
            return ok ? 1 : 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] target toggle failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }
}