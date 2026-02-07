# py_backend/unified_chat_system.py
"""
Enhanced Unified Chat System - Minimal Coordination Layer
----------------------------------------------------------
This file ONLY handles:
- Message routing (GUI ↔ Game ↔ Agent)
- WebSocket management
- File I/O coordination

All intelligence delegated to:
- agent.brain (language processing, symbol creation)
- agent.planner (decision making)
- agent.memory (experience storage)
- agent.emotion (affective responses)
"""

import asyncio
import json
import time
import logging
import numpy as np
from typing import Dict, Any, Optional, Set, List
from collections import deque
from dataclasses import dataclass
from websockets.exceptions import ConnectionClosed
from pathlib import Path

log = logging.getLogger("chat")


@dataclass
class ChatMessage:
    text: str
    timestamp: float
    expires: float
    sender: str
    is_emote: bool = False
    bubble_height: float = 2.0


class UnifiedChatSystem:
    """
    Minimal coordination layer - routes messages, manages connections.
    Intelligence lives in agent.brain.
    """

    def __init__(self):
        self.message_queues: Dict[str, deque] = {}
        self.gui_connections: Dict[str, any] = {}
        self.game_connections: Dict[str, any] = {}
        self.gui_active: Set[str] = set()
        self.entity_types: Dict[str, str] = {}
        self.registered_agents: Dict[str, any] = {}
        self.autonomous_tasks: Dict[str, asyncio.Task] = {}

    def register_agent(self, agent_id: str, agent):
        """Register agent - brain will handle all intelligence"""
        self.registered_agents[agent_id] = agent
        log.info(f"Agent registered: {agent_id}")

    def register_gui(self, agent_id: str, websocket):
        self.gui_connections[agent_id] = websocket
        self.gui_active.add(agent_id)
        log.info(f"GUI opened for {agent_id}")

    def unregister_gui(self, agent_id: str):
        if agent_id in self.gui_connections:
            del self.gui_connections[agent_id]
        self.gui_active.discard(agent_id)
        if agent_id in self.autonomous_tasks:
            self.autonomous_tasks[agent_id].cancel()
            del self.autonomous_tasks[agent_id]
        log.info(f"GUI closed for {agent_id}")

    def register_game(self, agent_id: str, websocket):
        self.game_connections[agent_id] = websocket
        log.info(f"Game client registered for {agent_id}")

    def unregister_game(self, agent_id: str):
        if agent_id in self.game_connections:
            del self.game_connections[agent_id]

    async def send_message(self, agent_id: str, message: str, target: str = "both",
                          sender: str = "agent", is_emote: bool = False,
                          bubble_height: Optional[float] = None, expire_after: float = 5.0):
        """Route message to GUI/game - no processing"""
        message = message.strip()
        if not message:
            return

        if bubble_height is None:
            entity_type = self.entity_types.get(agent_id, "npc")
            bubble_height = 3.0 if entity_type == "god" else 2.0

        msg_obj = ChatMessage(
            text=message, timestamp=time.time(), expires=time.time() + expire_after,
            sender=sender, is_emote=is_emote or (message.startswith("*") and message.endswith("*")),
            bubble_height=bubble_height
        )

        if agent_id not in self.message_queues:
            self.message_queues[agent_id] = deque(maxlen=100)
        self.message_queues[agent_id].append(msg_obj)

        if target in ["game", "both"] and agent_id in self.game_connections:
            await self._send_to_game(agent_id, msg_obj)
        if target in ["gui", "both"] and agent_id in self.gui_connections:
            await self._send_to_gui(agent_id, msg_obj)

    async def _send_to_game(self, agent_id: str, msg: ChatMessage):
        ws = self.game_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type": "say", "agent": agent_id, "message": msg.text,
                "timestamp": msg.timestamp, "is_emote": msg.is_emote,
                "bubble_height": msg.bubble_height, "expires": msg.expires
            }))
        except (ConnectionClosed, Exception) as e:
            log.warning(f"Game send failed for {agent_id}: {e}")

    async def _send_to_gui(self, agent_id: str, msg: ChatMessage):
        ws = self.gui_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type": "chat_message", "agent_id": agent_id, "message": msg.text,
                "sender": msg.sender, "timestamp": msg.timestamp, "is_emote": msg.is_emote
            }))
        except (ConnectionClosed, Exception) as e:
            log.warning(f"GUI send failed for {agent_id}: {e}")

    async def handle_user_message(self, agent_id: str, message: str):
        """Route user message to agent.brain for processing"""
        if agent_id not in self.message_queues:
            self.message_queues[agent_id] = deque(maxlen=100)

        self.message_queues[agent_id].append(ChatMessage(
            text=message, timestamp=time.time(), expires=time.time() + 5.0, sender="user"
        ))

        agent = self.registered_agents.get(agent_id)
        if not agent:
            return
        
        # Build context for brain
        context = self._build_context(agent)
        
        # BRAIN processes language
        if hasattr(agent.brain, 'process_language_input'):
            response = agent.brain.process_language_input(message, context)
        else:
            # Fallback if brain doesn't have language module yet
            response = self._fallback_response(agent, message, context)
        
        if response:
            await self.send_message(agent_id, response, target="gui", sender="agent")

    async def handle_file_upload(self, agent_id: str, file_data: bytes, 
                                  filename: str, filetype: str):
        """Route file to agent.brain for multimodal learning"""
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return
        
        upload_dir = Path("data/uploads") / agent_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / filename
        
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        # BRAIN handles file learning
        if hasattr(agent.brain, 'learn_from_file'):
            summary = agent.brain.learn_from_file(str(file_path), filetype)
        else:
            summary = self._fallback_file_learning(agent, file_path, filetype)
        
        if summary:
            await self.send_message(agent_id, summary, target="gui", sender="agent")

    async def handle_minecraft_perception(self, agent_id: str, 
                                          frame: Optional[np.ndarray] = None,
                                          audio: Optional[np.ndarray] = None,
                                          action: Optional[Dict] = None,
                                          game_state: Optional[Dict] = None):
        """Route perception to agent.brain for processing"""
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return
        
        # Store raw perception
        if not hasattr(agent, 'perception_buffer'):
            agent.perception_buffer = {}
        
        if frame is not None:
            agent.perception_buffer['visual'] = frame
            agent.perception_buffer['visual_timestamp'] = time.time()
        
        if audio is not None:
            agent.perception_buffer['audio'] = audio
            agent.perception_buffer['audio_timestamp'] = time.time()
        
        # BRAIN processes multimodal perception
        if hasattr(agent.brain, 'process_perception'):
            agent.brain.process_perception(frame, audio, action, game_state)
        else:
            self._fallback_perception(agent, frame, audio, action, game_state)
        
        # Check if brain wants to speak
        if hasattr(agent.brain, 'should_speak') and agent.brain.should_speak():
            if hasattr(agent.brain, 'generate_speech'):
                message = agent.brain.generate_speech(self._build_context(agent))
                if message:
                    target = "game" if agent_id in self.game_connections else "gui"
                    await self.send_message(agent_id, message, target=target, sender="agent")

    def _build_context(self, agent) -> Dict[str, Any]:
        """Build context dict for brain"""
        context = {
            'health': agent.health,
            'hunger': agent.hunger,
            'emotions': agent.emotion.snapshot(),
            'dominant_emotion': agent.emotion.dominant_emotion(),
            'memory_size': len(agent.memory.events)
        }
        
        if hasattr(agent, 'perception_buffer'):
            context.update(agent.perception_buffer)
        
        if hasattr(agent, 'last_action'):
            context['last_action'] = agent.last_action
        
        return context

    def _fallback_response(self, agent, message: str, context: Dict) -> Optional[str]:
        """Fallback if brain doesn't have language processing yet"""
        # Store in memory
        agent.memory.remember({
            'type': 'user_message',
            'text': message,
            'tags': ['chat', 'user']
        })
        
        # Brain evaluates as event
        if hasattr(agent, 'brain'):
            event = {'type': 'chat_input', 'payload': {'text': message}, 'tags': ['chat']}
            reward, emotion_delta = agent.brain.evaluate_event(event, context)
            for emotion, value in emotion_delta.items():
                agent.emotion.add(emotion, value)
        
        # Simple echo response
        return f"Heard: {message[:50]}"

    def _fallback_file_learning(self, agent, file_path: Path, filetype: str) -> str:
        """Fallback file learning if brain doesn't handle it"""
        if filetype.startswith('text/'):
            text = file_path.read_text(encoding='utf-8', errors='ignore')
            agent.memory.remember({
                'type': 'file_input',
                'tags': ['text', 'file'],
                'payload': {'filename': file_path.name, 'length': len(text)}
            })
            return f"Text file stored: {len(text)} chars"
        
        elif filetype.startswith('image/'):
            import cv2
            img = cv2.imread(str(file_path))
            if img is not None:
                h, w = img.shape[:2]
                agent.memory.remember({
                    'type': 'image_input',
                    'tags': ['vision', 'file'],
                    'payload': {'filename': file_path.name, 'size': (w, h)}
                })
                return f"Image stored: {w}x{h}"
        
        return f"File received: {file_path.name}"

    def _fallback_perception(self, agent, frame, audio, action, game_state):
        """Fallback perception processing"""
        if frame is not None:
            agent.memory.remember({
                'type': 'minecraft_vision',
                'tags': ['minecraft', 'vision'],
                'payload': {'timestamp': time.time()}
            })
        
        if action is not None and game_state is not None:
            obs_dict = {
                'health': game_state.get('health', 20.0),
                'hunger': game_state.get('hunger', 20.0),
                'position': game_state.get('position', {'x': 0, 'y': 64, 'z': 0})
            }
            
            obs = agent.perceive(obs_dict)
            
            if isinstance(action, dict):
                action_array = np.array([
                    action.get('move_forward', 0.0), action.get('move_strafe', 0.0),
                    1.0 if action.get('jump', False) else 0.0,
                    1.0 if action.get('sneak', False) else 0.0,
                    1.0 if action.get('attack', False) else 0.0,
                    1.0 if action.get('use', False) else 0.0,
                    1.0 if action.get('drop', False) else 0.0,
                    1.0 if action.get('open_inv', False) else 0.0,
                    1.0 if action.get('swap_hand', False) else 0.0,
                    action.get('yaw_delta', 0.0) / 2.0,
                    action.get('pitch_delta', 0.0) / 1.2
                ], dtype=np.float32)
            else:
                action_array = action
            
            outcome = {
                'health': obs_dict['health'],
                'hunger': obs_dict['hunger'],
                'is_dead': obs_dict['health'] <= 0,
                'task_reward': 0.0
            }
            
            if game_state.get('killed_entity'):
                outcome['task_reward'] += 1.0
            if game_state.get('took_damage'):
                outcome['task_reward'] -= 0.5
            
            if agent.last_obs is not None:
                agent.learn(agent.last_obs, action_array, obs, outcome)
            
            agent.last_obs = obs

    async def start_autonomous_speech(self, agent_id: str):
        """Start autonomous speech loop - brain decides when to speak"""
        if agent_id in self.autonomous_tasks:
            return
        
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return
        
        async def autonomous_loop():
            while agent_id in self.gui_active or agent_id in self.game_connections:
                try:
                    # BRAIN decides if it should speak
                    if hasattr(agent.brain, 'should_speak') and agent.brain.should_speak():
                        context = self._build_context(agent)
                        
                        # BRAIN generates message
                        if hasattr(agent.brain, 'generate_speech'):
                            message = agent.brain.generate_speech(context)
                            
                            if message:
                                target = "both"
                                if agent_id in self.gui_active and agent_id not in self.game_connections:
                                    target = "gui"
                                elif agent_id not in self.gui_active and agent_id in self.game_connections:
                                    target = "game"
                                
                                await self.send_message(agent_id, message, target=target, sender="agent")
                    
                    await asyncio.sleep(5.0)
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Autonomous speech error for {agent_id}: {e}")
                    await asyncio.sleep(10.0)
        
        task = asyncio.create_task(autonomous_loop())
        self.autonomous_tasks[agent_id] = task
        log.info(f"Autonomous speech started for {agent_id}")

    async def stop_autonomous_speech(self, agent_id: str):
        """Stop autonomous speech"""
        if agent_id in self.autonomous_tasks:
            self.autonomous_tasks[agent_id].cancel()
            del self.autonomous_tasks[agent_id]

    def get_chat_history(self, agent_id: str, limit: int = 50) -> list:
        """Get recent chat history"""
        if agent_id not in self.message_queues:
            return []
        return list(self.message_queues[agent_id])[-limit:]

    def is_gui_active(self, agent_id: str) -> bool:
        """Check if GUI is active"""
        return agent_id in self.gui_active


