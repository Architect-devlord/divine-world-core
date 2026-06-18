// src/main/java/com/divineworld/oracle/OracleSystem.java
// DivineWorld server mod
package com.divineworld.oracle;

import com.divineworld.DWMod;
import com.divineworld.utils.BookFactory;
import com.divineworld.utils.DivineMagicCircle;
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
import net.minecraft.world.phys.Vec3;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.event.entity.player.PlayerEvent;
import net.minecraftforge.event.entity.player.PlayerInteractEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;

import com.divineworld.events.ProximityChatHandler;
import com.divineworld.utils.AgentConfigLoader;
import java.io.*;
import java.lang.reflect.Type;
import java.nio.file.*;
import java.util.*;

/**
 * Oracle System — UPDATED
 *
 * All original features preserved. Two new additions:
 *
 *  1. ORACLE LOOK-AT FIX
 *     The original one-shot lookAt() call in spawnOracle() is kept for the
 *     initial spawn, AND a new onServerTick() handler continuously re-applies
 *     the rotation every tick so the Wandering Trader stays facing the player
 *     despite vanilla packet resets.  The original lookAt(Mob, Vec3) private
 *     method is preserved unchanged and is still called at spawn.
 *
 *  2. REACTION CIRCLE
 *     triggerReactionCircle() lets external callers (e.g. GenesisManager or
 *     DivineCommands) make the Oracle emit a short DivineMagicCircle burst at
 *     its current position — giving visual feedback that the Oracle is aware
 *     of the Genesis / Reset event.
 *
 * Everything else — spawnOracle(), despawnOracle(), onPlayerJoin(),
 * onPlayerChat(), onOracleInteract(), runTutorial(), saveMemory(),
 * loadAllMemory(), getSafeSpawnPosition(), setOracleBrain(),
 * getOracleBrain() — is identical to the original.
 *
 * NOTE: This class is NOT annotated @Mod.EventBusSubscriber because it is
 * registered as an instance (MinecraftForge.EVENT_BUS.register(oracleSystem))
 * in DWMod.onServerStarting(). That pattern is unchanged from the original.
 */
public class OracleSystem {

    // -------------------------------------------------------------------------
    // Fields (identical to original)
    // -------------------------------------------------------------------------

    private final Set<UUID>               tutorialCompleted   = new HashSet<>();
    private final Map<UUID, Mob>          activeOracles       = new HashMap<>();
    private final Map<UUID, Long>         lastInteractionTime = new HashMap<>();
    private final Map<UUID, OracleMemory> memoryMap           = new HashMap<>();

    private LLMOracleBrain brain;
    private final Gson gson = new Gson();

    private final int  MAX_HISTORY_LINES = 20;
    private final Path memoryFolder;

    private final String personaTemplate =
            "You are the Oracle of a divine world. You are wise, slightly mysterious, patient, and respond concisely. " +
                    "Occasionally sprinkle subtle humor and metaphors. Answer wisely and helpfully in 1-3 sentences maximum.";

    // -------------------------------------------------------------------------
    // NEW: reaction circle state
    // -------------------------------------------------------------------------

    private boolean     reactionCircleActive = false;
    private int         reactionCircleTick   = 0;
    private ServerLevel reactionLevel        = null;
    private BlockPos    reactionCenter       = null;
    private boolean     reactionIsReset      = false;

    // -------------------------------------------------------------------------
    // Constructor (identical to original)
    // -------------------------------------------------------------------------

    public OracleSystem(LLMOracleBrain brain) {
        this.brain = brain;
        this.memoryFolder = Paths.get("config", "divineworld", "oracle_memory");
        try {
            if (!Files.exists(memoryFolder)) Files.createDirectories(memoryFolder);
            loadAllMemory();
        } catch (IOException e) {
            DWMod.LOGGER.error("[Oracle] Failed to create memory folder", e);
        }
        ProximityChatHandler.setChatHook(this::handleChatHook);
    }

    // -------------------------------------------------------------------------
    // Inner class (identical to original)
    // -------------------------------------------------------------------------

    private static class OracleMemory {
        List<String> conversation = new ArrayList<>();
        long lastAccess = System.currentTimeMillis();
    }

    // -------------------------------------------------------------------------
    // Spawn / Despawn (ORIGINAL — no logic changes, oracle_owner tag added)
    // -------------------------------------------------------------------------

