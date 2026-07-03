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
 *
 * FIX (3-way form cycle): /godtoggle broadcasts MorphSyncPacket with
 * mobType = "form:god" | "form:humanoid" | "form:disguise" — prefixed with
 * "form:" so existing morph-type handling (isMorphed(), getMorphType()) is
 * never misled by a form-change into thinking the god transformed into a
 * vanilla mob named "god" or "humanoid".  Form packets are identified by
 * the prefix and routed to spawnFormParticles() instead of spawnParticles().
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public class TransformationHandler {

    // playerUUID → current morph type ("" = original form).
    // form:* packets are NOT stored here — they don't represent a mob morph.
    private static final Map<UUID, String>  MORPH_STATE    = new HashMap<>();
    // playerUUID → ticks of particles remaining
    private static final Map<UUID, Integer> PARTICLE_TICKS = new HashMap<>();

    // Separate particle counter for form-change bursts so they don't
    // stomp on / get stomped by any concurrent mob-morph particle burst.
    private static final Map<UUID, Integer> FORM_PARTICLE_TICKS = new HashMap<>();
    private static final Map<UUID, String>  FORM_STATE          = new HashMap<>();

    @SubscribeEvent
    public static void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        Minecraft mc = Minecraft.getInstance();
        if (mc.level == null) return;

        // ── Drain pending morph events from cache ────────────────────────────
        MorphStateCache.MorphEvent evt;
        while ((evt = MorphStateCache.poll()) != null) {
            String mobType = evt.mobType();
            if (mobType != null && mobType.startsWith("form:")) {
                // 3-way form-cycle packet (god/humanoid/disguise)
                String form = mobType.substring(5);   // strip "form:"
                FORM_STATE.put(evt.playerUUID(), form);
                FORM_PARTICLE_TICKS.put(evt.playerUUID(), 40);
                DWClientMod.LOGGER.info("[Transform] {} → form:{}",
                        evt.playerUUID(), form);
            } else {
                // Normal mob-morph or revert packet
                MORPH_STATE.put(evt.playerUUID(), mobType);
                PARTICLE_TICKS.put(evt.playerUUID(), 60);
                DWClientMod.LOGGER.info("[Transform] {} → {}",
                        evt.playerUUID(),
                        (mobType == null || mobType.isEmpty())
                            ? "REVERTED (" + evt.godType() + ")" : mobType);
            }
        }

        // ── Play particles for recently-transformed players ──────────────────
        for (Player player : mc.level.players()) {
            UUID id = player.getUUID();

            Integer mobTicks = PARTICLE_TICKS.get(id);
            if (mobTicks != null && mobTicks > 0) {
                String mobType = MORPH_STATE.getOrDefault(id, "");
                if (mobType.isEmpty()) {
                    mobType = player.getPersistentData().getString("dw_god_type");
                }
                spawnParticles(player, mobType);
                PARTICLE_TICKS.put(id, mobTicks - 1);
            }

            Integer formTicks = FORM_PARTICLE_TICKS.get(id);
            if (formTicks != null && formTicks > 0) {
                spawnFormParticles(player, FORM_STATE.getOrDefault(id, "god"));
                FORM_PARTICLE_TICKS.put(id, formTicks - 1);
            }
        }

        // ── Clean up disconnected players ────────────────────────────────────
        MORPH_STATE.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
        PARTICLE_TICKS.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
        FORM_STATE.keySet().removeIf(uuid ->
                mc.level.players().stream().noneMatch(p -> p.getUUID().equals(uuid)));
        FORM_PARTICLE_TICKS.keySet().removeIf(uuid ->
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

    /**
     * Cosmetic burst played when a god cycles between god/humanoid/disguise forms.
     * Distinct from spawnParticles() so the two counters don't fight each other.
     */
    private static void spawnFormParticles(Player player, String form) {
        if (player.level().random.nextFloat() > 0.4f) return;
        double x = player.getX() + (player.level().random.nextDouble() - 0.5) * 1.5;
        double y = player.getY() + player.level().random.nextDouble() * 2.5;
        double z = player.getZ() + (player.level().random.nextDouble() - 0.5) * 1.5;
        var particle = switch (form == null ? "" : form) {
            case "humanoid" -> ParticleTypes.ENCHANT;
            case "disguise" -> ParticleTypes.MYCELIUM;
            default         -> ParticleTypes.REVERSE_PORTAL;   // "god" form
        };
        player.level().addParticle(particle, x, y, z, 0, 0.2, 0);
    }

    public static boolean isMorphed(UUID playerUUID) {
        String s = MORPH_STATE.get(playerUUID);
        return s != null && !s.isEmpty();
    }

    public static String getMorphType(UUID playerUUID) {
        return MORPH_STATE.getOrDefault(playerUUID, "");
    }

    /** Returns the current form ("god" | "humanoid" | "disguise") for a player. */
    public static String getGodForm(UUID playerUUID) {
        return FORM_STATE.getOrDefault(playerUUID, "god");
    }

    public static void reset() {
        MORPH_STATE.clear();
        PARTICLE_TICKS.clear();
        FORM_STATE.clear();
        FORM_PARTICLE_TICKS.clear();
        MorphStateCache.clear();
    }
}