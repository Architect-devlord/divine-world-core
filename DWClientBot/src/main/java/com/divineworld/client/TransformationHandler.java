package com.divineworld.client;

import com.divineworld.client.network.MorphStateCache;
import net.minecraft.client.Minecraft;
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
 * Transformation Handler — DWClientBot
 * =====================================
 * Drains MorphStateCache (same mod) each ClientTickEvent and plays
 * cosmetic particle bursts for transformed players.
 *
 * Zero imports from the server mod.  The visual model change itself is the
 * entity swap done server-side by GodSpawnHandler.replaceGodBody() — all
 * clients already see it because it's a real world entity.  This class
 * only adds the particle effect on top.
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public class TransformationHandler {

    // playerUUID → current morph type ("" = original form)
    private static final Map<UUID, String>  MORPH_STATE    = new HashMap<>();
    // playerUUID → ticks of particles remaining
    private static final Map<UUID, Integer> PARTICLE_TICKS = new HashMap<>();

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;

        // ── Drain pending morph events from cache ────────────────────────────
        MorphStateCache.MorphEvent evt;
        while ((evt = MorphStateCache.poll()) != null) {
            MORPH_STATE.put(evt.playerUUID(), evt.mobType());
            PARTICLE_TICKS.put(evt.playerUUID(), 60); // 3-second burst
            DWClientMod.LOGGER.info("[Transform] {} → {}",
                    evt.playerUUID(),
                    evt.mobType().isEmpty() ? "REVERTED (" + evt.godType() + ")" : evt.mobType());
        }

        // ── Play particles for recently-transformed players ──────────────────
        for (Player player : mc.level.players()) {
            UUID id = player.getUUID();
            Integer remaining = PARTICLE_TICKS.get(id);
            if (remaining == null || remaining <= 0) continue;

            String mobType = MORPH_STATE.getOrDefault(id, "");
            if (mobType.isEmpty()) {
                mobType = player.getPersistentData().getString("dw_god_type");
            }
            spawnParticles(player, mobType);
            PARTICLE_TICKS.put(id, remaining - 1);
        }

        // ── Clean up disconnected players ────────────────────────────────────
        MORPH_STATE.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
        PARTICLE_TICKS.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
    }

    private static void spawnParticles(Player player, String mobType) {
        if (player.level().random.nextFloat() > 0.35f) return;
        double x = player.getX() + (player.level().random.nextDouble() - 0.5) * 2.0;
        double y = player.getY() + player.level().random.nextDouble() * 2.0;
        double z = player.getZ() + (player.level().random.nextDouble() - 0.5) * 2.0;
        var particle = switch (mobType == null ? "" : mobType) {
            case "ender_dragon", "dragon" -> ParticleTypes.DRAGON_BREATH;
            case "wither"                 -> ParticleTypes.SMOKE;
            case "warden"                 -> ParticleTypes.SCULK_SOUL;
            case "elder_guardian"         -> ParticleTypes.BUBBLE;
            case "creaking"               -> ParticleTypes.SPORE_BLOSSOM_AIR;
            case "oracle"                 -> ParticleTypes.ENCHANT;
            default                       -> ParticleTypes.PORTAL;
        };
        player.level().addParticle(particle, x, y, z, 0, 0.25, 0);
    }

    public static boolean isMorphed(UUID playerUUID) {
        String s = MORPH_STATE.get(playerUUID);
        return s != null && !s.isEmpty();
    }

    public static String getMorphType(UUID playerUUID) {
        return MORPH_STATE.getOrDefault(playerUUID, "");
    }

    public static void reset() {
        MORPH_STATE.clear();
        PARTICLE_TICKS.clear();
        MorphStateCache.clear();
    }
}