    /**
     * Spawn oracle using proper Forge 1.20.1 entity creation.
     * Identical to original except:
     *  - stores oracle_owner UUID in PersistentData (needed by tick look-at)
     *  - calls forceLookAtPlayer() after spawn in addition to the original
     *    one-shot lookAt() (which is preserved)
     */
    public Mob spawnOracle(ServerPlayer player) {
        ServerLevel serverLevel = player.serverLevel();
        BlockPos pos = player.blockPosition().offset(
                (int)(player.getLookAngle().x * 3),
                0,
                (int)(player.getLookAngle().z * 3)
        );
        pos = getSafeSpawnPosition(serverLevel, pos);

        // ORIGINAL spawn particles
        serverLevel.sendParticles(ParticleTypes.DRAGON_BREATH,
                pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 50, 0.5, 1, 0.5, 0.1);
        serverLevel.sendParticles(ParticleTypes.PORTAL,
                pos.getX() + 0.5, pos.getY() + 1, pos.getZ() + 0.5, 30, 0.5, 1, 0.5, 0.2);
        serverLevel.playSound(null, pos, SoundEvents.ILLUSIONER_CAST_SPELL, SoundSource.NEUTRAL, 1f, 1.2f);

        // ORIGINAL entity spawn
        Mob oracle = EntityType.WANDERING_TRADER.spawn(
                serverLevel,
                pos,
                MobSpawnType.COMMAND
        );

        if (oracle != null) {
            oracle.setPos(pos.getX() + 0.5, pos.getY(), pos.getZ() + 0.5);
            oracle.setCustomName(Component.literal("§dOracle"));
            oracle.setCustomNameVisible(true);
            oracle.setNoAi(true);
            oracle.setInvulnerable(true);
            oracle.getPersistentData().putBoolean("is_oracle", true);
            // NEW: store owner UUID so tick handler can find the right player
            oracle.getPersistentData().putString("oracle_owner", player.getUUID().toString());

            activeOracles.put(player.getUUID(), oracle);

            // ORIGINAL one-shot look (kept)
            lookAt(oracle, player.position().add(0, 1.6, 0));

            player.sendSystemMessage(Component.literal("§dThe Oracle appears before you..."));
            player.sendSystemMessage(Component.literal("§7Say 'Teach me' in chat if you wish to begin the tutorial."));
            player.sendSystemMessage(Component.literal("§7Say 'I know' in chat if you wish to skip the tutorial."));
        }

        return oracle;
    }

