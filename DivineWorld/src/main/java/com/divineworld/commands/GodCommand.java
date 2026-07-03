// src/main/java/com/divineworld/commands/GodCommand.java
// DivineWorld server mod
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
 * God Commands — form cycle and disguise toggle for god entities.
 *
 * COMMAND SYNTAX (single dispatcher.register call):
 *
 *   /godtoggle
 *     Cycle the caller's OWN form one step around the ring:
 *       god form  →  humanoid form  →  disguise (Steve/Alex)  →  god form  →  …
 *     Only god agents may use the no-arg form.
 *
 *   /godtoggle <god_name>
 *     Admin cycles a SPECIFIC god agent's form one step (same ring as above).
 *     Requires permission level 2.  <god_name> is the in-game name of the god
 *     puppet player (autocomplete suggests online god agents).
 *
 *   /godtoggle <agent_id> <mob>
 *     Admin transforms a specific god agent into the given mob type, or
 *     "revert"/"original" to restore their original form.
 *     Unchanged from the previous version — still calls GodDisguiseHandler.
 *
 * FORMS (managed by GodDisguiseHandler.cycleGodForm / applyGodForm):
 *   god      — real vanilla boss body visible, player puppet invisible
 *   humanoid — player puppet visible, rendered via GodHumanoidGeoRenderer
 *              using god_<type>.geo.json / .png / .animation.json
 *   disguise — player puppet visible, rendered as Steve or Alex at 1.0×
 *              no boss body, indistinguishable from a vanilla player
 *
 * Creaking note: in "god" form, the Creaking uses ai_creaking.* assets via
 * CreakingGeoRenderer.  In "humanoid" form it uses god_creaking.* like
 * every other god type.  The ai_creaking / god_creaking asset split is
 * handled transparently by GodHumanoidGeoModel.getModelResource() which
 * always asks for "god_" + godType regardless of which god type it is.
 */
public class GodCommand {

    // =========================================================================
    // Mob suggestion list (for the 2-arg <agent_id> <mob> form)
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

    private static boolean isRevertValue(String mob) {
        return "revert".equalsIgnoreCase(mob) || "original".equalsIgnoreCase(mob);
    }

    // =========================================================================
    // Registration
    // =========================================================================

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {

        dispatcher.register(Commands.literal("godtoggle")
                .requires(src -> src.hasPermission(2))

                // /godtoggle  — cycle OWN form (god only)
                .executes(GodCommand::cycleSelfForm)

                // /godtoggle <name_or_mob>  — one argument:
                //   • if the string matches an online god agent name → cycle THAT god's form
                //   • otherwise → kept for backward compatibility as "transform self into mob"
                //     (this use-case is rare and usually scripted via /god_transform; left
                //     as a convenience but the primary single-arg use is now the agent name)
                .then(Commands.argument("name_or_mob", StringArgumentType.string())
                        .suggests((ctx, builder) -> {
                            // Suggest god names first, then mob types
                            for (String g : AgentConfigLoader.getGodTypes()) builder.suggest(g);
                            builder.suggest("revert");
                            for (String m : COMMON_MOBS) builder.suggest(m);
                            return builder.buildFuture();
                        })
                        .executes(GodCommand::cycleTargetOrTransformSelf)

                        // /godtoggle <agent_id> <mob>  — 2-arg: admin targets a specific god
                        // for a mob-specific transform (unchanged behaviour)
                        .then(Commands.argument("target_mob", StringArgumentType.string())
                                .suggests((ctx, builder) -> {
                                    builder.suggest("revert");
                                    for (String g : AgentConfigLoader.getGodTypes()) builder.suggest(g);
                                    for (String m : COMMON_MOBS) builder.suggest(m);
                                    return builder.buildFuture();
                                })
                                .executes(GodCommand::transformTarget)
                        )
                )
        );

        DWMod.LOGGER.info("[GodCommand] Registered /godtoggle  "
                + "(no-arg: cycle own form | <god_name>: cycle target | <agent_id> <mob>: mob transform)");
    }

