# ------------------------------------------------------------------------------
# ai_core/actuators.py - Action execution with TCP + WebSocket fallback
# ------------------------------------------------------------------------------
import socket
import threading
import time
import json
import struct
import logging
from typing import Any, Dict, Optional, List, Callable
import numpy as np
import asyncio
import websockets

log = logging.getLogger("ai_core.actuators")
log.setLevel(logging.INFO)

# Protocol constants for WebSocket mode
MAGIC = 0x44574149  # 'DWAI'
FRAME_ACTION = 0x02

class MinecraftClient:
    """
    Dual-mode Minecraft client with TCP primary and WebSocket fallback.
    
    Automatically uses:
    1. TCP (port 8765) for low-latency action sending (preferred)
    2. WebSocket (port 11400) as fallback with full perception/action loop
    """
    
    def __init__(self, 
                 agent_id: str = "agent",
                 tcp_host: str = '127.0.0.1',
                 tcp_port: int = 8765,
                 ws_host: str = '127.0.0.1', 
                 ws_port: int = 11400,
                 prefer_tcp: bool = True):
        
        self.agent_id = agent_id
        self.prefer_tcp = prefer_tcp
        
        # TCP client
        self.tcp_client = ForgeIPCClient(tcp_host, tcp_port) if prefer_tcp else None
        
        # WebSocket client
        self.ws_client = MinecraftWebSocketClient(agent_id, ws_host, ws_port)
        
        # Track which mode is active
        self.active_mode = None
        self._check_lock = threading.Lock()
        
        # Start connection check thread
        threading.Thread(target=self._monitor_connections, daemon=True).start()
    
    def _monitor_connections(self):
        """Monitor and switch between TCP/WebSocket"""
        while True:
            with self._check_lock:
                if self.prefer_tcp and self.tcp_client and self.tcp_client.is_connected():
                    if self.active_mode != 'tcp':
                        log.info("🔵 Switched to TCP mode (primary)")
                        self.active_mode = 'tcp'
                
                elif self.ws_client.is_connected():
                    if self.active_mode != 'websocket':
                        log.info("🟢 Switched to WebSocket mode (fallback)")
                        self.active_mode = 'websocket'
                
                else:
                    if self.active_mode is not None:
                        log.warning("🔴 No connection available")
                        self.active_mode = None
            
            time.sleep(2.0)
    
    def send_action(self, action: Dict[str, Any]) -> bool:
        """Send action using best available protocol"""
        with self._check_lock:
            # Try TCP first if preferred
            if self.active_mode == 'tcp' and self.tcp_client:
                success = self.tcp_client.send_action(action, self.agent_id)
                if success:
                    return True
                else:
                    log.debug("TCP send failed, will try WebSocket")
            
            # Fallback to WebSocket
            if self.active_mode == 'websocket':
                try:
                    # Run async send in event loop
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.ws_client.send_action(action))
                        return True
                    else:
                        asyncio.run(self.ws_client.send_action(action))
                        return True
                except Exception as e:
                    log.error(f"WebSocket send failed: {e}")
            
            return False
    
    def apply_action(self, action: Dict[str, Any]) -> bool:
        """Alias for send_action"""
        return self.send_action(action)
    
    async def start_websocket(self):
        """Start WebSocket client (call from async context)"""
        await self.ws_client.connect()
    
    def get_active_mode(self) -> Optional[str]:
        """Get currently active protocol"""
        return self.active_mode
    
    def close(self):
        """Close all connections"""
        if self.tcp_client:
            self.tcp_client.close()
        if self.ws_client:
            asyncio.run(self.ws_client.close())


class ForgeIPCClient:
    """
    TCP client for low-latency action sending.
    """
    def __init__(self, host='127.0.0.1', port=8765, reconnect=True, timeout=3.0):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()
        self.reconnect = reconnect
        self.timeout = timeout
        self._stop = False
        self._connected = False
        threading.Thread(target=self._maintain, daemon=True).start()
    
    def _maintain(self):
        """Maintain connection in background"""
        while not self._stop:
            if self.sock is None:
                try:
                    s = socket.create_connection((self.host, self.port), timeout=self.timeout)
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    with self.lock:
                        self.sock = s
                        self._connected = True
                    log.info(f"TCP connected to {self.host}:{self.port}")
                except Exception:
                    self._connected = False
                    time.sleep(1.0)
            else:
                time.sleep(1.0)
    
    def is_connected(self) -> bool:
        """Check if TCP socket is connected"""
        return self._connected and self.sock is not None
    
    def send_action(self, action: Dict[str, Any], agent_id: str = "agent") -> bool:
        """Send action via TCP"""
        tick = int(time.time() * 1000)
        move_forward = float(action.get('move_forward', 0.0))
        move_strafe = float(action.get('move_strafe', 0.0))
        yaw = float(action.get('yaw_delta', 0.0))
        pitch = float(action.get('pitch_delta', 0.0))
        
        # Boolean actions
        jump = 1 if action.get('jump', False) else 0
        sneak = 1 if action.get('sneak', False) else 0
        attack = 1 if action.get('attack', False) else 0
        use = 1 if action.get('use', False) else 0
        drop = 1 if action.get('drop', False) else 0
        open_inv = 1 if action.get('open_inv', False) else 0
        swap_hand = 1 if action.get('swap_hand', False) else 0
        
        agent_bytes = agent_id.encode('utf-8')
        
        try:
            payload = struct.pack(
                f"!I{len(agent_bytes)}sQffffBBBBBBB",
                len(agent_bytes), agent_bytes, tick,
                move_forward, move_strafe, yaw, pitch,
                jump, sneak, attack, use, drop, open_inv, swap_hand
            )
        except Exception as e:
            log.error(f"Failed to pack TCP payload: {e}")
            return False
        
        with self.lock:
            if self.sock and payload:
                try:
                    self.sock.sendall(payload)
                    return True
                except Exception as e:
                    log.debug(f"TCP send error: {e}")
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
                    self._connected = False
        
        return False
    
    def close(self):
        """Close connection"""
        self._stop = True
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock = None
                self._connected = False


