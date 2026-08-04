// src/main/java/com/divineworld/commands/ServerGodAbilityExecutor.java
// DivineWorld server mod
package com.divineworld.commands;

import com.divineworld.DWMod;
import com.divineworld.events.GodSpawnHandler;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.effect.MobEffectInstance;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntityType;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.WitherSkeleton;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.List;

/**
 * ServerGodAbilityExecutor — all server-side ability effects.
 *
 * KEY CHANGES
 * -----------
 * 1. execute() dispatches via dw_original_god_type instead of the current
 *    dw_god_type so abilities work correctly across transforms (a Warden
 *    transformed into a Zombie still uses Warden abilities, not Zombie).
 *
 * 2. Warden burrow: auto-emerge removed. The AI agent now controls when
 *    to surface by sending "emerge". While burrowed the puppet is:
 *      - invisible              (setInvisible true)
 *      - invulnerable           (abilities.invulnerable = true — no suffocation)
 *      - physics disabled       (noPhysics = true)
 *    dw_burrowed NBT flag marks the state so logout handler can clean up.
 *
 * 3. Oracle god is now an Evoker body. Added "summon_vexes" and
 *    "summon_fangs" as server-side Oracle abilities alongside the existing
 *    wisdom/knowledge/healing powers.
 *
 * 4. Abilities include "transform_<mob>" and "revert" cases so Python AI
 *    can trigger transforms via the action frame channel.
 */
public class ServerGodAbilityExecutor {

    // =========================================================================
    // Entry point — dispatch via ORIGINAL god type
    // =========================================================================

    public static void execute(ServerPlayer godPlayer, String ability, ServerLevel level) {
        // FIX: use dw_original_god_type so abilities work after transforms.
        // dw_god_type changes on every replaceGodBody call; dw_original_god_type
        // is written once at spawn and never changed.
        String originalGodType = godPlayer.getPersistentData()
                .getString("dw_original_god_type");
        if (originalGodType == null || originalGodType.isEmpty()) {
            // Fallback for pre-fix saves
            originalGodType = TaggedEntitySystem.extractGodType(godPlayer);
        }
        if (originalGodType == null || originalGodType.isEmpty()) {
            DWMod.LOGGER.warn("[AbilityExecutor] No god type on player {}",
                    godPlayer.getName().getString());
            return;
        }

        String currentGodType = TaggedEntitySystem.extractGodType(godPlayer);
        DWMod.LOGGER.info("[AbilityExecutor] {} (original={} current={}) → {}",
                godPlayer.getName().getString(), originalGodType, currentGodType, ability);

        Entity bodyEntity    = GodSpawnHandler.getGodEntity(godPlayer.getUUID());
        LivingEntity attacker = (bodyEntity instanceof LivingEntity le) ? le : godPlayer;

        // Transform abilities are handled here before the type-dispatch so they
        // work regardless of the original god type.
        if (ability.startsWith("transform_")) {
            String targetMob = ability.substring("transform_".length());
            com.divineworld.events.GodDisguiseHandler.applyTransform(godPlayer, targetMob, level);
            return;
        }
        if ("revert".equals(ability)) {
            com.divineworld.events.GodDisguiseHandler.removeTransform(godPlayer);
            return;
        }

        // Dispatch via ORIGINAL god type
        switch (originalGodType) {
            case "warden"                 -> executeWardenAbility(godPlayer, attacker, ability, level);
            case "wither"                 -> executeWitherAbility(godPlayer, attacker, ability, level);
            case "ender_dragon", "dragon" -> executeDragonAbility(godPlayer, attacker, ability, level);
            case "elder_guardian"         -> executeElderGuardianAbility(godPlayer, attacker, ability, level);
            case "oracle"                 -> executeOracleAbility(godPlayer, attacker, ability, level);
            case "creaking"               -> executeCreakingAbility(godPlayer, attacker, ability, level);
            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown original god type: {}", originalGodType);
        }
    }

