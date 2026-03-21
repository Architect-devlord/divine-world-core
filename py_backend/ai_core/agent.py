# ai_core/agent.py - UNIFIED AGENT RUNTIME & BOOTSTRAP
"""
Unified Agent Runtime
=====================
Fully integrated standalone agent with WebSocket support and executable
generation.  Handles NPCs, God agents, and dynamic spawning.

Key changes from previous version
----------------------------------
1.  _init_world_model()  — creates WorldModel and calls
    brain.set_world_model(wm) instead of the old
    integrate_world_model_with_agent() which monkey-patched
    brain.evaluate_event from outside.

2.  _init_vision()       — calls add_vision_to_agent() so the full
    VisionAdapter pipeline (feature extraction, online vocab, Minecraft
    frame hook) is properly wired.  The old inline VisionAdapter() stub
    inside observe() is removed.

3.  initialize_reward_system() — called eagerly in __init__ so
    brain.reward_system is never None during autonomous operation.

4.  load()              — fixed WorldModel restore path; WorldModel
    takes WorldModelConfig not agent_id, and the config is stored in
    the checkpoint so it round-trips cleanly.

5.  GodBrainExtension   — removed from imports and usage. Gods use the
    same BrainCore; their personality weights make them different.

6.  Port wiring (this revision)
    ─────────────────────────────
    NPCAgent now accepts two explicit port params:

      backend_port  (int, default 0)
        The WebSocket port this agent's FastAPI server is listening on.
        Passed from main.py via  --port <N>  on the agent subprocess
        command-line. The Java mod connects TO this port as a WebSocket
        client at  ws://127.0.0.1:<backend_port>/ws/agent

      tcp_port  (int, default 0)
        The TCP action-server port this agent's Java TCPServer is
        listening on (value stored in agents.json for this agent's
        display name, starting at 11401).
        Passed from main.py via  --tcp-port <N>.
        If omitted (legacy / standalone usage), resolved lazily from
        agents.json by display name, then falls back to PORT_DEFAULT.

    MinecraftClient is constructed with the resolved values so there are
    no hardcoded port constants anywhere in the runtime.
"""

import asyncio
import argparse
import sys
import os
import time
import signal
import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, Literal, List
import json

import torch
import numpy as np
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_core.personality  import Personality, GenderType, assign_npc_gender, assign_god_gender
from ai_core.emotion      import EmotionSystem
from ai_core.reward_system import RewardSystem
from ai_core.brain_core   import BrainCore
from ai_core.planner      import CognitivePlanner
from ai_core.memory       import UnifiedMemoryStore
from ai_core.cognitive_loop import CognitiveLoop
from ai_core.communication_protocol import handle_agent_websocket, run_tcp_action_loop
from ai_core.config       import Config

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

log = logging.getLogger("agent")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
    )

# ---------------------------------------------------------------------------
# Port constants — mirror mc_uuid.py so there is a single source of truth
# ---------------------------------------------------------------------------
_TCP_PORT_DEFAULT    = 11401   # PORT_START in mc_uuid.py
_WS_PORT_OFFSET      = 10000   # WS backend = tcp_port + offset  (21401+)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # must be False when allow_origins=["*"]
    allow_methods=["*"],
    allow_headers=["*"],
)

global_agent  = None
global_server = None
active_websockets: List = []


# =============================================================================
# WebSocket endpoints
# =============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        await websocket.send_json({
            "type":     "connected",
            "agent_id": global_agent.agent_id if global_agent else "unknown",
            "protocol": "json",
            "version":  "1.0.0",
        })
        log.info(f"[WS] Client connected. Active: {len(active_websockets)}")

        while True:
            data    = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "chat":
                user_message = message.get("message", "")
                if global_agent and user_message:
                    response = await global_agent.process_chat(user_message)
                    await websocket.send_json({
                        "type":      "chat",
                        "from":      "agent",
                        "text":      response,
                        "timestamp": time.time(),
                    })
    except WebSocketDisconnect:
        log.info("[WS] Client disconnected")
    except Exception as e:
        log.error(f"[WS] Error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


@app.websocket("/ws/agent")
async def agent_perception_ws(websocket: WebSocket):
    """Binary perception/action WebSocket for Minecraft client."""
    try:
        await websocket.accept()
        data     = await websocket.receive_json()
        agent_id = data.get("agent_id")
        if not agent_id:
            await websocket.close(code=4000, reason="Missing agent_id")
            return
        log.info(f"WebSocket accepted for agent: {agent_id}")
        await handle_agent_websocket(websocket, agent_id, global_agent)
    except Exception as e:
        log.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=4001, reason=str(e))
        except Exception:
            pass


async def broadcast_to_clients(message: dict):
    dead = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        active_websockets.remove(ws)


# =============================================================================
# HTTP endpoints
# =============================================================================

async def broadcast_world_model(data: dict):
    """Broadcast a world_model_update to all connected WebSocket clients."""
    await broadcast_to_clients({
        "type":      "world_model_update",
        "data":      data,
        "timestamp": time.time(),
    })


async def broadcast_activity(activity_type: str, title: str):
    """Broadcast an activity_update event to all connected WebSocket clients."""
    await broadcast_to_clients({
        "type":          "activity_update",
        "activity_type": activity_type,
        "title":         title,
        "timestamp":     time.time(),
    })


@app.get("/status")
async def get_status():
    return global_agent.get_info() if global_agent else {"error": "Agent not running"}


@app.get("/thoughts")
async def get_thoughts():
    return {"thoughts": global_agent.thoughts[-20:]} if global_agent else {"thoughts": []}


@app.post("/chat")
async def chat(message: str = Form(...),
               agent_id: str = Form(None),
               allowed_websites: str = Form(None)):
    if not global_agent:
        return {"error": "Agent not running"}

    if allowed_websites:
        try:
            websites_data = json.loads(allowed_websites)
            formatted = [
                {'url': w, 'enabled': True, 'type': 'url'}
                if isinstance(w, str) else w
                for w in websites_data
            ]
            if hasattr(global_agent, 'web_browser'):
                global_agent.web_browser.update_allowed_websites(formatted)
        except Exception as e:
            log.error(f"Error updating allowed websites: {e}")

    response = await global_agent.process_chat(message)
    await broadcast_to_clients({
        "type": "chat", "from": "agent",
        "text": response, "timestamp": time.time(),
    })
    return {"response": response}


@app.post("/api/agents/{agent_id}/web/allow")
async def allow_websites(agent_id: str, data: Dict[str, Any]):
    if global_agent and hasattr(global_agent, 'web_browser'):
        global_agent.web_browser.update_allowed_websites(
            data.get('websites', [])
        )
        return {"status": "success"}
    return {"error": "Agent not running"}


# =============================================================================
# Controller (DWController) routes
# =============================================================================

_controller_runtime = None   # set lazily on first activate


def _get_controller():
    global _controller_runtime
    if _controller_runtime is None and global_agent is not None:
        try:
            from py_backend.utils.dw_controller import ControllerRuntime
            _controller_runtime = ControllerRuntime(global_agent)
        except Exception as e:
            log.error(f"ControllerRuntime init failed: {e}")
    return _controller_runtime


@app.get("/api/controller/detect-devices")
async def detect_devices(agent_id: str = "demo"):
    """Enumerate available cameras and microphones."""
    try:
        from py_backend.utils.dw_controller import ControllerRuntime
        rt          = ControllerRuntime.__new__(ControllerRuntime)
        rt.agent    = global_agent
        cameras     = rt.list_cameras()     if hasattr(rt, 'list_cameras')     else []
        microphones = rt.list_microphones() if hasattr(rt, 'list_microphones') else []
        return {
            "status":  "success",
            "devices": {"cameras": cameras, "microphones": microphones},
        }
    except Exception as e:
        log.error(f"detect-devices error: {e}")
        return {"status": "error", "devices": {"cameras": [], "microphones": []}}