class MinecraftWebSocketClient:
    """
    WebSocket client for robust bidirectional communication.
    Implements the binary protocol from WebSocketManager.java
    """
    
    def __init__(self, agent_id: str, host: str = '127.0.0.1', port: int = 11400):
        self.agent_id = agent_id
        self.uri = f"ws://{host}:{port}"
        self.ws = None
        self._connected = False
        self._reconnecting = False
        
    async def connect(self):
        """Connect to Minecraft mod WebSocket server"""
        if self._reconnecting:
            return
        
        self._reconnecting = True
        
        try:
            log.info(f"Connecting to WebSocket at {self.uri}...")
            self.ws = await websockets.connect(self.uri)
            
            # Send handshake
            handshake = {
                "agent_id": self.agent_id,
                "protocol": "binary",
                "version": "2.1.0"
            }
            await self.ws.send(json.dumps(handshake))
            
            self._connected = True
            log.info("✅ WebSocket connected and authenticated")
            
        except Exception as e:
            log.error(f"WebSocket connection failed: {e}")
            self._connected = False
        finally:
            self._reconnecting = False
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._connected and self.ws is not None and self.ws.open
    
    async def send_action(self, action: Dict[str, Any]):
        """Send action frame via WebSocket using binary protocol"""
        if not self.is_connected():
            if not self._reconnecting:
                asyncio.create_task(self.connect())
            return
        
        try:
            frame = self._build_action_frame(action)
            await self.ws.send(frame)
        except Exception as e:
            log.error(f"WebSocket send error: {e}")
            self._connected = False
    
    def _build_action_frame(self, action: Dict[str, Any]) -> bytes:
        """
        Build binary action frame matching WebSocketManager.handleActionFrame
        
        Format:
        - magic (4 bytes)
        - frame_type (4 bytes)
        - agent_id_len (4 bytes)
        - agent_id (variable)
        - timestamp (8 bytes)
        - move_forward (4 bytes)
        - move_strafe (4 bytes)
        - yaw_delta (4 bytes)
        - pitch_delta (4 bytes)
        - action_flags (1 byte)
        - hotbar_slot (1 byte)
        """
        buffer = bytearray()
        
        # Header
        buffer.extend(struct.pack('!I', MAGIC))
        buffer.extend(struct.pack('!I', FRAME_ACTION))
        
        # Agent ID
        agent_bytes = self.agent_id.encode('utf-8')
        buffer.extend(struct.pack('!I', len(agent_bytes)))
        buffer.extend(agent_bytes)
        
        # Timestamp
        buffer.extend(struct.pack('!d', time.time()))
        
        # Movement
        move_forward = float(np.clip(action.get('move_forward', 0.0), -1.0, 1.0))
        move_strafe = float(np.clip(action.get('move_strafe', 0.0), -1.0, 1.0))
        yaw_delta = float(np.clip(action.get('yaw_delta', 0.0) * 2.0, -180.0, 180.0))
        pitch_delta = float(np.clip(action.get('pitch_delta', 0.0) * 1.2, -90.0, 90.0))
        
        buffer.extend(struct.pack('!f', move_forward))
        buffer.extend(struct.pack('!f', move_strafe))
        buffer.extend(struct.pack('!f', yaw_delta))
        buffer.extend(struct.pack('!f', pitch_delta))
        
        # Action flags
        flags = 0
        if action.get('jump', False):
            flags |= 0b10000000
        if action.get('sneak', False):
            flags |= 0b01000000
        if action.get('attack', False):
            flags |= 0b00100000
        if action.get('use', False):
            flags |= 0b00010000
        if action.get('drop', False):
            flags |= 0b00001000
        if action.get('open_inv', False):
            flags |= 0b00000100
        if action.get('swap_hand', False):
            flags |= 0b00000010
        
        buffer.extend(struct.pack('!B', flags))
        
        # Hotbar slot
        buffer.extend(struct.pack('!B', 0xFF))  # No change
        
        return bytes(buffer)
    
    async def close(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self._connected = False


# Legacy compatibility
class ActuatorAdapterIsaacSim:
    """
    Adapter for Isaac Sim robot control.
    """
    def __init__(self, 
                 send_joint_positions: Optional[Callable[[List[float]], None]] = None,
                 set_camera_ori: Optional[Callable[[float, float], None]] = None):
        self.send_joint_positions = send_joint_positions
        self.set_camera_ori = set_camera_ori
    
    def apply_action(self, action: Dict[str, Any]):
        """Convert action dict to robot commands"""
        move_forward = float(np.clip(action.get("move_forward", 0.0), -1.0, 1.0))
        move_strafe = float(np.clip(action.get("move_strafe", 0.0), -1.0, 1.0))
        yaw = float(action.get("yaw_delta", 0.0))
        pitch = float(action.get("pitch_delta", 0.0))
        
        cmd = [move_forward, move_strafe, yaw, pitch]
        
        if self.send_joint_positions:
            self.send_joint_positions(cmd)
        
        if self.set_camera_ori:
            self.set_camera_ori(yaw, pitch)