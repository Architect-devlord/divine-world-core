// src/main/java/com/divineworld/commands/CraftCommand.java
// DivineWorld server mod — Forge 1.20.1
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.events.CraftingWalkManager;
import com.mojang.brigadier.CommandDispatcher;
import com.mojang.brigadier.arguments.StringArgumentType;
import com.mojang.brigadier.context.CommandContext;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.commands.Commands;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.resources.ResourceLocation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.crafting.*;
import net.minecraft.world.level.block.CraftingTableBlock;
import net.minecraftforge.registries.ForgeRegistries;

import java.util.*;

/**
 * /craft minecraft:&lt;item&gt; &lt;agent_name&gt;
 *
 * Teaches early agents the crafting mechanic by guiding them through the
 * full process — the same "control overridden, not consciousness" principle
 * as /breed: movement and inventory are managed here, but the perception
 * pipeline (WebSocket, obs_builder, cognitive_loop) keeps running normally
 * so the agent observes and remembers every step, it can see what's
 * happening to it but can't stop it.
 *
 * VERSION NOTE: this file targets Forge 1.20.1 specifically. RecipeHolder<T>
 * (the ID+Recipe wrapper class in net.minecraft.world.item.crafting) was
 * NOT introduced until 1.20.5 — confirmed against the 1.20.4->1.20.5 mod
 * migration primer. In 1.20.1, RecipeManager.getAllRecipesFor(RecipeType<T>)
 * returns List&lt;T&gt; directly (unwrapped), and Recipe.getId() exists
 * directly on the Recipe itself. Recipe#getResultItem/#assemble take a plain
 * RegistryAccess parameter (not HolderLookup.Provider — that rename is also
 * 1.20.5+). If this project is ever upgraded past 1.20.4, this file's recipe
 * lookups will need the RecipeHolder unwrap added back — check
 * docs.minecraftforge.net's Recipes page for that Minecraft version first.
 *
 * Validation order (strictly sequential — stops at the first failure):
 *
 *   1. The item string resolves to a known Minecraft item.
 *   2. The player name resolves to an online AI agent (NPC or god). If the
 *      name belongs to a real (non-agent) player, that's reported distinctly
 *      from "not found at all".
 *   3. The recipe exists in the vanilla/Forge recipe book for this item.
 *   4. The agent's inventory contains every required ingredient in the
 *      required quantities (each ingredient may appear in multiple recipe
 *      slots — e.g. a crafting table costs 4 planks; counts are totalled
 *      per ingredient group, and any candidate item satisfying that
 *      ingredient group counts toward the total).
 *   5a. If the recipe does NOT require a crafting table (shapeless, or
 *       shaped with width ≤ 2 AND height ≤ 2 — fits the 2×2 grid every
 *       player always carries): craft in-inventory via
 *       CraftingWalkManager.startInventoryCraft().
 *   5b. If the recipe REQUIRES a crafting table (shaped, width or height
 *       > 2 — needs the 3×3 grid): search 20 blocks for one, A*-path to
 *       it, then craft there via CraftingWalkManager.startTableCraft().
 */
public class CraftCommand {

    private static final double SEARCH_RADIUS = 20.0;

    public static void register(CommandDispatcher<CommandSourceStack> dispatcher) {
        dispatcher.register(Commands.literal("craft")
                .requires(src -> src.hasPermission(2))
                .then(Commands.argument("item", StringArgumentType.string())
                        .then(Commands.argument("agent", StringArgumentType.string())
                                .executes(CraftCommand::executeCraft)
                        )
                )
        );
        DWMod.LOGGER.info("[CraftCommand] Registered /craft <item> <agent>");
    }

