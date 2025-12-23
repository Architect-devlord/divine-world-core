package com.divineworld.oracle;

import com.divineworld.DWMod;
import com.divineworld.utils.BookFactory;
import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.network.chat.Component;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.*;
import net.minecraft.world.level.Level;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

import java.io.*;
import java.lang.reflect.Type;
import java.nio.file.*;
import java.util.*;

/**
 * Oracle System - FIXED for Minecraft 1.20.1 Forge with Parchment Mappings
 *
 * Fixes:
 * - Uses correct entity creation method (spawn() instead of deprecated create())
 * - Fixed pattern matching instanceof syntax
 * - Proper ServerLevel casting
 */
public class OracleSystem {

    private final Set<UUID> tutorialCompleted = new HashSet<>();
    private final Map<UUID, Mob> activeOracles = new HashMap<>();
    private final Map<UUID, Long> lastInteractionTime = new HashMap<>();
    private final Map<UUID, OracleMemory> memoryMap = new HashMap<>();
    private LLMOracleBrain brain;
    private final Gson gson = new Gson();

    private final int MAX_HISTORY_LINES = 20;
    private final Path memoryFolder;

    private final String personaTemplate =
            "You are the Oracle of a divine world. You are wise, slightly mysterious, patient, and respond concisely. " +
                    "Occasionally sprinkle subtle humor and metaphors. Answer wisely and helpfully.";

