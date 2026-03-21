# ai_core/communication_protocol.py
"""
High-performance communication protocol for DW AI ↔ Minecraft integration.
Uses WebSocket with binary frames for minimal latency.

Protocol Design
---------------
- WebSocket for bidirectional, low-latency communication
- Binary frames for images (JPEG compressed)
- MessagePack for efficient action serialization
- Frame buffering for smooth 20+ FPS video

Latency Target: <50ms round-trip (perception → action)

Vision Integration
------------------
Frames received here are pushed directly into the agent's VisionAdapter
via agent.vision.push_minecraft_frame(frame_bgr).

The VisionAdapter (vision.py) then:
  1. Extracts features with the agent's own learned CNN
  2. Assigns a visual token via online k-means (agent's own vocabulary)
  3. Stores the frame in agent memory
  4. Feeds the proprio vector to the WorldModel

No pretrained labels are used — the agent builds its visual vocabulary
purely from what it observes through this protocol.

Entity Type Convention
-----------------------
Entity types are transmitted as a (type_id, name, distance, angle) tuple.
type_id is an integer the agent will learn to associate with behaviour.
name is a raw string label from the Minecraft mod — the agent is NOT told
what it means; language grounding happens separately in brain_language.py.
"""

import asyncio
import json
import struct
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
import numpy as np
from io import BytesIO

try:
    import msgpack
except ImportError:
    msgpack = None
    print("⚠️  msgpack not installed. Install with: pip install msgpack")

log = logging.getLogger("comm_protocol")


# ─────────────────────────────────────────────────────────────────────────────
# Global visual-frame hook — vision.py registers itself here
# ─────────────────────────────────────────────────────────────────────────────

# vision.py's _wire_minecraft_protocol() replaces this with a real handler.
# Signature: (agent_id: str, frame_bgr: np.ndarray) -> None
_on_visual_frame = None


