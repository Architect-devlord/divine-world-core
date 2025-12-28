
// ============================================================================
// src/main/java/com/divineworld/client/GodAbilityVisualHandler.java
// ============================================================================

package com.divineworld.client;

import com.divineworld.client.DWClientMod;
import net.minecraft.client.Minecraft;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.player.Player;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.event.entity.living.LivingHurtEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * God Ability Visual Handler
 * Adds visual/audio effects when gods use abilities
 */
@Mod.EventBusSubscriber(modid = DWClientMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public class GodAbilityVisualHandler {

    @SubscribeEvent
    public static void onEntityHurt(LivingHurtEvent event) {
        if (event.getSource().getEntity() instanceof Player attacker) {
            if (!attacker.getPersistentData().contains("dw_god")) return;

            // Enhanced visual feedback for god attacks
            spawnGodAttackParticles(attacker, event.getEntity());
        }
    }

    private static void spawnGodAttackParticles(Player god, net.minecraft.world.entity.Entity target) {
        String godType = god.getPersistentData().getString("dw_god_type");

        // Spawn particles based on god type
        switch (godType) {
            case "ender_dragon" -> {
                // Purple dragon breath particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.DRAGON_BREATH,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
                target.level().playLocalSound(target.getX(), target.getY(), target.getZ(),
                        SoundEvents.ENDER_DRAGON_GROWL, SoundSource.HOSTILE,
                        0.5f, 1.0f, false);
            }
            case "wither" -> {
                // Dark smoke particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.LARGE_SMOKE,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
                target.level().playLocalSound(target.getX(), target.getY(), target.getZ(),
                        SoundEvents.WITHER_HURT, SoundSource.HOSTILE,
                        0.5f, 1.0f, false);
            }
            case "warden" -> {
                // Sculk particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.SCULK_SOUL,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
                target.level().playLocalSound(target.getX(), target.getY(), target.getZ(),
                        SoundEvents.WARDEN_ATTACK_IMPACT, SoundSource.HOSTILE,
                        0.5f, 1.0f, false);
            }
            case "elder_guardian" -> {
                // Bubble particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.BUBBLE,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
            }
            case "creaking" -> {
                // Spore particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.SPORE_BLOSSOM_AIR,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
            }
            case "oracle" -> {
                // Enchantment glint particles
                for (int i = 0; i < 10; i++) {
                    target.level().addParticle(ParticleTypes.ENCHANT,
                            target.getX() + (target.level().random.nextDouble() - 0.5),
                            target.getY() + target.getBbHeight() * 0.5,
                            target.getZ() + (target.level().random.nextDouble() - 0.5),
                            0, 0.1, 0);
                }
            }
        }
    }
}