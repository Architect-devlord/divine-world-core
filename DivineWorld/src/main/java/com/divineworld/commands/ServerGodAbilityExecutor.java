// src/main/java/com/divineworld/commands/ServerGodAbilityExecutor.java
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
 * ServerGodAbilityExecutor
 * ========================
 * Server-side mirror of the ability logic defined in the client-side AI god
 * entities (AIWarden, AIWither, AIEnderDragon, AIElderGuardian, AIOracle,
 * AICreaking). All damage, knockback, and status effects must run here on the
 * server so they actually affect the game world.
 *
 * FIX Bug #6
 * ----------
 * The original DivineCommands.executeGodAbility() only called
 *   PythonBackendClient.godUseAbility(agentId, ability)
 * which POSTed to the Python backend — the ability effects never ran in the
 * Minecraft world. This class is now called directly from
 * DivineCommands.executeGodAbility(), giving abilities real server-side impact.
 *
 * How abilities flow:
 *   Python AI decides → binary ActionFrame carries god_ability name + params
 *   → ActionExecutor (client) → GodEntityManager.executeGodAbility() (client visuals)
 *   → DivineCommands.executeGodAbility() (server command)
 *   → ServerGodAbilityExecutor.execute() (server damage/effects/particles)
 *   → PythonBackendClient.godUseAbility() fire-and-forget (reward signal)
 *
 * Cooldowns
 * ---------
 * Per-god cooldowns are stored in per-player NBT under "cd_<abilityName>".
 * tickAbilityCooldowns() must be called every server tick — wired in
 * DWEventHandler.onServerTick (Bug 13 fix).
 */
public class ServerGodAbilityExecutor {

    // =========================================================================
    // Entry point
    // =========================================================================

