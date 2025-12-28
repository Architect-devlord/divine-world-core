// src/main/java/com/divineworld/client/TransformationHandler.java
package com.divineworld.client;

import com.divineworld.client.chat.ClientChatBubbleHandler;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.AbstractClientPlayer;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Transformation Handler - Client-side
 * Monitors god entities for transformation state changes
 * Spawns particles and updates visual effects
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public class TransformationHandler {

    // Track transformation states
    private static final Map<UUID, Boolean> TRANSFORMATION_STATES = new HashMap<>();
    private static final Map<UUID, Integer> TRANSFORMATION_PARTICLES = new HashMap<>();

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;

        // Check all players for god transformation state changes
        for (Player player : mc.level.players()) {
            if (!player.getPersistentData().contains("dw_god")) continue;

            UUID playerId = player.getUUID();
            boolean currentlyDisguised = player.getPersistentData().getBoolean("dw_disguised");
            Boolean previousState = TRANSFORMATION_STATES.get(playerId);

            // State changed
            if (previousState == null || previousState != currentlyDisguised) {
                TRANSFORMATION_STATES.put(playerId, currentlyDisguised);

                // Start particle effect
                TRANSFORMATION_PARTICLES.put(playerId, 60); // 3 seconds of particles

                DWClientMod.LOGGER.info("God transformation detected: {} -> {}",
                        player.getName().getString(),
                        currentlyDisguised ? "DISGUISED" : "GOD FORM");
            }

            // Spawn transformation particles
            Integer particleTicks = TRANSFORMATION_PARTICLES.get(playerId);
            if (particleTicks != null && particleTicks > 0) {
                spawnTransformationParticles(player);
                TRANSFORMATION_PARTICLES.put(playerId, particleTicks - 1);
            }
        }

        // Cleanup disconnected players
        TRANSFORMATION_STATES.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
        TRANSFORMATION_PARTICLES.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
    }

    private static void spawnTransformationParticles(Player player) {
        if (player.level().random.nextFloat() > 0.3f) return;

        // Spawn particles around the entity
        double x = player.getX() + (player.level().random.nextDouble() - 0.5) * 2.0;
        double y = player.getY() + player.level().random.nextDouble() * 2.0;
        double z = player.getZ() + (player.level().random.nextDouble() - 0.5) * 2.0;

        // Different particle types based on god type
        String godType = player.getPersistentData().getString("dw_god_type");

        var particleType = switch (godType) {
            case "ender_dragon" -> ParticleTypes.DRAGON_BREATH;
            case "wither" -> ParticleTypes.SMOKE;
            case "warden" -> ParticleTypes.SCULK_SOUL;
            case "elder_guardian" -> ParticleTypes.BUBBLE;
            case "creaking" -> ParticleTypes.SPORE_BLOSSOM_AIR;
            case "oracle" -> ParticleTypes.ENCHANT;
            default -> ParticleTypes.PORTAL;
        };

        player.level().addParticle(particleType, x, y, z, 0, 0.3, 0);
    }

    public static void reset() {
        TRANSFORMATION_STATES.clear();
        TRANSFORMATION_PARTICLES.clear();
    }
}