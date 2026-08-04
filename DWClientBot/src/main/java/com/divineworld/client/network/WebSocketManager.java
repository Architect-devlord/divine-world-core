package com.divineworld.client.network;

import com.divineworld.client.DWClientMod;
import com.divineworld.client.entity.GodEntityManager;
import com.divineworld.client.vision.AudioCaptureSystem;
import com.divineworld.client.vision.VisionCaptureSystem;
import com.divineworld.client.control.ActionExecutor;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.culling.Frustum;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.animal.Animal;
import net.minecraft.world.entity.boss.enderdragon.EnderDragon;
import net.minecraft.world.entity.boss.wither.WitherBoss;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.monster.Monster;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * WebSocket Manager — Full rewrite with entity perception + wire format fixes.
 *
 * FIX F1 — wsFuture.join() removed from main thread (original)
 * FIX F2 — JPEG encoding moved off main thread (original)
 * FIX F3 — sendBinary() moved off main thread (original)
 * FIX F4 — reduced default capture resolution (original)
 *
 * NEW FIX W1 — Wire format mismatch: audio metadata section
 *   Java previously always wrote sampleRate + channels + bitsPerSample after
 *   audio data, even when audio_len = 0.  Python only reads those fields when
 *   audio_len > 0.  When the agent was silent, 6 bytes were left unconsumed and
 *   got misread as the sound_count field.  Fix: only write audio metadata when
 *   audio_len > 0, matching the Python decoder.
 *
 * NEW FIX W2 — Entity count hardcoded to 0
 *   entity_count was always written as 0, so perception.entities was always [].
 *   The agent could not see any nearby entity — zombies, players, animals were
 *   invisible to the perception system, making the learning loop unable to
 *   associate visual patterns with entity-related rewards.
 *   Fix: collectNearbyEntities() gathers entities within 32 blocks, assigns
 *   type_id bytes (hostile/passive/player/boss/item/projectile/god), and
 *   serializes them into the frame using the exact format Python expects:
 *     [1]  type_id  (uint8)
 *     [4]  name_len (uint32)
 *     [N]  name     (UTF-8 registry name, no "minecraft:" prefix)
 *     [4]  distance (float32, metres)
 *     [4]  angle    (float32, degrees relative to player's yaw)
 *   (plus rel_dx/rel_dy/rel_dz/movement_speed floats added later — see the
 *   full layout above buildPerceptionFrame() for the current field list)
 *
 * NEW FIX W3 — Sound events never sent
 *   Python's decoder reads a sound_count after the audio section, but Java
 *   never wrote it.  The try/except in Python swallowed this silently.
 *   Fix: add a static ConcurrentLinkedQueue<Map<String,Object>> for sound
 *   events.  Other client-mod classes (ClientEventHandler, etc.) call
 *   WebSocketManager.queueSoundEvent(map) when a relevant sound fires.
 *   The perception frame now includes those events after the audio section,
 *   exactly matching what Python's unpack_perception expects.
 *
 * NEW FIX W4 — perceptionExecutor thread leak on reconnect
 *   scheduleReconnect() ran on the old executor, which called initialize() and
 *   reassigned perceptionExecutor to a new instance without shutting the old
 *   one down.  One daemon thread leaked per disconnect cycle.
 *   Fix: explicitly shutdownNow() the old executor before replacing it.
 *
 * NEW FIX W5 — Reconnect stuck when initial connection fails
 *   If the first TCP handshake failed before onOpen() → startPerceptionLoop(),
 *   perceptionExecutor was null. scheduleReconnect() null-checked and returned
 *   without scheduling a retry — the client was permanently stuck.
 *   Fix: a static reconnect executor (separate from perceptionExecutor) is
 *   created once and never reassigned, so it is always available for retries.
 */
public class WebSocketManager {

    private static volatile WebSocket  webSocket;
    private static volatile String     agentId;
    private static final AtomicBoolean connected  = new AtomicBoolean(false);
    private static final AtomicBoolean connecting = new AtomicBoolean(false);

    private static volatile ScheduledExecutorService perceptionExecutor;

    /** FIX W5: dedicated reconnect executor — never nulled or replaced. */
    private static final ScheduledExecutorService reconnectExecutor =
        Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "DW-Reconnect");
            t.setDaemon(true);
            return t;
        });

    /** JPEG encoding + WS send — single thread keeps frames sequential. */
    private static final ExecutorService encodeExecutor =
        Executors.newSingleThreadExecutor(r -> {
            Thread t = new Thread(r, "DW-Encode-Send");
            t.setDaemon(true);
            t.setPriority(Thread.NORM_PRIORITY - 1);
            return t;
        });

    private static final int MAGIC            = 0x44574149;
    private static final int FRAME_CHAT       = 0x03;
    private static final int FRAME_PERCEPTION = 0x01;
    private static final int FRAME_ACTION     = 0x02;

    /** Entity type_id constants — must match Python protocol docstring. */
    private static final byte ENTITY_UNKNOWN    = 0;
    private static final byte ENTITY_PLAYER     = 1;
    private static final byte ENTITY_HOSTILE    = 2;
    private static final byte ENTITY_PASSIVE    = 3;
    private static final byte ENTITY_ITEM       = 4;
    private static final byte ENTITY_BOSS       = 5;
    private static final byte ENTITY_PROJECTILE = 6;
    private static final byte ENTITY_GOD        = 7;

    /** Max entities serialised per frame — limits frame size on crowded servers. */
    private static final int MAX_ENTITIES = 20;

    /** Max entity detection radius (blocks). */
    private static final double ENTITY_RADIUS = 32.0;

    /**
     * FIX W3: Sound event queue.
     * Other client classes call queueSoundEvent(map) when sounds fire.
     * Each map should have keys: sound_id, volume, distance, category.
     * The queue is drained once per frame and included in the binary frame.
     */
    private static final ConcurrentLinkedQueue<Map<String, Object>> soundEventQueue =
        new ConcurrentLinkedQueue<>();

    /** Max sound events per frame to bound frame size. */
    private static final int MAX_SOUND_EVENTS = 8;

    /** Per-connection binary frame accumulator. */
    private static volatile ByteArrayOutputStream msgAccum =
        new ByteArrayOutputStream(1024 * 1024);

    // =========================================================================
    // Public API — sound event injection
    // =========================================================================

    /**
     * FIX W3: Called by ClientEventHandler (or any client-mod class) when a
     * Minecraft sound fires near the agent.
     *
     * Required keys: "sound_id" (String), "volume" (Float), "distance" (Float).
     * Optional keys: "category" (String), "position" (Map with "x","y","z").
     */
    public static void queueSoundEvent(Map<String, Object> event) {
        if (event != null && soundEventQueue.size() < 64) {
            soundEventQueue.offer(event);
        }
    }

    // =========================================================================
    // Initialise
    // =========================================================================

    public static void initialize(String url, int port, String agentIdParam) {
        agentId = agentIdParam;

        VisionCaptureSystem.initialize();

        if (connecting.getAndSet(true)) {
            DWClientMod.LOGGER.info("[WS] Already connecting — skipping duplicate init");
            return;
        }

        URI serverUri = URI.create(url + ":" + port + "/ws/agent");
        DWClientMod.LOGGER.info("[WS] Connecting async to {}", serverUri);

        // FIX W4: shut down the old perceptionExecutor before replacing it
        ScheduledExecutorService oldExec = perceptionExecutor;
        if (oldExec != null && !oldExec.isShutdown()) {
            oldExec.shutdownNow();
        }
        perceptionExecutor = null;

        HttpClient client = HttpClient.newHttpClient();

        client.newWebSocketBuilder()
            .buildAsync(serverUri, new WebSocket.Listener() {

                @Override
                public void onOpen(WebSocket ws) {
                    DWClientMod.LOGGER.info("[WS] Connected to backend at {}", serverUri);
                    msgAccum = new ByteArrayOutputStream(1024 * 1024);
                    webSocket = ws;
                    connected.set(true);
                    connecting.set(false);
                    ws.request(1);
                    sendHandshake(ws);
                    startPerceptionLoop();
                }

                @Override
                public CompletionStage<?> onText(WebSocket ws, CharSequence data, boolean last) {
                    DWClientMod.LOGGER.debug("[WS] JSON: {}", data);
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer data, boolean last) {
                    byte[] chunk = new byte[data.remaining()];
                    data.get(chunk);
                    // msgAccum.write() is synchronized in JDK — safe from listener thread
                    try { msgAccum.write(chunk); } catch (Exception ignored) {}
                    if (last) {
                        ByteBuffer complete = ByteBuffer.wrap(msgAccum.toByteArray());
                        msgAccum.reset();
                        if (complete.remaining() >= 8) {
                            int peekMagic = complete.getInt();
                            int peekType  = complete.getInt();
                            complete.rewind();
                            if (peekMagic == MAGIC && peekType == FRAME_CHAT) {
                                handleChatFrame(complete);
                            } else {
                                handleActionFrame(complete);
                            }
                        }
                    }
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(WebSocket ws, int statusCode, String reason) {
                    DWClientMod.LOGGER.warn("[WS] Closed: {} {}", statusCode, reason);
                    connected.set(false);
                    connecting.set(false);
                    scheduleReconnect(url, port);
                    return null;
                }

                @Override
                public void onError(WebSocket ws, Throwable error) {
                    DWClientMod.LOGGER.error("[WS] Error: {}", error.getMessage());
                    connected.set(false);
                    connecting.set(false);
                    scheduleReconnect(url, port);
                }
            })
            .exceptionally(ex -> {
                DWClientMod.LOGGER.error("[WS] Connect failed: {}", ex.getMessage());
                connected.set(false);
                connecting.set(false);
                scheduleReconnect(url, port);
                return null;
            });

        DWClientMod.LOGGER.info("[WS] Connection initiated (non-blocking)");
    }

    // =========================================================================
    // Handshake
    // =========================================================================

    private static void sendHandshake(WebSocket ws) {
        String msg = String.format(
            "{\"agent_id\":\"%s\",\"protocol\":\"binary\",\"version\":\"2.1.0\"}",
            agentId);
        ws.sendText(msg, true);
    }

    // =========================================================================
    // Perception loop
    // =========================================================================

    private static void startPerceptionLoop() {
        ScheduledExecutorService current = perceptionExecutor;
        if (current != null && !current.isShutdown()) return;

        ScheduledExecutorService exec = Executors.newSingleThreadScheduledExecutor(r -> {
            Thread t = new Thread(r, "DW-Perception-Scheduler");
            t.setDaemon(true);
            return t;
        });
        perceptionExecutor = exec;

        exec.scheduleAtFixedRate(() -> {
            if (!connected.get() || webSocket == null) return;
            Minecraft.getInstance().execute(WebSocketManager::captureAndScheduleEncode);
        }, 200, 50, TimeUnit.MILLISECONDS);

        DWClientMod.LOGGER.info("[WS] Perception loop started (20 FPS)");
    }

    /**
     * Runs on Minecraft main thread — pixel readback and entity scan here.
     * All CPU-heavy work (JPEG encode, WS send) handed to encodeExecutor.
     */
    private static void captureAndScheduleEncode() {
        try {
            Minecraft mc = Minecraft.getInstance();
            if (mc.player == null || mc.level == null) return;
            if (!connected.get() || webSocket == null) return;

            // Cheap state reads — safe on main thread
            final float  health = mc.player.getHealth();
            final float  hunger = mc.player.getFoodData().getFoodLevel();
            final double x      = mc.player.getX();
            final double y      = mc.player.getY();
            final double z      = mc.player.getZ();
            final float  yaw    = mc.player.getYRot();
            final float  pitch  = mc.player.getXRot();

            // GPU readback — must be on main thread
            final int[] pixels = VisionCaptureSystem.grabPixels();
            final int   imgW   = VisionCaptureSystem.getWidth();
            final int   imgH   = VisionCaptureSystem.getHeight();
            if (pixels == null) return;

            // FIX W2: collect nearby entities — safe on main thread
            final List<EntityInfo> entities = collectNearbyEntities(mc);

            // Audio — reads from a buffer, safe on main thread
            final byte[] audioData = AudioCaptureSystem.captureAudioFrame();

            // FIX W3: drain sound event queue — snapshot this frame's events
            final List<Map<String, Object>> soundEvents = drainSoundEvents();

            encodeExecutor.submit(() -> {
                try {
                    byte[] imageData = VisionCaptureSystem.encodePixelsToJPEG(pixels, imgW, imgH);
                    if (imageData == null) return;

                    int blockMask = collectBlockNeighbourhood(mc);  // Step 2
                    ByteBuffer frame = buildPerceptionFrame(
                        imageData,
                        audioData != null ? audioData : new byte[0],
                        health, hunger, x, y, z, yaw, pitch,
                        imgW, imgH,
                        entities,
                        soundEvents,
                        blockMask
                    );

                    WebSocket ws = webSocket;
                    if (ws != null && connected.get()) {
                        ws.sendBinary(frame, true);
                    }
                } catch (Exception e) {
                    DWClientMod.LOGGER.error("[WS] Encode/send error: {}", e.getMessage());
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] captureAndScheduleEncode error: {}", e.getMessage());
        }
    }

    // =========================================================================
    // FIX W2 — Entity collection
    // =========================================================================

    private static final class EntityInfo {
        final byte   typeId;
        final String name;
        final float  distance;
        final float  angle;         // degrees, relative to player yaw (0 = in front)

        // Step 1 — egocentric relative position (same rotation convention as angle).
        // relDx = forward component (+ve = ahead), relDz = right component (+ve = right),
        // relDy = vertical offset (+ve = above player eye).  movementSpeed = scalar
        // magnitude of getDeltaMovement(); forced to 0 for ENTITY_UNKNOWN (audible-only).
        final float  relDx;
        final float  relDy;
        final float  relDz;
        final float  movementSpeed;

        EntityInfo(byte typeId, String name, float distance, float angle,
                   float relDx, float relDy, float relDz, float movementSpeed) {
            this.typeId        = typeId;
            this.name          = name;
            this.distance      = distance;
            this.angle         = angle;
            this.relDx         = relDx;
            this.relDy         = relDy;
            this.relDz         = relDz;
            this.movementSpeed = movementSpeed;
        }
    }

    /**
     * Collect entities the agent can currently SEE — not all nearby entities.
     *
     * Two-phase pipeline:
     *
     * Phase 1 — VISUAL (in frustum + line of sight):
     *   Use entitiesForRendering() which Minecraft already frustum-culls to the
     *   camera view.  For each candidate we additionally fire a ClipContext ray
     *   from the player's eye to the entity's centre — if the ray hits a solid
     *   block before reaching the entity, it is occluded and excluded.
     *   These entities are serialised with their real type_id and name so the
     *   agent can learn to associate visual patterns with entity types.
     *
     * Phase 2 — AUDIBLE (nearby but not visible, within SOUND_RADIUS):
     *   Entities inside SOUND_RADIUS that did NOT pass the visibility test are
     *   sent with type_id = ENTITY_UNKNOWN and name = "" so the agent gets a
     *   distance/angle signal (it "hears" something close) without knowing what
     *   it is.  This mirrors real perception: you hear rustling before you see
     *   the zombie.  The agent must turn toward the sound to identify it.
     *
     * Both phases run on the Minecraft main thread.
     */
    private static final double SOUND_RADIUS    = 16.0;   // audible but not visible
    private static final double SOUND_RADIUS_SQ = SOUND_RADIUS * SOUND_RADIUS;
    private static final double ENTITY_RADIUS_SQ = ENTITY_RADIUS * ENTITY_RADIUS;

    private static List<EntityInfo> collectNearbyEntities(Minecraft mc) {
        List<EntityInfo> result = new ArrayList<>();
        if (mc.player == null || mc.level == null) return result;

        Vec3   eyePos    = mc.player.getEyePosition();
        Vec3   playerPos = mc.player.position();
        double playerYaw = mc.player.getYRot();

        // ── Phase 1: frustum-culled + line-of-sight visible entities ──────
        // entitiesForRendering() returns only entities already in the camera
        // frustum — no need for a separate Frustum object.
        java.util.Set<java.util.UUID> visibleIds = new java.util.HashSet<>();

        for (Entity entity : mc.level.entitiesForRendering()) {
            if (entity == mc.player) continue;
            if (result.size() >= MAX_ENTITIES) break;

            double distSq = entity.distanceToSqr(playerPos);
            if (distSq > ENTITY_RADIUS_SQ) continue;

            // Line-of-sight raycast: player eye → entity centre
            Vec3 entityCentre = entity.getBoundingBox().getCenter();
            HitResult hit = mc.level.clip(new ClipContext(
                eyePos,
                entityCentre,
                ClipContext.Block.COLLIDER,
                ClipContext.Fluid.NONE,
                mc.player
            ));

            // If the ray hit a block before reaching the entity, it is occluded
            double hitDistSq = hit.getType() == HitResult.Type.BLOCK
                ? hit.getLocation().distanceToSqr(eyePos)
                : Double.MAX_VALUE;
            if (hitDistSq < entityCentre.distanceToSqr(eyePos) * 0.95) continue;

            float dist  = (float) Math.sqrt(distSq);
            float angle = computeRelativeAngle(playerPos, playerYaw, entity.position());
            byte  typeId = classifyEntity(entity);

            String regName = entity.getType().toString();
            if (regName.startsWith("minecraft:")) regName = regName.substring("minecraft:".length());
            if (regName.length() > 48) regName = regName.substring(0, 48);

            visibleIds.add(entity.getUUID());

            // Step 1: derive egocentric forward/right/vertical offsets from the
            // already-computed relative angle, guaranteeing the same rotation
            // convention as computeRelativeAngle() with no independent trig.
            Vec3  entityCentreForSpeed = entity.getBoundingBox().getCenter();
            float angleRad    = (float) Math.toRadians(angle);
            float relDxVal    = dist * (float) Math.cos(angleRad);   // forward
            float relDzVal    = dist * (float) Math.sin(angleRad);   // right
            float relDyVal    = (float) (entityCentreForSpeed.y - eyePos.y);
            float speedVal    = (float) entity.getDeltaMovement().length();
            result.add(new EntityInfo(typeId, regName, dist, angle,
                                      relDxVal, relDyVal, relDzVal, speedVal));
        }

        // ── Phase 2: nearby-but-not-visible (audible range) ───────────────
        // Use getEntities() for the full nearby set — includes entities that may
        // not be in the frustum (e.g. behind the player within 16 blocks).
        if (result.size() < MAX_ENTITIES) {
            AABB soundBox = mc.player.getBoundingBox().inflate(SOUND_RADIUS);
            for (Entity entity : mc.level.getEntities(mc.player, soundBox)) {
                if (entity == mc.player) continue;
                if (visibleIds.contains(entity.getUUID())) continue;  // already in phase 1
                if (result.size() >= MAX_ENTITIES) break;

                double distSq = entity.distanceToSqr(playerPos);
                if (distSq > SOUND_RADIUS_SQ) continue;

                float dist  = (float) Math.sqrt(distSq);
                float angle = computeRelativeAngle(playerPos, playerYaw, entity.position());

                // ENTITY_UNKNOWN + empty name: agent senses presence but cannot
                // identify it without turning to look.  Encourages exploration behaviour.
                // Step 1: full position info for audible entities; movement_speed forced to
                // 0 since speed can't be inferred from sound alone (per plan spec).
                float aAngleRad = (float) Math.toRadians(angle);
                float aRelDx    = dist * (float) Math.cos(aAngleRad);
                float aRelDz    = dist * (float) Math.sin(aAngleRad);
                float aRelDy    = (float) (entity.getBoundingBox().getCenter().y - eyePos.y);
                result.add(new EntityInfo(ENTITY_UNKNOWN, "", dist, angle,
                                          aRelDx, aRelDy, aRelDz, 0f));
            }
        }

        return result;
    }

    private static byte classifyEntity(Entity entity) {
        if (entity instanceof EnderDragon || entity instanceof WitherBoss) return ENTITY_BOSS;
        if (entity instanceof Monster)    return ENTITY_HOSTILE;
        if (entity instanceof Animal)     return ENTITY_PASSIVE;
        if (entity instanceof Player)     return ENTITY_PLAYER;
        if (entity instanceof ItemEntity) return ENTITY_ITEM;
        if (entity instanceof Projectile) return ENTITY_PROJECTILE;
        // Check if this is the local agent's own god body
        if (GodEntityManager.isGodEntity(entity)) return ENTITY_GOD;
        return ENTITY_UNKNOWN;
    }

    /**
     * Step 2 — Collect the 3×3×3 block neighbourhood around the agent's feet,
     * packed as a single uint32 bitmask (27 bits used, LSB = cell 0).
     *
     * Each bit is 1 if the cell is passable (no collision shape: air, liquids,
     * plants, signs, torches…) or 0 if solid/collidable. This is the only
     * block signal the agent receives — no type ID, no hardness, no material.
     *
     * Sampling order: forward/right/up (egocentric), where forward snaps to the
     * nearest cardinal direction, keeping "block directly ahead" in a stable slot
     * regardless of which way the agent faces.
     */
    private static int collectBlockNeighbourhood(Minecraft mc) {
        if (mc.player == null || mc.level == null) return 0;

        Level level  = mc.level;
        Vec3  pos    = mc.player.position();
        int   feetX  = (int) Math.floor(pos.x);
        int   feetY  = (int) Math.floor(pos.y);
        int   feetZ  = (int) Math.floor(pos.z);

        // Snap yaw to nearest cardinal using the same convention as computeRelativeAngle:
        // yaw=0 → forward=(0,0,+1)=south, 90 → (+1,0,0)=east, etc.
        float snapRad = (float) Math.toRadians(Math.round(mc.player.getYRot() / 90f) * 90f);
        int fwdX = Math.round((float) Math.sin(snapRad));
        int fwdZ = Math.round((float) Math.cos(snapRad));
        // Right = forward rotated 90° clockwise (sin→cos, cos→−sin)
        int rgtX = Math.round((float) Math.cos(snapRad));
        int rgtZ = -Math.round((float) Math.sin(snapRad));

        int mask = 0;
        int bit  = 0;
        // Iterate forward[-1..1], right[-1..1], up[-1..1]
        for (int f = -1; f <= 1; f++) {
            for (int r = -1; r <= 1; r++) {
                for (int u = -1; u <= 1; u++) {
                    int wx = feetX + f * fwdX + r * rgtX;
                    int wy = feetY + u;
                    int wz = feetZ + f * fwdZ + r * rgtZ;
                    BlockState bs = level.getBlockState(new BlockPos(wx, wy, wz));
                    // isPassable = 1 when no collision shape (air, liquid, vegetation…)
                    boolean passable = bs.getCollisionShape(level, new BlockPos(wx, wy, wz)).isEmpty();
                    if (passable) mask |= (1 << bit);
                    bit++;
                }
            }
        }
        return mask;
    }

    /**
     * Angle of `target` relative to `observer`'s yaw, in degrees.
     * 0° = directly in front, ±90° = to the sides, ±180° = behind.
     */
    private static float computeRelativeAngle(Vec3 observer, double observerYaw, Vec3 target) {
        double dx    = target.x - observer.x;
        double dz    = target.z - observer.z;
        double angle = Math.toDegrees(Math.atan2(dx, dz)) - observerYaw;
        // Normalise to [-180, 180]
        while (angle >  180) angle -= 360;
        while (angle < -180) angle += 360;
        return (float) angle;
    }

    // =========================================================================
    // FIX W3 — Sound event queue drain
    // =========================================================================

    private static List<Map<String, Object>> drainSoundEvents() {
        List<Map<String, Object>> events = new ArrayList<>();
        Map<String, Object> ev;
        while ((ev = soundEventQueue.poll()) != null && events.size() < MAX_SOUND_EVENTS) {
            events.add(ev);
        }
        return events;
    }

    // =========================================================================
    // Frame builder
    // =========================================================================

    /**
     * Build a FRAME_PERCEPTION binary frame.
     *
     * Wire layout (must match BinaryProtocol.unpack_perception in Python):
     *   [4]  MAGIC
     *   [4]  frame type (0x01)
     *   [4]  agent_id length
     *   [N]  agent_id UTF-8
     *   [8]  timestamp (double, seconds)
     *   [4]  image_data length
     *   [N]  image_data (JPEG)
     *   [2]  image_width (uint16)
     *   [2]  image_height (uint16)
     *   [4]  health (float32)
     *   [4]  hunger (float32)
     *   [4]  x (float32)
     *   [4]  y (float32)
     *   [4]  z (float32)
     *   [4]  yaw (float32)
     *   [4]  pitch (float32)
     *   [2]  entity_count (uint16)
     *   per entity:
     *     [1]  type_id (uint8)
     *     [4]  name_len (uint32)
     *     [N]  name UTF-8
     *     [4]  distance (float32)
     *     [4]  angle (float32)
     *     [4]  rel_dx (float32)          — egocentric forward offset
     *     [4]  rel_dy (float32)          — vertical offset from eye height
     *     [4]  rel_dz (float32)          — egocentric right offset
     *     [4]  movement_speed (float32)  — magnitude of entity's delta movement
     *   [4]  audio_data length
     *   [N]  audio_data (only present when length > 0)
     *   [4]  sample_rate (uint32)  ← FIX W1: only written when audio_len > 0
     *   [1]  channels (uint8)       ← FIX W1: only written when audio_len > 0
     *   [1]  bits_per_sample (uint8) ← FIX W1: only written when audio_len > 0
     *   [2]  sound_event_count (uint16)   ← FIX W3: new field
     *   per sound event:
     *     [4]  event_json_len (uint32)
     *     [N]  event_json UTF-8
     */
    private static ByteBuffer buildPerceptionFrame(
            byte[] imageData,
            byte[] audioData,
            float health, float hunger,
            double x, double y, double z,
            float yaw, float pitch,
            int imgW, int imgH,
            List<EntityInfo> entities,
            List<Map<String, Object>> soundEvents,
            int blockMask) {       // Step 2: 27-bit passability bitmask

        byte[] idBytes = agentId.getBytes(StandardCharsets.UTF_8);
        boolean hasAudio = audioData.length > 0;

        // Serialise entity bytes
        List<byte[]> entityBlobs = new ArrayList<>();
        for (EntityInfo ei : entities) {
            byte[] nameBytes = ei.name.getBytes(StandardCharsets.UTF_8);
            // Step 1: extended entity format (additive — existing fields unchanged):
            //   1(typeId) + 4(nameLen) + N(name) + 4(dist) + 4(angle)
            //   + 4(relDx) + 4(relDy) + 4(relDz) + 4(movementSpeed)
            ByteBuffer eb = ByteBuffer.allocate(1 + 4 + nameBytes.length + 4 + 4 + 4 + 4 + 4 + 4);
            eb.put(ei.typeId);
            eb.putInt(nameBytes.length);
            eb.put(nameBytes);
            eb.putFloat(ei.distance);
            eb.putFloat(ei.angle);
            eb.putFloat(ei.relDx);
            eb.putFloat(ei.relDy);
            eb.putFloat(ei.relDz);
            eb.putFloat(ei.movementSpeed);
            entityBlobs.add(eb.array());
        }

        // Serialise sound event JSON blobs
        List<byte[]> soundBlobs = new ArrayList<>();
        for (Map<String, Object> ev : soundEvents) {
            try {
                StringBuilder sb = new StringBuilder("{");
                ev.forEach((k, v) -> {
                    sb.append("\"").append(k).append("\":");
                    if (v instanceof String) sb.append("\"").append(v).append("\"");
                    else sb.append(v);
                    sb.append(",");
                });
                if (sb.charAt(sb.length() - 1) == ',') sb.setCharAt(sb.length() - 1, '}');
                else sb.append('}');
                soundBlobs.add(sb.toString().getBytes(StandardCharsets.UTF_8));
            } catch (Exception ignored) {}
        }

        // Calculate total frame size
        int entityBytes = entityBlobs.stream().mapToInt(b -> b.length).sum();
        // FIX W1: audio metadata section size depends on whether audio is present
        int audioSection = 4 + audioData.length + (hasAudio ? 4 + 1 + 1 : 0);
        int soundSection = 2 + soundBlobs.stream().mapToInt(b -> 4 + b.length).sum();

        int total = 4 + 4                          // MAGIC + type
                  + 4 + idBytes.length             // agent_id
                  + 8                               // timestamp
                  + 4 + imageData.length           // image
                  + 2 + 2                           // imgW, imgH
                  + 4 + 4                           // health, hunger
                  + 4 + 4 + 4                       // x, y, z
                  + 4 + 4                           // yaw, pitch
                  + 2 + entityBytes                 // entities
                  + audioSection
                  + soundSection
                  + 4;                              // Step 2: block neighbourhood (uint32 bitmask)

        ByteBuffer buf = ByteBuffer.allocate(total);

        buf.putInt(MAGIC);
        buf.putInt(FRAME_PERCEPTION);
        buf.putInt(idBytes.length);
        buf.put(idBytes);
        buf.putDouble(System.currentTimeMillis() / 1000.0);
        buf.putInt(imageData.length);
        buf.put(imageData);
        buf.putShort((short) imgW);
        buf.putShort((short) imgH);
        buf.putFloat(health);
        buf.putFloat(hunger);
        buf.putFloat((float) x);
        buf.putFloat((float) y);
        buf.putFloat((float) z);
        buf.putFloat(yaw);
        buf.putFloat(pitch);

        // Entities (FIX W2)
        buf.putShort((short) entityBlobs.size());
        for (byte[] eb : entityBlobs) buf.put(eb);

        // Audio (FIX W1: metadata only written when audio present)
        buf.putInt(audioData.length);
        if (hasAudio) {
            buf.put(audioData);
            buf.putInt(AudioCaptureSystem.getSampleRate());
            buf.put((byte) AudioCaptureSystem.getChannels());
            buf.put((byte) AudioCaptureSystem.getBitsPerSample());
        }

        // Sound events (FIX W3)
        buf.putShort((short) soundBlobs.size());
        for (byte[] sb : soundBlobs) {
            buf.putInt(sb.length);
            buf.put(sb);
        }

        // Step 2: block neighbourhood — 27-bit passability bitmask packed into uint32.
        // Appended last so all older fields are at unchanged byte offsets; Python decoder
        // reads this inside a try-except exactly like it handles sound events.
        buf.putInt(blockMask);

        buf.flip();
        return buf;
    }

    // =========================================================================
    // Inbound: ChatFrame (Python → Minecraft)
    // =========================================================================

    private static void handleChatFrame(ByteBuffer buf) {
        try {
            if (buf.remaining() < 8) return;
            if (buf.getInt() != MAGIC) return;
            if (buf.getInt() != FRAME_CHAT) return;

            int aidLen = buf.getInt();
            if (aidLen > 0 && buf.remaining() >= aidLen)
                buf.position(buf.position() + aidLen);

            if (buf.remaining() >= 8) buf.getDouble(); // timestamp

            if (buf.remaining() < 4) return;
            int msgLen = buf.getInt();
            if (msgLen <= 0 || buf.remaining() < msgLen) return;

            byte[] msgBytes = new byte[msgLen];
            buf.get(msgBytes);
            final String message = new String(msgBytes, StandardCharsets.UTF_8);

            Minecraft.getInstance().execute(() -> {
                net.minecraft.client.multiplayer.ClientPacketListener conn =
                    Minecraft.getInstance().getConnection();
                if (conn != null && !message.isEmpty()) {
                    String trimmed = message.length() > 256 ? message.substring(0, 256) : message;
                    conn.sendChat(trimmed);
                    DWClientMod.LOGGER.info("[WS] Agent spoke: {}", trimmed);
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] handleChatFrame error: {}", e.getMessage());
        }
    }

    // =========================================================================
    // Inbound: ActionFrame (Python → Minecraft)
    // =========================================================================

    private static void handleActionFrame(ByteBuffer buf) {
        try {
            if (buf.remaining() < 8) return;
            if (buf.getInt() != MAGIC) {
                DWClientMod.LOGGER.warn("[WS] Bad magic in action frame");
                return;
            }
            if (buf.getInt() != FRAME_ACTION) return;

            int aidLen = buf.getInt();
            if (aidLen > 0 && buf.remaining() >= aidLen)
                buf.position(buf.position() + aidLen);

            buf.getDouble(); // timestamp

            final float moveForward = buf.getFloat();
            final float moveStrafe  = buf.getFloat();
            final float yawDelta    = buf.getFloat();
            final float pitchDelta  = buf.getFloat();
            final byte  actionFlags = buf.get();
            final int   rawHotbar   = buf.get() & 0xFF;
            final int   hotbar      = (rawHotbar == 0xFF) ? -1 : rawHotbar;

            String godAbility = null;
            float  p1 = 0f, p2 = 0f, p3 = 0f;
            if (buf.remaining() >= 2) {
                int alen = buf.getShort() & 0xFFFF;
                if (alen > 0 && buf.remaining() >= alen) {
                    byte[] ab = new byte[alen];
                    buf.get(ab);
                    godAbility = new String(ab, StandardCharsets.UTF_8);
                    if (buf.remaining() >= 12) {
                        p1 = buf.getFloat();
                        p2 = buf.getFloat();
                        p3 = buf.getFloat();
                    }
                }
            }

            final String fa  = godAbility;
            final float fp1  = p1, fp2 = p2, fp3 = p3;
            final int fHotbar = hotbar;

            Minecraft.getInstance().execute(() -> {
                ActionExecutor.executeAction(
                    moveForward, moveStrafe, yawDelta, pitchDelta, actionFlags, fHotbar);

                // FIX (WS action-frame parity gap): this used to call
                // GodEntityManager.executeGodAbility() unconditionally for
                // any non-empty ability string, never learning the
                // inv:/screen: prefix distinction TCPServer.java already
                // has. Packaged agents appear to only use this WS
                // transport, so this meant they could never open
                // inventory or interact with screens at all - only real
                // god abilities ever reached GodEntityManager correctly.
                if (fa == null || fa.isEmpty()) return;

                if (fa.startsWith("inv:")) {
                    ActionExecutor.executeInventoryAction(fa);

                } else if (fa.startsWith("screen:")) {
                    ActionExecutor.executeScreenAction(fa);

                } else {
                    try {
                        GodEntityManager.executeGodAbility(fa, fp1, fp2, fp3);
                    } catch (Exception e) {
                        DWClientMod.LOGGER.debug("[WS] God ability dispatch error: {}",
                                e.getMessage());
                    }
                }
            });

        } catch (Exception e) {
            DWClientMod.LOGGER.error("[WS] handleActionFrame error: {}", e.getMessage());
        }
    }

    // =========================================================================
    // Reconnect — FIX W4 + W5
    // =========================================================================

    private static void scheduleReconnect(String url, int port) {
        // FIX W5: use reconnectExecutor (never null) instead of perceptionExecutor
        // (which is null if the first connection fails before onOpen fires).
        reconnectExecutor.schedule(() -> {
            DWClientMod.LOGGER.info("[WS] Attempting reconnect...");
            initialize(url, port, agentId);
        }, 5, TimeUnit.SECONDS);
    }

    // =========================================================================
    // Outbound text — proximity chat observation
    // =========================================================================

    public static void sendChatObservation(String speaker, String message) {
        if (!connected.get() || webSocket == null) return;
        String s  = message.replace("\\", "\\\\").replace("\"", "\\\"");
        String sp = speaker.replace("\\", "\\\\").replace("\"", "\\\"");
        String json = String.format(
            "{\"type\":\"chat_heard\",\"agent_id\":\"%s\","
          + "\"speaker\":\"%s\",\"message\":\"%s\",\"timestamp\":%d}",
            agentId, sp, s, System.currentTimeMillis());
        webSocket.sendText(json, true);
    }

    // =========================================================================
    // Lifecycle
    // =========================================================================

    public static void shutdown() {
        connected.set(false);
        connecting.set(false);
        ScheduledExecutorService exec = perceptionExecutor;
        if (exec != null) exec.shutdownNow();
        WebSocket ws = webSocket;
        if (ws != null) ws.sendClose(WebSocket.NORMAL_CLOSURE, "Shutting down");
        VisionCaptureSystem.cleanup();
    }

    public static boolean isConnected() { return connected.get(); }
}