    /**
     * Dispatch an ability for the given god agent.
     *
     * @param godPlayer the invisible puppet ServerPlayer
     * @param ability   ability name matching the AI entity class (e.g. "sonic_boom")
     * @param level     the ServerLevel they are in
     */
    public static void execute(ServerPlayer godPlayer, String ability, ServerLevel level) {
        String godType = TaggedEntitySystem.extractGodType(godPlayer);
        if (godType == null || godType.isEmpty()) {
            DWMod.LOGGER.warn("[AbilityExecutor] No god type on player {}",
                    godPlayer.getName().getString());
            return;
        }

        DWMod.LOGGER.info("[AbilityExecutor] {} ({}) → {}",
                godPlayer.getName().getString(), godType, ability);

        // Use the boss body as the damage source attacker so vanilla attribution
        // (kill messages, loot tables) names the god entity, not the hidden puppet.
        Entity bodyEntity = GodSpawnHandler.getGodEntity(godPlayer.getUUID());
        LivingEntity attacker = (bodyEntity instanceof LivingEntity le) ? le : godPlayer;

        switch (godType) {
            case "warden"                 -> executeWardenAbility(godPlayer, attacker, ability, level);
            case "wither"                 -> executeWitherAbility(godPlayer, attacker, ability, level);
            case "ender_dragon", "dragon" -> executeDragonAbility(godPlayer, attacker, ability, level);
            case "elder_guardian"         -> executeElderGuardianAbility(godPlayer, attacker, ability, level);
            case "oracle"                 -> executeOracleAbility(godPlayer, attacker, ability, level);
            case "creaking"               -> executeCreakingAbility(godPlayer, attacker, ability, level);
            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown god type: {}", godType);
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

    /**
     * Decrement all "cd_*" NBT keys by one tick.
     * Called every server tick from DWEventHandler.onServerTick (Bug 13 fix).
     */
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

    /** All living entities within radius of the puppet player, excluding it. */
    private static List<LivingEntity> nearbyLiving(ServerPlayer origin, double radius) {
        AABB box = origin.getBoundingBox().inflate(radius);
        return origin.level().getEntitiesOfClass(LivingEntity.class, box,
                e -> e != origin && e.isAlive());
    }

    /** Spawn a ring of particles around a world position. */
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
                // True raycast — step every 0.5 blocks along look vector, 30 blocks
                for (double d = 0; d <= 30; d += 0.5) {
                    Vec3 point = start.add(look.scale(d));
                    AABB hitBox = new AABB(point.x - 1.5, point.y - 1.5, point.z - 1.5,
                                          point.x + 1.5, point.y + 1.5, point.z + 1.5);
                    for (LivingEntity target : level.getEntitiesOfClass(LivingEntity.class, hitBox,
                            e -> e != player && e.isAlive())) {
                        // Sonic boom ignores armour — magic damage source
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
                // Reveal moving entities with a particle marker at their position
                for (LivingEntity target : nearbyLiving(player, 32)) {
                    if (target.getDeltaMovement().length() > 0.01) {
                        level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                                target.getX(), target.getY() + 1, target.getZ(),
                                15, 0.3, 0.2, 0.3, 0);
                    }
                }
                setCooldown(player, "sniff", 40);
            }

            case "burrow" -> {
                if (isOnCooldown(player, "burrow")) return;
                player.setInvisible(true);
                player.noPhysics = true;
                player.setDeltaMovement(0, -0.3, 0);
                level.sendParticles(ParticleTypes.SCULK_SOUL,
                        player.getX(), player.getY(), player.getZ(),
                        40, 0.6, 0.2, 0.6, 0.02);
                setCooldown(player, "burrow", 200);
                // Auto-emerge after 5 seconds with an upward burst + area damage
                DWMod.getInstance().scheduleTask(() -> {
                    player.setInvisible(false);
                    player.noPhysics = true;
                    for (LivingEntity target : nearbyLiving(player, 5)) {
                        target.hurt(level.damageSources().mobAttack(attacker), 20.0f);
                        Vec3 knock = target.position().subtract(player.position()).normalize();
                        target.push(knock.x * 2, 1.5, knock.z * 2);
                    }
                    level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                            player.getX(), player.getY(), player.getZ(),
                            80, 1.5, 0.2, 1.5, 0.1);
                }, 100); // 5 s
            }

            // Explicit emerge — used when the agent surfaces early or after a manual burrow
            case "emerge" -> {
                player.setInvisible(false);
                player.noPhysics = true;
                player.addEffect(new MobEffectInstance(MobEffects.MOVEMENT_SPEED, 60, 2));
                for (LivingEntity target : nearbyLiving(player, 5)) {
                    target.hurt(level.damageSources().mobAttack(attacker), 20.0f);
                    Vec3 knock = target.position().subtract(player.position()).normalize();
                    target.push(knock.x * 2, 1.5, knock.z * 2);
                }
                level.sendParticles(ParticleTypes.SCULK_CHARGE_POP,
                        player.getX(), player.getY(), player.getZ(),
                        80, 1.5, 0.2, 1.5, 0.1);
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
                // blue_skull is a charged variant — same server-side logic for now
                if (isOnCooldown(player, "wither_skull")) return;
                Vec3 look = player.getLookAngle();
                // Hit entities in a tight aim cone, 20 blocks
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
                Vec3 look   = player.getLookAngle();
                double power = 2.5;
                player.setDeltaMovement(look.x * power, 0.5, look.z * power);
                player.hurtMarked = true;
                // Also push the body so it doesn't lag behind
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
                                player.getX() + Math.cos(angle) * 3,
                                player.getY(),
                                player.getZ() + Math.sin(angle) * 3,
                                (float) (angle * 180 / Math.PI), 0);
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
                level.explode(attacker,
                        player.getX(), player.getY() + 1, player.getZ(),
                        4.0f, false,
                        net.minecraft.world.level.Level.ExplosionInteraction.NONE);
                setCooldown(player, "explosion", 160);
            }