    private static int executeCraft(CommandContext<CommandSourceStack> ctx) {
        CommandSourceStack source = ctx.getSource();
        String rawItem   = StringArgumentType.getString(ctx, "item");
        String agentName = StringArgumentType.getString(ctx, "agent");

        try {
            ServerLevel level = source.getLevel();

            // ── Step 1: resolve item string ──────────────────────────────
            // Accept both "minecraft:stone" and plain "stone"
            String itemKey = rawItem.contains(":") ? rawItem : "minecraft:" + rawItem;
            ResourceLocation itemRL = ResourceLocation.tryParse(itemKey);
            if (itemRL == null || !ForgeRegistries.ITEMS.containsKey(itemRL)) {
                source.sendFailure(Component.literal(
                        "§cUnknown item: " + rawItem
                        + " — use Minecraft's registry name, e.g. minecraft:crafting_table"));
                return 0;
            }
            Item targetItem = ForgeRegistries.ITEMS.getValue(itemRL);

            // ── Step 2: resolve agent name ───────────────────────────────
            ServerPlayer agent = findAgentByName(level, agentName);
            if (agent == null) {
                ServerPlayer anyPlayer = level.getServer().getPlayerList().getPlayerByName(agentName);
                if (anyPlayer != null) {
                    source.sendFailure(Component.literal(
                            "§c" + agentName + " is not an AI agent."));
                } else {
                    source.sendFailure(Component.literal(
                            "§cAgent not found or not online: " + agentName));
                }
                return 0;
            }

            if (CraftingWalkManager.isCraftActive(agent)) {
                source.sendFailure(Component.literal(
                        "§e" + agentName + " is already in the middle of a crafting sequence."));
                return 0;
            }

            // ── Step 3: find the recipe ──────────────────────────────────
            // getAllRecipesFor returns List<CraftingRecipe> directly in 1.20.1
            // (no RecipeHolder wrapper — see class doc's VERSION NOTE).
            List<CraftingRecipe> matches =
                    level.getServer().getRecipeManager()
                         .getAllRecipesFor(RecipeType.CRAFTING)
                         .stream()
                         .filter(r -> ItemStack.isSameItem(
                                 r.getResultItem(level.registryAccess()),
                                 new ItemStack(targetItem)))
                         .toList();

            if (matches.isEmpty()) {
                source.sendFailure(Component.literal(
                        "§cNo crafting recipe found for " + rawItem + "."));
                return 0;
            }

            CraftingRecipe recipe = matches.get(0);
            ItemStack result = recipe.getResultItem(level.registryAccess());

            // ── Step 4: ingredient availability check ────────────────────
            IngredientMap required = buildIngredientMap(recipe);
            IngredientCheck check   = checkInventory(agent, required);

            if (!check.satisfied()) {
                source.sendFailure(Component.literal(
                        "§e" + agentName + " doesn't carry the required materials: "
                        + check.missing()));
                return 0;
            }

            // ── Step 5: requires crafting table? ─────────────────────────
            boolean needsTable = requiresCraftingTable(recipe);

            if (!needsTable) {
                boolean started = CraftingWalkManager.startInventoryCraft(
                        agent, recipe, result.copy(), required.slotAssignments);
                if (!started) {
                    source.sendFailure(Component.literal(
                            "§cFailed to begin inventory crafting for " + agentName + "."));
                    return 0;
                }
                source.sendSuccess(() -> Component.literal(
                        "§a" + agentName + " is crafting §e" + rawItem + " §ain their inventory."), true);
                return 1;
            }

            BlockPos table = findCraftingTable(level, agent.blockPosition(), SEARCH_RADIUS);
            if (table == null) {
                source.sendSuccess(() -> Component.literal(
                        "§eNo crafting table found within " + (int) SEARCH_RADIUS
                        + " blocks of " + agentName + "."), false);
                return 0;
            }

            boolean started = CraftingWalkManager.startTableCraft(
                    agent, table, recipe, result.copy(), required.slotAssignments);
            if (!started) {
                source.sendFailure(Component.literal(
                        "§cFound a crafting table but " + agentName
                        + " could not find a walkable path to it."));
                return 0;
            }

            source.sendSuccess(() -> Component.literal(
                    "§a" + agentName + " is heading to a crafting table to craft §e" + rawItem + "§a."), true);
            return 1;

        } catch (Exception e) {
            DWMod.LOGGER.error("[CraftCommand] /craft failed", e);
            source.sendFailure(Component.literal("§c[Craft] " + e.getMessage()));
            return 0;
        }
    }

    // =========================================================================
    // Recipe analysis helpers
    // =========================================================================

    /**
     * Determine whether a recipe needs a 3×3 crafting table grid.
     *
     * ShapelessRecipe: no fixed grid; every vanilla shapeless recipe has
     * ≤ 4 ingredients, so all of them fit the 2×2 inventory grid.
     *
     * ShapedRecipe: fits in 2×2 if width ≤ 2 AND height ≤ 2. A 1×3, 3×1,
     * or 3×3 recipe (e.g. a pickaxe, a chest) must go to a crafting table.
     */
    static boolean requiresCraftingTable(CraftingRecipe recipe) {
        if (recipe instanceof ShapedRecipe shaped) {
            return shaped.getWidth() > 2 || shaped.getHeight() > 2;
        }
        return false;   // ShapelessRecipe and other CraftingRecipe subtypes fit 2×2
    }

