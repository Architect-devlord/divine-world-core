# py_backend/communication_protocol.py - OPTIMIZED FOR VIDEO/IMAGES
"""
High-performance communication protocol for AI-Minecraft integration.
Uses WebSocket with binary frames for minimal latency.

Protocol Design:
- WebSocket for bidirectional, low-latency communication
- Binary frames for images (JPEG compressed)
- MessagePack for efficient action serialization
- Frame buffering for smooth 20+ FPS video

Latency Target: <50ms round-trip (perception → action)
"""

import asyncio
import struct
import time
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass
import numpy as np
from io import BytesIO

try:
    import msgpack
except ImportError:
    msgpack = None
    print("⚠️  msgpack not installed. Install with: pip install msgpack")

log = logging.getLogger("comm_protocol")


@dataclass
class PerceptionFrame:
    """Single perception frame from Minecraft client"""
    agent_id: str
    timestamp: float
    
    # Visual data (JPEG compressed)
    image_data: bytes
    image_width: int
    image_height: int
    
    # Game state (compact)
    health: float
    hunger: float
    position: tuple  # (x, y, z)
    rotation: tuple  # (yaw, pitch)
    
    # Entities nearby (compact)
    entities: list  # [(type, distance, angle), ...]
    
    # Optional audio
    audio_data: Optional[bytes] = None
    audio_sample_rate: Optional[int] = None


@dataclass
class ActionFrame:
    """Action command to Minecraft client"""
    agent_id: str
    timestamp: float
    
    # Movement (floats -1.0 to 1.0)
    move_forward: float
    move_strafe: float
    
    # Camera (floats in degrees)
    yaw_delta: float
    pitch_delta: float
    
    # Boolean actions (packed into single byte)
    action_flags: int  # bits: jump|sneak|attack|use|drop|inv|swap_hand
    
    # Optional: inventory slot selection
    hotbar_slot: Optional[int] = None