    public OracleSystem(LLMOracleBrain brain) {
        this.brain = brain;
        this.memoryFolder = Paths.get("config", "divineworld", "oracle_memory");
        try {
            if (!Files.exists(memoryFolder)) Files.createDirectories(memoryFolder);
            loadAllMemory();
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    private static class OracleMemory {
        List<String> conversation = new ArrayList<>();
        long lastAccess = System.currentTimeMillis();
    }

    /**
     * FIXED: Spawn oracle using proper Forge 1.20.1 entity creation
     */
    public Mob spawnOracle(ServerPlayer player) {
        ServerLevel serverLevel = player.serverLevel(); // FIXED: Use serverLevel() instead of casting
        BlockPos pos = player.blockPosition().offset(
                (int)(player.getLookAngle().x * 3),
                0,
                (int)(player.getLookAngle().z * 3)
        );
        pos = getSafeSpawnPosition(serverLevel, pos);

        // Spawn particles
        serverLevel.sendParticles(ParticleTypes.DRAGON_BREATH,
                pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 50, 0.5, 1, 0.5, 0.1);
        serverLevel.sendParticles(ParticleTypes.PORTAL,
                pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 30, 0.5, 1, 0.5, 0.2);
        serverLevel.playSound(null, pos, SoundEvents.ILLUSIONER_CAST_SPELL, SoundSource.NEUTRAL, 1f, 1.2f);

        // FIXED: Use spawn() method instead of deprecated create()
        // This is the correct way in Forge 1.20.1
        Mob oracle = EntityType.WANDERING_TRADER.spawn(
                serverLevel,                    // ServerLevel
                pos,                            // BlockPos
                MobSpawnType.COMMAND            // MobSpawnType (was EntitySpawnReason in older versions)
        );

        if (oracle != null) {
            // Configure oracle
            oracle.setPos(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5);
            oracle.setCustomName(Component.literal("§dOracle"));
            oracle.setCustomNameVisible(true);
            oracle.setNoAi(true);
            oracle.setInvulnerable(true);
            oracle.getPersistentData().putBoolean("is_oracle", true);

            // Already added to world by spawn(), no need to call addFreshEntity()

            activeOracles.put(player.getUUID(), oracle);
            lookAt(oracle, player.position().add(0, 1.6, 0));

            player.sendSystemMessage(Component.literal("§dThe Oracle appears before you..."));
            player.sendSystemMessage(Component.literal("§7Say 'Teach me' in chat if you wish to begin the tutorial."));
            player.sendSystemMessage(Component.literal("§7Say 'I know' in chat if you wish to skip the tutorial."));
        }

        return oracle;
    }

    public void despawnOracle(ServerPlayer player) {
        if (!activeOracles.containsKey(player.getUUID())) return;

        Mob oracle = activeOracles.get(player.getUUID());
        if (oracle != null && !oracle.isRemoved()) {
            BlockPos pos = oracle.blockPosition();
            ServerLevel level = (ServerLevel) oracle.level(); // Safe cast since we know it's server-side

            // Despawn particles
            level.sendParticles(ParticleTypes.ELECTRIC_SPARK,
                    pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 40, 0.5, 1, 0.5, 0.1);
            level.sendParticles(ParticleTypes.END_ROD,
                    pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 30, 0.5, 1, 0.5, 0.05);
            level.playSound(null, pos, SoundEvents.ENDERMAN_TELEPORT, SoundSource.NEUTRAL, 1f, 1.3f);

            player.sendSystemMessage(Component.literal("§eThe Oracle vanishes."));
            oracle.remove(Entity.RemovalReason.DISCARDED);
        }
        activeOracles.remove(player.getUUID());
    }

    public void setOracleBrain(LLMOracleBrain newBrain) {
        this.brain = newBrain;
    }

    public LLMOracleBrain getOracleBrain() {
        return this.brain;
    }

    @SubscribeEvent
    public void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        // FIXED: Removed pattern matching as it's redundant
        if (!(event.getEntity() instanceof ServerPlayer)) return;
        ServerPlayer player = (ServerPlayer) event.getEntity();

        if (!tutorialCompleted.contains(player.getUUID())) {
            DWMod.getInstance().scheduleTask(() -> spawnOracle(player), 5);
        }
    }

    @SubscribeEvent
    public void onPlayerChat(net.minecraftforge.event.ServerChatEvent event) {
        // FIXED: Removed pattern matching
        ServerPlayer player = event.getPlayer();
        if (player == null) return;

        String message = event.getMessage().getString().trim();
        if (!activeOracles.containsKey(player.getUUID())) return;

        // Prevent the original message from being broadcast
        event.setMessage(Component.literal(""));

        if (message.equalsIgnoreCase("i know")) {
            DWMod.getInstance().scheduleTask(() -> {
                player.sendSystemMessage(Component.literal("§aTutorial skipped. Right-click the Oracle to receive your books."));
                tutorialCompleted.add(player.getUUID());
            }, 1);
            return;
        }

        if (message.equalsIgnoreCase("teach me")) {
            DWMod.getInstance().scheduleTask(() -> runTutorial(player), 1);
            return;
        }

        // Handle conversation with Oracle
        OracleMemory memory = memoryMap.computeIfAbsent(player.getUUID(), k -> new OracleMemory());
        memory.conversation.add("Player: " + message);
        memory.lastAccess = System.currentTimeMillis();

        player.sendSystemMessage(Component.literal("§7[Oracle is thinking...]"));

        StringBuilder prompt = new StringBuilder(personaTemplate).append("\n\n");
        for (String line : memory.conversation) {
            prompt.append(line).append("\n");
        }
        prompt.append("Oracle:");

        // Query LLM asynchronously
        brain.queryAsync(DWMod.getInstance().getServer(), prompt.toString(), answer -> {
            if (answer == null || answer.isBlank()) {
                answer = "§c[Oracle is silent...]";
            }
            player.sendSystemMessage(Component.literal("§d[Oracle] " + answer));
            memory.conversation.add("Oracle: " + answer);
            saveMemory(player.getUUID());
        });
    }

    @SubscribeEvent
    public void onOracleInteract(PlayerInteractEvent.EntityInteract event) {
        // FIXED: Removed pattern matching
        if (!(event.getEntity() instanceof ServerPlayer)) return;
        ServerPlayer player = (ServerPlayer) event.getEntity();

        if (!(event.getTarget() instanceof Mob)) return;
        Mob oracle = (Mob) event.getTarget();

        if (!oracle.getPersistentData().contains("is_oracle")) return;

        event.setCancellationResult(InteractionResult.SUCCESS);
        event.setCanceled(true);

        long now = System.currentTimeMillis();
        if (lastInteractionTime.containsKey(player.getUUID()) &&
                now - lastInteractionTime.get(player.getUUID()) < 2000) {
            player.sendSystemMessage(Component.literal("§7The Oracle waits for you to be ready..."));
            return;
        }
        lastInteractionTime.put(player.getUUID(), now);

        if (tutorialCompleted.contains(player.getUUID())) {
            // Give both books
            if (!player.getInventory().contains(BookFactory.genesisCodex())) {
                player.addItem(BookFactory.genesisCodex());
                player.addItem(BookFactory.firstFlameBook());
                player.addItem(BookFactory.commandReferenceCard()); // OPTIONAL

                player.sendSystemMessage(Component.literal(
                        "§b✨ You have received the sacred texts:"
                ));
                player.sendSystemMessage(Component.literal(
                        "§7- Genesis Codex (right-click ground)"
                ));
                player.sendSystemMessage(Component.literal(
                        "§7- Teachings of the First Flame (commands)"
                ));

                oracle.setNoAi(false);
                tutorialCompleted.add(player.getUUID());

                DWMod.getInstance().scheduleTask(() -> despawnOracle(player), 600);
            }
        }
    }

    private void lookAt(Mob mob, net.minecraft.world.phys.Vec3 target) {
        net.minecraft.world.phys.Vec3 dir = target.subtract(mob.position()).normalize();
        mob.setYRot((float) Math.toDegrees(Math.atan2(dir.z, dir.x)) - 90);
        mob.setXRot((float) -Math.toDegrees(Math.atan2(dir.y, Math.sqrt(dir.x * dir.x + dir.z * dir.z))));
    }

    private BlockPos getSafeSpawnPosition(Level level, BlockPos pos) {
        for (int i = 0; i < 5; i++) {
            if (level.getBlockState(pos).isAir() && level.getBlockState(pos.below()).isSolid()) {
                return pos;
            }
            pos = pos.above();
        }
        return pos;
    }

    private void runTutorial(ServerPlayer player) {
        final int[] step = {0};
        DWMod.getInstance().scheduleRepeatingTask(() -> {
            if (tutorialCompleted.contains(player.getUUID())) return false;

            switch (step[0]++) {
                case 0 -> player.sendSystemMessage(Component.literal(
                        "§e[Oracle] Welcome, divine one. I will teach you how this world breathes."));
                case 1 -> player.sendSystemMessage(Component.literal(
                        "§e[Oracle] Tribes form through Genesis. They grow, evolve, worship, and fall."));
                case 2 -> player.sendSystemMessage(Component.literal(
                        "§e[Oracle] Your will shapes their culture, belief, and destiny."));
                case 3 -> player.sendSystemMessage(Component.literal(
                        "§e[Oracle] You may reset the world, but only when all life has ended or genesis is used."));
                case 4 -> player.sendSystemMessage(Component.literal(
                        "§e[Oracle] Interact with me after this to receive sacred texts."));
                case 5 -> {
                    player.sendSystemMessage(Component.literal(
                            "§aThe tutorial has ended. Right-click the Oracle."));
                    tutorialCompleted.add(player.getUUID());
                    return false;
                }
            }
            return true;
        }, 60, 100);
    }

    private void saveMemory(UUID playerId) {
        OracleMemory memory = memoryMap.get(playerId);
        if (memory == null) return;

        Path file = memoryFolder.resolve(playerId.toString() + ".json");
        try (Writer writer = Files.newBufferedWriter(file)) {
            gson.toJson(memory, writer);
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    private void loadAllMemory() throws IOException {
        if (!Files.exists(memoryFolder)) return;

        try (var stream = Files.list(memoryFolder)) {
            stream.filter(f -> f.toString().endsWith(".json")).forEach(f -> {
                try (Reader reader = Files.newBufferedReader(f)) {
                    Type type = new TypeToken<OracleMemory>() {}.getType();
                    OracleMemory memory = gson.fromJson(reader, type);
                    UUID playerId = UUID.fromString(f.getFileName().toString().replace(".json", ""));
                    memoryMap.put(playerId, memory);
                } catch (Exception e) {
                    e.printStackTrace();
                }
            });
        }
    }
}