@app.post("/api/controller/activate")
async def activate_controller(data: Dict[str, Any]):
    if not global_agent:
        return {"status": "error", "message": "Agent not running"}
    ctrl = _get_controller()
    if ctrl is None:
        return {"status": "error", "message": "ControllerRuntime unavailable"}
    perm_settings = data.get("permissionSettings", {})
    granted = [k for k, v in perm_settings.items() if v]
    try:
        ctrl.grant_permissions(granted)
        ctrl.start_multimodal_learning(
            vision=perm_settings.get("camera",     False),
            audio= perm_settings.get("microphone", False),
        )
        log.info(f"Controller activated — permissions: {granted}")
        return {"status": "success", "permissions": granted}
    except Exception as e:
        log.error(f"Controller activate error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/controller/deactivate")
async def deactivate_controller(agent_id: str = Query(default="demo")):
    global _controller_runtime
    if _controller_runtime is not None:
        try:
            _controller_runtime.stop()
        except Exception as e:
            log.error(f"Controller deactivate error: {e}")
        _controller_runtime = None
    return {"status": "success"}


@app.get("/api/controller/status")
async def controller_status(agent_id: str = "demo"):
    ctrl = _get_controller()
    if ctrl is None:
        return {
            "active": False, "camera_active": False,
            "microphone_active": False, "permissions": {},
            "stats": {"frames_processed": 0, "audio_chunks_processed": 0,
                      "learning_events": 0, "files_processed": 0},
        }
    try:
        stats = ctrl.get_stats()
        return {
            "active":            ctrl.running if hasattr(ctrl, 'running') else False,
            "camera_active":     stats.get("camera_active",     False),
            "microphone_active": stats.get("microphone_active", False),
            "permissions":       ctrl.enabled_permissions if hasattr(ctrl, 'enabled_permissions') else {},
            "stats": {
                "frames_processed":       stats.get("frames_processed",       0),
                "audio_chunks_processed": stats.get("audio_chunks_processed", 0),
                "learning_events":        stats.get("learning_events",        0),
                "files_processed":        stats.get("files_processed",        0),
            },
        }
    except Exception as e:
        log.error(f"controller_status error: {e}")
        return {"active": False, "camera_active": False,
                "microphone_active": False, "permissions": {}, "stats": {}}