    /**
     * Build per-ingredient count requirements from a recipe.
     * Multiple slots requiring the same item type (e.g. 4 planks for a
     * crafting table) are collapsed into one total-count-per-item entry.
     */
    static IngredientMap buildIngredientMap(CraftingRecipe recipe) {
        IngredientMap out = new IngredientMap();
        List<Ingredient> ings = recipe.getIngredients();
        for (int slot = 0; slot < ings.size(); slot++) {
            Ingredient ing = ings.get(slot);
            if (ing.isEmpty()) continue;

            ItemStack[] candidates = ing.getItems();
            if (candidates.length == 0) continue;

            out.slotAssignments.put(slot, candidates);
            String key = getItemKey(candidates[0]);
            out.requiredCounts.merge(key, 1, Integer::sum);
            out.canonicalItems.put(key, candidates);
        }
        return out;
    }

    static String getItemKey(ItemStack stack) {
        ResourceLocation rl = ForgeRegistries.ITEMS.getKey(stack.getItem());
        return rl != null ? rl.toString() : "minecraft:air";
    }

    static final class IngredientMap {
        /** canonical item key → total count needed */
        final Map<String, Integer>      requiredCounts  = new LinkedHashMap<>();
        /** recipe slot index → ItemStack[] candidates for that slot */
        final Map<Integer, ItemStack[]> slotAssignments = new LinkedHashMap<>();
        /** canonical item key → all ItemStack candidates for this ingredient group */
        final Map<String, ItemStack[]>  canonicalItems  = new LinkedHashMap<>();
    }

    /**
     * Check whether the agent has every required ingredient in sufficient
     * quantities. Each ingredient group may be satisfied by ANY of its
     * candidate items (e.g. any plank colour for a crafting table).
     */
    static IngredientCheck checkInventory(ServerPlayer agent, IngredientMap required) {
        Map<String, Integer> available = new HashMap<>();
        for (ItemStack stack : agent.getInventory().items) {
            if (stack.isEmpty()) continue;
            available.merge(getItemKey(stack), stack.getCount(), Integer::sum);
        }

        List<String> missing = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : required.requiredCounts.entrySet()) {
            String canonKey = entry.getKey();
            int    needed   = entry.getValue();
            ItemStack[] candidates = required.canonicalItems.get(canonKey);

            int have = 0;
            for (ItemStack candidate : candidates) {
                have += available.getOrDefault(getItemKey(candidate), 0);
            }

            if (have < needed) {
                String shortName = canonKey.replace("minecraft:", "");
                missing.add(shortName + " ×" + needed + " (has " + have + ")");
            }
        }

        return new IngredientCheck(missing.isEmpty(),
                missing.isEmpty() ? "" : String.join(", ", missing));
    }

    record IngredientCheck(boolean satisfied, String missing) {}

    // =========================================================================
    // Crafting table search — mirrors BreedCommand's adjacent-bed-pair finder
    // =========================================================================

    private static BlockPos findCraftingTable(ServerLevel level, BlockPos anchor, double radius) {
        int rH = (int) Math.ceil(radius);
        int rV = 8;
        double rSq = radius * radius;

        BlockPos closest    = null;
        double   bestDistSq = Double.MAX_VALUE;

        for (int dx = -rH; dx <= rH; dx++) {
            for (int dz = -rH; dz <= rH; dz++) {
                if (dx * dx + dz * dz > rSq) continue;
                for (int dy = -rV; dy <= rV; dy++) {
                    BlockPos pos = anchor.offset(dx, dy, dz);
                    if (!(level.getBlockState(pos).getBlock() instanceof CraftingTableBlock)) continue;
                    double distSq = dx * dx + dy * dy + dz * dz;
                    if (distSq < bestDistSq) {
                        bestDistSq = distSq;
                        closest = pos;
                    }
                }
            }
        }
        return closest;
    }

    // =========================================================================
    // Agent lookup
    // =========================================================================

    private static ServerPlayer findAgentByName(ServerLevel level, String name) {
        for (ServerPlayer p : level.getServer().getPlayerList().getPlayers()) {
            if (!p.getName().getString().equalsIgnoreCase(name)) continue;
            if (DWNPCManager.isAIPlayer(p) || DWNPCManager.isGodPlayer(p)) return p;
        }
        return null;
    }
}