    // =========================================================================
    // Cooldown helpers  (NBT key prefix "cd_")
    // =========================================================================

    private static boolean isOnCooldown(ServerPlayer player, String key) {
        return player.getPersistentData().getInt("cd_" + key) > 0;
    }

    private static void setCooldown(ServerPlayer player, String key, int ticks) {
        player.getPersistentData().putInt("cd_" + key, ticks);
    }

    public static void tickAbilityCooldowns(ServerPlayer player) {
        var nbt = player.getPersistentData();
        for (String key : nbt.getAllKeys()) {
            if (key.startsWith("cd_")) {
                int v = nbt.getInt(key);
                if (v > 0) nbt.putInt(key, v - 1);
            }
        }
    }

    // =========================================================================
    // Shared utilities
    // =========================================================================

    private static List<LivingEntity> nearbyLiving(ServerPlayer origin, double radius) {
        AABB box = origin.getBoundingBox().inflate(radius);
        return origin.level().getEntitiesOfClass(LivingEntity.class, box,
                e -> e != origin && e.isAlive());
    }

    private static void ringParticles(ServerLevel level, Vec3 center,
                                      net.minecraft.core.particles.ParticleOptions particle,
                                      int count, double radius, double yOffset) {
        for (int i = 0; i < count; i++) {
            double angle = (Math.PI * 2 * i) / count;
            double x = center.x + Math.cos(angle) * radius;
            double z = center.z + Math.sin(angle) * radius;
            level.sendParticles(particle, x, center.y + yOffset, z, 1, 0, 0, 0, 0);
        }
    }

    // =========================================================================
    // WARDEN abilities
    // =========================================================================

