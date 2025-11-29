# py_backend/utils/action_format_sync.py
"""
Action format synchronization between Python backend and Java client.
Ensures NPCAgent actions are properly formatted for DWClientBot.
"""
import numpy as np
from typing import Dict, Any

class ActionFormatter:
    """
    Converts NPCAgent action arrays to DWClientBot-compatible JSON.
    """
    
    @staticmethod
    def npc_to_forge(action_array: np.ndarray) -> Dict[str, Any]:
        """
        Convert NPCAgent 11-element action array to Forge IPC format.
        
        Action array format:
        [0] move_forward: -1.0 to 1.0
        [1] move_strafe: -1.0 to 1.0
        [2] jump: >0.5 = true
        [3] sneak: >0.5 = true
        [4] attack: >0.5 = true
        [5] use: >0.5 = true
        [6] drop: >0.5 = true
        [7] open_inv: >0.5 = true
        [8] swap_hand: >0.5 = true
        [9] yaw_delta: -2.0 to 2.0 (scaled)
        [10] pitch_delta: -1.2 to 1.2 (scaled)
        """
        action = np.clip(action_array, -1.0, 1.0)
        
        return {
            # Movement (continuous)
            'move_forward': float(action[0]),
            'move_strafe': float(action[1]),
            
            # Actions (boolean)
            'jump': bool(action[2] > 0.5),
            'sneak': bool(action[3] > 0.5),
            'attack': bool(action[4] > 0.5),
            'use': bool(action[5] > 0.5),
            'drop': bool(action[6] > 0.5),
            'open_inv': bool(action[7] > 0.5),
            'swap_hand': bool(action[8] > 0.5),
            
            # Camera (scaled)
            'yaw_delta': float(action[9] * 2.0),  # Scale to ±2 degrees
            'pitch_delta': float(action[10] * 1.2),  # Scale to ±1.2 degrees
            
            # Duration hints (for Java client)
            'forward_ticks': 1 if abs(action[0]) > 0.1 else 0,
            'strafe_ticks': 1 if abs(action[1]) > 0.1 else 0,
            'jump_ticks': 1 if action[2] > 0.5 else 0,
        }
    
    @staticmethod
    def forge_to_npc(forge_action: Dict[str, Any]) -> np.ndarray:
        """
        Convert Forge IPC format back to NPCAgent array (for testing/replay).
        """
        return np.array([
            forge_action.get('move_forward', 0.0),
            forge_action.get('move_strafe', 0.0),
            1.0 if forge_action.get('jump', False) else 0.0,
            1.0 if forge_action.get('sneak', False) else 0.0,
            1.0 if forge_action.get('attack', False) else 0.0,
            1.0 if forge_action.get('use', False) else 0.0,
            1.0 if forge_action.get('drop', False) else 0.0,
            1.0 if forge_action.get('open_inv', False) else 0.0,
            1.0 if forge_action.get('swap_hand', False) else 0.0,
            forge_action.get('yaw_delta', 0.0) / 2.0,
            forge_action.get('pitch_delta', 0.0) / 1.2,
        ], dtype=np.float32)


# Integration with main.py WebSocket handler
async def send_action_to_client(agent_id: str, action_array: np.ndarray):
    """
    Send properly formatted action to DWClientBot WebSocket.
    """
    formatter = ActionFormatter()
    forge_action = formatter.npc_to_forge(action_array)
    
    # Add to WebSocket message
    ws_message = {
        "type": "action",
        "agent": agent_id,
        "action": forge_action
    }
    
    # Send via WebSocket (assuming ws connection exists)
    if agent_id in agent_manager.websockets:
        ws = agent_manager.websockets[agent_id]
        await ws.send_json(ws_message)