class BinaryProtocol:
    """
    Binary protocol for high-performance communication.
    
    Frame Format:
    ------------
    PERCEPTION FRAME (Client → Backend):
    [4 bytes] Magic: 0x44574149 ('DWAI')
    [4 bytes] Frame type: 0x01 (perception)
    [4 bytes] Agent ID length
    [N bytes] Agent ID (UTF-8)
    [8 bytes] Timestamp (double)
    [4 bytes] Image data length
    [N bytes] JPEG image data
    [2 bytes] Image width
    [2 bytes] Image height
    [4 bytes] Health (float)
    [4 bytes] Hunger (float)
    [12 bytes] Position (3x float)
    [8 bytes] Rotation (2x float)
    [2 bytes] Entity count
    [N bytes] Entity data (packed)
    [4 bytes] Audio data length (0 if no audio)
    [N bytes] Audio data (optional)
    
    ACTION FRAME (Backend → Client):
    [4 bytes] Magic: 0x44574149
    [4 bytes] Frame type: 0x02 (action)
    [4 bytes] Agent ID length
    [N bytes] Agent ID
    [8 bytes] Timestamp
    [4 bytes] Move forward (float)
    [4 bytes] Move strafe (float)
    [4 bytes] Yaw delta (float)
    [4 bytes] Pitch delta (float)
    [1 byte] Action flags
    [1 byte] Hotbar slot (0xFF if none)
    """
    
    MAGIC = 0x44574149  # 'DWAI'
    FRAME_PERCEPTION = 0x01
    FRAME_ACTION = 0x02
    FRAME_CHAT = 0x03
    
    @staticmethod
    def pack_perception(frame: PerceptionFrame) -> bytes:
        """Pack perception frame into binary"""
        buffer = BytesIO()
        
        # Header
        buffer.write(struct.pack('!I', BinaryProtocol.MAGIC))
        buffer.write(struct.pack('!I', BinaryProtocol.FRAME_PERCEPTION))
        
        # Agent ID
        agent_id_bytes = frame.agent_id.encode('utf-8')
        buffer.write(struct.pack('!I', len(agent_id_bytes)))
        buffer.write(agent_id_bytes)
        
        # Timestamp
        buffer.write(struct.pack('!d', frame.timestamp))
        
        # Image data
        buffer.write(struct.pack('!I', len(frame.image_data)))
        buffer.write(frame.image_data)
        buffer.write(struct.pack('!HH', frame.image_width, frame.image_height))
        
        # Game state
        buffer.write(struct.pack('!ff', frame.health, frame.hunger))
        buffer.write(struct.pack('!fff', *frame.position))
        buffer.write(struct.pack('!ff', *frame.rotation))
        
        # Entities
        buffer.write(struct.pack('!H', len(frame.entities)))
        for entity in frame.entities:
            # Each entity: type_id (1 byte), distance (float), angle (float)
            entity_type, distance, angle = entity
            buffer.write(struct.pack('!Bff', entity_type, distance, angle))
        
        # Audio (optional)
        if frame.audio_data:
            buffer.write(struct.pack('!I', len(frame.audio_data)))
            buffer.write(frame.audio_data)
            buffer.write(struct.pack('!I', frame.audio_sample_rate))
        else:
            buffer.write(struct.pack('!I', 0))
        
        return buffer.getvalue()
    
    @staticmethod
    def unpack_perception(data: bytes) -> PerceptionFrame:
        """Unpack binary perception frame"""
        buffer = BytesIO(data)
        
        # Verify magic
        magic = struct.unpack('!I', buffer.read(4))[0]
        if magic != BinaryProtocol.MAGIC:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        
        # Verify frame type
        frame_type = struct.unpack('!I', buffer.read(4))[0]
        if frame_type != BinaryProtocol.FRAME_PERCEPTION:
            raise ValueError(f"Invalid frame type: {frame_type}")
        
        # Agent ID
        agent_id_len = struct.unpack('!I', buffer.read(4))[0]
        agent_id = buffer.read(agent_id_len).decode('utf-8')
        
        # Timestamp
        timestamp = struct.unpack('!d', buffer.read(8))[0]
        
        # Image
        image_len = struct.unpack('!I', buffer.read(4))[0]
        image_data = buffer.read(image_len)
        image_width, image_height = struct.unpack('!HH', buffer.read(4))
        
        # Game state
        health, hunger = struct.unpack('!ff', buffer.read(8))
        position = struct.unpack('!fff', buffer.read(12))
        rotation = struct.unpack('!ff', buffer.read(8))
        
        # Entities
        entity_count = struct.unpack('!H', buffer.read(2))[0]
        entities = []
        for _ in range(entity_count):
            entity_type, distance, angle = struct.unpack('!Bff', buffer.read(9))
            entities.append((entity_type, distance, angle))
        
        # Audio (optional)
        audio_len = struct.unpack('!I', buffer.read(4))[0]
        audio_data = None
        audio_sample_rate = None
        if audio_len > 0:
            audio_data = buffer.read(audio_len)
            audio_sample_rate = struct.unpack('!I', buffer.read(4))[0]
        
        return PerceptionFrame(
            agent_id=agent_id,
            timestamp=timestamp,
            image_data=image_data,
            image_width=image_width,
            image_height=image_height,
            health=health,
            hunger=hunger,
            position=position,
            rotation=rotation,
            entities=entities,
            audio_data=audio_data,
            audio_sample_rate=audio_sample_rate
        )
    
    @staticmethod
    def pack_action(frame: ActionFrame) -> bytes:
        """Pack action frame into binary"""
        buffer = BytesIO()
        
        # Header
        buffer.write(struct.pack('!I', BinaryProtocol.MAGIC))
        buffer.write(struct.pack('!I', BinaryProtocol.FRAME_ACTION))
        
        # Agent ID
        agent_id_bytes = frame.agent_id.encode('utf-8')
        buffer.write(struct.pack('!I', len(agent_id_bytes)))
        buffer.write(agent_id_bytes)
        
        # Timestamp
        buffer.write(struct.pack('!d', frame.timestamp))
        
        # Movement
        buffer.write(struct.pack('!ffff',
            frame.move_forward,
            frame.move_strafe,
            frame.yaw_delta,
            frame.pitch_delta
        ))
        
        # Action flags
        buffer.write(struct.pack('!B', frame.action_flags))
        
        # Hotbar slot
        hotbar = frame.hotbar_slot if frame.hotbar_slot is not None else 0xFF
        buffer.write(struct.pack('!B', hotbar))
        
        return buffer.getvalue()
    
    @staticmethod
    def unpack_action(data: bytes) -> ActionFrame:
        """Unpack binary action frame"""
        buffer = BytesIO(data)
        
        # Verify magic
        magic = struct.unpack('!I', buffer.read(4))[0]
        if magic != BinaryProtocol.MAGIC:
            raise ValueError(f"Invalid magic: {hex(magic)}")
        
        # Verify frame type
        frame_type = struct.unpack('!I', buffer.read(4))[0]
        if frame_type != BinaryProtocol.FRAME_ACTION:
            raise ValueError(f"Invalid frame type: {frame_type}")
        
        # Agent ID
        agent_id_len = struct.unpack('!I', buffer.read(4))[0]
        agent_id = buffer.read(agent_id_len).decode('utf-8')
        
        # Timestamp
        timestamp = struct.unpack('!d', buffer.read(8))[0]
        
        # Movement
        move_forward, move_strafe, yaw_delta, pitch_delta = struct.unpack('!ffff', buffer.read(16))
        
        # Action flags
        action_flags = struct.unpack('!B', buffer.read(1))[0]
        
        # Hotbar slot
        hotbar = struct.unpack('!B', buffer.read(1))[0]
        hotbar_slot = None if hotbar == 0xFF else hotbar
        
        return ActionFrame(
            agent_id=agent_id,
            timestamp=timestamp,
            move_forward=move_forward,
            move_strafe=move_strafe,
            yaw_delta=yaw_delta,
            pitch_delta=pitch_delta,
            action_flags=action_flags,
            hotbar_slot=hotbar_slot
        )
    
    @staticmethod
    def action_flags_to_dict(flags: int) -> Dict[str, bool]:
        """Convert action flags byte to dict"""
        return {
            'jump': bool(flags & 0b10000000),
            'sneak': bool(flags & 0b01000000),
            'attack': bool(flags & 0b00100000),
            'use': bool(flags & 0b00010000),
            'drop': bool(flags & 0b00001000),
            'open_inv': bool(flags & 0b00000100),
            'swap_hand': bool(flags & 0b00000010),
        }
    
    @staticmethod
    def dict_to_action_flags(actions: Dict[str, bool]) -> int:
        """Convert action dict to flags byte"""
        flags = 0
        if actions.get('jump', False): flags |= 0b10000000
        if actions.get('sneak', False): flags |= 0b01000000
        if actions.get('attack', False): flags |= 0b00100000
        if actions.get('use', False): flags |= 0b00010000
        if actions.get('drop', False): flags |= 0b00001000
        if actions.get('open_inv', False): flags |= 0b00000100
        if actions.get('swap_hand', False): flags |= 0b00000010
        return flags


