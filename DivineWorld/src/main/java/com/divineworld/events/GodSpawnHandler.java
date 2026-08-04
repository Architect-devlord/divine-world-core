// src/main/java/com/divineworld/events/GodSpawnHandler.java
// DivineWorld server mod
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
 * Entity type mapping (UPDATED):
 *   oracle   → EVOKER       (robed mage look; can summon Vexes/fangs as god powers)
 *   creaking → AI_CREAKING  (custom GeckoLib entity — see getGodEntityType() below;
 *                            real Creaking doesn't exist until MC 1.21.4, this
 *                            project targets 1.20.1. FIX: this line previously
 *                            said "→ WARDEN", stale from before the custom
 *                            entity existed — the actual switch body has been
 *                            correct for a while, only this comment was wrong)
 *   warden   → WARDEN
 *   wither   → WITHER
 *   dragon   → ENDER_DRAGON
 *   elder_guardian → ELDER_GUARDIAN
 *
 * Burrow behaviour (UPDATED):
 *   Both Warden (executeWardenAbility's own "burrow"/"emerge" cases) and
 *   Creaking (executeCreakingAbility's "toggle_underground"/"emerge" cases)
 *   share this same dw_burrowed-flag mechanic independently — each god
 *   agent controls when to emerge itself, no auto-emerge timer for either.
 *   While burrowed, the god puppet is invulnerable and invisible.
 *   dw_burrowed NBT flag is cleared on logout for safety.
 *
 *   CORRECTION: this comment previously said only "The Warden god agent
 *   controls when to emerge" — accurate for Warden alone, but incomplete
 *   once Creaking's own independent "emerge" case (previously unreachable
 *   from Python's ability lists, now fixed — see action_format_sync.py's
 *   GOD_ABILITY_NAMES["creaking"]) is actually selectable by the agent too.
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
        if (godType == null) return;

        DWMod.LOGGER.info("🌟 Scheduling god body spawn: {} → {} in 40 ticks", username, godType);
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

        godEntity.moveTo(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5,
                player.getYRot(), 0.0f);

        // Disable vanilla AI
        if (godEntity instanceof EnderDragon dragon) {
            // FIX CF-2: HOVERING phase calls getDragonFight() which returns null
            // in non-End dimensions → NullPointerException on first phase tick.
            // SITTING_FLAPPING_WINGS is safe in all dimensions and looks natural.
            dragon.getPhaseManager().setPhase(EnderDragonPhase.SITTING_SCANNING);
        } else if (godEntity instanceof net.minecraft.world.entity.Mob mob) {
            mob.setNoAi(true);
        }

        // Wither: clear invulnerability timer so body is immediately hittable
        if (godEntity instanceof WitherBoss wither) {
            wither.setInvulnerableTicks(0);
        }

        // Tag entity
        TaggedEntitySystem.tagEntity(godEntity, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(godEntity, godType);
        TaggedEntitySystem.setAIID(godEntity, agentId);
        TaggedEntitySystem.setDivinePower(godEntity, 100);
        TaggedEntitySystem.makeGenesisImmune(godEntity);

        GOD_ENTITY_MAP.put(player.getUUID(), godEntity);
        level.addFreshEntity(godEntity);

        // Register god player — sole call site
        DWNPCManager.registerGodPlayer(player, agentId, godType);

        // Store ORIGINAL god type (never overwritten by transforms)
        player.getPersistentData().putString("dw_original_god_type", godType);

        // Clear any stale burrow state from a previous session
        if (player.getPersistentData().getBoolean("dw_burrowed")) {
            player.getPersistentData().putBoolean("dw_burrowed", false);
            DWMod.LOGGER.info("[GodSpawnHandler] Cleared stale dw_burrowed flag for {}", agentId);
        }

        // Puppet: invisible, no physics, not invulnerable (body takes hits)
        player.setInvisible(true);
        player.getAbilities().mayfly       = true;
        player.getAbilities().flying       = true;
        player.getAbilities().invulnerable = false;
        player.noPhysics = true;
        player.onUpdateAbilities();

        boostGodPuppetAttributes(player, godType);

        DWMod.LOGGER.info("✅ God body spawned: {} ({}) for agent {}",
                godType, godEntity.getUUID(), agentId);
    }

    private static void boostGodPuppetAttributes(ServerPlayer player, String godType) {
        double health, attackDamage, speed;
        switch (godType) {
            case "wither"                    -> { health = 300; attackDamage = 20; speed = 0.35; }
            case "ender_dragon", "dragon"    -> { health = 200; attackDamage = 15; speed = 0.30; }
            case "warden"                    -> { health = 500; attackDamage = 30; speed = 0.30; }
            case "elder_guardian"            -> { health = 250; attackDamage = 18; speed = 0.25; }
            case "creaking"                  -> { health = 200; attackDamage = 15; speed = 0.30; }
            case "oracle"                    -> { health = 150; attackDamage =  8; speed = 0.30; }
            default                          -> { health = 100; attackDamage = 10; speed = 0.30; }
        }
        var maxHp = player.getAttribute(Attributes.MAX_HEALTH);
        var atk   = player.getAttribute(Attributes.ATTACK_DAMAGE);
        var spd   = player.getAttribute(Attributes.MOVEMENT_SPEED);
        if (maxHp != null) maxHp.setBaseValue(health);
        if (atk   != null) atk.setBaseValue(attackDamage);
        if (spd   != null) spd.setBaseValue(speed);
        player.setHealth(player.getMaxHealth());
    }

    // =========================================================================
    // Body replacement
    // =========================================================================

    public static boolean replaceGodBody(ServerPlayer player, String mobType) {
        UUID playerUUID = player.getUUID();
        Entity oldBody  = GOD_ENTITY_MAP.remove(playerUUID);
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

        if (newBody instanceof EnderDragon dragon) {
            // Same CF-2 fix as spawnGodBody(): HOVERING's tick logic calls
            // getDragonFight(), which is null outside The End and NPEs on the
            // first phase tick. This call site had the identical bug — it's
            // the same "spawn a dragon body" operation, just for a mid-game
            // transform instead of the initial spawn, and the fix was only
            // ever applied to the other one.
            dragon.getPhaseManager().setPhase(EnderDragonPhase.SITTING_SCANNING);
        } else if (newBody instanceof net.minecraft.world.entity.Mob mob) {
            mob.setNoAi(true);
        }
        if (newBody instanceof WitherBoss wither) {
            wither.setInvulnerableTicks(0);
        }

        TaggedEntitySystem.tagEntity(newBody, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(newBody, mobType.toLowerCase());
        TaggedEntitySystem.setAIID(newBody, agentId);
        TaggedEntitySystem.makeGenesisImmune(newBody);

        // Only update CURRENT type — original stays in "dw_original_god_type"
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

    /**
     * Map god type keys to entity types.
     *
     * All six god types now spawn DivineWorld's own custom entities
     * (com.divineworld.entity.gods.*), moved here from DWClientBot's
     * com.divineworld.client.entity.gods package where they were fully
     * built (GeckoLib humanoid rig, per-type abilities, correct dimensions,
     * registered renderers) but never actually spawned anywhere — this
     * method previously returned plain vanilla EntityType.WARDEN/WITHER/
     * ENDER_DRAGON/ELDER_GUARDIAN/EVOKER, which are AI-less placeholders
     * with none of that. See ModEntities/EntityAttributeRegistrar/
     * DivineClientSetup for the matching registration.
     *
     * The EnderDragon/WitherBoss-specific instanceof checks a few lines
     * below in spawnGodBody()/replaceGodBody() (dragon phase, invulnerable
     * ticks) naturally stop applying now — AIEnderDragon/AIWither aren't
     * instances of the vanilla classes, so those vanilla-AI-specific fixups
     * are simply skipped rather than needed, which is correct: the custom
     * classes don't have a vanilla phase manager or invulnerability-tick
     * mechanic to begin with.
     */
    static EntityType<?> getGodEntityType(String godType) {
        return switch (godType) {
            case "ender_dragon", "dragon" -> com.divineworld.entity.ModEntities.AI_ENDER_DRAGON.get();
            case "wither"                 -> com.divineworld.entity.ModEntities.AI_WITHER.get();
            case "warden"                 -> com.divineworld.entity.ModEntities.AI_WARDEN.get();
            case "elder_guardian"         -> com.divineworld.entity.ModEntities.AI_ELDER_GUARDIAN.get();
            case "oracle"                 -> com.divineworld.entity.ModEntities.AI_ORACLE.get();
            case "creaking"               -> com.divineworld.entity.ModEntities.AI_CREAKING.get();
            default                       -> null;
        };
    }

    /** Resolve a short vanilla mob id (e.g. "zombie") via the Forge registry. */
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

    /**
     * Trigger a GeckoLib animation on the god body entity if it is an
     * AICreakingEntity (GeoEntity). Safe to call for any god type — no-ops
     * for vanilla boss entities that don't implement GeoEntity.
     *
     * @param playerUuid      UUID of the god puppet player
     * @param controllerName  "base_controller" or "ability_controller"
     * @param animName        animation ID matching the .animation.json entry
     */
    public static void triggerGodAnimation(java.util.UUID playerUuid,
                                           String controllerName,
                                           String animName) {
        Entity body = GOD_ENTITY_MAP.get(playerUuid);
        if (body instanceof com.divineworld.entity.AICreakingEntity creaking) {
            creaking.triggerAnim(controllerName, animName);
        }
        // Future: add more GeoEntity god types here as they are implemented
    }

    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        // Clean up stale burrow state so it doesn't persist to next session
        if (player.getPersistentData().getBoolean("dw_burrowed")) {
            player.setInvisible(false);
            player.noPhysics = false;
            player.getAbilities().invulnerable = false;
            player.onUpdateAbilities();
            player.getPersistentData().putBoolean("dw_burrowed", false);
            DWMod.LOGGER.info("[GodSpawnHandler] Cleared burrow state on logout: {}",
                    player.getName().getString());
        }

        Entity godEntity = GOD_ENTITY_MAP.remove(player.getUUID());
        if (godEntity != null && !godEntity.isRemoved()) {
            godEntity.remove(Entity.RemovalReason.DISCARDED);
            DWMod.LOGGER.info("🌟 Removed god body for disconnected: {}",
                    player.getName().getString());
        }
    }
}