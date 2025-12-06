package com.divineworld.entity.god;

import com.google.common.collect.ImmutableSet;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.AABB;
import java.util.*;

/**
 * Handles god disguise / shapeshift logic.
 * Gods can mimic any living entity (except other gods).
 * Inspired by Among Us-style shapeshifting but designed for emergent AI use.
 */
public class GodDisguiseHandler {

    // Prevent shapeshifting into these entity types
    private static final Set<EntityType<?>> FORBIDDEN_FORMS = ImmutableSet.of(
            EntityType.ENDER_DRAGON, EntityType.WITHER, EntityType.WARDEN, EntityType.ELDER_GUARDIAN
    );

    /**
     * Main toggle entrypoint for disguise transformation.
     * If 'toMortal' is true → god disguises into something.
     * Otherwise → reverts to original god form.
     */
    public static void switchForm(DWGodEntity god, boolean toMortal, ServerLevel level) {
        if (god == null || level == null) return;

        boolean currentlyMortal = god.isInMortalDisguise();

        if (toMortal && !currentlyMortal) {
            LivingEntity targetForm = findDisguiseTarget(level, god);
            applyDisguise(god, targetForm);
        } else if (!toMortal && currentlyMortal) {
            removeDisguise(god);
        }
    }

    /**
     * Chooses a disguise target:
     * 1. Nearby NPC or player (not a god)
     * 2. Random mob type if no suitable entity found nearby
     */
    private static LivingEntity findDisguiseTarget(ServerLevel level, DWGodEntity god) {
        List<LivingEntity> candidates = level.getEntitiesOfClass(
                LivingEntity.class,
                new AABB(god.blockPosition()).inflate(20),
                e -> e != god && !isGodEntity(e) && !(e instanceof Player && ((Player)e).isCreative())
        );

        if (!candidates.isEmpty()) {
            Collections.shuffle(candidates);
            return candidates.get(0);
        }

        // Fallback: spawn a random disguise mob temporarily (self-created disguise)
        Optional<EntityType<? extends Mob>> randomMob = level.registryAccess()
                .registryOrThrow(net.minecraft.core.registries.Registries.ENTITY_TYPE)
                .stream()
                .filter(et -> !FORBIDDEN_FORMS.contains(et) && Mob.class.isAssignableFrom(et.getBaseClass()))
                .map(et -> (EntityType<? extends Mob>) et)
                .findAny();

        if (randomMob.isPresent()) {
            Mob fakeMob = randomMob.get().create(level);
            if (fakeMob != null) {
                fakeMob.moveTo(god.getX(), god.getY(), god.getZ());
                return fakeMob;
            }
        }
        return null;
    }

    /**
     * Applies disguise attributes visually and logically.
     * The disguise is stored inside god metadata (inMortalDisguise).
     */
    private static void applyDisguise(DWGodEntity god, LivingEntity targetForm) {
        if (targetForm == null) {
            god.setCustomName(Component.literal("Mysterious Stranger"));
            god.toggleDisguiseForm();
            return;
        }

        // Copy name and type hints
        String disguiseName = targetForm.hasCustomName()
                ? targetForm.getCustomName().getString()
                : targetForm.getName().getString();

        god.setCustomName(Component.literal(disguiseName));
        god.setCustomNameVisible(true);
        god.setInvisible(false);
        god.setGlowingTag(false);
        god.toggleDisguiseForm();

        // Optional: aura dampening for stealth
        god.getAttribute(net.minecraft.world.entity.ai.attributes.Attributes.MAX_HEALTH).setBaseValue(targetForm.getMaxHealth());
        god.setHealth(targetForm.getHealth());

        // You can visually sync appearance via packets if client mod is present
        // (e.g., disguise skins, models, or client-rendered overlays)
    }

    /**
     * Removes disguise and restores full god form attributes.
     */
    private static void removeDisguise(DWGodEntity god) {
        god.toggleDisguiseForm();
        god.setCustomName(Component.literal("Divine Being"));
        god.setGlowingTag(true);
    }

    /**
     * Used to randomize disguise appearance (custom skins or names).
     * Later expanded by client-side rendering logic.
     */
    public static void randomizeDisguiseAppearance(DWGodEntity god) {
        if (god != null && god.isInMortalDisguise()) {
            String[] aliases = {
                    "Mysterious Stranger", "Lost Merchant", "Quiet Hermit", "Wandering Trader",
                    "Kind Farmer", "Lone Traveler", "Unknown Villager" , ""
            };
            String chosen = aliases[new Random().nextInt(aliases.length)];
            god.setCustomName(Component.literal(chosen));
        }
    }

    /**
     * Prevent shapeshifting into other gods.
     */
    private static boolean isGodEntity(Entity e) {
        return e instanceof DWGodEntity;
    }
}