    // =========================================================================
    // /godtoggle  — cycle caller's own form one step
    // =========================================================================

    private static int cycleSelfForm(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer player = ctx.getSource().getPlayerOrException();

            if (!DWNPCManager.isGodPlayer(player)) {
                player.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only god agents may cycle forms with this command."));
                return 0;
            }

            String before = GodDisguiseHandler.getGodForm(player);
            GodDisguiseHandler.cycleGodForm(player);
            String after  = GodDisguiseHandler.getGodForm(player);
            DWMod.LOGGER.info("[godtoggle] {} cycled form: {} → {}",
                    DWNPCManager.getAgentId(player), before, after);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] cycle-self failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // /godtoggle <name_or_mob>  — disambiguates: cycle a named god OR mob-transform self
    // =========================================================================

    private static int cycleTargetOrTransformSelf(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor = ctx.getSource().getPlayerOrException();
            String arg = StringArgumentType.getString(ctx, "name_or_mob");

            // Try to find a god agent with this name first
            ServerPlayer targetGod = findGodByName(ctx.getSource().getLevel(), arg);
            if (targetGod != null) {
                // Single arg is a god name → cycle that god's form
                String before = GodDisguiseHandler.getGodForm(targetGod);
                GodDisguiseHandler.cycleGodForm(targetGod);
                String after  = GodDisguiseHandler.getGodForm(targetGod);
                executor.sendSystemMessage(Component.literal(
                        "§d[God Toggle] " + arg + ": form " + before + " → " + after));
                DWMod.LOGGER.info("[godtoggle] {} cycled {}: {} → {}",
                        executor.getName().getString(), arg, before, after);
                return 1;
            }

            // Not a god name — treat as mob type for self-transform (backward compat)
            if (!DWNPCManager.isGodPlayer(executor) && !ctx.getSource().hasPermission(4)) {
                executor.sendSystemMessage(Component.literal(
                        "§c[God Toggle] Only gods or operators (level 4) may transform."));
                return 0;
            }

            if (isRevertValue(arg)) {
                GodDisguiseHandler.removeTransform(executor);
                return 1;
            }

            boolean ok = GodDisguiseHandler.applyTransform(executor, arg, ctx.getSource().getLevel());
            if (ok) executor.getPersistentData().putString("dw_last_disguise", arg.toLowerCase());
            return ok ? 1 : 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] cycle-target-or-transform failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // /godtoggle <agent_id> <mob>  — 2-arg admin mob-transform (unchanged)
    // =========================================================================

    private static int transformTarget(CommandContext<CommandSourceStack> ctx) {
        try {
            ServerPlayer executor = ctx.getSource().getPlayerOrException();
            String agentId  = StringArgumentType.getString(ctx, "name_or_mob");
            String mob      = StringArgumentType.getString(ctx, "target_mob");

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
                return 1;
            }

            boolean ok = GodDisguiseHandler.applyTransform(
                    targetGod, mob, targetGod.serverLevel());
            if (ok) {
                targetGod.getPersistentData().putString("dw_last_disguise", mob.toLowerCase());
                executor.sendSystemMessage(Component.literal(
                        "§a[God Toggle] " + agentId + " → §b" + mob));
            }
            return ok ? 1 : 0;

        } catch (Exception e) {
            DWMod.LOGGER.error("[godtoggle] 2-arg transform failed", e);
            ctx.getSource().sendFailure(Component.literal("§c[God Toggle] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // Helper — find an online god agent by display name
    // =========================================================================

    private static ServerPlayer findGodByName(ServerLevel level, String name) {
        for (ServerPlayer p : level.getServer().getPlayerList().getPlayers()) {
            if (DWNPCManager.isGodPlayer(p) &&
                    p.getName().getString().equalsIgnoreCase(name)) {
                return p;
            }
        }
        return null;
    }
}