    private static void executeWardenAbility(ServerPlayer player, LivingEntity attacker,
                                             String ability, ServerLevel level) {
        switch (ability) {

            case "sonic_boom" -> {
                if (isOnCooldown(player, "sonic_boom")) return;
                Vec3 look  = player.getLookAngle();
                Vec3 start = player.getEyePosition();
                for (double d = 0; d <= 30; d += 0.5) {
                    Vec3 point  = start.add(look.scale(d));
                    AABB hitBox = new AABB(point.x-1.5, point.y-1.5, point.z-1.5,
                            point.x+1.5, point.y+1.5, point.z+1.5);
                    for (LivingEntity target : level.getEntitiesOfClass(LivingEntity.class, hitBox,
                            e -> e != player && e.isAlive())) {
                        target.hurt(level.damageSources().magic(), 25.0f);
                        Vec3 knock = target.position().subtract(player.position()).normalize();
                        target.push(knock.x * 3, 1.0, knock.z * 3);
                    }
                    if (d % 1.0 < 0.5) {
                        level.sendParticles(ParticleTypes.SONIC_BOOM,
                                point.x, point.y, point.z, 1, 0, 0, 0, 0);
                    }
                }
                setCooldown(player, "sonic_boom", 100);
            }

            case "darkness" -> {
                if (isOnCooldown(player, "darkness")) return;
                for (LivingEntity target : nearbyLiving(player, 20)) {
                    target.addEffect(new MobEffectInstance(MobEffects.BLINDNESS, 300, 0, false, true));
                    target.addEffect(new MobEffectInstance(MobEffects.DARKNESS,  300, 0, false, true));
                }
                ringParticles(level, player.position(), ParticleTypes.SCULK_SOUL, 60, 10, 1);
                setCooldown(player, "darkness", 300);
            }

            case "sniff" -> {
                if (isOnCooldown(player, "sniff")) return;
                for (LivingEntity target : nearbyLiving(player, 32)) {
                    if (target.getDeltaMovement().length() > 0.01) {
                        level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                                target.getX(), target.getY() + 1, target.getZ(),
                                15, 0.3, 0.2, 0.3, 0);
                    }
                }
                setCooldown(player, "sniff", 40);
            }

            // FIX: No auto-emerge — the AI agent sends "emerge" when ready.
            // While burrowed the puppet is invulnerable (prevents suffocation).
            case "burrow" -> {
                if (isOnCooldown(player, "burrow")) return;
                player.setInvisible(true);
                player.noPhysics = true;
                player.getAbilities().invulnerable = true;   // prevent suffocation damage
                player.onUpdateAbilities();
                player.setDeltaMovement(0, -0.3, 0);
                // Also hide the body entity
                Entity body = GodSpawnHandler.getGodEntity(player.getUUID());
                if (body != null) body.setInvisible(true);
                // Mark burrowed — logout handler uses this to clean up
                player.getPersistentData().putBoolean("dw_burrowed", true);
                level.sendParticles(ParticleTypes.SCULK_SOUL,
                        player.getX(), player.getY(), player.getZ(),
                        40, 0.6, 0.2, 0.6, 0.02);
                setCooldown(player, "burrow", 200);
                DWMod.LOGGER.info("[Warden] {} burrowed — waiting for AI emerge signal",
                        player.getName().getString());
            }

            // AI-controlled emerge — no timer, agent decides when to surface
            case "emerge" -> {
                if (!player.getPersistentData().getBoolean("dw_burrowed")) return;
                player.getPersistentData().putBoolean("dw_burrowed", false);
                player.setInvisible(false);
                player.noPhysics = false;
                player.getAbilities().invulnerable = false;
                player.onUpdateAbilities();
                // Restore body visibility
                Entity body = GodSpawnHandler.getGodEntity(player.getUUID());
                if (body != null) body.setInvisible(false);
                player.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 60, 2));
                for (LivingEntity target : nearbyLiving(player, 5)) {
                    target.hurt(level.damageSources().mobAttack(attacker), 20.0f);
                    Vec3 knock = target.position().subtract(player.position()).normalize();
                    target.push(knock.x * 2, 1.5, knock.z * 2);
                }
                level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                        player.getX(), player.getY(), player.getZ(),
                        80, 1.5, 0.2, 1.5, 0.1);
                DWMod.LOGGER.info("[Warden] {} emerged", player.getName().getString());
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown warden ability: {}", ability);
        }
    }

    // =========================================================================
    // WITHER abilities
    // =========================================================================

    private static void executeWitherAbility(ServerPlayer player, LivingEntity attacker,
                                             String ability, ServerLevel level) {
        switch (ability) {

            case "wither_skull", "blue_skull" -> {
                if (isOnCooldown(player, "wither_skull")) return;
                Vec3 look = player.getLookAngle();
                for (LivingEntity target : nearbyLiving(player, 20)) {
                    Vec3 toTarget = target.position().subtract(player.position()).normalize();
                    if (look.dot(toTarget) > 0.9) {
                        target.hurt(level.damageSources().magic(), 8.0f);
                        target.addEffect(new MobEffectInstance(MobEffects.WITHER, 100, 1, false, true));
                    }
                }
                for (int i = 1; i <= 10; i++) {
                    Vec3 p = player.getEyePosition().add(look.scale(i * 2));
                    level.sendParticles(ParticleTypes.SOUL_FIRE_FLAME,
                            p.x, p.y, p.z, 3, 0.1, 0.1, 0.1, 0);
                }
                setCooldown(player, "wither_skull", 20);
            }

            case "dash" -> {
                if (isOnCooldown(player, "dash")) return;
                Vec3 look    = player.getLookAngle();
                double power = 2.5;
                player.setDeltaMovement(look.x * power, 0.5, look.z * power);
                player.hurtMarked = true;
                Entity godEntity = GodSpawnHandler.getGodEntity(player.getUUID());
                if (godEntity != null) {
                    godEntity.setDeltaMovement(look.x * power, 0.5, look.z * power);
                }
                level.sendParticles(ParticleTypes.LARGE_SMOKE,
                        player.getX(), player.getY() + 1, player.getZ(),
                        20, 0.5, 0.3, 0.5, 0.1);
                setCooldown(player, "dash", 60);
            }

            case "summon_wither_skeletons" -> {
                if (isOnCooldown(player, "summon_wither_skeletons")) return;
                for (int i = 0; i < 3; i++) {
                    WitherSkeleton skeleton = EntityType.WITHER_SKELETON.create(level);
                    if (skeleton != null) {
                        double angle = (Math.PI * 2 / 3) * i;
                        skeleton.moveTo(
                                player.getX() + Math.cos(angle) * 3, player.getY(),
                                player.getZ() + Math.sin(angle) * 3,
                                (float)(angle * 180 / Math.PI), 0);
                        level.addFreshEntity(skeleton);
                    }
                }
                level.sendParticles(ParticleTypes.LARGE_SMOKE,
                        player.getX(), player.getY() + 1, player.getZ(),
                        30, 1.5, 0.5, 1.5, 0.05);
                setCooldown(player, "summon_wither_skeletons", 200);
            }

            case "explosion" -> {
                if (isOnCooldown(player, "explosion")) return;
                level.explode(attacker, player.getX(), player.getY() + 1, player.getZ(),
                        4.0f, false, net.minecraft.world.level.Level.ExplosionInteraction.NONE);
                setCooldown(player, "explosion", 160);
            }

            case "fly" -> {
                if (isOnCooldown(player, "fly")) return;
                boolean nowFlying = player.getAbilities().flying;
                player.getAbilities().flying = !nowFlying;
                player.onUpdateAbilities();
                setCooldown(player, "fly", 20);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown wither ability: {}", ability);
        }
    }

    // =========================================================================
    // ENDER DRAGON abilities
    // =========================================================================

    private static void executeDragonAbility(ServerPlayer player, LivingEntity attacker,
                                             String ability, ServerLevel level) {
        switch (ability) {

            case "dragon_breath" -> {
                if (isOnCooldown(player, "dragon_breath")) return;
                Vec3 breathPos = player.position().add(player.getLookAngle().scale(3));
                for (LivingEntity target : nearbyLiving(player, 8)) {
                    target.hurt(level.damageSources().dragonBreath(), 6.0f);
                    target.setSecondsOnFire(5);
                }
                level.sendParticles(ParticleTypes.DRAGON_BREATH,
                        breathPos.x, breathPos.y + 0.5, breathPos.z,
                        60, 1.5, 0.8, 1.5, 0.04);
                setCooldown(player, "dragon_breath", 100);
            }

            case "fireball" -> {
                if (isOnCooldown(player, "fireball")) return;
                Vec3 look = player.getLookAngle();
                net.minecraft.world.entity.projectile.DragonFireball fireball =
                        new net.minecraft.world.entity.projectile.DragonFireball(
                                level, attacker, look.x, look.y, look.z);
                fireball.moveTo(player.getX(), player.getEyeY(), player.getZ());
                level.addFreshEntity(fireball);
                setCooldown(player, "fireball", 40);
            }

            case "perch" -> {
                if (isOnCooldown(player, "perch")) return;
                player.getAbilities().flying = !player.getAbilities().flying;
                player.onUpdateAbilities();
                setCooldown(player, "perch", 20);
            }

            case "fly" -> {
                if (isOnCooldown(player, "fly")) return;
                player.getAbilities().flying = true;
                player.getAbilities().mayfly = true;
                player.onUpdateAbilities();
                setCooldown(player, "fly", 20);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown dragon ability: {}", ability);
        }
    }

    // =========================================================================
    // ELDER GUARDIAN abilities
    // =========================================================================

    private static void executeElderGuardianAbility(ServerPlayer player, LivingEntity attacker,
                                                    String ability, ServerLevel level) {
        switch (ability) {

            case "mining_fatigue" -> {
                if (isOnCooldown(player, "mining_fatigue")) return;
                for (LivingEntity target : nearbyLiving(player, 30)) {
                    target.addEffect(new MobEffectInstance(MobEffects.DIG_SLOWDOWN, 1200, 2, false, true));
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 48, 15, 1);
                setCooldown(player, "mining_fatigue", 1200);
            }

            case "laser_beam" -> {
                if (isOnCooldown(player, "laser_beam")) return;
                level.sendParticles(ParticleTypes.CRIT,
                        player.getX(), player.getEyeY(), player.getZ(),
                        20, 0.2, 0.2, 0.2, 0.1);
                DWMod.getInstance().scheduleTask(() -> {
                    Vec3 look  = player.getLookAngle();
                    Vec3 start = player.getEyePosition();
                    for (double d = 0; d <= 50; d += 0.5) {
                        Vec3 p      = start.add(look.scale(d));
                        AABB hitBox = new AABB(p.x-1, p.y-1, p.z-1, p.x+1, p.y+1, p.z+1);
                        for (LivingEntity t : level.getEntitiesOfClass(LivingEntity.class, hitBox,
                                e -> e != player && e.isAlive())) {
                            t.hurt(level.damageSources().magic(), 50.0f);
                            t.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SLOWDOWN, 60, 2));
                        }
                        if (d % 1.0 < 0.5) {
                            level.sendParticles(ParticleTypes.END_ROD, p.x, p.y, p.z, 1, 0, 0, 0, 0);
                        }
                    }
                }, 40);
                setCooldown(player, "laser_beam", 60);
            }

            case "thorn_attack" -> {
                if (isOnCooldown(player, "thorn_attack")) return;
                for (LivingEntity t : nearbyLiving(player, 4)) {
                    t.hurt(level.damageSources().thorns(attacker), 12.0f);
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 24, 4, 0.5);
                setCooldown(player, "thorn_attack", 20);
            }

            case "guardian_spikes" -> {
                if (isOnCooldown(player, "guardian_spikes")) return;
                for (LivingEntity t : nearbyLiving(player, 3)) {
                    t.hurt(level.damageSources().thorns(attacker), 12.0f);
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 24, 3, 0.5);
                setCooldown(player, "guardian_spikes", 400);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown elder_guardian ability: {}", ability);
        }
    }

    // =========================================================================
    // ORACLE abilities  (Evoker body — Vex/fang summons are oracle powers)
    // =========================================================================

    private static void executeOracleAbility(ServerPlayer player, LivingEntity attacker,
                                             String ability, ServerLevel level) {
        switch (ability) {

            // ── Evoker-native powers (Oracle controls these as god abilities) ──

            case "summon_vexes" -> {
                if (isOnCooldown(player, "summon_vexes")) return;
                for (int i = 0; i < 3; i++) {
                    net.minecraft.world.entity.monster.Vex vex =
                            EntityType.VEX.create(level);
                    if (vex != null) {
                        double angle = (Math.PI * 2 * i) / 3;
                        vex.moveTo(player.getX() + Math.cos(angle) * 2,
                                player.getY() + 1,
                                player.getZ() + Math.sin(angle) * 2, 0, 0);
                        // FIX: setOwner(Mob) — attacker is LivingEntity but god body
                        // entities (Evoker, Warden, Wither…) all extend Mob.
                        // If for any reason attacker is not a Mob (e.g. the fallback
                        // godPlayer ServerPlayer), skip setOwner; the vex still spawns.
                        if (attacker instanceof net.minecraft.world.entity.Mob mob) {
                            vex.setOwner(mob);
                        }
                        vex.setLimitedLife(40 * 20);   // 40 seconds
                        level.addFreshEntity(vex);
                    }
                }
                ringParticles(level, player.position(), ParticleTypes.ENCHANT, 30, 3, 1);
                setCooldown(player, "summon_vexes", 200);
            }

            case "summon_fangs" -> {
                if (isOnCooldown(player, "summon_fangs")) return;
                Vec3 look = player.getLookAngle();
                for (int i = 0; i < 10; i++) {
                    Vec3 pos = player.position().add(look.scale(i * 1.2));
                    net.minecraft.world.entity.projectile.EvokerFangs fangs =
                            EntityType.EVOKER_FANGS.create(level);
                    if (fangs != null) {
                        fangs.moveTo(pos.x, pos.y, pos.z, 0, 0);
                        fangs.setOwner(attacker);
                        level.addFreshEntity(fangs);
                    }
                }
                setCooldown(player, "summon_fangs", 80);
            }

            // ── Oracle-unique god powers ──────────────────────────────────────

            case "wisdom_aura" -> {
                if (isOnCooldown(player, "wisdom_aura")) return;
                for (LivingEntity ally : nearbyLiving(player, 15)) {
                    ally.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 600, 1, false, true));
                    ally.addEffect(new MobEffectInstance(MobEffects.DAMAGE_BOOST,   600, 1, false, true));
                }
                ringParticles(level, player.position(), ParticleTypes.ENCHANT, 48, 7, 1);
                setCooldown(player, "wisdom_aura", 600);
            }

            case "foresight" -> {
                if (isOnCooldown(player, "foresight")) return;
                for (LivingEntity target : nearbyLiving(player, 30)) {
                    level.sendParticles(ParticleTypes.END_ROD,
                            target.getX(), target.getY() + 2, target.getZ(),
                            5, 0.1, 0.2, 0.1, 0);
                }
                setCooldown(player, "foresight", 100);
            }

            case "teleport" -> {
                if (isOnCooldown(player, "teleport")) return;
                Vec3 dest = player.position().add(player.getLookAngle().scale(20));
                player.teleportTo(dest.x, dest.y, dest.z);
                Entity godEntity = GodSpawnHandler.getGodEntity(player.getUUID());
                if (godEntity != null) {
                    godEntity.moveTo(dest.x, dest.y, dest.z, player.getYRot(), player.getXRot());
                }
                level.sendParticles(ParticleTypes.PORTAL,
                        dest.x, dest.y + 1, dest.z, 40, 0.5, 0.8, 0.5, 0.1);
                setCooldown(player, "teleport", 60);
            }

            case "healing_wave" -> {
                if (isOnCooldown(player, "healing_wave")) return;
                for (LivingEntity ally : nearbyLiving(player, 20)) {
                    ally.heal(20.0f);
                }
                player.heal(20.0f);
                ringParticles(level, player.position(), ParticleTypes.HEART, 32, 10, 1);
                setCooldown(player, "healing_wave", 400);
            }

            case "knowledge_beam" -> {
                if (isOnCooldown(player, "knowledge_beam")) return;
                Vec3 look  = player.getLookAngle();
                Vec3 start = player.getEyePosition();
                for (double d = 0; d <= 40; d += 0.5) {
                    Vec3 p      = start.add(look.scale(d));
                    AABB hitBox = new AABB(p.x-0.8, p.y-0.8, p.z-0.8,
                            p.x+0.8, p.y+0.8, p.z+0.8);
                    for (LivingEntity t : level.getEntitiesOfClass(LivingEntity.class, hitBox,
                            e -> e != player && e.isAlive())) {
                        t.hurt(level.damageSources().magic(), 40.0f);
                        t.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SLOWDOWN, 80, 3));
                    }
                    if (d % 1.0 < 0.5) {
                        level.sendParticles(ParticleTypes.END_ROD, p.x, p.y, p.z, 1, 0, 0, 0, 0);
                    }
                }
                setCooldown(player, "knowledge_beam", 200);
            }

            case "fly" -> {
                if (isOnCooldown(player, "fly")) return;
                player.getAbilities().flying = !player.getAbilities().flying;
                player.getAbilities().mayfly  = true;
                player.onUpdateAbilities();
                level.sendParticles(ParticleTypes.ENCHANT,
                        player.getX(), player.getY() + 1, player.getZ(),
                        20, 0.5, 0.8, 0.5, 0.1);
                setCooldown(player, "fly", 20);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown oracle ability: {}", ability);
        }
    }

    // =========================================================================
    // CREAKING abilities
    // =========================================================================

    private static void executeCreakingAbility(ServerPlayer player, LivingEntity attacker,
                                               String ability, ServerLevel level) {
        // Helper: get the Creaking body entity for animation triggers
        java.util.UUID uuid = player.getUUID();

        switch (ability) {

            // ── Tentacle whip — damage + animation ───────────────────────
            case "tentacle_whip" -> {
                if (isOnCooldown(player, "tentacle_whip")) return;
                boolean tentaclesOut = isBodyTentaclesDeployed(uuid);
                for (LivingEntity target : nearbyLiving(player, 8)) {
                    target.hurt(level.damageSources().mobAttack(attacker), 12.0f);
                    Vec3 knock = target.position().subtract(player.position()).normalize();
                    target.push(knock.x * 2, 0.5, knock.z * 2);
                }
                level.sendParticles(ParticleTypes.SPORE_BLOSSOM_AIR,
                        player.getX(), player.getY() + 1, player.getZ(),
                        50, 2, 0.5, 2, 0.03);
                // FIX CF-1: trigger animation on body entity
                // Use tentacle_attack when tentacles are deployed, attack otherwise
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller",
                        tentaclesOut ? "tentacle_attack" : "attack");
                setCooldown(player, "tentacle_whip", 40);
            }

            // ── Life steal — grab and drain ───────────────────────────────
            case "life_steal" -> {
                if (isOnCooldown(player, "life_steal")) return;
                float stolen = 0;
                for (LivingEntity target : nearbyLiving(player, 8)) {
                    if (target.getHealth() / target.getMaxHealth() < 0.2f) {
                        target.hurt(level.damageSources().magic(), 15.0f);
                        stolen += 15.0f;
                    }
                }
                if (stolen > 0) player.heal(stolen * 0.5f);
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "grab_eat");
                setCooldown(player, "life_steal", 80);
            }

            // ── Deploy tentacles ──────────────────────────────────────────
            case "deploy_tentacles" -> {
                if (isOnCooldown(player, "deploy_tentacles")) return;
                setBodyTentaclesDeployed(uuid, true);
                for (LivingEntity target : nearbyLiving(player, 6)) {
                    target.hurt(level.damageSources().magic(), 8.0f);
                    target.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SLOWDOWN, 60, 3));
                }
                level.sendParticles(ParticleTypes.SPORE_BLOSSOM_AIR,
                        player.getX(), player.getY() + 1, player.getZ(),
                        40, 1.5, 0.5, 1.5, 0.02);
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "tentacles_out");
                setCooldown(player, "deploy_tentacles", 100);
            }

            // ── Retract tentacles ─────────────────────────────────────────
            case "retract_tentacles" -> {
                if (isOnCooldown(player, "retract_tentacles")) return;
                setBodyTentaclesDeployed(uuid, false);
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "tentacles_retract");
                setCooldown(player, "retract_tentacles", 40);
            }

            // ── Underground / burrow — AI controls emerge ─────────────────
            case "toggle_underground", "burrow" -> {
                if (isOnCooldown(player, "burrow")) return;
                // Puppet invulnerability + no physics — AICreakingEntity handles the
                // body's own visibility via setUnderground(). Matches what Warden's
                // burrow already does for the puppet (see executeWardenAbility above);
                // this call site was missing noPhysics, leaving the invisible puppet
                // still fully subject to gravity/collision while nominally burrowed.
                player.getAbilities().invulnerable = true;
                player.noPhysics = true;
                player.onUpdateAbilities();
                player.getPersistentData().putBoolean("dw_burrowed", true);
                setBodyUnderground(uuid, true);
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "burrow");
                level.sendParticles(ParticleTypes.ASH,
                        player.getX(), player.getY(), player.getZ(), 30, 0.5, 0.2, 0.5, 0.05);
                setCooldown(player, "burrow", 200);
                DWMod.LOGGER.info("[Creaking] {} burrowed — AI controls emerge", player.getName().getString());
            }

            // ── Emerge — AI sends this when ready to surface ──────────────
            case "emerge", "dig_out" -> {
                if (!player.getPersistentData().getBoolean("dw_burrowed")) return;
                player.getPersistentData().putBoolean("dw_burrowed", false);
                player.getAbilities().invulnerable = false;
                player.noPhysics = false;
                player.onUpdateAbilities();
                setBodyUnderground(uuid, false);
                GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "dig_out");
                for (LivingEntity target : nearbyLiving(player, 5)) {
                    target.hurt(level.damageSources().mobAttack(attacker), 18.0f);
                    Vec3 knock = target.position().subtract(player.position()).normalize();
                    target.push(knock.x * 2.5, 1.5, knock.z * 2.5);
                }
                level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                        player.getX(), player.getY(), player.getZ(), 60, 1, 0.2, 1, 0.1);
                DWMod.LOGGER.info("[Creaking] {} emerged", player.getName().getString());
            }

            // ── Ceiling mode — wall-climb entrance leap ───────────────────
            case "toggle_ceiling" -> {
                if (isOnCooldown(player, "toggle_ceiling")) return;
                boolean currentlyUp = isBodyOnCeiling(uuid);
                if (!currentlyUp) {
                    player.addEffect(new MobEffectInstance(MobEffects.LEVITATION, 60, 3));
                    player.noPhysics = true;
                    setBodyOnCeiling(uuid, true);
                    GodSpawnHandler.triggerGodAnimation(uuid, "ability_controller", "tentacle_jump");
                } else {
                    player.removeEffect(MobEffects.LEVITATION);
                    player.noPhysics = false;
                    setBodyOnCeiling(uuid, false);
                }
                level.sendParticles(ParticleTypes.ASH,
                        player.getX(), player.getY(), player.getZ(), 30, 0.5, 0.2, 0.5, 0.05);
                setCooldown(player, "toggle_ceiling", 40);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown creaking ability: {}", ability);
        }
    }

    // ── Body entity state helpers ─────────────────────────────────────────────

    private static com.divineworld.entity.AICreakingEntity getCreakingBody(java.util.UUID uuid) {
        net.minecraft.world.entity.Entity e = GodSpawnHandler.getGodEntity(uuid);
        return e instanceof com.divineworld.entity.AICreakingEntity c ? c : null;
    }

    private static boolean isBodyTentaclesDeployed(java.util.UUID uuid) {
        com.divineworld.entity.AICreakingEntity c = getCreakingBody(uuid);
        return c != null && c.isTentaclesDeployed();
    }

    private static void setBodyTentaclesDeployed(java.util.UUID uuid, boolean v) {
        com.divineworld.entity.AICreakingEntity c = getCreakingBody(uuid);
        if (c != null) c.setTentaclesDeployed(v);
    }

    private static boolean isBodyOnCeiling(java.util.UUID uuid) {
        com.divineworld.entity.AICreakingEntity c = getCreakingBody(uuid);
        return c != null && c.isOnCeiling();
    }

    private static void setBodyOnCeiling(java.util.UUID uuid, boolean v) {
        com.divineworld.entity.AICreakingEntity c = getCreakingBody(uuid);
        if (c != null) c.setOnCeiling(v);
    }

    private static void setBodyUnderground(java.util.UUID uuid, boolean v) {
        com.divineworld.entity.AICreakingEntity c = getCreakingBody(uuid);
        if (c != null) c.setUnderground(v);
    }
}