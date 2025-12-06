package com.divineworld.utils;

import net.minecraft.server.network.Filterable;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.component.WrittenBookContent;
import net.minecraft.network.chat.Component;
import net.minecraft.core.component.DataComponents;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.listener.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;


import java.util.List;

public class BookFactory {

    public static ItemStack genesisCodex() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);

        WrittenBookContent content = new WrittenBookContent(
                Filterable.passThrough("Genesis Codex"), // title
                "Oracle",                                // author
                0,                                       // generation (0 = original)
                List.of(
                        Filterable.passThrough(Component.literal(
                                "Use this book to create the first civilizations. Right-click on the ground to spawn the first tribe. " +
                                        "They will grow, evolve, and shape the world according to your divine will."
                        )),
                        Filterable.passThrough(Component.literal(
                                "As tribes grow, they will develop culture, beliefs, and technology. Guide them wisely, for their fate rests in your hands."
                        ))
                ),
                false // resolved
        );

        book.set(DataComponents.WRITTEN_BOOK_CONTENT, content);
        return book;
    }

    public static ItemStack firstFlameBook() {
        ItemStack book = new ItemStack(Items.WRITTEN_BOOK);

        WrittenBookContent content = new WrittenBookContent(
                Filterable.passThrough("Teachings of the First Flame"),
                "Oracle",
                0,
                List.of(
                        Filterable.passThrough(Component.literal(
                                "This world began in flame. From that fire, you were born. You are the divine architect, the shaper of destinies."
                        )),
                        Filterable.passThrough(Component.literal(
                                "The tribes will worship you, fear you, or forget you. Your actions shape their beliefs. Choose your path with wisdom."
                        )),
                        Filterable.passThrough(Component.literal(
                                "When all life ends or when genesis is invoked again, the world may be reborn. This is the cycle of divine creation."
                        ))
                ),
                false
        );

        book.set(DataComponents.WRITTEN_BOOK_CONTENT, content);
        return book;
    }

    @Mod.EventBusSubscriber(modid = "divineworld")
    public class DivineEventHandler {

        @SubscribeEvent
        public static void onBookUse(PlayerInteractEvent.RightClickBlock event) {
            if (GenesisManager.onGenesisUse(event.getEntity(), event.getLevel(), event.getHand()) == InteractionResult.SUCCESS) {
                event.setCanceled(true);
            }
        }
    }

}
