// src/main/java/com/divineworld/events/GodControlHandler.java
package com.divineworld.events;

import com.divineworld.DWMod;
import com.divineworld.entity.DWNPCManager;
import com.divineworld.utils.TaggedEntitySystem;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.boss.enderdragon.EnderDragon;
import net.minecraft.world.entity.boss.wither.WitherBoss;
import net.minecraft.world.entity.monster.warden.Warden;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

/**
 * Synchronizes god entity movement with player controls
 */
@Mod.EventBusSubscriber(modid = DWMod.MOD_ID, bus = Mod.EventBusSubscriber.Bus.FORGE)
public class GodControlHandler {

    @SubscribeEvent
    public static void onPlayerTick(TickEvent.PlayerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        if (!(event.player instanceof ServerPlayer player)) return;

        // Check if this player controls a god entity
        if (!DWNPCManager.isGodPlayer(player)) return;

        Entity godEntity = GodSpawnHandler.getGodEntity(player.getUUID());

        if (godEntity == null || godEntity.isRemoved()) return;

        // Sync position and rotation
        syncGodWithPlayer(player, godEntity);
    }

    /**
     * Sync god entity with player controls
     */
    private static void syncGodWithPlayer(ServerPlayer player, Entity godEntity) {
        // Copy player's look angles
        godEntity.setYRot(player.getYRot());
        godEntity.setXRot(player.getXRot());
        godEntity.setYHeadRot(player.getYHeadRot());

        // Copy movement (for flying gods)
        if (godEntity instanceof EnderDragon || godEntity instanceof WitherBoss) {
            // Flying gods follow player position
            double dx = player.getX() - godEntity.getX();
            double dy = player.getY() - godEntity.getY();
            double dz = player.getZ() - godEntity.getZ();

            double speed = 0.3;
            godEntity.setDeltaMovement(dx * speed, dy * speed, dz * speed);
        } else {
            // Ground gods teleport to player position
            godEntity.moveTo(player.getX(), player.getY(), player.getZ(),
                    player.getYRot(), player.getXRot());
        }

        // Keep player at god position (invisible follower)
        player.moveTo(godEntity.getX(), godEntity.getY() + 100, godEntity.getZ());
    }
}