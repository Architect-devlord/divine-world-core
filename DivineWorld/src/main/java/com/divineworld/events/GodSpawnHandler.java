// src/main/java/com/divineworld/events/GodSpawnHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.utils.AgentConfigLoader;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.core.BlockPos;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.boss.enderdragon.EnderDragon;
import net.minecraft.world.entity.boss.enderdragon.phases.EnderDragonPhase;
import net.minecraft.world.entity.boss.wither.WitherBoss;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * GodSpawnHandler — spawns a vanilla boss entity when a god agent joins,
 * and tears it down when they disconnect.
 *
 * The entity is the agent's visible "body"; the ServerPlayer puppet is
 * invisible (noPhysics = true) and co-located with it.
 * GodControlHandler syncs their positions every tick.
 *
 * FIXES in this file
 * ──────────────────
 * Bug 1  — Double registerGodPlayer: removed from DWEventHandler; this file
 *           is the sole caller, after the body is fully in the world.
 *
 * Bug 3  — EnderDragon AI not disabled: EnderDragon doesn't extend Mob so
 *           instanceof Mob → setNoAi silently skipped it. Fixed by checking
 *           for EnderDragon first and using the DragonPhaseManager to lock
 *           the dragon in HOVERING phase, disabling all autonomous AI.
 *
 * Bug 4  — Gods incorrectly invulnerable: removed all setInvulnerable(true)
 *           calls from spawnGodBody and replaceGodBody. God bodies must be
 *           damageable; only the invisible puppet uses invulnerable = false.
 *
 * Bug 5  — Original god type lost on transform: spawnGodBody writes
 *           "dw_original_god_type" once at spawn. replaceGodBody only
 *           updates "dw_god_type". removeTransform reads from
 *           "dw_original_god_type" and always gets the right value back.
 *
 * Bug 7  — God puppet has default player stats (2 dmg): boostGodPuppetAttributes
 *           scales MAX_HEALTH, ATTACK_DAMAGE, and MOVEMENT_SPEED to match
 *           each god tier so melee attacks via ActionExecutor hit with force.
 *
 * Bug 8  — GodEntityManager never called addFreshEntity: fixed in
 *           GodEntityManager.java (client side). Noted here for reference.
 *
 * Bug 12 — Wither shield NBT key wrong: putInt("WitherBirthTime", -1000)
 *           used the wrong key. The actual field Wither reads for its
 *           invulnerability timer is "Invul" (see WitherBoss.readAdditionalSaveData).
 *           Fixed: we call wither.makeInvulnerable(0) which sets Invul=0
 *           directly via the public API, bypassing NBT key names entirely.
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GodSpawnHandler {

    /** player UUID → server-side boss entity */
    private static final Map<UUID, Entity> GOD_ENTITY_MAP = new HashMap<>();

    // =========================================================================
    // Join — schedule body spawn
    // =========================================================================

    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        String username = player.getName().getString();
        String godType  = AgentConfigLoader.getGodTypeForName(username);
        if (godType == null) return; // not a god agent

        DWMod.LOGGER.info("🌟 Scheduling god body spawn: {} → {} in 40 ticks", username, godType);

        // 40-tick delay (2 s) lets the player fully load before we read their
        // position and spawn the body next to them.
        DWMod.getInstance().scheduleTask(
                () -> spawnGodBody(player, godType, username), 40);
    }

    // =========================================================================
    // Body spawn
    // =========================================================================

    private static void spawnGodBody(ServerPlayer player, String godType, String agentId) {
        if (player.isRemoved() || !player.isAlive()) {
            DWMod.LOGGER.warn("[GodSpawnHandler] Player {} gone before body spawn", agentId);
            return;
        }

        ServerLevel level = player.serverLevel();
        BlockPos    pos   = player.blockPosition();

        EntityType<?> entityType = getGodEntityType(godType);
        if (entityType == null) {
            DWMod.LOGGER.error("❌ Unknown god type: {}", godType);
            return;
        }

        Entity godEntity = entityType.create(level);
        if (godEntity == null) {
            DWMod.LOGGER.error("❌ Failed to create entity for god type: {}", godType);
            return;
        }

        // Position at player's feet
        godEntity.moveTo(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5,
                player.getYRot(), 0.0f);

        // ── Disable vanilla AI ──────────────────────────────────────────────
        // FIX Bug 3: EnderDragon does NOT extend Mob — the old instanceof check
        // silently skipped it. Lock it to HOVERING phase instead.
        if (godEntity instanceof EnderDragon dragon) {
            dragon.getPhaseManager().setPhase(EnderDragonPhase.HOVERING);
        } else if (godEntity instanceof net.minecraft.world.entity.Mob mob) {
            mob.setNoAi(true);
            // FIX Bug 4: do NOT call mob.setInvulnerable(true) — god bodies must be damageable.
        }

        // ── Wither shield fix (Bug 12) ──────────────────────────────────────
        // WitherBoss spawns with an invulnerability timer (NBT key "Invul").
        // The old code tried putInt("WitherBirthTime", -1000) which is the
        // WRONG key — Wither never reads "WitherBirthTime". The correct field
        // is "Invul" (see WitherBoss.readAdditionalSaveData line ~300).
        //
        // Fix: call makeInvulnerable(0) which sets invulTimer = 0 via the
        // public API, making the Wither body immediately hittable.
        if (godEntity instanceof WitherBoss wither) {
            wither.setInvulnerableTicks(0); // sets Invul=0, no shield on spawn
        }

        // ── Tag entity ─────────────────────────────────────────────────────
        TaggedEntitySystem.tagEntity(godEntity, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(godEntity, godType);
        TaggedEntitySystem.setAIID(godEntity, agentId);
        TaggedEntitySystem.setDivinePower(godEntity, 100);
        TaggedEntitySystem.makeGenesisImmune(godEntity);

        // ── Link body to puppet ────────────────────────────────────────────
        GOD_ENTITY_MAP.put(player.getUUID(), godEntity);
        level.addFreshEntity(godEntity);

        // ── Register god player (sole call site — FIX Bug 1) ───────────────
        DWNPCManager.registerGodPlayer(player, agentId, godType);

        // ── Store original god type (FIX Bug 5) ────────────────────────────
        // replaceGodBody overwrites "dw_god_type"; this key stays constant so
        // GodDisguiseHandler.removeTransform can always restore the right body.
        player.getPersistentData().putString("dw_original_god_type", godType);

        // ── Puppet visibility + physics ────────────────────────────────────
        player.setInvisible(true);
        player.getAbilities().mayfly    = true;
        player.getAbilities().flying    = true;
        player.getAbilities().invulnerable = false; // body takes the hits
        player.noPhysics = true;                    // puppet passes through blocks
        player.onUpdateAbilities();

        // ── Boost puppet attributes (FIX Bug 7) ───────────────────────────
        boostGodPuppetAttributes(player, godType);

        DWMod.LOGGER.info("✅ God body spawned: {} ({}) for agent {}",
                godType, godEntity.getUUID(), agentId);
    }

    // ── Attribute scaling ─────────────────────────────────────────────────────

    /**
     * Scale the invisible puppet's combat attributes to the god tier so that
     * melee swings via ActionExecutor.executeAction() deal appropriate damage.
     * Values mirror the createAttributes() blocks in each client-side AI entity.
     */
    private static void boostGodPuppetAttributes(ServerPlayer player, String godType) {
        double health, attackDamage, speed;

        switch (godType) {
            case "wither"         -> { health = 300; attackDamage = 20; speed = 0.35; }
            case "ender_dragon",
                 "dragon"         -> { health = 200; attackDamage = 15; speed = 0.30; }
            case "warden"         -> { health = 500; attackDamage = 30; speed = 0.30; }
            case "elder_guardian" -> { health = 250; attackDamage = 18; speed = 0.25; }
            case "creaking"       -> { health = 200; attackDamage = 15; speed = 0.30; }
            case "oracle"         -> { health = 150; attackDamage =  8; speed = 0.30; }
            default               -> { health = 100; attackDamage = 10; speed = 0.30; }
        }

        var maxHp = player.getAttribute(Attributes.MAX_HEALTH);
        var atk   = player.getAttribute(Attributes.ATTACK_DAMAGE);
        var spd   = player.getAttribute(Attributes.MOVEMENT_SPEED);

        if (maxHp != null) maxHp.setBaseValue(health);
        if (atk   != null) atk.setBaseValue(attackDamage);
        if (spd   != null) spd.setBaseValue(speed);

        player.setHealth(player.getMaxHealth()); // heal to full after buff
    }

    // =========================================================================
    // Body replacement (called by GodDisguiseHandler)
    // =========================================================================

    /**
     * Swap out the current god body for a new entity of the given type.
     * Called by GodDisguiseHandler.applyTransform and removeTransform.
     *
     * @param player  the god agent's invisible puppet
     * @param mobType god-type key ("warden", "oracle") or any vanilla mob id
     * @return true on success
     */
    public static boolean replaceGodBody(ServerPlayer player, String mobType) {
        UUID playerUUID = player.getUUID();

        // Discard old body
        Entity oldBody = GOD_ENTITY_MAP.remove(playerUUID);
        if (oldBody != null && !oldBody.isRemoved()) {
            oldBody.remove(Entity.RemovalReason.DISCARDED);
        }

        ServerLevel level   = player.serverLevel();
        String      agentId = TaggedEntitySystem.getAIID(player);

        EntityType<?> entityType = getGodEntityType(mobType.toLowerCase());
        if (entityType == null) entityType = resolveVanillaEntityType(mobType.toLowerCase());
        if (entityType == null) {
            DWMod.LOGGER.error("[GodSpawnHandler] Unknown mob type for transform: {}", mobType);
            return false;
        }

        Entity newBody = entityType.create(level);
        if (newBody == null) {
            DWMod.LOGGER.error("[GodSpawnHandler] Failed to create entity: {}", mobType);
            return false;
        }

        newBody.moveTo(player.getX(), player.getY(), player.getZ(),
                player.getYRot(), player.getXRot());

        // Disable AI — same pattern as spawnGodBody
        if (newBody instanceof EnderDragon dragon) {
            dragon.getPhaseManager().setPhase(EnderDragonPhase.HOVERING);
        } else if (newBody instanceof net.minecraft.world.entity.Mob mob) {
            mob.setNoAi(true);
            // FIX Bug 4: no setInvulnerable(true) here either
        }

        // Wither shield fix also applies to replacement bodies (Bug 12)
        if (newBody instanceof WitherBoss wither) {
            wither.setInvulnerableTicks(0);
        }

        // Tag
        TaggedEntitySystem.tagEntity(newBody, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(newBody, mobType.toLowerCase());
        TaggedEntitySystem.setAIID(newBody, agentId);
        TaggedEntitySystem.makeGenesisImmune(newBody);

        // FIX Bug 5: only update current type, not the original.
        player.getPersistentData().putString("dw_god_type", mobType.toLowerCase());
        TaggedEntitySystem.setGodType(player, mobType.toLowerCase());

        GOD_ENTITY_MAP.put(playerUUID, newBody);
        level.addFreshEntity(newBody);

        DWMod.LOGGER.info("[GodSpawnHandler] {} transformed → {}", agentId, mobType);
        return true;
    }

    // =========================================================================
    // Entity type resolution
    // =========================================================================

    private static EntityType<?> getGodEntityType(String godType) {
        return switch (godType) {
            case "ender_dragon", "dragon" -> EntityType.ENDER_DRAGON;
            case "wither"                 -> EntityType.WITHER;
            case "warden"                 -> EntityType.WARDEN;
            case "elder_guardian"         -> EntityType.ELDER_GUARDIAN;
            case "oracle"                 -> EntityType.WANDERING_TRADER;
            case "creaking"               -> EntityType.EVOKER; // placeholder TODO: add the custom creaking model here
            default                       -> null;
        };
    }

    /** Resolve a short vanilla mob id ("zombie") via the Forge registry. */
    static EntityType<?> resolveVanillaEntityType(String mobId) {
        String registryId = mobId.contains(":") ? mobId : "minecraft:" + mobId;
        try {
            net.minecraft.resources.ResourceLocation loc =
                    new net.minecraft.resources.ResourceLocation(registryId);
            EntityType<?> type =
                    net.minecraftforge.registries.ForgeRegistries.ENTITY_TYPES.getValue(loc);
            if (type == EntityType.PIG && !registryId.equals("minecraft:pig")) return null;
            return type;
        } catch (Exception e) {
            DWMod.LOGGER.warn("[GodSpawnHandler] Cannot resolve '{}': {}", registryId, e.getMessage());
            return null;
        }
    }

    // =========================================================================
    // Accessors & cleanup
    // =========================================================================

    public static Entity getGodEntity(UUID playerUuid) {
        return GOD_ENTITY_MAP.get(playerUuid);
    }

    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;
        Entity godEntity = GOD_ENTITY_MAP.remove(player.getUUID());
        if (godEntity != null && !godEntity.isRemoved()) {
            godEntity.remove(Entity.RemovalReason.DISCARDED);
            DWMod.LOGGER.info("🌟 Removed god body for disconnected: {}", player.getName().getString());
        }
    }
}