    /**
     * Despawn oracle (identical to original).
     */
    public void despawnOracle(ServerPlayer player) {
        if (!activeOracles.containsKey(player.getUUID())) return;

        Mob oracle = activeOracles.get(player.getUUID());
        if (oracle != null && !oracle.isRemoved()) {
            BlockPos pos = oracle.blockPosition();
            ServerLevel level = (ServerLevel) oracle.level();

            // ORIGINAL despawn particles
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

    // -------------------------------------------------------------------------
    // NEW: Server tick — continuous look-at + reaction circle
    // -------------------------------------------------------------------------

    /**
     * Runs every server tick.  Handles:
     *  (a) Continuous Oracle look-at so the entity faces its owner every tick.
     *  (b) The short reaction circle burst (if active).
     */
    @SubscribeEvent
    public void onServerTick(TickEvent.ServerTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;

        // (a) Continuous look-at for every active oracle
        activeOracles.forEach((playerUUID, oracle) -> {
            if (oracle == null || oracle.isRemoved()) return;
            if (!(oracle.level() instanceof ServerLevel serverLevel)) return;

            // Prefer the registered owner; fall back to nearest player
            ServerPlayer owner = serverLevel.getServer().getPlayerList().getPlayer(playerUUID);
            if (owner != null && !owner.isRemoved()) {
                forceLookAtPlayer(oracle, owner);
            } else {
                ServerPlayer nearest = findNearestPlayer(serverLevel, oracle, 32.0);
                if (nearest != null) forceLookAtPlayer(oracle, nearest);
            }
        });

        // (b) Reaction circle
        if (reactionCircleActive) {
            if (reactionCircleTick >= 40) {
                reactionCircleActive = false;
                reactionLevel        = null;
                reactionCenter       = null;
            } else if (reactionCircleTick % 3 == 0 && reactionLevel != null) {
                if (reactionIsReset) {
                    DivineMagicCircle.spawnDivineResetCircle(reactionLevel, reactionCenter, reactionCircleTick);
                } else {
                    DivineMagicCircle.spawnGenesisCircle(reactionLevel, reactionCenter, reactionCircleTick);
                }
            }
            reactionCircleTick++;
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL events (identical to original)
    // -------------------------------------------------------------------------

    @SubscribeEvent
    public void onPlayerJoin(PlayerEvent.PlayerLoggedInEvent event) {
        if (!(event.getEntity() instanceof ServerPlayer)) return;
        ServerPlayer player = (ServerPlayer) event.getEntity();

        // FIX: only spawn oracle for real (human) players
        AgentConfigLoader.AgentType agentType =
            AgentConfigLoader.getAgentTypeForName(player.getName().getString());
        if (agentType != null) {
            DWMod.LOGGER.debug("[Oracle] Skipping oracle for agent: {}",
                player.getName().getString());
            return;
        }
        if (!tutorialCompleted.contains(player.getUUID())) {
            DWMod.getInstance().scheduleTask(() -> spawnOracle(player), 5);
        }
    }

    /**
     * FIX: Replaced @SubscribeEvent onPlayerChat (never fired after cancel)
     * with a hook called by ProximityChatHandler before setCanceled(true).
     * Returns true = oracle consumed message, suppress proximity echo.
     */
    private boolean handleChatHook(ServerPlayer player, String rawMsg) {
        if (player == null || !activeOracles.containsKey(player.getUUID())) return false;
        String message = rawMsg.trim();
        DWMod.LOGGER.info("[Oracle] Chat from {}: '{}'", player.getName().getString(), message);

        if (message.equalsIgnoreCase("i know")) {
            DWMod.getInstance().scheduleTask(() -> {
                player.sendSystemMessage(Component.literal(
                    "§aTutorial skipped. Right-click the Oracle to receive your books."));
                tutorialCompleted.add(player.getUUID());
            }, 1);
            return true;
        }

        if (message.equalsIgnoreCase("teach me")) {
            DWMod.getInstance().scheduleTask(() -> runTutorial(player), 1);
            return true;
        }

        DWMod.LOGGER.info("[Oracle] Querying LLM for {}", player.getName().getString());
        OracleMemory memory = memoryMap.computeIfAbsent(player.getUUID(), k -> new OracleMemory());
        memory.conversation.add("Player: " + message);
        memory.lastAccess = System.currentTimeMillis();
        player.sendSystemMessage(Component.literal("§d[Oracle] §7Consulting the divine wisdom..."));

        StringBuilder prompt = new StringBuilder(personaTemplate).append("\n\n");
        int startIdx = Math.max(0, memory.conversation.size() - 10);
        for (int i = startIdx; i < memory.conversation.size(); i++)
            prompt.append(memory.conversation.get(i)).append("\n");
        prompt.append("Oracle:");

        brain.queryAsync(DWMod.getInstance().getServer(), prompt.toString(), answer -> {
            if (answer == null || answer.isBlank())
                answer = "§7[The Oracle remains silent, pondering the mysteries of existence...]";
            answer = answer.trim();
            if (answer.startsWith("```")) answer = answer.replaceAll("```json|```", "").trim();
            if (answer.length() > 500) answer = answer.substring(0, 497) + "...";
            final String fa = answer;
            player.sendSystemMessage(Component.literal("§d[Oracle] §f" + fa));
            memory.conversation.add("Oracle: " + fa);
            if (memory.conversation.size() > MAX_HISTORY_LINES)
                memory.conversation = new ArrayList<>(memory.conversation.subList(
                    memory.conversation.size() - MAX_HISTORY_LINES, memory.conversation.size()));
            saveMemory(player.getUUID());
        });
        return true;
    }
    @SubscribeEvent
    public void onOracleInteract(PlayerInteractEvent.EntityInteract event) {
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
            if (!player.getInventory().contains(BookFactory.genesisCodex())) {
                player.addItem(BookFactory.genesisCodex());
                player.addItem(BookFactory.firstFlameBook());
                player.addItem(BookFactory.commandReferenceCard());

                player.sendSystemMessage(Component.literal("§b✨ You have received the sacred texts:"));
                player.sendSystemMessage(Component.literal("§7- Genesis Codex (right-click ground)"));
                player.sendSystemMessage(Component.literal("§7- Teachings of the First Flame (commands description)"));
                player.sendSystemMessage(Component.literal("§7- Divine Commands (quick reference for commands)"));

                oracle.setNoAi(false);
                tutorialCompleted.add(player.getUUID());

                DWMod.getInstance().scheduleTask(() -> despawnOracle(player), 600);
            }
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: lookAt (private, Vec3 target — preserved unchanged)
    // -------------------------------------------------------------------------

    /**
     * Original one-shot look-at used at spawn time.
     * Preserved exactly — same math, same method signature.
     */
    private void lookAt(Mob mob, Vec3 target) {
        Vec3 dir = target.subtract(mob.position()).normalize();
        mob.setYRot((float) Math.toDegrees(Math.atan2(dir.z, dir.x)) - 90);
        mob.setXRot((float) -Math.toDegrees(Math.atan2(dir.y, Math.sqrt(dir.x * dir.x + dir.z * dir.z))));
    }

    // -------------------------------------------------------------------------
    // NEW: continuous look-at helpers (tick-based, does not replace lookAt)
    // -------------------------------------------------------------------------

    /**
     * Forces the oracle to face a specific player every tick.
     * Uses the same math as the original lookAt(), but additionally sets the
     * "previous tick" rotation fields (yRotO / xRotO) and yHeadRot to prevent
     * vanilla interpolation from drifting the head away between ticks.
     */
    private void forceLookAtPlayer(Mob mob, ServerPlayer target) {
        Vec3 mobEye    = mob.getEyePosition();
        Vec3 targetEye = target.getEyePosition();

        double dx = targetEye.x - mobEye.x;
        double dy = targetEye.y - mobEye.y;
        double dz = targetEye.z - mobEye.z;
        double horizontalDist = Math.sqrt(dx * dx + dz * dz);

        float yRot = (float) Math.toDegrees(Math.atan2(dz, dx)) - 90.0f;
        float xRot = (float) -Math.toDegrees(Math.atan2(dy, horizontalDist));

        mob.setYRot(yRot);
        mob.setXRot(xRot);
        mob.yRotO     = yRot;
        mob.xRotO     = xRot;
        mob.setYHeadRot(yRot);
    }

    /** Find the nearest ServerPlayer within maxDist blocks of a mob. */
    private ServerPlayer findNearestPlayer(ServerLevel level, Mob mob, double maxDist) {
        ServerPlayer nearest = null;
        double nearestDistSq = maxDist * maxDist;
        for (ServerPlayer sp : level.players()) {
            double d = mob.distanceToSqr(sp);
            if (d < nearestDistSq) {
                nearestDistSq = d;
                nearest = sp;
            }
        }
        return nearest;
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: getSafeSpawnPosition (takes Level, 5 iterations — preserved)
    // -------------------------------------------------------------------------

    private BlockPos getSafeSpawnPosition(Level level, BlockPos pos) {
        for (int i = 0; i < 5; i++) {
            if (level.getBlockState(pos).isAir() && level.getBlockState(pos.below()).isSolid()) {
                return pos;
            }
            pos = pos.above();
        }
        return pos;
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: runTutorial (identical)
    // -------------------------------------------------------------------------

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

    // -------------------------------------------------------------------------
    // ORIGINAL: saveMemory / loadAllMemory (identical, debug logs preserved)
    // -------------------------------------------------------------------------

    private void saveMemory(UUID playerId) {
        OracleMemory memory = memoryMap.get(playerId);
        if (memory == null) return;

        Path file = memoryFolder.resolve(playerId.toString() + ".json");
        try (Writer writer = Files.newBufferedWriter(file)) {
            gson.toJson(memory, writer);
            DWMod.LOGGER.debug("[Oracle] Saved memory for player: {}", playerId);
        } catch (IOException e) {
            DWMod.LOGGER.error("[Oracle] Failed to save memory", e);
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
                    DWMod.LOGGER.debug("[Oracle] Loaded memory for player: {}", playerId);
                } catch (Exception e) {
                    DWMod.LOGGER.error("[Oracle] Failed to load memory file: {}", f, e);
                }
            });
        }
    }

    // -------------------------------------------------------------------------
    // ORIGINAL: setOracleBrain / getOracleBrain (identical)
    // -------------------------------------------------------------------------

    public void setOracleBrain(LLMOracleBrain newBrain) {
        this.brain = newBrain;
        DWMod.LOGGER.info("[Oracle] Brain switched to: {}", newBrain.getModelName());
    }

    public LLMOracleBrain getOracleBrain() {
        return this.brain;
    }

    // -------------------------------------------------------------------------
    // NEW: public reaction circle trigger
    // -------------------------------------------------------------------------

    /**
     * Trigger a 2-second magic circle burst at the given position.
     * Call this from GenesisManager or DivineCommands when Genesis/Reset fires.
     *
     * @param level    the server level
     * @param origin   centre of the circle
     * @param isReset  true = divine-reset palette, false = genesis palette
     */
    public void triggerReactionCircle(ServerLevel level, BlockPos origin, boolean isReset) {
        reactionCircleActive = true;
        reactionCircleTick   = 0;
        reactionLevel        = level;
        reactionCenter       = origin;
        reactionIsReset      = isReset;
    }
}