            // FIX JC-02: AIWither dispatches "fly" but ServerGodAbilityExecutor had no case
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
                Vec3 look      = player.getLookAngle();
                Vec3 breathPos = player.position().add(look.scale(3));
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
                boolean nowFlying = player.getAbilities().flying;
                player.getAbilities().flying = !nowFlying;
                player.onUpdateAbilities();
                setCooldown(player, "perch", 20);
            }

            // FIX JC-02: AIEnderDragon dispatches "fly" but no server case existed
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
                    target.addEffect(new MobEffectInstance(
                            MobEffects.DIG_SLOWDOWN, 1200, 2, false, true));
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 48, 15, 1);
                setCooldown(player, "mining_fatigue", 1200);
            }

            case "laser_beam" -> {
                if (isOnCooldown(player, "laser_beam")) return;
                // Charge burst, then fire after a 2-second delay
                level.sendParticles(ParticleTypes.CRIT,
                        player.getX(), player.getEyeY(), player.getZ(),
                        20, 0.2, 0.2, 0.2, 0.1);
                DWMod.getInstance().scheduleTask(() -> {
                    Vec3 look  = player.getLookAngle();
                    Vec3 start = player.getEyePosition();
                    for (double d = 0; d <= 50; d += 0.5) {
                        Vec3 p = start.add(look.scale(d));
                        AABB hitBox = new AABB(p.x - 1, p.y - 1, p.z - 1,
                                              p.x + 1, p.y + 1, p.z + 1);
                        for (LivingEntity target : level.getEntitiesOfClass(
                                LivingEntity.class, hitBox,
                                e -> e != player && e.isAlive())) {
                            target.hurt(level.damageSources().magic(), 50.0f);
                            target.addEffect(new MobEffectInstance(
                                    MobEffects.MOVEMENT_SLOWDOWN, 60, 2));
                        }
                        if (d % 1.0 < 0.5) {
                            level.sendParticles(ParticleTypes.END_ROD,
                                    p.x, p.y, p.z, 1, 0, 0, 0, 0);
                        }
                    }
                }, 40); // 40 ticks = 2 s charge
                setCooldown(player, "laser_beam", 60);
            }

            case "thorn_attack" -> {
                if (isOnCooldown(player, "thorn_attack")) return;
                for (LivingEntity target : nearbyLiving(player, 4)) {
                    target.hurt(level.damageSources().thorns(attacker), 12.0f);
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 24, 4, 0.5);
                setCooldown(player, "thorn_attack", 20);
            }

            case "guardian_spikes" -> {
                if (isOnCooldown(player, "guardian_spikes")) return;
                for (LivingEntity target : nearbyLiving(player, 3)) {
                    target.hurt(level.damageSources().thorns(attacker), 12.0f);
                }
                ringParticles(level, player.position(), ParticleTypes.BUBBLE, 24, 3, 0.5);
                setCooldown(player, "guardian_spikes", 400);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown elder_guardian ability: {}", ability);
        }
    }

    // =========================================================================
    // ORACLE abilities
    // =========================================================================

    private static void executeOracleAbility(ServerPlayer player, LivingEntity attacker,
                                              String ability, ServerLevel level) {
        switch (ability) {

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
                // Reveal nearby entities with a particle marker above their head
                for (LivingEntity target : nearbyLiving(player, 30)) {
                    level.sendParticles(ParticleTypes.END_ROD,
                            target.getX(), target.getY() + 2, target.getZ(),
                            5, 0.1, 0.2, 0.1, 0);
                }
                setCooldown(player, "foresight", 100);
            }

            case "teleport" -> {
                if (isOnCooldown(player, "teleport")) return;
                Vec3 look = player.getLookAngle();
                Vec3 dest = player.position().add(look.scale(20));
                player.teleportTo(dest.x, dest.y, dest.z);
                // Also move the body so GodControlHandler doesn't snap it back
                Entity godEntity = GodSpawnHandler.getGodEntity(player.getUUID());
                if (godEntity != null) {
                    godEntity.moveTo(dest.x, dest.y, dest.z,
                            player.getYRot(), player.getXRot());
                }
                level.sendParticles(ParticleTypes.PORTAL,
                        dest.x, dest.y + 1, dest.z,
                        40, 0.5, 0.8, 0.5, 0.1);
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
                    Vec3 p = start.add(look.scale(d));
                    AABB hitBox = new AABB(p.x - 0.8, p.y - 0.8, p.z - 0.8,
                                          p.x + 0.8, p.y + 0.8, p.z + 0.8);
                    for (LivingEntity target : level.getEntitiesOfClass(
                            LivingEntity.class, hitBox,
                            e -> e != player && e.isAlive())) {
                        target.hurt(level.damageSources().magic(), 40.0f);
                        target.addEffect(new MobEffectInstance(
                                MobEffects.MOVEMENT_SLOWDOWN, 80, 3));
                    }
                    if (d % 1.0 < 0.5) {
                        level.sendParticles(ParticleTypes.END_ROD,
                                p.x, p.y, p.z, 1, 0, 0, 0, 0);
                    }
                }
                setCooldown(player, "knowledge_beam", 200);
            }

            // FIX JC-02: AIOracle dispatches "fly" but no server case existed
            case "fly" -> {
                if (isOnCooldown(player, "fly")) return;
                boolean nowFlying = player.getAbilities().flying;
                player.getAbilities().flying = !nowFlying;
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
        switch (ability) {

            case "tentacle_whip" -> {
                if (isOnCooldown(player, "tentacle_whip")) return;
                for (LivingEntity target : nearbyLiving(player, 8)) {
                    target.hurt(level.damageSources().mobAttack(attacker), 12.0f);
                    Vec3 knock = target.position().subtract(player.position()).normalize();
                    target.push(knock.x * 2, 0.5, knock.z * 2);
                }
                level.sendParticles(ParticleTypes.SPORE_BLOSSOM_AIR,
                        player.getX(), player.getY() + 1, player.getZ(),
                        50, 2, 0.5, 2, 0.03);
                setCooldown(player, "tentacle_whip", 40);
            }

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
                setCooldown(player, "life_steal", 80);
            }

            case "toggle_underground" -> {
                if (isOnCooldown(player, "toggle_underground")) return;
                player.noPhysics = !player.noPhysics;
                level.sendParticles(ParticleTypes.ASH,
                        player.getX(), player.getY(), player.getZ(),
                        30, 0.5, 0.2, 0.5, 0.05);
                setCooldown(player, "toggle_underground", 40);
            }

            case "toggle_ceiling" -> {
                if (isOnCooldown(player, "toggle_ceiling")) return;
                boolean currentlyUp = player.hasEffect(MobEffects.LEVITATION);
                if (!currentlyUp) {
                    player.addEffect(new MobEffectInstance(MobEffects.LEVITATION, 100, 3));
                    player.noPhysics = true;
                } else {
                    player.removeEffect(MobEffects.LEVITATION);
                    player.noPhysics = false;
                }
                level.sendParticles(ParticleTypes.ASH,
                        player.getX(), player.getY(), player.getZ(),
                        30, 0.5, 0.2, 0.5, 0.05);
                setCooldown(player, "toggle_ceiling", 40);
            }

            case "deploy_tentacles" -> {
                if (isOnCooldown(player, "deploy_tentacles")) return;
                for (LivingEntity target : nearbyLiving(player, 6)) {
                    target.hurt(level.damageSources().magic(), 8.0f);
                    target.addEffect(new MobEffectInstance(
                            MobEffects.MOVEMENT_SLOWDOWN, 60, 3));
                }
                level.sendParticles(ParticleTypes.SPORE_BLOSSOM_AIR,
                        player.getX(), player.getY() + 1, player.getZ(),
                        40, 1.5, 0.5, 1.5, 0.02);
                setCooldown(player, "deploy_tentacles", 100);
            }

            default -> DWMod.LOGGER.warn("[AbilityExecutor] Unknown creaking ability: {}", ability);
        }
    }
}