class HighPerformanceWebSocketHandler:
    """
    WebSocket handler optimized for real-time video/action streaming.
    
    Features:
    - Binary frame support
    - Frame buffering for smooth playback
    - Automatic compression (JPEG for images)
    - Latency monitoring
    """
    
    def __init__(self, websocket, agent_id: str):
        self.websocket = websocket
        self.agent_id = agent_id
        
        # Frame buffers
        self.perception_buffer = asyncio.Queue(maxsize=5)
        self.action_buffer = asyncio.Queue(maxsize=10)
        
        # Latency tracking
        self.latencies = []
        self.frame_count = 0
        
        # Statistics
        self.bytes_received = 0
        self.bytes_sent = 0
        self.start_time = time.time()
    
    async def send_action(self, action: ActionFrame):
        """Send action to client"""
        try:
            data = BinaryProtocol.pack_action(action)
            await self.websocket.send_bytes(data)
            
            self.bytes_sent += len(data)
            
        except Exception as e:
            log.error(f"Failed to send action: {e}")
    
    async def receive_perception(self) -> Optional[PerceptionFrame]:
        """Receive perception from client"""
        try:
            data = await self.websocket.receive_bytes()
            
            self.bytes_received += len(data)
            
            frame = BinaryProtocol.unpack_perception(data)
            
            # Track latency
            latency = time.time() - frame.timestamp
            self.latencies.append(latency)
            if len(self.latencies) > 100:
                self.latencies.pop(0)
            
            self.frame_count += 1
            
            return frame
            
        except Exception as e:
            log.error(f"Failed to receive perception: {e}")
            return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get communication statistics"""
        uptime = time.time() - self.start_time
        
        return {
            'agent_id': self.agent_id,
            'uptime': uptime,
            'frame_count': self.frame_count,
            'fps': self.frame_count / uptime if uptime > 0 else 0,
            'avg_latency_ms': np.mean(self.latencies) * 1000 if self.latencies else 0,
            'max_latency_ms': max(self.latencies) * 1000 if self.latencies else 0,
            'bytes_received': self.bytes_received,
            'bytes_sent': self.bytes_sent,
            'bandwidth_in_mbps': (self.bytes_received * 8 / uptime / 1_000_000) if uptime > 0 else 0,
            'bandwidth_out_mbps': (self.bytes_sent * 8 / uptime / 1_000_000) if uptime > 0 else 0,
        }


# Helper functions for image compression/decompression

def compress_frame_to_jpeg(frame: np.ndarray, quality: int = 75) -> bytes:
    """Compress numpy frame to JPEG bytes"""
    try:
        import cv2
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if success:
            return buffer.tobytes()
        else:
            raise RuntimeError("JPEG encoding failed")
    except ImportError:
        # Fallback to PIL
        from PIL import Image
        img = Image.fromarray(frame)
        buffer = BytesIO()
        img.save(buffer, format='JPEG', quality=quality)
        return buffer.getvalue()


def decompress_jpeg_to_frame(jpeg_data: bytes) -> np.ndarray:
    """Decompress JPEG bytes to numpy frame"""
    try:
        import cv2
        nparr = np.frombuffer(jpeg_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        return frame
    except ImportError:
        # Fallback to PIL
        from PIL import Image
        img = Image.open(BytesIO(jpeg_data))
        return np.array(img)


# Usage example for main.py integration

async def handle_agent_websocket(websocket, agent_id: str, agent):
    """
    Enhanced WebSocket handler for main.py
    
    Usage in main.py:
    @app.websocket("/ws/agent")
    async def agent_ws(websocket: WebSocket):
        await websocket.accept()
        data = await websocket.receive_json()
        agent_id = data.get("agent_id")
        agent = agent_manager.get_agent(agent_id)
        await handle_agent_websocket(websocket, agent_id, agent)
    """
    handler = HighPerformanceWebSocketHandler(websocket, agent_id)
    
    log.info(f"🔌 WebSocket connected: {agent_id}")
    
    try:
        while True:
            # Receive perception from client
            perception = await handler.receive_perception()
            
            if perception is None:
                break
            
            # Decompress image
            frame = decompress_jpeg_to_frame(perception.image_data)
            
            # Agent processes perception
            obs_dict = {
                'frame': frame,
                'health': perception.health,
                'hunger': perception.hunger,
                'position': perception.position,
                'rotation': perception.rotation,
                'entities': perception.entities,
                'timestamp': perception.timestamp
            }
            
            # Agent decides action
            obs = agent.perceive(obs_dict)
            action_array = agent.decide(obs, deterministic=False)
            action_dict = agent.act(action_array)
            
            # Convert to binary action frame
            action_frame = ActionFrame(
                agent_id=agent_id,
                timestamp=time.time(),
                move_forward=action_dict['move_forward'],
                move_strafe=action_dict['move_strafe'],
                yaw_delta=action_dict['yaw_delta'],
                pitch_delta=action_dict['pitch_delta'],
                action_flags=BinaryProtocol.dict_to_action_flags(action_dict),
                hotbar_slot=action_dict.get('hotbar_slot')
            )
            
            # Send action to client
            await handler.send_action(action_frame)
            
            # Learn from experience
            if agent.last_obs is not None:
                outcome = {
                    'health': perception.health,
                    'hunger': perception.hunger,
                    'is_dead': perception.health <= 0,
                    'task_reward': 0.0
                }
                
                agent.learn(agent.last_obs, action_array, obs, outcome)
            
            agent.last_obs = obs
            
            # Log stats every 100 frames
            if handler.frame_count % 100 == 0:
                stats = handler.get_stats()
                log.info(f"📊 {agent_id} Stats: {stats['fps']:.1f} FPS, "
                        f"{stats['avg_latency_ms']:.1f}ms latency, "
                        f"{stats['bandwidth_in_mbps']:.2f} Mbps in")
    
    except Exception as e:
        log.error(f"WebSocket error for {agent_id}: {e}")
    
    finally:
        log.info(f"🔌 WebSocket disconnected: {agent_id}")
        stats = handler.get_stats()
        log.info(f"Final stats: {stats}")