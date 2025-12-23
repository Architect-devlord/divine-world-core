// src/main/java/com/divineworld/utils/BookFactory.java
package com.divineworld.utils;

import com.divineworld.DWMod;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Book Factory - Creates divine books for players
 * FIXED for 1.20.1 - Uses NBT instead of DataComponents
 */
public class BookFactory {

    /**
     * Genesis Codex - Right-click to spawn 2 AI agents
     */
    public static ItemStack genesisCodex() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);

        CompoundTag tag = book.getOrCreateTag();

        // Book metadata
        tag.putString("title", "Genesis Codex");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0); // Original
        tag.putBoolean("resolved", true);
        // Pages
        ListTag pages = new ListTag();

        // Page 1
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§5§lGenesis Codex§r\n\n")
                                .append(Component.literal("Use this book to create the first civilizations.\n\n"))
                                .append(Component.literal("Right-click on the ground to spawn the first tribe - one male and one female being.\n\n"))
                                .append(Component.literal("They will grow, evolve, and shape the world."))
                )
        ));

        // Page 2
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§6Warning:§r\n\n")
                                .append(Component.literal("Genesis has a 5-minute cooldown.\n\n"))
                                .append(Component.literal("The first beings will arrive with empty minds.\n\n"))
                                .append(Component.literal("Guide them wisely."))
                )
        ));

        tag.put("pages", pages);

        return book;
    }

    /**
     * Teachings of the First Flame - Command reference guide
     */
    public static ItemStack firstFlameBook() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);

        CompoundTag tag = book.getOrCreateTag();

        // Book metadata
        tag.putString("title", "Teachings of the First Flame");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0);

        // Pages
        ListTag pages = new ListTag();

        // Page 1 - Introduction
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§4§lTeachings of the First Flame§r\n\n")
                                .append(Component.literal("This world began in flame. From that fire, you were born.\n\n"))
                                .append(Component.literal("You are the divine architect, the shaper of destinies.\n\n"))
                                .append(Component.literal("These are the sacred commands of creation."))
                        )
                ));

        // Page 2 - Genesis Commands
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§6§lGenesis§r\n\n")
                                .append(Component.literal("§e/genesis§r\n"))
                                .append(Component.literal("Spawn 2 AI agents (male + female) in front of you.\n\n"))
                                .append(Component.literal("Use this to create the first beings or repopulate after divine reset.\n\n"))
                                .append(Component.literal("Cooldown: 5 minutes"))
                        )
                ));

        // Page 3 - Divine Reset
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§c§lDivine Reset§r\n\n")
                                .append(Component.literal("§e/divine_reset§r\n"))
                                .append(Component.literal("Kill all AI agents and DELETE their memories.\n\n"))
                                .append(Component.literal("§4Warning:§r This is irreversible! All agents will be purged from existence.\n\n"))
                                .append(Component.literal("Only gods may invoke this."))
                        )
                ));

        // Page 4 - Memory Management
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§b§lMemory Management§r\n\n" )
                                .append(Component.literal("§e/clear_memories all§r\n"))
                                .append(Component.literal("Clear all agent memories\n\n"))
                                .append(Component.literal("§e/clear_memories <id>§r\n"))
                                .append(Component.literal("Clear specific agent\n\n"))
                                .append(Component.literal("§e/clear_memories all @a[name=AI_001]§r\n"))
                                .append(Component.literal("Clear all except AI_001"))
                        )
                ));

        // Page 5 - Spawn Gods
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§5§lSpawn Gods§r\n\n")
                                .append(Component.literal("§e/spawn_god <type>§r\n\n"))
                                .append(Component.literal("Types:\n"))
                                .append(Component.literal("• ender_dragon\n"))
                                .append(Component.literal("• wither\n"))
                                .append(Component.literal("• warden\n"))
                                .append(Component.literal("• elder_guardian\n"))
                                .append(Component.literal("• oracle\n"))
                                .append(Component.literal("• creaking"))
                        )
                ));

        // Page 6 - God Abilities
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§d§lGod Abilities§r\n\n")
                                .append(Component.literal("§e/god_ability <id> <ability>§r\n\n"))
                                .append(Component.literal("Examples:\n"))
                                .append(Component.literal("• dragon_breath\n"))
                                .append(Component.literal("• wither_skull\n"))
                                .append(Component.literal("• sonic_boom\n"))
                                .append(Component.literal("• laser_beam\n"))
                                .append(Component.literal("• wisdom_aura\n"))
                                .append(Component.literal("• healing_wave"))
                        )
                ));

        // Page 7 - God Transformations
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§3§lGod Transformations§r\n\n")
                                .append(Component.literal("§e/god_transform <id> <mob>§r\n\n"))
                                .append(Component.literal("Transform into:\n"))
                                .append(Component.literal("• player\n"))
                                .append(Component.literal("• villager\n"))
                                .append(Component.literal("• pig, cow, sheep\n"))
                                .append(Component.literal("• zombie, skeleton\n"))
                                .append(Component.literal("• Any vanilla mob"))
                        )
                ));

        // Page 8 - List Agents
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§a§lList Agents§r\n\n")
                                .append(Component.literal("§e/list_agents§r\n\n"))
                                .append(Component.literal("Shows all AI agents currently in the world:\n"))
                                .append(Component.literal("• Normal agents\n"))
                                .append(Component.literal("• God agents\n"))
                                .append(Component.literal("• Their IDs\n"))
                                .append(Component.literal("• Their types\n\n"))
                                .append(Component.literal("Useful for management and debugging."))
                        )
                ));

        // Page 9 - Philosophy
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§6§lThe Divine Cycle§r\n\n")
                                .append(Component.literal("The tribes will worship you, fear you, or forget you.\n\n"))
                                .append(Component.literal("Your actions shape their beliefs.\n\n"))
                                .append(Component.literal("When all life ends or genesis is invoked again, the world may be reborn.\n\n"))
                                .append(Component.literal("This is the eternal cycle."))
                        )
                ));

        // Page 10 - Wisdom
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§e§lFinal Wisdom§r\n\n")
                                .append(Component.literal("Power without wisdom is destruction.\n\n"))
                                .append(Component.literal("The divine reset is mercy for some, tragedy for others.\n\n"))
                                .append(Component.literal("Choose your path carefully, for you shape not just worlds, but souls.\n\n"))
                                .append(Component.literal("§7- The Oracle"))
                        )
                ));

        tag.put("pages", pages);

        return book;
    }

    /**
     * Quick Reference Card - Compact command guide
     */
    public static ItemStack commandReferenceCard() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);

        CompoundTag tag = book.getOrCreateTag();

        tag.putString("title", "Divine Commands");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0);

        ListTag pages = new ListTag();

        // Single page with all commands
        pages.add(StringTag.valueOf(
                Component.Serializer.toJson(
                        Component.literal("§6§lQuick Reference§r\n\n")
                                .append(Component.literal("§e/genesis§r - Spawn 2 agents\n"))
                                .append(Component.literal("§e/divine_reset§r - Purge all\n"))
                                .append(Component.literal("§e/clear_memories§r - Wipe minds\n"))
                                .append(Component.literal("§e/spawn_god§r - Create god\n"))
                                .append(Component.literal("§e/god_ability§r - Use power\n"))
                                .append(Component.literal("§e/god_transform§r - Change form\n"))
                                .append(Component.literal("§e/list_agents§r - Show all"))
                        )
                ));

        tag.put("pages", pages);

        return book;
    }

    /**
     * Event handler for Genesis Codex usage
     */
    @Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
    public static class DivineEventHandler {

        @SubscribeEvent
        public static void onBookUse(PlayerInteractEvent.RightClickBlock event) {
            if (GenesisManager.onGenesisUse((ServerPlayer) event.getEntity(), event.getLevel(), event.getHand()) == InteractionResult.SUCCESS) {
                event.setCanceled(true);
            }
        }
    }
}