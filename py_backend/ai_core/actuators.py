# ------------------------------------------------------------------------------
# ai_core/actuators.py - Action execution 
# ------------------------------------------------------------------------------
import socket
import threading
import time
import json
import struct
import logging
from typing import Any, Dict, Optional, List, Callable
import numpy as np

log = logging.getLogger("ai_core.actuators")
log.setLevel(logging.INFO)

class ForgeIPCClient:
    """
    Binary-first Forge IPC client for Minecraft mod communication.
    """
    def __init__(self, host='127.0.0.1', port=8765, reconnect=True, timeout=3.0):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()
        self.reconnect = reconnect
        self.timeout = timeout
        self._stop = False
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
                    log.info("ForgeIPC: connected (binary)")
                except Exception:
                    time.sleep(1.0)
            else:
                time.sleep(1.0)
    
    def send_action(self, action: Dict[str, Any], agent_id: str = "agent") -> bool:
        """Send action to Minecraft client"""
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
        except Exception:
            payload = None
        
        with self.lock:
            if self.sock and payload:
                try:
                    self.sock.sendall(payload)
                    return True
                except Exception:
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock = None
        
        return False
    
    def apply_action(self, action: Dict[str, Any]) -> bool:
        """Alias for send_action"""
        return self.send_action(action)
    
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