chat_system = UnifiedChatSystem()


# Integration helpers for main.py
async def handle_frontend_chat(agent_id: str, message: str):
    """Handle chat from frontend - routes to agent.brain"""
    await chat_system.handle_user_message(agent_id, message)


async def handle_frontend_file_upload(agent_id: str, file_data: bytes, 
                                       filename: str, filetype: str):
    """Handle file upload - routes to agent.brain"""
    await chat_system.handle_file_upload(agent_id, file_data, filename, filetype)


async def handle_minecraft_frame(agent_id: str, frame_data: np.ndarray, 
                                 game_state: Optional[Dict] = None):
    """Handle Minecraft perception - routes to agent.brain"""
    await chat_system.handle_minecraft_perception(
        agent_id=agent_id,
        frame=frame_data,
        audio=None,
        action=None,
        game_state=game_state
    )


async def start_agent_autonomous_speech(agent_id: str):
    """Start autonomous speech - brain controls timing and content"""
    await chat_system.start_autonomous_speech(agent_id)

async def send_thought(self, agent_id: str, thought: str, is_internal: bool = True):
    '''Send thought to frontend (appears in thoughts panel)'''
    # This will be handled by the bridge
    if agent_id in self.gui_connections:
        try:
            await self.gui_connections[agent_id].send(json.dumps({
                "type": "agent_thought" if is_internal else "internal_thought",
                "agent_id": agent_id,
                "internal_thought": thought,
                "timestamp": time.time()
        }))
        except Exception as e:
            log.debug(f"Failed to send thought: {e}")
    
async def send_visualization(self, agent_id: str, visualization_data: Dict[str, Any]):
    '''Send visualization to frontend (3D mental workspace)'''
    if agent_id in self.gui_connections:
        try:
            await self.gui_connections[agent_id].send(json.dumps({
                "type": "visualization_update",
                "agent_id": agent_id,
                "data": visualization_data,
                "timestamp": time.time()
            }))
        except Exception as e:
            log.debug(f"Failed to send visualization: {e}")