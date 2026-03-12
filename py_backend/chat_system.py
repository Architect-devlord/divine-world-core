# py_backend/chat_system.py
"""
Chat System
===================
Minimal coordination layer — routes messages between the React GUI,
the Minecraft game client, and the NPCAgent.  All intelligence is
delegated to the agent's subsystems:

  agent.brain    — language processing, symbol creation
  agent.planner  — decision making
  agent.memory   — experience storage
  agent.emotion  — affective responses

This file does NOT process language or make decisions.  It only routes.

Public API (used by main.py / FastAPI endpoints)
------------------------------------------------
  chat_system                          — module-level singleton
  handle_frontend_chat(id, msg)        — route user chat to brain
  handle_frontend_file_upload(...)     — route file upload to brain
  handle_minecraft_frame(...)          — route Minecraft perception
  start_agent_autonomous_speech(id)    — kick off the brain-driven loop
"""

import asyncio
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import numpy as np
from websockets.exceptions import ConnectionClosed

log = logging.getLogger("chat")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    text:          str
    timestamp:     float
    expires:       float
    sender:        str
    is_emote:      bool  = False
    bubble_height: float = 2.0


# ---------------------------------------------------------------------------
# UnifiedChatSystem
# ---------------------------------------------------------------------------

class UnifiedChatSystem:
    """
    Routes messages between GUI WebSockets, game WebSockets, and agents.
    Instantiate once as a module-level singleton; register agents and
    connections as they come up.
    """

    def __init__(self):
        self.message_queues:    Dict[str, deque]          = {}
        self.gui_connections:   Dict[str, Any]            = {}
        self.game_connections:  Dict[str, Any]            = {}
        self.gui_active:        Set[str]                  = set()
        self.entity_types:      Dict[str, str]            = {}
        self.registered_agents: Dict[str, Any]            = {}
        self.autonomous_tasks:  Dict[str, asyncio.Task]   = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_agent(self, agent_id: str, agent):
        """Register an NPCAgent instance for routing."""
        self.registered_agents[agent_id] = agent
        # Store entity type for bubble-height selection
        agent_type = getattr(agent, "agent_type", "npc")
        self.entity_types[agent_id] = (
            "god" if str(agent_type).startswith("god") else "npc"
        )
        log.info(f"Agent registered: {agent_id} ({self.entity_types[agent_id]})")

    def register_gui(self, agent_id: str, websocket):
        self.gui_connections[agent_id] = websocket
        self.gui_active.add(agent_id)
        log.info(f"GUI opened for {agent_id}")

    def unregister_gui(self, agent_id: str):
        self.gui_connections.pop(agent_id, None)
        self.gui_active.discard(agent_id)
        task = self.autonomous_tasks.pop(agent_id, None)
        if task:
            task.cancel()
        log.info(f"GUI closed for {agent_id}")

    def register_game(self, agent_id: str, websocket):
        self.game_connections[agent_id] = websocket
        log.info(f"Game client registered for {agent_id}")

    def unregister_game(self, agent_id: str):
        self.game_connections.pop(agent_id, None)

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    async def send_message(self, agent_id: str, message: str,
                           target: str = "both", sender: str = "agent",
                           is_emote: bool = False,
                           bubble_height: Optional[float] = None,
                           expire_after: float = 5.0):
        """Route a message to GUI and/or game WebSocket."""
        message = message.strip()
        if not message:
            return

        if bubble_height is None:
            bubble_height = (
                3.0 if self.entity_types.get(agent_id) == "god" else 2.0
            )

        msg = ChatMessage(
            text          = message,
            timestamp     = time.time(),
            expires       = time.time() + expire_after,
            sender        = sender,
            is_emote      = is_emote or (message.startswith("*") and message.endswith("*")),
            bubble_height = bubble_height,
        )

        self.message_queues.setdefault(agent_id, deque(maxlen=100)).append(msg)

        if target in ("game", "both"):
            await self._send_to_game(agent_id, msg)
        if target in ("gui", "both"):
            await self._send_to_gui(agent_id, msg)

    async def _send_to_game(self, agent_id: str, msg: ChatMessage):
        ws = self.game_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type":          "say",
                "agent":         agent_id,
                "message":       msg.text,
                "timestamp":     msg.timestamp,
                "is_emote":      msg.is_emote,
                "bubble_height": msg.bubble_height,
                "expires":       msg.expires,
            }))
        except (ConnectionClosed, Exception) as e:
            log.warning(f"Game send failed for {agent_id}: {e}")

    async def _send_to_gui(self, agent_id: str, msg: ChatMessage):
        ws = self.gui_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type":      "chat_message",
                "agent_id":  agent_id,
                "message":   msg.text,
                "sender":    msg.sender,
                "timestamp": msg.timestamp,
                "is_emote":  msg.is_emote,
            }))
        except (ConnectionClosed, Exception) as e:
            log.warning(f"GUI send failed for {agent_id}: {e}")

    # ------------------------------------------------------------------
    # Inbound routing from GUI
    # ------------------------------------------------------------------

    async def handle_user_message(self, agent_id: str, message: str):
        """Route a user chat message to agent.brain for processing."""
        self.message_queues.setdefault(agent_id, deque(maxlen=100)).append(
            ChatMessage(text=message, timestamp=time.time(),
                        expires=time.time() + 5.0, sender="user")
        )

        agent = self.registered_agents.get(agent_id)
        if not agent:
            return

        context = self._build_context(agent)

        if hasattr(agent.brain, "process_language_input"):
            response = agent.brain.process_language_input(message, context)
        else:
            response = self._fallback_response(agent, message, context)

        if response:
            await self.send_message(agent_id, response, target="gui", sender="agent")

    async def handle_file_upload(self, agent_id: str, file_data: bytes,
                                  filename: str, filetype: str):
        """Save an uploaded file and route it to agent.brain."""
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return

        upload_dir = Path("data/uploads") / agent_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path  = upload_dir / filename

        file_path.write_bytes(file_data)

        if hasattr(agent.brain, "learn_from_file"):
            summary = agent.brain.learn_from_file(str(file_path), filetype)
        else:
            summary = self._fallback_file_learning(agent, file_path, filetype)

        if summary:
            await self.send_message(agent_id, summary, target="gui", sender="agent")

    async def handle_minecraft_perception(
        self, agent_id: str,
        frame:      Optional[np.ndarray] = None,
        audio:      Optional[np.ndarray] = None,
        action:     Optional[Dict]       = None,
        game_state: Optional[Dict]       = None,
    ):
        """Route perception data to agent.brain."""
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return

        if not hasattr(agent, "perception_buffer"):
            agent.perception_buffer = {}

        if frame is not None:
            agent.perception_buffer["visual"]           = frame
            agent.perception_buffer["visual_timestamp"] = time.time()

        if audio is not None:
            agent.perception_buffer["audio"]            = audio
            agent.perception_buffer["audio_timestamp"]  = time.time()

        if hasattr(agent.brain, "process_perception"):
            agent.brain.process_perception(frame, audio, action, game_state)
        else:
            self._fallback_perception(agent, frame, audio, action, game_state)

        if hasattr(agent.brain, "should_speak") and agent.brain.should_speak():
            if hasattr(agent.brain, "generate_speech"):
                msg = agent.brain.generate_speech(self._build_context(agent))
                if msg:
                    tgt = "game" if agent_id in self.game_connections else "gui"
                    await self.send_message(agent_id, msg, target=tgt, sender="agent")

    # ------------------------------------------------------------------
    # Autonomous speech loop
    # ------------------------------------------------------------------

    async def start_autonomous_speech(self, agent_id: str):
        """Start brain-driven autonomous speech — brain controls timing."""
        if agent_id in self.autonomous_tasks:
            return
        agent = self.registered_agents.get(agent_id)
        if not agent:
            return

        async def _loop():
            while (agent_id in self.gui_active
                   or agent_id in self.game_connections):
                try:
                    if (hasattr(agent.brain, "should_speak")
                            and agent.brain.should_speak()):
                        ctx = self._build_context(agent)
                        if hasattr(agent.brain, "generate_speech"):
                            msg = agent.brain.generate_speech(ctx)
                            if msg:
                                in_gui  = agent_id in self.gui_active
                                in_game = agent_id in self.game_connections
                                tgt = (
                                    "both" if (in_gui and in_game) else
                                    "gui"  if in_gui               else
                                    "game"
                                )
                                await self.send_message(
                                    agent_id, msg, target=tgt, sender="agent"
                                )
                    await asyncio.sleep(5.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    log.error(f"Autonomous speech error ({agent_id}): {e}")
                    await asyncio.sleep(10.0)

        self.autonomous_tasks[agent_id] = asyncio.create_task(_loop())
        log.info(f"Autonomous speech started: {agent_id}")

    async def stop_autonomous_speech(self, agent_id: str):
        task = self.autonomous_tasks.pop(agent_id, None)
        if task:
            task.cancel()

    # ------------------------------------------------------------------
    # Thought / visualization push (GUI → thoughts/3D panels)
    # ------------------------------------------------------------------

    async def send_thought(self, agent_id: str, thought: str,
                           is_internal: bool = True):
        ws = self.gui_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type":           "agent_thought" if is_internal else "internal_thought",
                "agent_id":       agent_id,
                "internal_thought": thought,
                "timestamp":      time.time(),
            }))
        except Exception as e:
            log.debug(f"Thought send failed: {e}")

    async def send_visualization(self, agent_id: str, data: Dict[str, Any]):
        ws = self.gui_connections.get(agent_id)
        if not ws:
            return
        try:
            await ws.send(json.dumps({
                "type":      "visualization_update",
                "agent_id":  agent_id,
                "data":      data,
                "timestamp": time.time(),
            }))
        except Exception as e:
            log.debug(f"Visualization send failed: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def is_gui_active(self, agent_id: str) -> bool:
        return agent_id in self.gui_active

    def _build_context(self, agent) -> Dict[str, Any]:
        ctx = {
            "health":           agent.health,
            "hunger":           agent.hunger,
            "emotions":         agent.emotion.snapshot(),
            "dominant_emotion": agent.emotion.dominant_emotion(),
            "memory_size":      len(agent.memory.events),
        }
        if hasattr(agent, "perception_buffer"):
            ctx.update(agent.perception_buffer)
        if hasattr(agent, "last_action"):
            ctx["last_action"] = agent.last_action
        return ctx

    def _fallback_response(self, agent, message: str,
                            context: Dict) -> Optional[str]:
        agent.memory.remember({
            "type": "user_message", "text": message, "tags": ["chat", "user"]
        })
        if hasattr(agent, "brain"):
            ev = {"type": "chat_input",
                  "payload": {"text": message}, "tags": ["chat"]}
            reward, emotion_delta = agent.brain.evaluate_event(ev, context)
            for emotion, value in emotion_delta.items():
                agent.emotion.add(emotion, value)
        return f"Heard: {message[:50]}"

    def _fallback_file_learning(self, agent, file_path: Path,
                                 filetype: str) -> str:
        if filetype.startswith("text/"):
            text = file_path.read_text(encoding="utf-8", errors="ignore")
            agent.memory.remember({
                "type": "file_input", "tags": ["text", "file"],
                "payload": {"filename": file_path.name, "length": len(text)},
            })
            return f"Text file stored: {len(text)} chars"

        if filetype.startswith("image/"):
            import cv2
            img = cv2.imread(str(file_path))
            if img is not None:
                h, w = img.shape[:2]
                agent.memory.remember({
                    "type": "image_input", "tags": ["vision", "file"],
                    "payload": {"filename": file_path.name, "size": (w, h)},
                })
                return f"Image stored: {w}×{h}"

        return f"File received: {file_path.name}"

    def _fallback_perception(self, agent, frame, audio, action, game_state):
        if frame is not None:
            agent.memory.remember({
                "type": "minecraft_vision", "tags": ["minecraft", "vision"],
                "payload": {"timestamp": time.time()},
            })

        if action is None or game_state is None:
            return

        obs_dict = {
            "health":   game_state.get("health",   20.0),
            "hunger":   game_state.get("hunger",   20.0),
            "position": game_state.get("position", {"x": 0, "y": 64, "z": 0}),
        }
        obs = agent.perceive(obs_dict)

        if isinstance(action, dict):
            action_array = np.array([
                action.get("move_forward",  0.0),
                action.get("move_strafe",   0.0),
                1.0 if action.get("jump",      False) else 0.0,
                1.0 if action.get("sneak",     False) else 0.0,
                1.0 if action.get("attack",    False) else 0.0,
                1.0 if action.get("use",       False) else 0.0,
                1.0 if action.get("drop",      False) else 0.0,
                1.0 if action.get("open_inv",  False) else 0.0,
                1.0 if action.get("swap_hand", False) else 0.0,
                action.get("yaw_delta",   0.0) / 2.0,
                action.get("pitch_delta", 0.0) / 1.2,
            ], dtype=np.float32)
        else:
            action_array = action

        outcome = {
            "health":      obs_dict["health"],
            "hunger":      obs_dict["hunger"],
            "is_dead":     obs_dict["health"] <= 0,
            "task_reward": 0.0,
        }
        if game_state.get("killed_entity"):
            outcome["task_reward"] += 1.0
        if game_state.get("took_damage"):
            outcome["task_reward"] -= 0.5

        if agent.last_obs is not None:
            agent.learn(agent.last_obs, action_array, obs, outcome)
        agent.last_obs = obs


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

chat_system = UnifiedChatSystem()


# ---------------------------------------------------------------------------
# Integration helpers for main.py
# ---------------------------------------------------------------------------

async def handle_frontend_chat(agent_id: str, message: str):
    """Route chat from the React frontend to agent.brain."""
    await chat_system.handle_user_message(agent_id, message)


async def handle_frontend_file_upload(agent_id: str, file_data: bytes,
                                       filename: str, filetype: str):
    """Route a file upload to agent.brain."""
    await chat_system.handle_file_upload(agent_id, file_data, filename, filetype)


async def handle_minecraft_frame(agent_id: str,
                                  frame_data: np.ndarray,
                                  game_state: Optional[Dict] = None):
    """Route Minecraft frame data to agent.brain."""
    await chat_system.handle_minecraft_perception(
        agent_id=agent_id, frame=frame_data, game_state=game_state,
    )


async def start_agent_autonomous_speech(agent_id: str):
    """Start brain-driven autonomous speech for agent."""
    await chat_system.start_autonomous_speech(agent_id)