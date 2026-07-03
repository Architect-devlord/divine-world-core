// src/main/java/com/divineworld/events/GodDisguiseHandler.java
// DivineWorld server mod
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.network.NetworkHandler;
import com.divineworld.utils.AgentConfigLoader;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.Mob;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.*;

/**
 * God Disguise Handler — server-side transformation system
 *
 * FIX Bug #5 — original god type overwritten by transform
 * --------------------------------------------------------
 * The original code in both removeTransform() and replaceGodBody() read
 * the god type to restore from "dw_god_type". The problem:
 *   replaceGodBody() writes  player.getPersistentData().putString("dw_god_type", mobType)
 * …so after any transform the cached "dw_god_type" equals the TRANSFORM TARGET
 * (e.g. "warden"), not the original body type (e.g. "oracle").
 * removeTransform() would then restore a warden body instead of the oracle.
 *
 * Fix: GodSpawnHandler.spawnGodBody() now ALSO writes "dw_original_god_type"
 * which is never touched by replaceGodBody(). removeTransform() reads from
 * "dw_original_god_type" exclusively, so revert always goes back to the right form.
 *
 * FIX Bug #4 — morph bodies must NOT be invulnerable
 * ---------------------------------------------------
 * Real-player morph entities no longer call mob.setInvulnerable(true).
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GodDisguiseHandler {

    private static final Map<UUID, Entity> MORPH_MAP = new HashMap<>();

    private static final Set<String> GOD_TIER_TYPES = Set.of(
            "ender_dragon", "dragon", "wither", "warden", "elder_guardian"
    );

    private static final Set<String> FORBIDDEN_TYPES = Set.of(
            "area_effect_cloud", "falling_block", "item", "item_frame",
            "end_crystal", "armor_stand", "experience_orb"
    );

    // =========================================================================
    // Public API
    // =========================================================================

    public static boolean applyTransform(ServerPlayer player, String mobType, ServerLevel level) {
        if (!canTransform(player)) {
            player.sendSystemMessage(Component.literal(
                    "§c[Transform] Permission denied. Only gods or operators (level 4) can transform."));
            return false;
        }

        if (!DWNPCManager.isGodPlayer(player) && GOD_TIER_TYPES.contains(mobType.toLowerCase())) {
            player.sendSystemMessage(Component.literal(
                    "§c[Transform] Only god agents can take that form."));
            return false;
        }

        String normType = mobType.toLowerCase().replace("minecraft:", "");
        if (FORBIDDEN_TYPES.contains(normType)) {
            player.sendSystemMessage(Component.literal(
                    "§c[Transform] That entity type cannot be used."));
            return false;
        }

        // ── God agent path ────────────────────────────────────────────────────
        if (DWNPCManager.isGodPlayer(player)) {
            boolean ok = GodSpawnHandler.replaceGodBody(player, normType);
            if (!ok) {
                player.sendSystemMessage(Component.literal(
                        "§c[Transform] Unknown mob type: §7" + mobType));
                return false;
            }
            // Mark as disguised; store CURRENT transform type for display only.
            // "dw_original_god_type" is untouched (set once in spawnGodBody).
            player.getPersistentData().putBoolean("dw_disguised", true);
            player.getPersistentData().putString("dw_disguise_type", normType);

            spawnMorphParticles(player, level, normType);
            NetworkHandler.broadcastMorph(player, level, normType);

            player.sendSystemMessage(Component.literal(
                    "§a[Transform] You now appear as: §b" + normType +
                    "\n§7Use §c/god_transform revert§7 to return."));
            DWMod.LOGGER.info("[Transform] God {} → {}", DWNPCManager.getAgentId(player), normType);
            return true;
        }

        // ── Real player (op-4) path ───────────────────────────────────────────
        removeTransform(player);

        EntityType<?> entityType = GodSpawnHandler.resolveVanillaEntityType(normType);
        if (entityType == null) {
            player.sendSystemMessage(Component.literal(
                    "§c[Transform] Unknown mob type: §7" + mobType));
            return false;
        }

        Entity morph = entityType.create(level);
        if (morph == null) {
            player.sendSystemMessage(Component.literal("§c[Transform] Failed to create entity."));
            return false;
        }

        BlockPos pos = player.blockPosition();
        morph.moveTo(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5,
                player.getYRot(), player.getXRot());
        if (morph instanceof Mob mob) {
            mob.setNoAi(true);
            // FIX Bug #4: do NOT call mob.setInvulnerable(true) here
        }
        morph.getPersistentData().putBoolean("dw_disguise", true);
        morph.getPersistentData().putString("dw_disguise_owner", player.getUUID().toString());

        level.addFreshEntity(morph);
        MORPH_MAP.put(player.getUUID(), morph);

        player.setInvisible(true);
        player.getAbilities().mayfly = true;
        player.getAbilities().flying = true;
        player.onUpdateAbilities();

        player.getPersistentData().putBoolean("dw_disguised", true);
        player.getPersistentData().putString("dw_disguise_type", normType);

        spawnMorphParticles(player, level, normType);
        NetworkHandler.broadcastMorph(player, level, normType);

        player.sendSystemMessage(Component.literal(
                "§a[Transform] You appear as: §b" + normType +
                "\n§7Use §c/god_transform revert §7to return."));
        DWMod.LOGGER.info("[Transform] Player {} (op4) → {}", player.getName().getString(), normType);
        return true;
    }

    /**
     * Revert to original form.
     *
     * FIX Bug #5: For god agents, we read "dw_original_god_type" (written once
     * in GodSpawnHandler.spawnGodBody) rather than "dw_god_type" (which gets
     * overwritten by every replaceGodBody call during a transform).
     */
    public static void removeTransform(ServerPlayer player) {
        ServerLevel level = player.serverLevel();

        if (DWNPCManager.isGodPlayer(player)) {
            // FIX: read the ORIGINAL type, not the current transform target
            String originalType = player.getPersistentData().getString("dw_original_god_type");
            if (originalType == null || originalType.isEmpty()) {
                // Fallback chain: agents.json → oracle
                originalType = AgentConfigLoader.getGodTypeForName(player.getName().getString());
            }
            if (originalType == null || originalType.isEmpty()) originalType = "oracle";

            GodSpawnHandler.replaceGodBody(player, originalType);
        } else {
            Entity morph = MORPH_MAP.remove(player.getUUID());
            if (morph != null && !morph.isRemoved()) {
                spawnMorphParticles(player, level, "revert");
                morph.remove(Entity.RemovalReason.DISCARDED);
            }
            player.setInvisible(false);
            player.getAbilities().mayfly = false;
            player.getAbilities().flying = false;
            player.onUpdateAbilities();
        }

        player.getPersistentData().putBoolean("dw_disguised", false);
        player.getPersistentData().remove("dw_disguise_type");

        NetworkHandler.broadcastMorph(player, level, "");
        player.sendSystemMessage(Component.literal("§d[Transform] You return to your true form."));
        DWMod.LOGGER.info("[Transform] {} reverted", player.getName().getString());
    }

    public static boolean canTransform(ServerPlayer player) {
        if (DWNPCManager.isAIPlayer(player) && !DWNPCManager.isGodPlayer(player)) return false;
        if (DWNPCManager.isGodPlayer(player)) return true;
        return player.hasPermissions(4);
    }

    public static boolean isTransformed(ServerPlayer player) {
        if (DWNPCManager.isGodPlayer(player)) {
            return player.getPersistentData().getBoolean("dw_disguised");
        }
        Entity morph = MORPH_MAP.get(player.getUUID());
        return morph != null && !morph.isRemoved();
    }

    // =========================================================================
    // Three-way form cycle — GOD → HUMANOID → DISGUISE → GOD
    // Managed separately from the mob-transform system (dw_disguised / replaceGodBody).
    // dw_form NBT key: "god" | "humanoid" | "disguise"
    // =========================================================================

    /** Form constants — match what GodEntityRenderer (DWClientBot) reads from dw_form. */
    private static final String FORM_GOD      = "god";
    private static final String FORM_HUMANOID = "humanoid";
    private static final String FORM_DISGUISE = "disguise";

    /**
     * Returns the current form for a god player, defaulting to "god" when the
     * NBT key is absent (i.e. on first join before any toggle has been issued).
     */
    public static String getGodForm(ServerPlayer player) {
        String form = player.getPersistentData().getString("dw_form");
        return (form == null || form.isEmpty()) ? FORM_GOD : form;
    }

    /**
     * Advance the god's form one step around the cycle:
     *   god  →  humanoid  →  disguise  →  god  →  …
     *
     * Server-side effects per form:
     *   god      — boss body VISIBLE,  player puppet INVISIBLE (existing behaviour)
     *   humanoid — boss body INVISIBLE, player puppet VISIBLE  (GeckoLib model)
     *   disguise — boss body INVISIBLE, player puppet VISIBLE  (Steve/Alex skin)
     *
     * The client-side renderer (GodEntityRenderer) picks up the form from the
     * dw_form NBT key which is synced via the existing MorphSyncPacket channel
     * — we send broadcastMorph() with the form name as the "mobType" payload so
     * TransformationHandler on the client can fire any form-change particles.
     * The NBT is synced to all nearby clients automatically by Forge's normal
     * entity data sync (player.getPersistentData() on a ServerPlayer is part of
     * the player's tracked data block that vanilla broadcasts on change).
     */
    public static void cycleGodForm(ServerPlayer player) {
        if (!DWNPCManager.isGodPlayer(player)) {
            player.sendSystemMessage(Component.literal(
                    "§c[Form Toggle] Only god agents can cycle forms."));
            return;
        }
        String current = getGodForm(player);
        String next = switch (current) {
            case FORM_GOD      -> FORM_HUMANOID;
            case FORM_HUMANOID -> FORM_DISGUISE;
            default            -> FORM_GOD;   // DISGUISE → GOD, and any unknown state
        };
        applyGodForm(player, next);
    }

    /**
     * Set a god player's form directly (also used by cycleGodForm and by
     * external callers like GodCommand.toggleCycleTarget()).
     */
    public static void applyGodForm(ServerPlayer player, String form) {
        ServerLevel level = player.serverLevel();

        // Toggle boss-body and puppet visibility based on target form
        Entity bossBody = GodSpawnHandler.getGodEntity(player.getUUID());

        switch (form) {
            case FORM_GOD -> {
                // Boss body is the visible representation — puppet hides
                if (bossBody != null) bossBody.setInvisible(false);
                player.setInvisible(true);
            }
            case FORM_HUMANOID -> {
                // Puppet renders using GeckoLib humanoid model — boss body hides
                if (bossBody != null) bossBody.setInvisible(true);
                player.setInvisible(false);
            }
            case FORM_DISGUISE -> {
                // Puppet renders as Steve or Alex — boss body hides
                if (bossBody != null) bossBody.setInvisible(true);
                player.setInvisible(false);
                // Pick Steve or Alex randomly and remember it for the renderer.
                // Stored as a boolean: true = Steve (classic/wide), false = Alex (slim).
                boolean isSteve = level.random.nextBoolean();
                player.getPersistentData().putBoolean("dw_is_steve", isSteve);
            }
        }

        // Persist form state — synced to all clients via Forge's player NBT sync
        player.getPersistentData().putString("dw_form", form);

        // Broadcast via the existing MorphSyncPacket channel so TransformationHandler
        // on DWClientBot can fire per-form particles and log the event.
        // We pass the form name as mobType — TransformationHandler already handles
        // unknown mobType strings gracefully (falls through to PORTAL particles).
        NetworkHandler.broadcastMorph(player, level, "form:" + form);

        spawnMorphParticles(player, level,
                player.getPersistentData().getString("dw_original_god_type"));

        player.sendSystemMessage(Component.literal(switch (form) {
            case FORM_GOD      -> "§5You reveal your §l§5divine form§r§5.";
            case FORM_HUMANOID -> "§dYou take on your §l§dhumanoid form§r§d.";
            case FORM_DISGUISE -> "§7You blend in as a §l§7mortal§r§7.";
            default            -> "§dForm changed to: " + form;
        }));

        DWMod.LOGGER.info("[GodForm] {} → form:{}", DWNPCManager.getAgentId(player), form);
    }



    // =========================================================================
    // Tick sync — real-player morph bodies
    // =========================================================================

    public static void tickMorphBodies(ServerLevel level) {
        for (Map.Entry<UUID, Entity> entry : MORPH_MAP.entrySet()) {
            Entity morph = entry.getValue();
            if (morph == null || morph.isRemoved()) continue;

            ServerPlayer owner = level.getServer().getPlayerList().getPlayer(entry.getKey());
            if (owner == null) continue;

            morph.setYRot(owner.getYRot());
            morph.setXRot(owner.getXRot());
            morph.setYHeadRot(owner.getYHeadRot());
            morph.moveTo(owner.getX(), owner.getY(), owner.getZ(),
                    owner.getYRot(), owner.getXRot());
        }
    }

    // =========================================================================
    // Cleanup on disconnect
    // =========================================================================

    @SubscribeEvent
    public static void onPlayerLeave(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        Entity morph = MORPH_MAP.remove(player.getUUID());
        if (morph != null && !morph.isRemoved()) {
            morph.remove(Entity.RemovalReason.DISCARDED);
            DWMod.LOGGER.info("[Transform] Removed morph for disconnected: {}",
                    player.getName().getString());
        }
    }

    // =========================================================================
    // Particles
    // =========================================================================

    private static void spawnMorphParticles(ServerPlayer player, ServerLevel level, String godType) {
        var particle = switch (godType) {
            case "ender_dragon", "dragon" -> ParticleTypes.DRAGON_BREATH;
            case "wither"                 -> ParticleTypes.SMOKE;
            case "warden"                 -> ParticleTypes.SCULK_SOUL;
            case "elder_guardian"         -> ParticleTypes.BUBBLE;
            case "creaking"               -> ParticleTypes.SPORE_BLOSSOM_AIR;
            case "oracle"                 -> ParticleTypes.ENCHANT;
            case "revert"                 -> ParticleTypes.TOTEM_OF_UNDYING;
            default                       -> ParticleTypes.PORTAL;
        };
        double px = player.getX(), py = player.getY() + 1, pz = player.getZ();
        level.sendParticles(particle, px, py, pz, 50, 0.5, 0.8, 0.5, 0.12);
        level.playSound(null, player.blockPosition(),
                SoundEvents.ENDERMAN_TELEPORT, SoundSource.PLAYERS, 0.9f, 1.0f);
    }
}