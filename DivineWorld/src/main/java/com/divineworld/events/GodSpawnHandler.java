// src/main/java/com/divineworld/events/GodSpawnHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.boss.enderdragon.EnderDragon;
import net.minecraft.world.entity.boss.wither.WitherBoss;
import net.minecraft.world.entity.monster.ElderGuardian;
import net.minecraft.world.entity.monster.warden.Warden;
import net.minecraft.core.BlockPos;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * FIXED God Spawn Handler - Minecraft Forge 1.20.1
 * Handles spawning god entities when AI agents join with GOD prefix
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GodSpawnHandler {

    // Track player -> god entity mappings
    private static final Map<UUID, Entity> GOD_ENTITY_MAP = new HashMap<>();

    @SubscribeEvent
    public static void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        String username = player.getName().getString();

        // Check for god agent pattern: GOD_<type>_<agentId>
        if (username.startsWith("GOD_")) {
            String[] parts = username.substring(4).split("_", 2);
            if (parts.length == 2) {
                String godType = parts[0].toLowerCase();
                String agentId = parts[1];

                DWMod.LOGGER.info("🌟 Detected god agent: {} (Type: {})", agentId, godType);

                // Schedule god body spawn (wait for player to fully load)
                DWMod.getInstance().scheduleTask(() -> {
                    spawnGodBody(player, godType, agentId);
                }, 40); // 2 seconds delay
            }
        }
    }

    /**
     * Spawn god entity at player's position
     */
    private static void spawnGodBody(ServerPlayer player, String godType, String agentId) {
        ServerLevel level = player.serverLevel();
        BlockPos pos = player.blockPosition();

        EntityType<?> entityType = getGodEntityType(godType);

        if (entityType == null) {
            DWMod.LOGGER.error("❌ Unknown god type: {}", godType);
            return;
        }

        // Create god entity
        Entity godEntity = entityType.create(level);

        if (godEntity == null) {
            DWMod.LOGGER.error("❌ Failed to create god entity: {}", godType);
            return;
        }

        // Position the god entity
        godEntity.moveTo(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5,
                player.getYRot(), player.getXRot());

        // Tag as god entity
        TaggedEntitySystem.tagEntity(godEntity, TaggedEntitySystem.TAG_DW_GOD);
        TaggedEntitySystem.setGodType(godEntity, godType);
        TaggedEntitySystem.setAIID(godEntity, agentId);
        TaggedEntitySystem.setDivinePower(godEntity, 100);
        TaggedEntitySystem.makeGenesisImmune(godEntity);

        // Link to player
        GOD_ENTITY_MAP.put(player.getUUID(), godEntity);

        // Spawn in world
        level.addFreshEntity(godEntity);

        // Register as god player
        DWNPCManager.registerGodPlayer(player, agentId, godType);

        // Make player invisible and invulnerable (they control the god body)
        player.setInvisible(true);
        player.setInvulnerable(true);
        player.getAbilities().mayfly = true;
        player.getAbilities().flying = true;
        player.onUpdateAbilities();

        DWMod.LOGGER.info("✅ Spawned god body: {} for player {} (Agent: {})",
                godType, player.getName().getString(), agentId);
    }

    /**
     * Map god type string to EntityType
     */
    private static EntityType<?> getGodEntityType(String godType) {
        return switch (godType) {
            case "ender_dragon", "dragon" -> EntityType.ENDER_DRAGON;
            case "wither" -> EntityType.WITHER;
            case "warden" -> EntityType.WARDEN;
            case "elder_guardian" -> EntityType.ELDER_GUARDIAN;
            case "oracle" -> EntityType.WANDERING_TRADER; // Oracle uses villager-like body
            case "creaking" -> EntityType.ZOMBIE; // Placeholder until Creaking exists
            default -> null;
        };
    }

    /**
     * Get god entity for a player
     */
    public static Entity getGodEntity(UUID playerUuid) {
        return GOD_ENTITY_MAP.get(playerUuid);
    }

    /**
     * Cleanup when player leaves
     */
    @SubscribeEvent
    public static void onPlayerLogout(PlayerEvent.PlayerLoggedOutEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer player)) return;

        UUID uuid = player.getUUID();
        Entity godEntity = GOD_ENTITY_MAP.get(uuid);

        if (godEntity != null) {
            godEntity.remove(Entity.RemovalReason.DISCARDED);
            GOD_ENTITY_MAP.remove(uuid);
            DWMod.LOGGER.info("🌟 Removed god entity for player: {}", player.getName().getString());
        }
    }
}