def _dispatch_visual_frame(agent_id: str, frame_bgr: np.ndarray):
    """
    Call the registered visual-frame hook (set by vision.py).
    Safe to call even before the hook is registered — silently no-ops.
    """
    global _on_visual_frame
    if _on_visual_frame is not None:
        try:
            _on_visual_frame(agent_id, frame_bgr)
        except Exception as e:
            log.warning(f"_on_visual_frame hook error for {agent_id}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PerceptionFrame:
    """Single perception frame from Minecraft client."""
    agent_id: str
    timestamp: float

    # Visual data (JPEG compressed)
    image_data: bytes
    image_width: int
    image_height: int

    # Game state
    health: float
    hunger: float
    position: tuple   # (x, y, z)
    rotation: tuple   # (yaw, pitch)

    # Entities: list of (type_id: int, name: str, distance: float, angle: float)
    entities: list

    # Optional raw PCM audio from server-side microphone capture
    audio_data: Optional[bytes] = None
    audio_sample_rate: Optional[int] = None

    # Optional structured sound events from the Minecraft mod.
    # Each entry is a dict: {sound_id, volume, distance, category, position?}
    # The mod sends these when entities nearby make sounds, blocks break, etc.
    # Routed to MinecraftSoundAdapter.receive_sound_event() in the WS handler.
    sound_events: Optional[list] = None


@dataclass
class ActionFrame:
    """Action command to Minecraft client."""
    agent_id: str
    timestamp: float

    # Movement (floats -1.0 to 1.0)
    move_forward: float
    move_strafe: float

    # Camera (floats in degrees)
    yaw_delta: float
    pitch_delta: float

    # Boolean actions packed into a single byte
    # bits: jump | sneak | attack | use | drop | open_inv | swap_hand | sprint
    action_flags: int

    # Optional inventory slot (0–8), None = no change
    hotbar_slot: Optional[int] = None

    # Optional god-mode ability (DW-specific extension)
    god_ability: Optional[str] = None
    god_params: Optional[Dict[str, float]] = None


@dataclass
class ChatFrame:
    """Chat message from agent → Minecraft client."""
    agent_id: str
    timestamp: float
    message: str


# ─────────────────────────────────────────────────────────────────────────────
# Binary protocol
# ─────────────────────────────────────────────────────────────────────────────

class BinaryProtocol:
    """
    Binary frame codec.

    PERCEPTION FRAME (Client → Backend)
    ────────────────────────────────────
    [4]  Magic 0x44574149 ('DWAI')
    [4]  Frame type 0x01
    [4]  Agent-ID length
    [N]  Agent-ID (UTF-8)
    [8]  Timestamp (double)
    [4]  JPEG length
    [N]  JPEG bytes
    [2]  Image width
    [2]  Image height
    [4]  Health (float)
    [4]  Hunger (float)
    [12] Position (3× float x, y, z)
    [8]  Rotation (2× float yaw, pitch)
    [2]  Entity count
    For each entity:
      [1]  type_id (uint8)
      [4]  name length (uint32)
      [N]  name (UTF-8)
      [4]  distance (float)
      [4]  angle (float)
    [4]  Audio length (0 = no audio)
    [N]  Audio bytes  (if length > 0)
    [4]  Audio sample rate (if audio present)
    [2]  Sound event count (uint16)
    For each sound event (JSON-encoded for simplicity):
      [4]  JSON length (uint32)
      [N]  JSON bytes (UTF-8)

    ACTION FRAME (Backend → Client)
    ────────────────────────────────
    [4]  Magic 0x44574149
    [4]  Frame type 0x02
    [4]  Agent-ID length
    [N]  Agent-ID (UTF-8)
    [8]  Timestamp (double)
    [4]  move_forward (float)
    [4]  move_strafe  (float)
    [4]  yaw_delta    (float)
    [4]  pitch_delta  (float)
    [1]  action_flags (uint8)
    [1]  hotbar_slot  (uint8, 0xFF = none)
    [2]  god_ability length (uint16, 0 = none)
    [N]  god_ability (UTF-8, if length > 0)
    [4]  param1 (float, present when ability length > 0)
    [4]  param2 (float)
    [4]  param3 (float)
    """

    MAGIC              = 0x44574149   # 'DWAI'
    FRAME_PERCEPTION   = 0x01
    FRAME_ACTION       = 0x02
    FRAME_CHAT         = 0x03

    # ── Perception ────────────────────────────────────────────────────────

    @staticmethod
    def pack_perception(frame: PerceptionFrame) -> bytes:
        buf = BytesIO()

        buf.write(struct.pack('!II', BinaryProtocol.MAGIC,
                              BinaryProtocol.FRAME_PERCEPTION))

        aid = frame.agent_id.encode('utf-8')
        buf.write(struct.pack('!I', len(aid)))
        buf.write(aid)

        buf.write(struct.pack('!d', frame.timestamp))

        buf.write(struct.pack('!I', len(frame.image_data)))
        buf.write(frame.image_data)
        buf.write(struct.pack('!HH', frame.image_width, frame.image_height))

        buf.write(struct.pack('!ff', frame.health, frame.hunger))
        buf.write(struct.pack('!fff', *frame.position))
        buf.write(struct.pack('!ff', *frame.rotation))

        buf.write(struct.pack('!H', len(frame.entities)))
        for entity in frame.entities:
            type_id, name, distance, angle = entity
            name_bytes = (name or "").encode('utf-8')
            buf.write(struct.pack('!B', int(type_id)))
            buf.write(struct.pack('!I', len(name_bytes)))
            buf.write(name_bytes)
            buf.write(struct.pack('!ff', float(distance), float(angle)))

        if frame.audio_data:
            buf.write(struct.pack('!I', len(frame.audio_data)))
            buf.write(frame.audio_data)
            buf.write(struct.pack('!I', frame.audio_sample_rate or 16000))
        else:
            buf.write(struct.pack('!I', 0))

        # Sound events (structured Minecraft sounds from mod)
        sound_events = frame.sound_events or []
        buf.write(struct.pack('!H', len(sound_events)))
        for ev in sound_events:
            ev_bytes = json.dumps(ev).encode('utf-8')
            buf.write(struct.pack('!I', len(ev_bytes)))
            buf.write(ev_bytes)

        return buf.getvalue()

    @staticmethod
    def unpack_perception(data: bytes) -> PerceptionFrame:
        buf = BytesIO(data)

        magic, ftype = struct.unpack('!II', buf.read(8))
        if magic != BinaryProtocol.MAGIC:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        if ftype != BinaryProtocol.FRAME_PERCEPTION:
            raise ValueError(f"Expected perception frame, got type {ftype}")

        aid_len = struct.unpack('!I', buf.read(4))[0]
        agent_id = buf.read(aid_len).decode('utf-8')

        timestamp = struct.unpack('!d', buf.read(8))[0]

        img_len = struct.unpack('!I', buf.read(4))[0]
        image_data = buf.read(img_len)
        img_w, img_h = struct.unpack('!HH', buf.read(4))

        health, hunger = struct.unpack('!ff', buf.read(8))
        position = struct.unpack('!fff', buf.read(12))
        rotation = struct.unpack('!ff', buf.read(8))

        entity_count = struct.unpack('!H', buf.read(2))[0]
        entities = []
        for _ in range(entity_count):
            type_id = struct.unpack('!B', buf.read(1))[0]
            name_len = struct.unpack('!I', buf.read(4))[0]
            name = buf.read(name_len).decode('utf-8')
            distance, angle = struct.unpack('!ff', buf.read(8))
            entities.append((type_id, name, distance, angle))

        audio_len = struct.unpack('!I', buf.read(4))[0]
        audio_data = None
        audio_sample_rate = None
        if audio_len > 0:
            audio_data = buf.read(audio_len)
            audio_sample_rate = struct.unpack('!I', buf.read(4))[0]
            # channels (1 byte) and bits_per_sample (1 byte) — sent by Java mod
            buf.read(2)  # consume without exposing (always mono/16-bit from mod)

        # Sound events (may not be present in older mod versions — safe to skip)
        sound_events = []
        try:
            sound_count = struct.unpack('!H', buf.read(2))[0]
            for _ in range(sound_count):
                ev_len = struct.unpack('!I', buf.read(4))[0]
                ev_bytes = buf.read(ev_len)
                sound_events.append(json.loads(ev_bytes.decode('utf-8')))
        except Exception:
            pass   # older mod versions without sound event support

        return PerceptionFrame(
            agent_id=agent_id,
            timestamp=timestamp,
            image_data=image_data,
            image_width=img_w,
            image_height=img_h,
            health=health,
            hunger=hunger,
            position=position,
            rotation=rotation,
            entities=entities,
            audio_data=audio_data,
            audio_sample_rate=audio_sample_rate,
            sound_events=sound_events or None,
        )

    # ── Action ─────────────────────────────────────────────────────────────

    @staticmethod
    def pack_action(frame: ActionFrame) -> bytes:
        buf = BytesIO()

        buf.write(struct.pack('!II', BinaryProtocol.MAGIC,
                              BinaryProtocol.FRAME_ACTION))

        aid = frame.agent_id.encode('utf-8')
        buf.write(struct.pack('!I', len(aid)))
        buf.write(aid)

        buf.write(struct.pack('!d', frame.timestamp))

        buf.write(struct.pack('!ffff',
                              frame.move_forward,
                              frame.move_strafe,
                              frame.yaw_delta,
                              frame.pitch_delta))

        buf.write(struct.pack('!B', frame.action_flags))

        hotbar = frame.hotbar_slot if frame.hotbar_slot is not None else 0xFF
        buf.write(struct.pack('!B', hotbar))

        if frame.god_ability:
            ab = frame.god_ability.encode('utf-8')
            buf.write(struct.pack('!H', len(ab)))
            buf.write(ab)
            params = frame.god_params or {}
            buf.write(struct.pack('!fff',
                                  params.get('param1', 0.0),
                                  params.get('param2', 0.0),
                                  params.get('param3', 0.0)))
        else:
            buf.write(struct.pack('!H', 0))

        return buf.getvalue()

    @staticmethod
    def unpack_action(data: bytes) -> ActionFrame:
        buf = BytesIO(data)

        magic, ftype = struct.unpack('!II', buf.read(8))
        if magic != BinaryProtocol.MAGIC:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        if ftype != BinaryProtocol.FRAME_ACTION:
            raise ValueError(f"Expected action frame, got type {ftype}")

        aid_len = struct.unpack('!I', buf.read(4))[0]
        agent_id = buf.read(aid_len).decode('utf-8')

        timestamp = struct.unpack('!d', buf.read(8))[0]

        move_forward, move_strafe, yaw_delta, pitch_delta = \
            struct.unpack('!ffff', buf.read(16))

        action_flags = struct.unpack('!B', buf.read(1))[0]

        hotbar_raw = struct.unpack('!B', buf.read(1))[0]
        hotbar_slot = None if hotbar_raw == 0xFF else hotbar_raw

        # God ability (present when ability-length > 0)
        god_ability = None
        god_params = None
        remaining = buf.read(2)
        if len(remaining) == 2:
            ab_len = struct.unpack('!H', remaining)[0]
            if ab_len > 0:
                god_ability = buf.read(ab_len).decode('utf-8')
                p1, p2, p3 = struct.unpack('!fff', buf.read(12))
                god_params = {'param1': p1, 'param2': p2, 'param3': p3}

        return ActionFrame(
            agent_id=agent_id,
            timestamp=timestamp,
            move_forward=move_forward,
            move_strafe=move_strafe,
            yaw_delta=yaw_delta,
            pitch_delta=pitch_delta,
            action_flags=action_flags,
            hotbar_slot=hotbar_slot,
            god_ability=god_ability,
            god_params=god_params,
        )

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def action_flags_to_dict(flags: int) -> Dict[str, bool]:
        return {
            'jump':      bool(flags & 0b10000000),
            'sneak':     bool(flags & 0b01000000),
            'attack':    bool(flags & 0b00100000),
            'use':       bool(flags & 0b00010000),
            'drop':      bool(flags & 0b00001000),
            'open_inv':  bool(flags & 0b00000100),
            'swap_hand': bool(flags & 0b00000010),
            'sprint':    bool(flags & 0b00000001),
        }

    @staticmethod
    def dict_to_action_flags(actions: Dict[str, bool]) -> int:
        flags = 0
        if actions.get('jump'):      flags |= 0b10000000
        if actions.get('sneak'):     flags |= 0b01000000
        if actions.get('attack'):    flags |= 0b00100000
        if actions.get('use'):       flags |= 0b00010000
        if actions.get('drop'):      flags |= 0b00001000
        if actions.get('open_inv'):  flags |= 0b00000100
        if actions.get('swap_hand'): flags |= 0b00000010
        if actions.get('sprint'):    flags |= 0b00000001
        return flags

    # ── Chat ───────────────────────────────────────────────────────────────

    @staticmethod
    def pack_chat(frame: 'ChatFrame') -> bytes:
        """
        CHAT FRAME (Backend → Client)
        ─────────────────────────────
        [4]  Magic 0x44574149
        [4]  Frame type 0x03
        [4]  Agent-ID length
        [N]  Agent-ID (UTF-8)
        [8]  Timestamp (double)
        [4]  Message length
        [N]  Message (UTF-8)
        """
        buf = BytesIO()
        buf.write(struct.pack('!II', BinaryProtocol.MAGIC,
                              BinaryProtocol.FRAME_CHAT))
        aid = frame.agent_id.encode('utf-8')
        buf.write(struct.pack('!I', len(aid)))
        buf.write(aid)
        buf.write(struct.pack('!d', frame.timestamp))
        msg = frame.message.encode('utf-8')
        buf.write(struct.pack('!I', len(msg)))
        buf.write(msg)
        return buf.getvalue()

    @staticmethod
    def unpack_chat(data: bytes) -> 'ChatFrame':
        buf = BytesIO(data)
        magic, ftype = struct.unpack('!II', buf.read(8))
        if magic != BinaryProtocol.MAGIC:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        if ftype != BinaryProtocol.FRAME_CHAT:
            raise ValueError(f"Expected chat frame, got type {ftype}")
        aid_len = struct.unpack('!I', buf.read(4))[0]
        agent_id = buf.read(aid_len).decode('utf-8')
        timestamp = struct.unpack('!d', buf.read(8))[0]
        msg_len = struct.unpack('!I', buf.read(4))[0]
        message = buf.read(msg_len).decode('utf-8')
        return ChatFrame(agent_id=agent_id, timestamp=timestamp, message=message)


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket handler
# ─────────────────────────────────────────────────────────────────────────────

class HighPerformanceWebSocketHandler:
    """
    WebSocket handler for one connected agent.

    Responsibilities
    ----------------
    - Receive binary PerceptionFrames from the Minecraft mod
    - Decode JPEG → numpy BGR frame and push to agent.vision
    - Build the info dict (health, hunger, position, entities) for the agent
    - Call agent.step() which internally runs observe → decide → act
    - Send the resulting ActionFrame back to the mod
    - Track latency and bandwidth statistics
    """

    def __init__(self, websocket, agent_id: str):
        self.websocket  = websocket
        self.agent_id   = agent_id
        self._agent_ref = None   # set by handle_agent_websocket after construction

        self.latencies: list = []
        self.frame_count     = 0
        self.bytes_received  = 0
        self.bytes_sent      = 0
        self.start_time      = time.time()

    async def send_action(self, action: ActionFrame):
        try:
            data = BinaryProtocol.pack_action(action)
            await self.websocket.send_bytes(data)
            self.bytes_sent += len(data)
        except Exception as e:
            log.error(f"[{self.agent_id}] Failed to send action: {e}")

    async def send_chat(self, message: str):
        """Send a chat message to the Minecraft client (agent speaks in-world)."""
        try:
            frame = ChatFrame(
                agent_id=self.agent_id,
                timestamp=time.time(),
                message=message,
            )
            data = BinaryProtocol.pack_chat(frame)
            await self.websocket.send_bytes(data)
            self.bytes_sent += len(data)
            log.debug(f"[{self.agent_id}] Chat sent: {message[:60]}")
        except Exception as e:
            log.error(f"[{self.agent_id}] Failed to send chat: {e}")

    async def receive_perception(self) -> Optional[PerceptionFrame]:
        """
        Receive the next frame from the Minecraft mod WebSocket.

        The mod sends two frame types on the same connection:
          • Binary frames  — PerceptionFrame (JPEG + game state)
          • Text frames    — JSON chat_heard observations
                            {"type":"chat_heard","agent_id":...,"speaker":...,"message":...}

        Text frames are processed in-place (memory + brain event) and then
        the loop continues waiting for the next binary perception frame.
        Returning None only on genuine errors / disconnects.
        """
        while True:
            try:
                msg = await self.websocket.receive()
                msg_type = msg.get("type")

                # ── Text frame: chat_heard observation ────────────────────
                if msg_type == "websocket.receive" and "text" in msg:
                    try:
                        payload = json.loads(msg["text"])
                        if payload.get("type") == "chat_heard":
                            self._handle_chat_heard(payload)
                        # Any other text frame: log and continue waiting
                        else:
                            log.debug(
                                f"[{self.agent_id}] Unhandled text frame: "
                                f"{payload.get('type', '?')}"
                            )
                    except Exception as e:
                        log.debug(f"[{self.agent_id}] Text frame parse error: {e}")
                    continue   # wait for next frame (binary perception)

                # ── Binary frame: PerceptionFrame ─────────────────────────
                if msg_type == "websocket.receive" and "bytes" in msg:
                    data = msg["bytes"]
                    if not data:
                        return None
                    self.bytes_received += len(data)
                    frame = BinaryProtocol.unpack_perception(data)

                    latency = time.time() - frame.timestamp
                    self.latencies.append(latency)
                    if len(self.latencies) > 100:
                        self.latencies.pop(0)

                    self.frame_count += 1
                    return frame

                # ── Disconnect ────────────────────────────────────────────
                if msg_type in ("websocket.disconnect", None):
                    return None

            except Exception as e:
                log.error(f"[{self.agent_id}] Failed to receive perception: {e}")
                return None

    def _handle_chat_heard(self, payload: dict):
        """
        Process a chat_heard JSON text frame from the Minecraft mod.

        Stores the overheard message in the agent's memory and routes it
        through brain.evaluate_event() so emotion, reward, and language
        systems react to what the NPC heard nearby.

        This is the PRIMARY path for NPC agents — ProximityChatHandler on
        the server mod triggers WebSocketManager.sendChatObservation() which
        sends this frame directly over the already-open /ws/agent connection.
        The HTTP /api/agents/chat_heard endpoint is the fallback for god agents.
        """
        # Java WebSocketManager.sendChatObservation sends: speaker, message
        # (already using the right field name in the text frame path)
        speaker = payload.get("speaker") or payload.get("speaker_name", "unknown")
        message = payload.get("message", "")
        if not message:
            return

        agent = self._agent_ref
        if agent is None:
            return

        agent.memory.remember({
            "type":      "chat_heard",
            "speaker":   speaker,
            "message":   message,
            "timestamp": time.time(),
            "text":      message,
        }, tags=["chat", "proximity", "heard", "social"])

        event = {
            "type":    "chat_heard",
            "tags":    ["social", "speech", "proximity"],
            "payload": {"speaker": speaker, "message": message},
        }
        agent.brain.evaluate_event(event)

        agent.emotion.add("anticipation", 0.1)
        agent.emotion.add("trust",        0.05)

        log.debug(f"[{self.agent_id}] Heard {speaker}: {message[:60]}")

    def get_stats(self) -> Dict[str, Any]:
        uptime = time.time() - self.start_time
        return {
            'agent_id':          self.agent_id,
            'uptime':            uptime,
            'frame_count':       self.frame_count,
            'fps':               self.frame_count / uptime if uptime > 0 else 0,
            'avg_latency_ms':    np.mean(self.latencies) * 1000 if self.latencies else 0,
            'max_latency_ms':    max(self.latencies) * 1000 if self.latencies else 0,
            'bytes_received':    self.bytes_received,
            'bytes_sent':        self.bytes_sent,
            'bandwidth_in_mbps': (self.bytes_received * 8 / uptime / 1_000_000)
                                  if uptime > 0 else 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Image helpers
# ─────────────────────────────────────────────────────────────────────────────

def compress_frame_to_jpeg(frame: np.ndarray, quality: int = 75) -> bytes:
    """Compress HxWx3 uint8 BGR numpy array to JPEG bytes."""
    try:
        import cv2
        ok, buf = cv2.imencode('.jpg', frame,
                               [cv2.IMWRITE_JPEG_QUALITY, quality])
        if ok:
            return buf.tobytes()
        raise RuntimeError("JPEG encoding failed")
    except ImportError:
        from PIL import Image
        from io import BytesIO as _BIO
        img = Image.fromarray(frame[..., ::-1])   # BGR → RGB
        b = _BIO()
        img.save(b, format='JPEG', quality=quality)
        return b.getvalue()


def decompress_jpeg_to_frame(jpeg_data: bytes) -> np.ndarray:
    """Decompress JPEG bytes to HxWx3 uint8 BGR numpy array."""
    try:
        import cv2
        arr = np.frombuffer(jpeg_data, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except ImportError:
        from PIL import Image
        from io import BytesIO as _BIO
        img = Image.open(_BIO(jpeg_data)).convert('RGB')
        arr = np.array(img)
        return arr[..., ::-1]   # RGB → BGR


# ─────────────────────────────────────────────────────────────────────────────
# Main WebSocket loop
# ─────────────────────────────────────────────────────────────────────────────

async def run_tcp_action_loop(agent, agent_id: str, loop_hz: float = 20.0):
    """
    Standalone action loop driven purely by the agent's policy over TCP.

    This runs when the agent is in minecraft mode and the WebSocket to the
    mod is not yet connected (or as a supplement to the WS loop).
    It does NOT receive perception frames — it uses the agent's last known
    observation and sends actions at loop_hz via minecraft_client.send().

    Usage in agent.py run_standalone_agent() (minecraft mode):
        asyncio.ensure_future(run_tcp_action_loop(agent, agent_id))
    """
    import asyncio as _asyncio
    interval = 1.0 / max(1.0, loop_hz)
    log.info(f"[TCPActionLoop] Starting for {agent_id} at {loop_hz:.0f} Hz")

    is_god = bool(getattr(agent, 'god_type', None) and
                  hasattr(agent, 'god_controls'))

    while True:
        try:
            mc = getattr(agent, 'minecraft_client', None)
            if mc is None:
                await _asyncio.sleep(interval)
                continue

            # FIX: _ws_client was removed from MinecraftClient (B-05 — it was a
            # self-loop to Python's own port). TCP is the sole outbound channel.
            tcp_pool  = getattr(mc, '_tcp_pool', None)
            tcp_ready = tcp_pool is not None and tcp_pool.is_connected()
            if not tcp_ready:
                await _asyncio.sleep(interval)
                continue

            # Use last known obs or a zero vector
            obs = agent.last_obs
            if obs is None:
                import numpy as np
                obs = np.zeros(50, dtype=np.float32)

            action_array = agent.decide(obs, deterministic=False)
            if is_god and len(action_array) >= 18:  # FIX B-15: GodTransformerPolicy.TOTAL_DIM = 18
                action_dict = agent.act_god(action_array)
            else:
                action_dict = agent.act(action_array)

            # apply_action() routes TCP-first (prefer_tcp=True), WS as fallback
            mc.apply_action(action_dict)

        except Exception as e:
            log.debug(f"[TCPActionLoop] {e}")

        await _asyncio.sleep(interval)



# =============================================================================
# GRPO-style policy update helper
# =============================================================================
# Called after deliberate() has already ranked imagined trajectories.
# The world model generated a group of trajectories; we use their relative
# reward scores as advantages (GRPO formulation) to push a gradient step
# =============================================================================

def _grpo_policy_update(agent, deliberation_result, obs: "np.ndarray") -> None:
    """
    Group Relative Policy Optimisation update using imagination rankings.

    Scores from brain.deliberate() are normalised into advantages:
        advantage_i = (score_i - mean) / (std + ε)
    One gradient step per call — no separate critic needed.
    """
    try:
        import torch, numpy as _np
        if agent.policy is None or deliberation_result is None:
            return
        if len(deliberation_result.ranked_actions) < 2:
            return

        scores     = _np.array([s for s, _ in deliberation_result.ranked_actions], dtype=_np.float32)
        advantages = (scores - scores.mean()) / (scores.std() + 1e-8)
        obs_t      = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)

        optimizer = getattr(agent.policy, 'optimizer', None)
        if optimizer is None:
            optimizer = torch.optim.Adam(agent.policy.parameters(), lr=3e-5)
            agent.policy.optimizer = optimizer

        optimizer.zero_grad()

        # FIX RL-04: old code mapped planning action names ('collect', 'flee')
        # to movement dim indices via ACTION_TYPE_INDEX, which is semantically
        # wrong — 'collect' maps to dim 0 (move_forward), meaning GRPO was
        # reinforcing "move forward" for any high-scoring plan regardless of
        # what the plan required.
        #
        # Correct approach: sample the current policy action for this observation,
        # then reinforce that sample proportionally to its advantage.
        # This is the standard REINFORCE / GRPO update: maximise E[adv * log π(a|s)].
        try:
            action_mean, _ = agent.policy.forward(obs_t)
            log_std = getattr(agent.policy, 'log_std', None)
            if log_std is None:
                log_std = getattr(agent.policy, 'log_std_base', torch.zeros_like(action_mean))
            std  = torch.exp(log_std)
            dist = torch.distributions.Normal(action_mean, std)
            # Sample one action from current policy for this observation
            sampled_action = dist.sample()
            log_prob       = dist.log_prob(sampled_action).sum(dim=-1)  # (1,)

            # Weight log_prob by mean advantage across the group.
            # Using mean advantage (not per-action) because we have one
            # sampled action per observation, not per trajectory.
            mean_adv = float(advantages.mean())
            loss     = -(mean_adv * log_prob).mean()
            loss.backward()
        except Exception:
            pass

        torch.nn.utils.clip_grad_norm_(agent.policy.parameters(), 1.0)
        optimizer.step()
    except Exception as e:
        log.debug(f"[GRPO] policy update skipped: {e}")


_wm_train_counters: dict = {}

def _feed_world_model(agent, agent_id: str, frame_bgr, obs: "np.ndarray",
                      action_array: "np.ndarray", reward: float,
                      done: bool, train_every: int = 20) -> None:
    """Feed one perception frame into the world model buffer and train periodically."""
    try:
        buf = getattr(agent, 'world_model_buffer', None)
        if buf is None:
            return
        import cv2 as _cv2, numpy as _np
        wm_cfg   = getattr(getattr(agent, 'world_model', None), 'config', None)
        vis_size = wm_cfg.vision_size if wm_cfg else 84
        frame_sm = _cv2.resize(frame_bgr, (vis_size, vis_size)).astype(_np.float32) / 255.0
        buf.add_step(
            vision=frame_sm, proprio=obs.astype(_np.float32),
            action=action_array.astype(_np.float32),
            reward=float(reward), termination=bool(done),
        )
        if done:
            buf.end_trajectory()
        cnt = _wm_train_counters.get(agent_id, 0) + 1
        _wm_train_counters[agent_id] = cnt
        if cnt % train_every == 0:
            trainer = getattr(agent, 'world_model_trainer', None)
            if trainer is not None and len(buf.trajectories) > 0:
                # FIX: train_online_step no longer accepts a trajectory arg —
                # it trains on whatever complete episodes are in the shared buffer.
                # Passing trajectory= was corrupting the live episode buffer.
                trainer.train_online_step()
    except Exception as e:
        log.debug(f"[{agent_id}] _feed_world_model failed: {e}")

async def handle_agent_websocket(websocket, agent_id: str, agent):
    """
    Main per-agent WebSocket loop.

    Wires into vision.py cleanly:
      1. Decode JPEG → BGR frame
      2. Push frame into agent.vision via _dispatch_visual_frame()
         (vision.py registered _on_visual_frame during add_vision_to_agent())
      3. Build info dict with game-state for agent.observe()
      4. Call agent.observe(frame, info) — this triggers the full
         VisionAdapter pipeline (feature extraction, vocab update, memory)
      5. Route any audio bytes from the frame into the AudioProcessor so
         the agent hears Minecraft sounds / speech with the same pipeline
         as microphone audio — RewardSystem, memory, language learning all apply
      6. Agent decides: act() for NPCs, act_god() for gods (18-dim policy, GodTransformerPolicy.TOTAL_DIM=18)
      7. Send ActionFrame back to mod (god_ability/params included when fired)
      8. Feed reward signal to agent.learn()

    Usage in main.py
    ─────────────────
    ::
        @app.websocket("/ws/agent")
        async def agent_ws(websocket: WebSocket):
            await websocket.accept()
            data   = await websocket.receive_json()
            aid    = data["agent_id"]
            agent  = agent_manager.get_agent(aid)
            await handle_agent_websocket(websocket, aid, agent)
    """
    handler = HighPerformanceWebSocketHandler(websocket, agent_id)
    handler._agent_ref = agent   # needed by _handle_chat_heard
    log.info(f"🔌 WebSocket connected: {agent_id}")

    # Resolve whether this is a god agent once, not every frame
    is_god = bool(getattr(agent, 'god_type', None) and
                  hasattr(agent, 'god_controls'))

    last_obs    = None
    last_action = None

    # Register an async chat sender so the cognitive loop can push chat
    # messages directly into Minecraft.  The queue is drained every frame
    # so the agent speaks in real time.
    import asyncio as _asyncio
    _chat_queue: _asyncio.Queue = _asyncio.Queue(maxsize=32)

    async def _agent_send_chat(message: str):
        """Called by cognitive_loop / process_chat to speak in Minecraft."""
        try:
            _chat_queue.put_nowait(message)
        except _asyncio.QueueFull:
            log.debug(f"[{agent_id}] Chat queue full, dropping: {message[:40]}")

    # Attach the sender to the agent so cognitive_loop can call it
    agent._minecraft_send_chat = _agent_send_chat

    try:
        while True:
            # ── 1. Receive raw perception ─────────────────────────────────
            perception = await handler.receive_perception()
            if perception is None:
                break

            # ── 2. Decode image ───────────────────────────────────────────
            frame_bgr = decompress_jpeg_to_frame(perception.image_data)
            if frame_bgr is None:
                log.warning(f"[{agent_id}] JPEG decode returned None — skipping frame.")
                continue

            # ── 3. Push frame into vision system ──────────────────────────
            # vision.py registered _on_visual_frame during add_vision_to_agent().
            _dispatch_visual_frame(agent_id, frame_bgr)

            # ── 3b. Dispatch structured Minecraft sound events ────────────
            # The mod sends per-frame sound events (entity sounds, ambient,
            # explosions) as structured dicts in perception.sound_events.
            # Each one goes to MinecraftSoundAdapter.receive_sound_event()
            # which routes it through brain.evaluate_event() — same pipeline
            # as all other sensory inputs.
            if perception.sound_events:
                recv_fn = getattr(agent, 'receive_minecraft_sound', None)
                if recv_fn is not None:
                    for sound_ev in perception.sound_events:
                        try:
                            recv_fn(sound_ev)
                        except Exception as e:
                            log.debug(
                                f"[{agent_id}] Sound event dispatch error: {e}"
                            )

            # ── 4. Build info dict for agent.observe() ────────────────────
            info = {
                'health':    perception.health,
                'hunger':    perception.hunger,
                'position':  perception.position,
                'rotation':  perception.rotation,
                'entities':  perception.entities,
                'timestamp': perception.timestamp,
            }

            # ── 5. Agent observation ──────────────────────────────────────
            # observe() stores the visual frame in memory/vision pipeline
            # but returns shape (3,84,84) which the policy cannot use.
            # Policy expects 50-dim obs (Box(50,) per env.py).
            # perceive() builds the correct 50-dim vector and updates agent.last_obs.
            agent.observe(frame_bgr, info)
            agent.health = perception.health
            agent.hunger = perception.hunger
            obs = agent.perceive({
                'health':   perception.health,
                'hunger':   perception.hunger,
                'position': {
                    'x': perception.position[0],
                    'y': perception.position[1],
                    'z': perception.position[2],
                },
                'yaw':      perception.rotation[0],
                'pitch':    perception.rotation[1],
                'entities': perception.entities,
            })   # returns 50-dim ndarray, updates agent.last_obs

            # ── 6. Route Minecraft audio through AudioProcessor ───────────
            # The Minecraft mod captures in-world audio (mob sounds, ambient,
            # player speech) and packs it into the perception frame.
            # We inject it directly into the agent's audio pipeline so
            # everything — transcription, feature extraction, evaluate_event,
            # memory storage — works identically to microphone audio.
            if perception.audio_data and len(perception.audio_data) > 0:
                audio_proc = getattr(agent, 'audio_processor', None)
                if audio_proc is not None:
                    try:
                        sample_rate = perception.audio_sample_rate or 16000
                        # Decode raw PCM int16 bytes → numpy float array
                        audio_np = np.frombuffer(
                            perception.audio_data, dtype=np.int16
                        ).astype(np.float32) / 32767.0

                        # Inject into AudioCapture's ring buffer so
                        # process_audio_chunk() picks it up on the next call.
                        # We bypass start_recording() — data comes from
                        # Minecraft, not the local mic.
                        if audio_proc.capture is not None:
                            audio_proc.capture.audio_buffer.append(
                                np.frombuffer(perception.audio_data,
                                              dtype=np.int16)
                            )
                            audio_proc.capture.sample_rate = sample_rate
                            # Mark as listening so process_audio_chunk() runs
                            if not audio_proc.is_listening:
                                audio_proc.is_listening = True

                        else:
                            # No AudioCapture (pyaudio absent) — process directly
                            features = audio_proc.feature_extractor.extract_features(
                                np.frombuffer(perception.audio_data, dtype=np.int16),
                                sample_rate,
                            )
                            emotion_label = audio_proc.feature_extractor.detect_emotion(
                                features
                            )
                            transcription = None
                            if (features.get('volume', 0.0) > 0.05 and
                                    audio_proc.recognizer is not None):
                                transcription = audio_proc.recognizer.transcribe(
                                    np.frombuffer(perception.audio_data,
                                                  dtype=np.int16),
                                    sample_rate,
                                )

                            # Route through brain — full RewardSystem path
                            event = {
                                'type': 'audio_input',
                                'tags': ['audio', 'perception', 'minecraft',
                                         'speech' if transcription else 'ambient'],
                                'payload': {
                                    'volume':        features.get('volume', 0.0),
                                    'pitch':         features.get('pitch_mean', 0.0),
                                    'emotion_label': emotion_label,
                                    'has_speech':    transcription is not None,
                                    'word_count':    len(transcription.split())
                                                     if transcription else 0,
                                    'source':        'minecraft',
                                },
                            }
                            agent.brain.evaluate_event(event)

                            if transcription or emotion_label not in ('neutral', None):
                                agent.memory.remember({
                                    'type':          'audio_input',
                                    'transcription': transcription,
                                    'emotion_label': emotion_label,
                                    'features':      features,
                                    'source':        'minecraft',
                                    'timestamp':     time.time(),
                                    'text':          transcription or '',
                                }, tags=['audio', 'perception', 'minecraft'])

                    except Exception as e:
                        log.debug(f"[{agent_id}] Minecraft audio routing failed: {e}")

            # ── 7. Agent decision & action ────────────────────────────────
            action_array = agent.decide(obs, deterministic=False)

            # Gods use act_god() which handles the full 18-dim vector (GodTransformerPolicy.TOTAL_DIM=18):
            # dims 0-10 → movement, dims 11-15 → ability trigger + params.
            # NPCs use act() which only looks at dims 0-10.
            if is_god and len(action_array) >= 18:  # FIX B-15: GodTransformerPolicy.TOTAL_DIM = 18
                action_dict = agent.act_god(action_array)
            else:
                action_dict = agent.act(action_array)

            # ── 8. Send action ────────────────────────────────────────────
            action_frame = ActionFrame(
                agent_id     = agent_id,
                timestamp    = time.time(),
                move_forward = float(action_dict.get('move_forward', 0.0)),
                move_strafe  = float(action_dict.get('move_strafe',  0.0)),
                yaw_delta    = float(action_dict.get('yaw_delta',    0.0)),
                pitch_delta  = float(action_dict.get('pitch_delta',  0.0)),
                action_flags = BinaryProtocol.dict_to_action_flags(action_dict),
                hotbar_slot  = action_dict.get('hotbar_slot'),
                god_ability  = action_dict.get('god_ability'),
                god_params   = action_dict.get('god_params'),
            )
            await handler.send_action(action_frame)

            # ── 8b. Drain pending chat messages ───────────────────────────
            # The cognitive loop enqueues in-world chat via agent._minecraft_send_chat().
            # We drain here (after every action frame) so speech is timely.
            while not _chat_queue.empty():
                try:
                    chat_msg = _chat_queue.get_nowait()
                    await handler.send_chat(chat_msg)
                except Exception:
                    break

            # ── 9. Learning ───────────────────────────────────────────────
            if last_obs is not None and last_action is not None:
                outcome = {
                    'health':      perception.health,
                    'hunger':      perception.hunger,
                    'is_dead':     perception.health <= 0,
                    'task_reward': 0.0,
                }
                agent.learn(last_obs, last_action, obs, outcome)

                # ── 9a. World model buffer + periodic training ─────────────
                _feed_world_model(
                    agent, agent_id, frame_bgr, obs, last_action,
                    float(outcome.get('task_reward', 0.0)),
                    bool(outcome.get('is_dead', False)),
                    train_every=20,
                )

                # ── 9b. GRPO policy update ────────────────────────────────
                _delib = getattr(agent.brain, '_last_deliberation_result', None)
                if _delib is not None:
                    _grpo_policy_update(agent, _delib, obs)
                    agent.brain._last_deliberation_result = None

                # ── 9a. World model buffer + periodic WM training ─────────
                # Feeds every perception frame into WorldModelReplayBuffer.
                # Calls train_online_step() every 20 frames so the world model
                # continuously learns from real Minecraft experience.
                _reward_for_wm = float(outcome.get('task_reward', 0.0))
                _done_for_wm   = bool(outcome.get('is_dead', False))
                _feed_world_model(
                    agent, agent_id, frame_bgr, obs,
                    last_action, _reward_for_wm, _done_for_wm,
                    train_every=20,
                )

                # ── 9b. GRPO policy update ────────────────────────────────
                # If the brain just ran a deliberation this cycle, use the
                # ranked trajectories as the advantage group and push one
                # gradient step through TransformerPolicy — no critic needed.
                _delib = getattr(agent.brain, '_last_deliberation_result', None)
                if _delib is not None:
                    _grpo_policy_update(agent, _delib, obs)
                    agent.brain._last_deliberation_result = None

            last_obs    = obs
            last_action = action_array

            # ── 10. Periodic stats ────────────────────────────────────────
            if handler.frame_count % 100 == 0:
                stats = handler.get_stats()
                log.info(
                    f"📊 [{agent_id}] {stats['fps']:.1f} FPS  "
                    f"{stats['avg_latency_ms']:.1f} ms avg latency  "
                    f"{stats['bandwidth_in_mbps']:.2f} Mbps in"
                )

    except Exception as e:
        log.error(f"WebSocket error for {agent_id}: {e}", exc_info=True)

    finally:
        log.info(f"🔌 WebSocket disconnected: {agent_id}")
        log.info(f"Final stats: {handler.get_stats()}")

        # FIX #23: save agent state on disconnect so progress since the last
        # periodic save (up to 5 min) is not lost on network failures.
        if agent is not None:
            try:
                sp = agent.metadata.get(
                    'brain_save_path',
                    f"data/brains/{agent_id}/brain.pcap"
                )
                import pathlib as _pl
                _pl.Path(sp).parent.mkdir(parents=True, exist_ok=True)
                agent.save(sp)
                log.info(f"[{agent_id}] 💾 Disconnect save: {sp}")
            except Exception as _se:
                log.warning(f"[{agent_id}] Disconnect save failed: {_se}")


async def handle_sound_event_websocket(websocket, agent_id: str, agent):
    """
    Dedicated WebSocket endpoint for structured Minecraft sound events.

    The Minecraft mod connects to /ws/sound and pushes JSON sound events
    as they fire in-game. This is the preferred audio path because it:
      - Requires no audio capture hardware on the server
      - Works in headless / cloud deployments
      - Carries semantic metadata (sound_id, category, distance) that
        raw PCM audio cannot provide
      - Has near-zero bandwidth cost

    The raw PCM path in handle_agent_websocket handles voice/speech that
    the mod records from the in-game voice chat. These two paths coexist.

    Expected JSON message format from mod:
        {
          "type":     "sound_event",
          "sound_id": "entity.creeper.primed",
          "volume":   0.8,
          "distance": 12.3,
          "category": "hostile",
          "position": {"x": -42, "y": 64, "z": 18}
        }

    Usage in main.py:
        @app.websocket("/ws/sound")
        async def sound_ws(websocket: WebSocket):
            await websocket.accept()
            data = await websocket.receive_json()
            aid  = data["agent_id"]
            agent = agent_manager.get_agent(aid)
            await handle_sound_event_websocket(websocket, aid, agent)
    """
    log.info(f"🔊 Sound WebSocket connected: {agent_id}")

    if not hasattr(agent, 'receive_minecraft_sound'):
        log.warning(
            f"[{agent_id}] No MinecraftSoundAdapter — "
            "call add_audio_processing_to_agent() during init"
        )
        return

    try:
        while True:
            try:
                msg = await websocket.receive_json()
            except Exception:
                break

            if not isinstance(msg, dict):
                continue

            msg_type = msg.get('type', '')

            if msg_type == 'sound_event':
                try:
                    agent.receive_minecraft_sound(msg)
                except Exception as e:
                    log.debug(f"[{agent_id}] Sound event error: {e}")

            elif msg_type == 'ability_outcome':
                # Mod responds with ability outcome after processing a god action.
                # Route back through use_god_ability() with the real outcome data
                # so the RewardSystem can score how the ability performed.
                if hasattr(agent, 'use_god_ability'):
                    try:
                        agent.use_god_ability(
                            msg.get('ability_name', ''),
                            outcome={
                                'ability_success':  msg.get('success',        False),
                                'ability_damage':   msg.get('damage',         0.0),
                                'ability_healing':  msg.get('healing',        0.0),
                                'surprise_attack':  msg.get('surprise_attack', False),
                            },
                        )
                    except Exception as e:
                        log.debug(f"[{agent_id}] Ability outcome error: {e}")

    except Exception as e:
        log.error(f"Sound WebSocket error for {agent_id}: {e}")

    finally:
        log.info(f"🔊 Sound WebSocket disconnected: {agent_id}")
        # Save on sound WS disconnect too — keeps state consistent
        if agent is not None:
            try:
                sp = agent.metadata.get(
                    'brain_save_path',
                    f"data/brains/{agent_id}/brain.pcap"
                )
                import pathlib as _pl
                _pl.Path(sp).parent.mkdir(parents=True, exist_ok=True)
                agent.save(sp)
            except Exception:
                pass  # best-effort — main WS save is authoritative