@app.post("/api/upload")
async def upload_file(file:     UploadFile = File(...),
                      agent_id: str        = Form(...),
                      filetype: str        = Form(...),
                      sync:     bool       = Form(False)):
    if not global_agent:
        return {"error": "Agent not running"}
    try:
        content      = await file.read()
        text_content = content.decode('utf-8')
        global_agent.memory.remember({
            'type':     'file_upload',
            'filename': file.filename,
            'filetype': filetype,
            'content':  text_content,
            'size':     len(content),
        }, tags=['file', 'upload', 'learning'])
        if sync:
            global_agent.thoughts.append({
                "timestamp": time.time(),
                "thought":   f"Processed file: {file.filename} ({filetype})",
            })
        return {"success": True, "filename": file.filename, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# Port resolution helper
# =============================================================================

def _resolve_minecraft_ports(
    custom_name:  Optional[str],
    agent_id:     str,
    tcp_port_hint: int = 0,
    ws_port_hint:  int = 0,
) -> tuple:
    """
    Return (tcp_port, ws_port) for the MinecraftClient.

    Resolution order for tcp_port:
      1. Explicit tcp_port_hint  (passed as --tcp-port from main.py)
      2. agents.json lookup by display name
      3. Hard-coded default _TCP_PORT_DEFAULT (11401)

    Resolution order for ws_port:
      1. Explicit ws_port_hint  (passed as --port from main.py)
      2. tcp_port + _WS_PORT_OFFSET
    """
    tcp = tcp_port_hint

    if tcp <= 0:
        display = custom_name or agent_id
        try:
            from py_backend.utils.mc_uuid import AgentNameManager
            looked_up = AgentNameManager().get_port_for_name(display)
            if looked_up:
                tcp = looked_up
                log.info(f"[PortResolve] '{display}' → TCP {tcp} (agents.json)")
            else:
                tcp = _TCP_PORT_DEFAULT
                log.warning(
                    f"[PortResolve] '{display}' not in agents.json — "
                    f"using default TCP {tcp}"
                )
        except Exception as e:
            tcp = _TCP_PORT_DEFAULT
            log.warning(f"[PortResolve] agents.json lookup failed ({e}), "
                        f"using default TCP {tcp}")

    ws = ws_port_hint if ws_port_hint > 0 else tcp + _WS_PORT_OFFSET

    log.info(f"[PortResolve] Final ports → TCP {tcp} / WS {ws}")
    return tcp, ws


# =============================================================================
# NPCAgent
# =============================================================================

class NPCAgent:
    """
    Fully autonomous NPC / God agent with standalone runtime.

    Port params
    -----------
    backend_port  — WebSocket port this agent's FastAPI server is listening on.
                    The Java mod connects here: ws://127.0.0.1:<backend_port>/ws/agent
                    Passed via --port from main.py.  0 = derive from tcp_port.

    tcp_port      — TCP action-server port the Java TCPServer listens on
                    (from agents.json, starting at 11401).
                    Passed via --tcp-port from main.py.  0 = auto-resolve.
    """

    def __init__(self,
                 agent_id:       str,
                 gender:         Optional[GenderType]       = None,
                 persona_traits: Optional[Dict[str, float]] = None,
                 client_process                             = None,
                 autonomous:     bool                       = True,
                 use_scylla:     bool                       = True,
                 mode:           str                        = 'autonomous',
                 god_type:       Optional[str]              = None,
                 custom_name:    Optional[str]              = None,
                 backend_port:   int                        = 0,
                 tcp_port:       int                        = 0):

        self.agent_id        = agent_id
        self.custom_name     = custom_name
        self.autonomous_mode = autonomous
        self.mode            = mode
        self.god_type        = god_type

        # Resolve Minecraft communication ports up front so they are available
        # for MinecraftClient construction and for get_info() logging.
        self._tcp_port, self._backend_port = _resolve_minecraft_ports(
            custom_name   = custom_name,
            agent_id      = agent_id,
            tcp_port_hint = tcp_port,
            ws_port_hint  = backend_port,
        )

        # ── Core components ───────────────────────────────────────────────
        if gender is None:
            gender = assign_npc_gender()
        self.personality = Personality(gender=gender, traits=persona_traits)
        self.emotion     = EmotionSystem()

        self.memory = UnifiedMemoryStore(
            agent_id=agent_id,
            capacity=10000,
            use_scylla=use_scylla,
            scylla_hosts=['127.0.0.1'],
        )

        self.brain   = BrainCore(agent_ref=self)
        self.planner = CognitivePlanner(brain=self.brain)

        self._init_language()

        # ── Continual learning ────────────────────────────────────────────
        try:
            from ai_core.continual_learner import add_continual_learning
            add_continual_learning(self, strategy='replay')
            log.info(f"[{agent_id}] Continual learning attached (strategy=replay)")
        except Exception as e:
            log.warning(f"[{agent_id}] Continual learning not available: {e}")

        # ── State ─────────────────────────────────────────────────────────
        self.health       = 20.0
        self.hunger       = 20.0
        self.last_obs     = None
        self.last_action  = None
        self.step_count   = 0

        self.client_process = client_process
        self.agent_type     = 'npc'
        self.policy         = None
        self.metadata:  Dict[str, Any] = {}

        # Neural stack
        self.world_model         = None
        self.world_model_trainer = None
        self.world_model_buffer  = None
        self._neural_integrated  = False

        # FIX #1: EpisodicMemory was never initialized — learn() used a hasattr
        # guard that was always False, keeping the PPO replay buffer empty for
        # the entire live Minecraft session.  Initialize eagerly here so every
        # call to learn() actually stores (obs, action, reward, next_obs, done).
        from ai_core.memory import EpisodicMemory as _EM
        self.episodic_memory = _EM(capacity=50_000)

        self.thoughts = [
            {"timestamp": time.time(), "thought": "Initializing agent systems..."},
            {"timestamp": time.time(), "thought": "Memory system online"},
            {"timestamp": time.time(), "thought": "Ready to interact and learn"},
        ]

        # ── Subsystem init (order matters) ────────────────────────────────

        # 1. Reward system — eager, so brain.reward_system is never None
        self.reward_system: Optional[RewardSystem] = None
        self.initialize_reward_system()

        # 2. World model
        self._init_world_model()

        # 3. Vision
        self._init_vision()

        # 4. Audio
        self._init_audio_processor()

        # 5. Cognitive loop
        self.cognitive_loop = None
        if self.autonomous_mode:
            self._init_cognitive_loop()

        log.info(
            f"NPCAgent init: {agent_id} "
            f"(mode={mode}, autonomous={autonomous}, "
            f"tcp={self._tcp_port}, ws={self._backend_port})"
        )

        # ── Auto-initialize policy so decide() never falls back to random ─────
        # initialize_policy() was only available as a manual call — nothing
        # called it, so self.policy stayed None and decide() used an 11-dim
        # random vector.  Build the spaces here and initialize eagerly.
        try:
            import gymnasium as _gym
            _obs_space = _gym.spaces.Box(
                low=-np.inf, high=np.inf, shape=(50,), dtype=np.float32
            )
            _act_space = _gym.spaces.Box(
                low=-1.0, high=1.0, shape=(13,), dtype=np.float32
            )
            self.initialize_policy(_obs_space, _act_space)
        except Exception as _pe:
            log.warning(f"[{agent_id}] Policy auto-init failed: {_pe}")

        # ── Optional integrations ─────────────────────────────────────────
        try:
            from ai_core.web_browser import add_web_browsing_to_agent
            add_web_browsing_to_agent(self)
            log.info(f"[{agent_id}] Web browsing initialized")
        except Exception as e:
            log.warning(f"Web browsing not available: {e}")

        if self.mode == 'minecraft':
            from ai_core.actuators import MinecraftClient
            self.minecraft_client = MinecraftClient(
                agent_id=agent_id,
                tcp_host='127.0.0.1', tcp_port=self._tcp_port,
                ws_host='127.0.0.1',  ws_port=self._backend_port,
                prefer_tcp=True,
            )
            log.info(
                f"[{agent_id}] Minecraft client initialised "
                f"(TCP:{self._tcp_port} / WS:{self._backend_port})"
            )
        else:
            self.minecraft_client = None

        if god_type:
            try:
                from ai_core.god_controls import integrate_god_controls
                integrate_god_controls(self)
                log.info(f"[{agent_id}] God controls initialized for {god_type}")
            except Exception as e:
                log.warning(f"God controls not available: {e}")

    # =========================================================================
    # Subsystem initialisation
    # =========================================================================

    def _init_language(self):
        try:
            from ai_core.brain_language import add_language_to_brain
            add_language_to_brain(self.brain)
            log.info(f"[{self.agent_id}] Language intelligence initialised")
        except Exception as e:
            log.warning(
                f"[{self.agent_id}] Language init failed — "
                f"speech and language learning unavailable: {e}"
            )

    def _init_cognitive_loop(self):
        self.cognitive_loop = CognitiveLoop(agent=self, loop_interval=0.5)
        log.info(f"[{self.agent_id}] Cognitive loop initialised")

    def _init_world_model(self):
        try:
            from ai_core.world_model import (
                WorldModel, WorldModelConfig,
                WorldModelReplayBuffer, WorldModelTrainer,
            )
            config        = WorldModelConfig(
                device='cuda' if torch.cuda.is_available() else 'cpu'
            )
            wm            = WorldModel(config)
            replay_buffer = WorldModelReplayBuffer(
                capacity=50_000, sequence_length=64
            )
            trainer       = WorldModelTrainer(wm, replay_buffer, batch_size=16)

            self.world_model         = wm
            self.world_model_buffer  = replay_buffer
            self.world_model_trainer = trainer
            self.brain.set_world_model(wm)

            log.info(f"[{self.agent_id}] WorldModel attached to BrainCore")
        except Exception as e:
            log.warning(f"[{self.agent_id}] World model not available: {e}")

    def _init_vision(self):
        try:
            from ai_core.vision import add_vision_to_agent
            add_vision_to_agent(
                self,
                feature_dim=64,
                max_vocab_size=256,
                frame_h=84,
                frame_w=84,
                fps=15.0,
                enable_depth=True,
                auto_start=True,
            )
            log.info(f"[{self.agent_id}] VisionAdapter attached")
        except Exception as e:
            log.warning(f"[{self.agent_id}] Vision not available: {e}")

    def _init_audio_processor(self):
        try:
            from ai_core.audio_processors import add_audio_processing_to_agent
            add_audio_processing_to_agent(self)
            log.info(f"[{self.agent_id}] Audio processing initialised")
        except Exception as e:
            log.warning(f"Audio processing not available: {e}")

    # =========================================================================
    # Reward system
    # =========================================================================

    def initialize_reward_system(self, obs_dim: int = 50, action_dim: int = 13):  # FIX DIM-02: was 11, must match TransformerPolicy.BASE_DIM
        if self.reward_system is not None:
            return
        self.reward_system = RewardSystem(
            obs_dim=obs_dim,
            action_dim=action_dim,
            personality=self.personality,
            emotion_system=self.emotion,
            use_rnd=True,
            use_icm=True,
        )
        self.brain.set_reward_system(self.reward_system)
        log.info(f"[{self.agent_id}] RewardSystem initialised and wired to BrainCore")

    # =========================================================================
    # Autonomous control
    # =========================================================================

    async def start_autonomous_mode(self):
        if not self.cognitive_loop:
            self._init_cognitive_loop()
        await self.cognitive_loop.start()
        log.info(f"✅ {self.agent_id} is now FULLY AUTONOMOUS")

    async def stop_autonomous_mode(self):
        if self.cognitive_loop:
            await self.cognitive_loop.stop()
        log.info(f"🛑 {self.agent_id} autonomous mode stopped")

    def is_autonomous(self) -> bool:
        return bool(self.cognitive_loop and self.cognitive_loop.running)

    async def broadcast(self, message: dict):
        await broadcast_to_clients(message)

    # =========================================================================
    # Perception & action
    # =========================================================================

    def perceive(self, raw_observation: Dict[str, Any]) -> np.ndarray:
        obs_parts = []

        obs_parts.append(raw_observation.get('health',     20.0) / 20.0)
        obs_parts.append(raw_observation.get('hunger',     20.0) / 20.0)
        obs_parts.append(raw_observation.get('saturation',  5.0) / 20.0)

        pos = raw_observation.get('position', {'x': 0, 'y': 0, 'z': 0})
        obs_parts.extend([
            pos['x'] / 100.0, pos['y'] / 100.0, pos['z'] / 100.0
        ])

        obs_parts.append(raw_observation.get('yaw',   0.0) / 360.0)
        obs_parts.append(raw_observation.get('pitch', 0.0) /  90.0)
        # FIX INT-04: old code only stored len(entities)/10 — full entity data
        # (type_id, name, distance, angle) discarded. Agents never learned which
        # entity types are near. Now encode the nearest 3 entities explicitly:
        #   dim = [type_id/7, distance/32, sin(angle_rad), cos(angle_rad)]
        # type_id range: 0=unknown 1=player 2=hostile 3=passive 4=item 5=boss 6=projectile 7=god
        # Absent entities → [0, 0, 0, 0] (type=unknown, distance=0 signals nothing present)
        entities = raw_observation.get('entities', [])
        obs_parts.append(len(entities) / 10.0)  # keep count for backward compat
        # Sort by distance ascending so nearest 3 are always in the same slots
        sorted_ents = sorted(entities, key=lambda e: e[2] if len(e) > 2 else 999)[:3]
        for ent in sorted_ents:
            type_id  = ent[0] if len(ent) > 0 else 0
            distance = ent[2] if len(ent) > 2 else 0.0
            angle    = ent[3] if len(ent) > 3 else 0.0
            angle_rad = float(angle) * 3.14159265 / 180.0
            obs_parts.append(float(type_id) / 7.0)
            obs_parts.append(min(float(distance), 32.0) / 32.0)
            obs_parts.append(float(np.sin(angle_rad)))
            obs_parts.append(float(np.cos(angle_rad)))
        # Pad missing entities with zeros
        for _ in range(3 - len(sorted_ents)):
            obs_parts.extend([0.0, 0.0, 0.0, 0.0])

        obs_parts.append(raw_observation.get('inventory', {}).get('slot_count', 0) / 36.0)

        obs_parts.extend(self.personality.as_array().tolist())
        obs_parts.extend(self.emotion.as_array().tolist())

        if self.reward_system and self.reward_system.reward_history:
            recent = list(self.reward_system.reward_history)[-20:]
            obs_parts.extend([
                np.mean(recent), np.std(recent),
                np.max(recent),  np.min(recent),
                len([r for r in recent if r > 0]) / len(recent),
            ])
        else:
            obs_parts.extend([0.0] * 5)

        obs_parts.append(len(self.memory.events) / 1000.0)
        obs_parts.append(0.0)

        while len(obs_parts) < 50:
            obs_parts.append(0.0)

        obs_array     = np.array(obs_parts[:50], dtype=np.float32)
        self.last_obs = obs_array

        if self.cognitive_loop and self.cognitive_loop.running:
            self.cognitive_loop.receive_state_update({
                'health':          self.health,
                'hunger':          self.hunger,
                'raw_observation': raw_observation,
            })

        return obs_array

    def observe(self, image: np.ndarray,
                info: Optional[Dict[str, Any]] = None) -> np.ndarray:
        info = info or {}
        try:
            if image is not None:
                processed = image.astype(np.float32).transpose(2, 0, 1) / 255.0
            else:
                processed = np.zeros((3, 84, 84), dtype=np.float32)

            self.memory.remember({
                'type':        'visual_observation',
                'image_shape': list(image.shape) if image is not None else [],
                'description': info.get('description', 'Visual observation'),
                'source':      info.get('source', 'unknown'),
                'timestamp':   time.time(),
            }, tags=['vision', 'observation'])

            thought = f"I observed: {info.get('description', 'a visual scene')}"
            self.thoughts.append({"timestamp": time.time(), "thought": thought})
            if len(self.thoughts) > 100:
                self.thoughts = self.thoughts[-100:]

            return processed

        except Exception as e:
            log.error(f"observe() fallback error: {e}")
            return np.zeros((3, 84, 84), dtype=np.float32)

    # =========================================================================
    # Learning
    # =========================================================================

    def learn(self, obs: np.ndarray, action: np.ndarray,
              next_obs: np.ndarray, outcome: dict):
        obs_t      = torch.tensor(obs,      dtype=torch.float32).unsqueeze(0)
        action_t   = torch.tensor(action,   dtype=torch.float32).unsqueeze(0)
        next_obs_t = torch.tensor(next_obs, dtype=torch.float32).unsqueeze(0)

        event = {
            'type':    'experience',
            'tags':    ['learning', 'experience', 'rl'],
            'payload': outcome,
        }
        signal = self.reward_system.compute_reward(
            event=event,
            obs=obs_t, action=action_t, next_obs=next_obs_t,
            outcome=outcome,
        )
        self.reward_system.apply_signal(signal)

        self.memory.remember({
            'type':    'experience',
            'obs':     obs.tolist(),
            'action':  action.tolist(),
            'reward':  signal.total,
            'outcome': outcome,
        }, tags=['learning', 'experience', 'rl'])

        exp_event = {'type': 'experience', 'tags': ['rl'], 'payload': outcome}
        self.brain._update_learning(exp_event, outcome, signal.total)
        self.brain._store_continual_experience(exp_event, signal.total, outcome)

        # FIX INT-01: populate EpisodicMemory so PPO batch training has samples.
        # Was never called — replay buffer stayed empty during all live play.
        done = bool(outcome.get('is_dead', False))
        if hasattr(self, 'episodic_memory') and self.episodic_memory is not None:
            self.episodic_memory.add(
                obs, action, signal.total, next_obs, done,
                priority=abs(signal.total) + 1e-6,
            )

    # =========================================================================
    # Status
    # =========================================================================

    def is_alive(self) -> bool:
        if self.client_process:
            return self.client_process.is_alive
        return True

    def get_info(self) -> Dict[str, Any]:
        info = {
            'agent_id':        self.agent_id,
            'custom_name':     self.custom_name,
            'agent_type':      self.agent_type,
            'mode':            self.mode,
            'gender':          self.personality.gender,
            'is_alive':        self.is_alive(),
            'step_count':      self.step_count,
            'health':          self.health,
            'hunger':          self.hunger,
            'personality':     self.personality.to_dict(),
            'emotions':        self.emotion.snapshot(),
            'memory_size':     len(self.memory.events),
            'dominant_emotion':self.emotion.dominant_emotion(),
            'autonomous':      self.is_autonomous(),
            'tcp_port':        self._tcp_port,
            'backend_port':    self._backend_port,
        }
        if hasattr(self.brain, 'language') and self.brain.language is not None:
            info['language'] = self.brain.get_language_progress()
        if self.cognitive_loop:
            info['cognitive_status'] = self.cognitive_loop.get_status()
        info['memory_stats'] = self.memory.get_stats()
        if self.client_process:
            info['backend_url'] = self.client_process.backend_url
            info['server']      = self.client_process.server_addr
        if self.metadata:
            info['metadata'] = self.metadata
        if hasattr(self, 'vision') and self.vision is not None:
            try:
                info['vision'] = self.vision.get_stats()
            except Exception:
                pass
        return info

    async def process_chat(self, message: str) -> str:
        self.memory.remember({
            'type':    'chat_message',
            'sender':  'user',
            'message': message,
        }, tags=['chat', 'user', 'learning'])

        import re
        mentioned_urls = re.findall(r'(https?://[^\s]+)', message)
        if mentioned_urls and hasattr(self, 'web_browser'):
            for url in mentioned_urls:
                self.memory.remember({
                    'type':    'url_mentioned',
                    'url':     url,
                    'context': message[:200],
                    'source':  'user_chat',
                }, tags=['web', 'url', 'mentioned'])
                trigger_words = ('check', 'look', 'browse', 'visit', 'read',
                                 'open', 'go to', 'see', 'find')
                if any(w in message.lower() for w in trigger_words):
                    self.web_browser.add_url_to_queue(url)
                    log.info(f"[{self.agent_id}] URL queued by user request: {url}")

        response = f"I am {self.agent_id}. You said: {message}"
        try:
            if (hasattr(self.brain, 'language') and
                    self.brain.language is not None and
                    self.brain.language.language_stage >= 1):
                ctx = {
                    'current_message': message,
                    'personality':     self.personality.to_dict(),
                    'emotions':        self.emotion.snapshot(),
                    'recent_memory':   self.memory.recall(5),
                }
                resp = self.brain.language.generate_speech(ctx)
                if resp and resp.strip():
                    response = resp
        except Exception as e:
            log.warning(f"Brain response generation failed: {e}")

        self.memory.remember({
            'type':    'chat_message',
            'sender':  'agent',
            'message': response,
        }, tags=['chat', 'agent', 'response'])

        thought = f"Chatted with user: \"{message[:50]}...\""
        self.thoughts.append({"timestamp": time.time(), "thought": thought})
        if len(self.thoughts) > 100:
            self.thoughts = self.thoughts[-100:]

        await broadcast_to_clients({
            "type":             "agent_thought",
            "internal_thought": thought,
            "timestamp":        time.time(),
        })
        return response

    # =========================================================================
    # Save / Load
    # =========================================================================

    def save(self, path: str):
        from ai_core.brain_capsule import BrainCapsule

        language_state = None
        if hasattr(self.brain, 'language') and self.brain.language is not None:
            language_state = self.brain.language.state_dict()

        metadata = {
            'agent_id':    self.agent_id,
            'custom_name': self.custom_name,
            'agent_type':  self.agent_type,
            'mode':        self.mode,
            'gender':      self.personality.gender,
            'step_count':  self.step_count,
            'saved_at':    time.time(),
            'autonomous':  self.autonomous_mode,
            # FIX: god_type was never persisted — a restarted god agent had
            # god_type=None, so god_controls, ability space, and 18-dim policy
            # never re-initialised after load().
            'god_type':    self.god_type,
            # Persist resolved ports so they survive restarts without
            # needing another agents.json lookup on cold start.
            'tcp_port':    self._tcp_port,
            'backend_port':self._backend_port,
        }
        metadata.update(self.metadata)

        pregnancy_state = None
        breeding_sys    = getattr(self, '_breeding_system', None)
        if breeding_sys is not None:
            pregnancy_state = breeding_sys.get_serialisable_pregnancy(self.agent_id)

        capsule = BrainCapsule(
            metadata         = metadata,
            personality      = self.personality.to_dict(),
            emotion_snapshot = self.emotion.snapshot(),
            memory_snapshot  = self.memory.recall(1000),
            language_state   = language_state,
            gender           = str(self.personality.gender),
            pregnancy_state  = pregnancy_state,
        )

        model_state: Dict[str, Any] = {}

        if self.policy:
            try:
                model_state['policy'] = {
                    k: v.cpu() if isinstance(v, torch.Tensor) else v
                    for k, v in self.policy.state_dict().items()
                }
            except Exception as e:
                log.error(f"[{self.agent_id}] Failed to serialize policy: {e}")

        if self.world_model is not None:
            try:
                model_state['world_model'] = {
                    'config': self.world_model.config,
                    'state':  {
                        k: v.cpu() if isinstance(v, torch.Tensor) else v
                        for k, v in self.world_model.state_dict().items()
                    },
                }
            except Exception as e:
                log.error(f"[{self.agent_id}] Failed to serialize world model: {e}")

        if hasattr(self, 'vision') and self.vision is not None:
            try:
                model_state['vision'] = self.vision.state_dict()
            except Exception as e:
                log.warning(f"[{self.agent_id}] Vision state not saved: {e}")

        if self.reward_system is not None:
            try:
                rs = {}
                if self.reward_system.use_rnd:
                    rs['rnd'] = {
                        k: v.cpu() if isinstance(v, torch.Tensor) else v
                        for k, v in self.reward_system.rnd.state_dict().items()
                    }
                if self.reward_system.use_icm:
                    rs['icm'] = {
                        k: v.cpu() if isinstance(v, torch.Tensor) else v
                        for k, v in self.reward_system.icm.state_dict().items()
                    }
                if rs:
                    model_state['reward_system'] = rs
            except Exception as e:
                log.warning(f"[{self.agent_id}] RewardSystem state not saved: {e}")

        # Bug #21 fix: persist EpisodicMemory replay buffer (capped at 10k
        # transitions to bound file size to ~5 MB regardless of run length).
        if getattr(self, 'episodic_memory', None) is not None:
            try:
                buf = self.episodic_memory
                cap = min(len(buf.buffer), 10_000)
                model_state['episodic_memory'] = {
                    'transitions': list(buf.buffer)[-cap:],
                    'priorities':  list(buf.priorities)[-cap:],
                    'capacity':    buf.capacity,
                }
            except Exception as e:
                log.warning(f"[{self.agent_id}] EpisodicMemory not saved: {e}")

        # Bug #22 fix: persist WorldModelTrainer progress counter and recent
        # loss history so training resumes from the correct step rather than 0.
        if getattr(self, 'world_model_trainer', None) is not None:
            try:
                trainer = self.world_model_trainer
                model_state['world_model_trainer'] = {
                    'step_count':   trainer.step_count,
                    'loss_history': list(trainer.loss_history),
                }
            except Exception as e:
                log.warning(f"[{self.agent_id}] WorldModelTrainer state not saved: {e}")

        capsule.model_state = model_state
        capsule.save(path)
        log.info(f"[{self.agent_id}] Saved to {path}")

    def load(self, path: str):
        from ai_core.brain_capsule import BrainCapsule

        capsule = BrainCapsule.load(path)

        self.personality = Personality.from_dict(capsule.personality)

        if capsule.emotion_snapshot:
            for emotion, value in capsule.emotion_snapshot.items():
                self.emotion.emotions[emotion] = value

        if capsule.memory_snapshot:
            for event in capsule.memory_snapshot:
                self.memory.remember(event, tags=event.get('tags', []))

        if capsule.language_state and hasattr(self.brain, 'language') and self.brain.language is not None:
            try:
                self.brain.language.load_state_dict(capsule.language_state)
                log.info(f"[{self.agent_id}] Language restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Language restore failed: {e}")

        saved = capsule.model_state or {}

        if self.policy and 'policy' in saved:
            try:
                self.policy.load_state_dict(saved['policy'])
                log.info(f"[{self.agent_id}] Policy restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Policy restore failed: {e}")

        if 'world_model' in saved:
            try:
                from ai_core.world_model import WorldModel
                wm_entry = saved['world_model']
                if isinstance(wm_entry, dict) and 'config' in wm_entry:
                    wm = WorldModel(wm_entry['config'])
                    wm.load_state_dict(wm_entry['state'])
                else:
                    if self.world_model is not None:
                        wm = WorldModel(self.world_model.config)
                        wm.load_state_dict(wm_entry, strict=False)
                    else:
                        raise ValueError(
                            "Legacy world model checkpoint but no config available."
                        )
                self.world_model = wm
                self.brain.set_world_model(wm)
                log.info(f"[{self.agent_id}] World model restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] World model restore failed: {e}")

        if 'vision' in saved and hasattr(self, 'vision') and self.vision is not None:
            try:
                self.vision.load_state_dict(saved['vision'])
                log.info(f"[{self.agent_id}] Vision vocab restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Vision restore failed: {e}")

        if 'reward_system' in saved and self.reward_system is not None:
            try:
                rs = saved['reward_system']
                if self.reward_system.use_rnd and 'rnd' in rs:
                    self.reward_system.rnd.load_state_dict(rs['rnd'])
                if self.reward_system.use_icm and 'icm' in rs:
                    self.reward_system.icm.load_state_dict(rs['icm'])
                log.info(f"[{self.agent_id}] RewardSystem (RND/ICM) restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] RewardSystem restore failed: {e}")

        # Bug #21 fix: restore EpisodicMemory replay buffer
        if 'episodic_memory' in saved and getattr(self, 'episodic_memory', None) is not None:
            try:
                em = saved['episodic_memory']
                self.episodic_memory.buffer.clear()
                self.episodic_memory.priorities.clear()
                for t in em.get('transitions', []):
                    self.episodic_memory.buffer.append(t)
                for p in em.get('priorities', []):
                    self.episodic_memory.priorities.append(p)
                log.info(
                    f"[{self.agent_id}] EpisodicMemory restored "
                    f"({len(self.episodic_memory.buffer)} transitions)"
                )
            except Exception as e:
                log.warning(f"[{self.agent_id}] EpisodicMemory restore failed: {e}")

        # Bug #22 fix: restore WorldModelTrainer progress
        if 'world_model_trainer' in saved and getattr(self, 'world_model_trainer', None) is not None:
            try:
                ts = saved['world_model_trainer']
                self.world_model_trainer.step_count = ts.get('step_count', 0)
                from collections import deque as _dq
                self.world_model_trainer.loss_history = _dq(
                    ts.get('loss_history', []), maxlen=1000
                )
                log.info(
                    f"[{self.agent_id}] WorldModelTrainer restored "
                    f"(step {self.world_model_trainer.step_count})"
                )
            except Exception as e:
                log.warning(f"[{self.agent_id}] WorldModelTrainer restore failed: {e}")

        self.step_count      = capsule.metadata.get('step_count',   0)
        self.custom_name     = capsule.metadata.get('custom_name',  self.custom_name)
        self.agent_type      = capsule.metadata.get('agent_type',   'npc')
        self.mode            = capsule.metadata.get('mode',         'autonomous')
        self.autonomous_mode = capsule.metadata.get('autonomous',   True)

        # FIX: restore god_type and re-integrate god controls.
        # Without this, a restarted god agent has god_type=None, the 18-dim
        # GodTransformerPolicy never initialises (policy falls back to 11-dim
        # random), and all god abilities are silently lost on restart.
        restored_god_type = capsule.metadata.get('god_type')
        if restored_god_type and not self.god_type:
            self.god_type = restored_god_type
            try:
                from ai_core.god_controls import integrate_god_controls
                integrate_god_controls(self)
                log.info(
                    f"[{self.agent_id}] God controls re-integrated "
                    f"for {restored_god_type} from brain capsule"
                )
            except Exception as e:
                log.warning(f"[{self.agent_id}] God controls restore failed: {e}")

        # Restore persisted ports if they were not explicitly set at init time.
        # This means a restarted agent always uses the same ports as the first
        # run, even if agents.json is briefly unavailable.
        if self._tcp_port == _TCP_PORT_DEFAULT:   # only override the fallback default
            saved_tcp = capsule.metadata.get('tcp_port', 0)
            if saved_tcp > 0:
                self._tcp_port     = saved_tcp
                self._backend_port = capsule.metadata.get(
                    'backend_port', saved_tcp + _WS_PORT_OFFSET
                )
                log.info(
                    f"[{self.agent_id}] Ports restored from brain: "
                    f"TCP {self._tcp_port} / WS {self._backend_port}"
                )

        if capsule.pregnancy_state is not None:
            self._pending_pregnancy = capsule.pregnancy_state
        else:
            self._pending_pregnancy = None

        log.info(f"[{self.agent_id}] Loaded from {path}")

    # =========================================================================
    # Neural stack
    # =========================================================================

    def integrate_neural_stack(self, force: bool = False):
        if self._neural_integrated and not force:
            return
        self._init_world_model()
        self._neural_integrated = True
        log.info(f"[{self.agent_id}] Neural stack integrated.")

    # =========================================================================
    # Mental simulation & internal thought
    # =========================================================================

    def imagine_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        if self.world_model is None:
            return {'type': 'thought_flow', 'label': 'No World Model'}
        try:
            workspace = getattr(self.world_model, 'mental_workspace', None)
            if workspace:
                objects = [
                    {
                        'id':         obj.get('id'),
                        'type':       obj.get('type', 'unknown'),
                        'position':   obj.get('position', [0, 0, 0]),
                        'properties': obj.get('properties', {}),
                    }
                    for obj in workspace.objects
                ]
                return {'type': 'world_model', 'label': 'Mental Simulation',
                        'objects': objects}
        except Exception as e:
            log.error(f"Mental simulation error: {e}")
        return {'type': 'thought_flow', 'label': 'Thinking...'}

    def generate_internal_thought(self,
                                   context: Dict[str, Any]) -> Optional[str]:
        try:
            if not hasattr(self.brain, 'language') or self.brain.language is None:
                return None
            if self.brain.language.language_stage < 1:
                return None
            traits = self.personality.traits
            p      = (1.0 - traits.get('sociability', 0.5) +
                      traits.get('openness', 0.5)) / 2.0
            if np.random.rand() > p:
                return None
            internal = self.brain.language.generate_speech(context)
            if internal and internal.strip():
                self.thoughts.append({"timestamp": time.time(),
                                       "thought": internal})
                if len(self.thoughts) > 100:
                    self.thoughts = self.thoughts[-100:]
                return internal
        except Exception as e:
            log.error(f"Internal thought error: {e}")
        return None

    # =========================================================================
    # Cleanup
    # =========================================================================

    async def shutdown(self):
        if self.cognitive_loop:
            await self.stop_autonomous_mode()
        if hasattr(self, 'vision') and self.vision is not None:
            try:
                self.vision.stop()
            except Exception:
                pass
        brain_path = Path(
            self.metadata.get('brain_save_path',
                               f"data/brains/{self.agent_id}/brain.pcap")
        )
        brain_path.parent.mkdir(parents=True, exist_ok=True)
        self.save(str(brain_path))
        if hasattr(self.memory, 'close'):
            self.memory.close()
        log.info(f"[{self.agent_id}] Shutdown complete")

    def initialize_policy(self, obs_space, action_space):
        if self.policy is not None:
            return
        if self.god_type:
            from rl.policy import GodTransformerPolicy
            from ai_core.god_controls import GodControlSystem
            import gymnasium as gym
            n_abilities = len(GodControlSystem(self.god_type).abilities)
            god_action_space = gym.spaces.Box(
                low=-1.0, high=1.0,
                shape=(GodTransformerPolicy.TOTAL_DIM,),
                dtype=np.float32,
            )
            self.policy = GodTransformerPolicy(
                observation_space=obs_space,
                action_space=god_action_space,
                lr_schedule=lambda _: 3e-4,
                n_abilities=n_abilities,
            )
            log.info(
                f"[{self.agent_id}] GodTransformerPolicy initialised "
                f"({n_abilities} abilities, 18-dim action space)"
            )
        else:
            from rl.policy import TransformerPolicy
            self.policy = TransformerPolicy(
                observation_space=obs_space,
                action_space=action_space,
                lr_schedule=lambda _: 3e-4,
            )
            log.info(f"[{self.agent_id}] TransformerPolicy initialised (13-dim)")

    def decide(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        if self.policy is None:
            # FIX: was 11-dim random — must match BASE_DIM=13 for NPCs, 18 for gods
            base = np.clip(np.random.randn(13) * 0.3, -1.0, 1.0)
            return np.concatenate([base, np.zeros(5)]) if self.god_type else base  # 18-dim god fallback
        with torch.no_grad():
            obs_t  = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
            action = self.policy._predict(obs_t, deterministic=deterministic)
            return action.squeeze().cpu().numpy()

    def act(self, action: np.ndarray) -> dict:
        """
        Convert a 13-dim policy output to a controls dict.

        FIX DIM-01 / INT-02: old code clipped to [:11], silently dropping
        sprint (dim 11) and hotbar_slot (dim 12) for every NPC agent.
        TransformerPolicy outputs 13 dims (BASE_DIM = 13) — all must be used.
        """
        # Keep full array in last_action so ICM gets correct dims
        self.last_action = action
        self.step_count += 1

        a = np.clip(action[:13], -1.0, 1.0)

        # hotbar_slot: dim 12 > -0.5 → active slot [0..8]; ≤ -0.5 → no change
        raw_slot = float(a[12]) if len(a) > 12 else -1.0
        hotbar   = (max(0, min(8, int(round((raw_slot + 1.0) / 2.0 * 8.0))))
                    if raw_slot > -0.5 else None)

        controls = {
            'move_forward': float(a[0]),
            'move_strafe':  float(a[1]),
            'jump':         bool(a[2] > 0.5),
            'sneak':        bool(a[3] > 0.5),
            'attack':       bool(a[4] > 0.5),
            'use':          bool(a[5] > 0.5),
            'drop':         bool(a[6] > 0.5),
            'open_inv':     bool(a[7] > 0.5),
            'swap_hand':    bool(a[8] > 0.5),
            'yaw_delta':    float(a[9]  * 2.0),
            'pitch_delta':  float(a[10] * 1.2),
            'sprint':       bool(a[11] > 0.5) if len(a) > 11 else False,
            'hotbar_slot':  hotbar,
        }
        return controls

    def act_god(self, action: np.ndarray) -> dict:
        # act() handles dims 0-10 (movement + camera).
        # Dims 11-12 (sprint, hotbar_slot) are part of the base 13-dim layout
        # but act() clips to [:11], so we handle them here.
        controls = self.act(action)

        # Sprint — dim 11
        if len(action) >= 12 and float(action[11]) > 0.5:
            controls['sprint'] = True

        # Hotbar slot — dim 12  (maps [-1,1] → slot 0-8, sentinel <= -0.5 = no change)
        if len(action) >= 13:
            raw_slot = float(action[12])
            if raw_slot > -0.5:
                controls['hotbar_slot'] = max(0, min(8,
                    int(round((raw_slot + 1.0) / 2.0 * 8.0))))

        # ── God ability dims (GodTransformerPolicy.TOTAL_DIM = 18) ──────────
        # dim 13: trigger_flag  (>= 0.5 = use an ability this step)
        # dim 14: ability_idx   (0 … n_abilities-1)
        # dim 15: param1
        # dim 16: param2
        # dim 17: param3
        # FIX B-03: old code read dim 11 as trigger and dim 12 as ability_idx,
        # which are sprint and hotbar_slot respectively — abilities never fired.
        god_ability = None
        god_params  = None

        if (hasattr(self, 'god_controls') and
                len(action) >= 18 and
                float(action[13]) >= 0.5):
            names       = self.god_controls.ability_names()
            ability_idx = int(round(float(action[14])))
            if 0 <= ability_idx < len(names):
                god_ability = names[ability_idx]
                god_params  = {
                    'param1': float(action[15]),
                    'param2': float(action[16]),
                    'param3': float(action[17]),
                }
                self.use_god_ability(god_ability, outcome=None, **god_params)
                log.debug(
                    f"[{self.agent_id}] 🔥 God ability: {god_ability} "
                    f"p=({god_params['param1']:.2f},"
                    f"{god_params['param2']:.2f},"
                    f"{god_params['param3']:.2f})"
                )

        if god_ability:
            controls['god_ability'] = god_ability
            controls['god_params']  = god_params
        return controls


# =============================================================================
# Standalone runtime
# =============================================================================

async def run_server(port: int = 8000):
    global global_server
    config        = uvicorn.Config(app, host="127.0.0.1", port=port,
                                   log_level="warning")
    global_server = uvicorn.Server(config)
    await global_server.serve()


async def run_standalone_agent(
    agent_id:           str,
    mode:               str                        = 'autonomous',
    load_brain:         Optional[str]              = None,
    brain_save_path:    Optional[str]              = None,
    duration:           Optional[float]            = None,
    chat_interface:     bool                       = False,
    god_type:           Optional[str]              = None,
    gender:             Optional[Any]              = None,
    personality_traits: Optional[Dict[str, float]] = None,
    spawn_pos:          Optional[tuple]            = None,
    genesis_ancestor:   bool                       = False,
    port:               int                        = 0,    # WS backend port
    tcp_port:           int                        = 0,    # TCP action-server port
    custom_name:        Optional[str]              = None,
):
    global global_agent

    # If port is still 0 here (standalone / test usage), derive sensible
    # defaults so the agent starts without main.py providing them.
    if port <= 0 and tcp_port <= 0:
        tcp_port = _TCP_PORT_DEFAULT
        port     = tcp_port + _WS_PORT_OFFSET
    elif port <= 0:
        port = tcp_port + _WS_PORT_OFFSET
    elif tcp_port <= 0:
        tcp_port = max(_TCP_PORT_DEFAULT, port - _WS_PORT_OFFSET)

    print(f"\n{'='*70}")
    print(f"  🤖 STARTING AGENT: {agent_id}")
    print(f"  TCP action-server : {tcp_port}")
    print(f"  WS backend port   : {port}")
    print(f"{'='*70}")

    agent = NPCAgent(
        agent_id=agent_id,
        autonomous=(mode == 'autonomous'),
        mode=mode,
        god_type=god_type,
        gender=gender,
        persona_traits=personality_traits,
        custom_name=custom_name,
        backend_port=port,
        tcp_port=tcp_port,
    )

    if brain_save_path:
        agent.metadata['brain_save_path'] = brain_save_path
    if spawn_pos:
        agent.metadata['spawn_pos'] = spawn_pos
    if genesis_ancestor:
        agent.metadata['genesis_ancestor'] = genesis_ancestor

    global_agent = agent

    # FIX #4/#13: Save the initial brain capsule BEFORE starting the server.
    # Previously server_task was created first — a client could connect before
    # brain.pcap existed, causing load() failures in the /status endpoint.
    # global_agent is already set above so no null-deref risk on first request.
    initial_path = Path(brain_save_path or f"data/brains/{agent_id}/brain.pcap")
    initial_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save(str(initial_path))

    server_task = asyncio.create_task(run_server(port=port))

    if load_brain and Path(load_brain).exists():
        try:
            agent.load(load_brain)
            print(f"✅ Brain loaded from {load_brain}")
        except Exception as e:
            print(f"⚠️  Brain load failed: {e}")

    print(f"\n📊 Agent Info:")
    print(f"  Personality: {agent.personality.to_dict()}")
    print(f"  Memory: {agent.memory.get_stats()['backend']}")
    if hasattr(agent.brain, 'language') and agent.brain.language is not None:
        print(f"  Language stage: {agent.brain.language.language_stage}")
    print(f"  Memory events: {len(agent.memory.events)}")
    print(f"\n  🌐 API: http://127.0.0.1:{port}")
    print(f"  🔌 WS:  ws://127.0.0.1:{port}/ws")
    print(f"  🎮 TCP: 127.0.0.1:{tcp_port}  (Java TCPServer)\n")

    if mode == 'autonomous':
        await agent.start_autonomous_mode()
    elif mode == 'minecraft':
        # Start the TCP-driven action loop immediately.
        # This sends actions over TCP regardless of WebSocket state,
        # so the agent controls the body as soon as TCPServer accepts the connection.
        asyncio.ensure_future(run_tcp_action_loop(agent, agent_id, loop_hz=20.0))

        # ── UltimMC presence check ────────────────────────────────────────
        # When the agent runs inside its own packaged exe, UltimMC is bundled
        # alongside it (launched by main.py _auto_package_agent).  If it is
        # NOT present the agent is being run in isolation (e.g. dev mode)
        # without a Minecraft client — log clearly and suggest alternatives.
        ultimmc_path = Path(sys.argv[0]).parent / "UltimMC" / "bin" / "UltimMC"
        if not ultimmc_path.exists():
            log.warning(
                "\n"
                "╔══════════════════════════════════════════════════════════════╗\n"
                "║  ⚠️  UltimMC NOT FOUND — Minecraft client will not launch  ║\n"
                "║                                                              ║\n"
                "║  Expected path: %s\n"
                "║                                                              ║\n"
                "║  This agent was started in minecraft mode but has no        ║\n"
                "║  bundled UltimMC launcher.  Options:                        ║\n"
                "║    • Let main.py launch the agent (auto-packages UltimMC)   ║\n"
                "║    • Re-run with --mode autonomous (no Minecraft needed)    ║\n"
                "║    • Re-run with --mode chat       (text-only interface)    ║\n"
                "║                                                              ║\n"
                "║  The agent will still start and wait for a mod connection.  ║\n"
                "║  If one arrives it will work; otherwise actions are no-ops. ║\n"
                "╚══════════════════════════════════════════════════════════════╝",
                ultimmc_path,
            )

        # Wait for the Minecraft mod connection regardless of UltimMC presence.
        # When launched by main.py, Minecraft is started separately after packaging
        # and the mod will connect here once the player joins the server.
        # The 300s timeout covers the worst-case where packaging takes >10 minutes.
        print("✅ Minecraft mode — waiting for mod connection (up to 300s)...")
        try:
            connected = await asyncio.wait_for(
                agent.minecraft_client.wait_for_connection(timeout=300.0),
                timeout=305.0,
            )
            if connected:
                print("✅ Minecraft connected!")
            else:
                print("⚠️  Minecraft mod not yet connected — will retry when mod joins.")
        except asyncio.TimeoutError:
            print("⚠️  Connection wait timed out — continuing anyway.")

    start_time = time.time()
    chat_task  = asyncio.create_task(chat_loop(agent)) if chat_interface else None

    _last_periodic_save = time.time()
    try:
        while True:
            if duration and (time.time() - start_time) >= duration:
                break
            # FIX: old code used % 300 which skips when asyncio.sleep(1) drifts
            # past the exact second boundary — guaranteed under event loop load.
            if time.time() - _last_periodic_save >= 300:
                _last_periodic_save = time.time()
                sp = Path(
                    agent.metadata.get('brain_save_path',
                                       f"data/brains/{agent_id}/brain.pcap")
                )
                sp.parent.mkdir(parents=True, exist_ok=True)
                try:
                    agent.save(str(sp))
                    log.info(f"[{agent_id}] ⏱️  Periodic brain save: {sp}")
                except Exception as _se:
                    log.warning(f"[{agent_id}] Periodic save failed: {_se}")
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping...")
    finally:
        if chat_task:
            chat_task.cancel()
        if global_server:
            global_server.should_exit = True
            try:
                await asyncio.wait_for(global_server.shutdown(), timeout=5.0)
            except Exception:
                pass
        await agent.shutdown()
        print(f"\n✅ {agent_id} stopped. Runtime: {time.time()-start_time:.1f}s")


async def chat_loop(agent):
    print("\n💬 Chat Mode (Ctrl+C to exit)\n" + "=" * 70)
    while True:
        try:
            user_input = await asyncio.to_thread(input, "You: ")
            if not user_input.strip():
                continue
            ctx = {
                'health':           agent.health,
                'hunger':           agent.hunger,
                'emotions':         agent.emotion.snapshot(),
                'dominant_emotion': agent.emotion.dominant_emotion(),
            }
            response = agent.brain.process_language_input(user_input, ctx)
            print(f"{agent.agent_id}: {response or '[Learning...]'}")
        except EOFError:
            break
        except Exception as e:
            log.error(f"Chat error: {e}")


# =============================================================================
# Executable generator
# =============================================================================

class AgentExecutableGenerator:
    """Generate PyInstaller executables for dynamically spawned agents."""

    def __init__(self, output_dir: str = "build/agents/dist"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.build_temp = Path("build/agents/build_temp")
        self.build_temp.mkdir(parents=True, exist_ok=True)

    def generate_executable(self,
                             agent_id:           str,
                             agent_type:         Literal['npc', 'god'] = 'npc',
                             god_type:           Optional[str]          = None,
                             gender:             Optional[GenderType]   = None,
                             personality_traits: Optional[Dict]         = None
                             ) -> Optional[Path]:
        if gender is None:
            gender = assign_god_gender() if agent_type == 'god' else assign_npc_gender()

        wrapper_script   = self.build_temp / f"{agent_id}_wrapper.py"
        personality_json = json.dumps(personality_traits or {})
        god_arg          = f" --god-type {god_type}" if god_type else ""

        wrapper_script.write_text(f'''
import sys
from ai_core.agent import main
sys.argv = [sys.argv[0],
    "--agent-id", "{agent_id}", "--mode", "autonomous",
    "--gender", "{gender}", "--personality", "{personality_json}"{god_arg}]
if __name__ == "__main__":
    main()
''')

        exe_name = (
            f"DW_Agent_{agent_id.replace(' ', '_')}"
            if agent_type == 'npc'
            else f"DW_God_{agent_id.replace(' ', '_')}"
        )

        try:
            import PyInstaller.__main__
        except ImportError:
            log.error("PyInstaller not installed.")
            return None

        PyInstaller.__main__.run([
            '--onefile', f'--name={exe_name}',
            f'--distpath={self.output_dir}',
            f'--buildpath={self.build_temp}',
            f'--specpath={self.build_temp}',
            '--hidden-import=torch', '--hidden-import=numpy',
            '--hidden-import=fastapi', '--hidden-import=uvicorn',
            '--hidden-import=ai_core', '--collect-all=ai_core',
            '--collect-all=torch', '--console',
            str(wrapper_script),
        ])

        exe_path = self.output_dir / exe_name
        if exe_path.exists():
            log.info(f"✅ Executable: {exe_path}")
            return exe_path
        log.error(f"❌ Executable not found: {exe_path}")
        return None

    def launch_executable(self,
                           exe_path:     Path,
                           port:         int           = 0,
                           tcp_port:     int           = 0,
                           minecraft:    bool          = False,
                           ultimmc_path: Optional[str] = None
                           ) -> Optional[subprocess.Popen]:
        if not exe_path.exists():
            log.error(f"Not found: {exe_path}")
            return None
        cmd = [str(exe_path)]
        if port:
            cmd += ['--port', str(port)]
        if tcp_port:
            cmd += ['--tcp-port', str(tcp_port)]
        if minecraft:
            cmd.append('--minecraft')
            if ultimmc_path:
                cmd.extend(['--ultimmc-path', ultimmc_path])
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            log.info(f"✅ Launched PID {proc.pid}")
            return proc
        except Exception as e:
            log.error(f"Launch failed: {e}")
            return None


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Divine World Standalone Agent")

    parser.add_argument('--agent-id',    default='demo')
    parser.add_argument('--port',        type=int, default=0,
                        help='WebSocket backend port this agent listens on '
                             '(set by main.py to tcp_port + 10000)')
    parser.add_argument('--tcp-port',    type=int, default=0,
                        help='TCP action-server port (from agents.json, '
                             'starts at 11401; set by main.py via --tcp-port)')
    parser.add_argument('--mode',        choices=['autonomous', 'chat', 'minecraft'],
                        default='autonomous')
    parser.add_argument('--god-type',
                        choices=['ender_dragon', 'wither', 'warden', 'oracle',
                                 'elder_guardian', 'creaking'])
    parser.add_argument('--load-brain')
    parser.add_argument('--brain-save-path')
    parser.add_argument('--duration',        type=float)
    parser.add_argument('--chat',            action='store_true')
    parser.add_argument('--log-level',
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO')
    parser.add_argument('--gender',          choices=['male', 'female', 'dual'])
    parser.add_argument('--personality')
    parser.add_argument('--spawn-x',         type=float)
    parser.add_argument('--spawn-y',         type=float)
    parser.add_argument('--spawn-z',         type=float)
    parser.add_argument('--genesis-ancestor')
    parser.add_argument('--custom-name')

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s',
    )

    signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))

    personality_traits = None
    if args.personality:
        try:
            personality_traits = json.loads(args.personality)
        except json.JSONDecodeError:
            print(f"⚠️  Invalid personality JSON: {args.personality}")

    try:
        asyncio.run(run_standalone_agent(
            agent_id          = args.agent_id,
            mode              = args.mode,
            load_brain        = args.load_brain,
            brain_save_path   = args.brain_save_path,
            duration          = args.duration,
            chat_interface    = args.chat,
            god_type          = args.god_type,
            gender            = args.gender,
            personality_traits= personality_traits,
            spawn_pos         = (args.spawn_x, args.spawn_y, args.spawn_z)
                                 if args.spawn_x is not None else None,
            genesis_ancestor  = args.genesis_ancestor == 'true'
                                 if args.genesis_ancestor else False,
            port              = args.port,
            tcp_port          = args.tcp_port,
            custom_name       = args.custom_name,
        ))
    except KeyboardInterrupt:
        print("\n✅ Agent stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()