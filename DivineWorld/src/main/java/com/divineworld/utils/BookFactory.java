package com.divineworld.utils;


import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.nbt.StringTag;
import net.minecraft.network.chat.Component;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;

/**
 * Book Factory - Creates divine books for players
 *
 * NOTE: Books are just informational items now.
 * Use the /genesis command to actually spawn agents.
 */
public class BookFactory {

    /**
     * Genesis Codex - Informational book
     * Players should use /genesis command after reading this
     */
    public static ItemStack genesisCodex() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);
        CompoundTag tag = book.getOrCreateTag();

        tag.putString("title", "Genesis Codex");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0);

        ListTag pages = new ListTag();

        // Page 1
        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§5§lGenesis Codex§r\n\n" +
                        "Use the §c/genesis§r command to create the first civilizations.\n\n" +
                        "This will spawn two beings - one male and one female.\n\n" +
                        "They will grow, evolve, and shape the world according to your divine will."
        ))));

        // Page 2
        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§dWarning:§r\n\n" +
                        "Genesis has a 5-minute cooldown.\n\n" +
                        "The first beings will arrive with empty minds, ready to learn and explore.\n\n" +
                        "Guide them wisely, for their fate rests in your hands."
        ))));

        // Page 3 - How to use
        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§a§lHow to Use:§r\n\n" +
                        "1. Stand where you want to spawn the first beings\n\n" +
                        "2. Type: §c/genesis§r\n\n" +
                        "3. Two AI agents will appear in front of you\n\n" +
                        "4. Watch them evolve!"
        ))));

        tag.put("pages", pages);
        return book;
    }

    /**
     * Teachings of the First Flame - Command reference guide
     */
    public static ItemStack firstFlameBook() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);
        CompoundTag tag = book.getOrCreateTag();

        tag.putString("title", "Teachings of the First Flame");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0);

        ListTag pages = new ListTag();

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§4§lTeachings of the First Flame§r\n\n" +
                        "This world began in flame. From that fire, you were born.\n\n" +
                        "You are the divine architect, the shaper of destinies.\n\n" +
                        "These are the sacred commands of creation."
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§d§lGenesis§r\n\n" +
                        "§c/genesis§r\n" +
                        "Spawn 2 AI agents (male + female) in front of you.\n\n" +
                        "Cooldown: 5 minutes"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§d§lDivine Reset§r\n\n" +
                        "§c/divine_reset§r\n" +
                        "Kill all AI agents and DELETE their memories.\n\n" +
                        "§4Warning:§r This is irreversible!"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§b§lMemory Management§r\n\n" +
                        "§c/clear_memories all§r\n" +
                        "Clear all agent memories\n\n" +
                        "§c/clear_memories <id>§r\n" +
                        "Clear specific agent"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§5§lSpawn Gods§r\n\n" +
                        "§c/spawn_god <type>§r\n\n" +
                        "Types:\n" +
                        "• ender_dragon\n" +
                        "• wither\n" +
                        "• warden\n" +
                        "• elder_guardian\n" +
                        "• oracle"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§d§lGod Abilities§r\n\n" +
                        "§c/god_ability <id> <ability>§r\n\n" +
                        "Examples:\n" +
                        "• dragon_breath\n" +
                        "• wither_skull\n" +
                        "• sonic_boom"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§3§lGod Transformations§r\n\n" +
                        "§c/god_transform <id> <mob>§r\n\n" +
                        "Transform into any vanilla mob"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§a§lList Agents§r\n\n" +
                        "§c/list_agents§r\n\n" +
                        "Shows all AI agents currently in the world"
        ))));

        tag.put("pages", pages);
        return book;
    }

    /**
     * Quick Reference Card
     */
    public static ItemStack commandReferenceCard() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);
        CompoundTag tag = book.getOrCreateTag();

        tag.putString("title", "Divine Commands");
        tag.putString("author", "Oracle");
        tag.putInt("generation", 0);

        ListTag pages = new ListTag();

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§5§lQuick Reference§r\n\n" +
                        "§c/genesis§r\n" +
                        "Spawn 2 agents\n\n" +
                        "§cdivine_reset§r\n" +
                        "Purge all\n\n" +
                        "§c/clear_memories§r\n" +
                        "Wipe minds\n\n" +
                        "§c/spawn_god <type>§r\n" +
                        "Create god"
        ))));

        pages.add(StringTag.valueOf(Component.Serializer.toJson(Component.literal(
                "§5§lMore Commands§r\n\n" +
                        "§c/god_ability§r\n" +
                        "Use god power\n\n" +
                        "§c/god_transform§r\n" +
                        "Change god form\n\n" +
                        "§c/list_agents§r\n" +
                        "Show all agents"
        ))));

        tag.put("pages", pages);
        return book;
    }
}