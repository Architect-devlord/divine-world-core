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
from ai_core.communication_protocol import handle_agent_websocket
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
        # Temporary instance just for enumeration (no agent required)
        class _Stub:
            pass
        rt = ControllerRuntime.__new__(ControllerRuntime)
        rt.agent = global_agent
        cameras    = rt.list_cameras()    if hasattr(rt, 'list_cameras')    else []
        microphones= rt.list_microphones() if hasattr(rt, 'list_microphones') else []
        return {
            "status":  "success",
            "devices": {
                "cameras":     cameras,
                "microphones": microphones,
            },
        }
    except Exception as e:
        log.error(f"detect-devices error: {e}")
        return {"status": "error", "devices": {"cameras": [], "microphones": []}}


@app.post("/api/controller/activate")
async def activate_controller(data: Dict[str, Any]):
    """
    Activate DWController with the permissions the user granted in the UI.
    Body: {agent_id, permissions: [str], permissionSettings: {camera,microphone,filesystem,network},
           devices: {camera: int, microphone: int}}
    """
    if not global_agent:
        return {"status": "error", "message": "Agent not running"}

    ctrl = _get_controller()
    if ctrl is None:
        return {"status": "error", "message": "ControllerRuntime unavailable"}

    perm_settings = data.get("permissionSettings", {})
    devices       = data.get("devices", {})

    # Convert UI permission keys → ControllerRuntime.grant_permissions() format
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
    """Stop all controller activity and release hardware."""
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
    """Return current controller state and activity stats."""
    ctrl = _get_controller()
    if ctrl is None:
        return {
            "active":            False,
            "camera_active":     False,
            "microphone_active": False,
            "permissions":       {},
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
# NPCAgent
# =============================================================================

class NPCAgent:
    """
    Fully autonomous NPC / God agent with standalone runtime.
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
                 custom_name:    Optional[str]              = None):

        self.agent_id        = agent_id
        self.custom_name     = custom_name
        self.autonomous_mode = autonomous
        self.mode            = mode
        self.god_type        = god_type

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

        self.thoughts = [
            {"timestamp": time.time(), "thought": "Initializing agent systems..."},
            {"timestamp": time.time(), "thought": "Memory system online"},
            {"timestamp": time.time(), "thought": "Ready to interact and learn"},
        ]

        # ── Subsystem init (order matters) ────────────────────────────────

        # 1. Reward system — eager, so brain.reward_system is never None
        #    during autonomous operation
        self.reward_system: Optional[RewardSystem] = None
        self.initialize_reward_system()

        # 2. World model — calls brain.set_world_model() internally
        self._init_world_model()

        # 3. Vision — full pipeline via add_vision_to_agent()
        self._init_vision()

        # 4. Audio
        self._init_audio_processor()

        # 5. Cognitive loop
        self.cognitive_loop = None
        if self.autonomous_mode:
            self._init_cognitive_loop()

        log.info(f"NPCAgent init: {agent_id} (mode={mode}, autonomous={autonomous})")

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
                tcp_host='127.0.0.1', tcp_port=8765,
                ws_host='127.0.0.1',  ws_port=11400,
                prefer_tcp=True,
            )
            log.info(f"[{agent_id}] Minecraft client initialised")
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
        from ai_core.brain_language import add_language_to_brain
        add_language_to_brain(self.brain)
        log.info(f"[{self.agent_id}] Language intelligence initialised")

    def _init_cognitive_loop(self):
        self.cognitive_loop = CognitiveLoop(agent=self, loop_interval=0.5)
        log.info(f"[{self.agent_id}] Cognitive loop initialised")

    def _init_world_model(self):
        """
        Create WorldModel and wire it into BrainCore via set_world_model().
        No monkey-patching of brain.evaluate_event.
        """
        try:
            from ai_core.world_model import (
                WorldModel, WorldModelConfig,
                WorldModelReplayBuffer, WorldModelTrainer,
            )
            config       = WorldModelConfig(
                device='cuda' if torch.cuda.is_available() else 'cpu'
            )
            wm           = WorldModel(config)
            replay_buffer = WorldModelReplayBuffer(
                capacity=50_000, sequence_length=64
            )
            trainer      = WorldModelTrainer(wm, replay_buffer, batch_size=16)

            self.world_model         = wm
            self.world_model_buffer  = replay_buffer
            self.world_model_trainer = trainer

            # ← Clean wiring: BrainCore owns the connection
            self.brain.set_world_model(wm)

            log.info(f"[{self.agent_id}] WorldModel attached to BrainCore")
        except Exception as e:
            log.warning(f"[{self.agent_id}] World model not available: {e}")

    def _init_vision(self):
        """
        Attach full VisionAdapter pipeline (feature extraction, online vocab,
        Minecraft frame hook, cognitive loop patch).
        Replaces the old inline VisionAdapter() stub inside observe().
        """
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
    # Reward system — eager init
    # =========================================================================

    def initialize_reward_system(self,
                                  obs_dim:    int = 50,
                                  action_dim: int = 11):
        """
        Initialise the RewardSystem and wire it into BrainCore.

        Called eagerly in __init__ so brain.reward_system is never None
        during autonomous operation.  Safe to call again (no-op if already
        initialised).
        """
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
        """Convert raw observation dict to fixed-size feature vector."""
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
        obs_parts.append(len(raw_observation.get('entities', [])) / 10.0)
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

        obs_array    = np.array(obs_parts[:50], dtype=np.float32)
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
        """
        Process a visual frame through the VisionAdapter pipeline.

        If add_vision_to_agent() has been called (normal path), this method
        is already patched by vision.py to run the full pipeline and return
        a CHW float32 tensor.

        This fallback implementation handles the rare case where vision was
        not available at init time.
        """
        info = info or {}
        try:
            # vision.py patches this method during _init_vision()
            # If we reach here the patch didn't happen — do a minimal fallback
            if image is not None:
                processed = image.astype(np.float32).transpose(2, 0, 1) / 255.0
            else:
                processed = np.zeros((3, 84, 84), dtype=np.float32)

            self.memory.remember({
                'type':             'visual_observation',
                'image_shape':      list(image.shape) if image is not None else [],
                'description':      info.get('description', 'Visual observation'),
                'source':           info.get('source', 'unknown'),
                'timestamp':        time.time(),
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
        """Learn from a single (obs, action, next_obs, outcome) transition."""
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
        }
        if hasattr(self.brain, 'language'):
            info['language'] = self.brain.get_language_progress()
        if self.cognitive_loop:
            info['cognitive_status'] = self.cognitive_loop.get_status()
        info['memory_stats'] = self.memory.get_stats()
        if self.client_process:
            info['backend_url'] = self.client_process.backend_url
            info['server']      = self.client_process.server_addr
        if self.metadata:
            info['metadata'] = self.metadata

        # Vision stats if available
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

        # ── URL detection: store in memory, don't auto-queue ──────────────
        # The agent decides whether to browse via brain.should_browse().
        # Forcing URLs into the queue would be the USER controlling browsing,
        # not the agent. Instead we store mentioned URLs as memory events so
        # the cognitive loop can notice them when it's curious enough.
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
                # Only queue if explicitly asked ("can you check..." / "look at...")
                trigger_words = ('check', 'look', 'browse', 'visit', 'read',
                                 'open', 'go to', 'see', 'find')
                if any(w in message.lower() for w in trigger_words):
                    self.web_browser.add_url_to_queue(url)
                    log.info(f"[{self.agent_id}] URL queued by user request: {url}")

        response = f"I am {self.agent_id}. You said: {message}"
        try:
            if (hasattr(self.brain, 'language') and
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
        if hasattr(self.brain, 'language'):
            language_state = self.brain.language.state_dict()

        metadata = {
            'agent_id':   self.agent_id,
            'custom_name':self.custom_name,
            'agent_type': self.agent_type,
            'mode':       self.mode,
            'gender':     self.personality.gender,
            'step_count': self.step_count,
            'saved_at':   time.time(),
            'autonomous': self.autonomous_mode,
        }
        metadata.update(self.metadata)

        # Serialise pregnancy state if the breeding system is tracking this agent
        pregnancy_state = None
        breeding_sys = getattr(self, '_breeding_system', None)
        if breeding_sys is not None:
            # Use get_serialisable_pregnancy() not get_pregnancy_status() —
            # the status method includes ephemeral fields (days_remaining etc)
            # that are meaningless after a restart and would confuse from_dict().
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

        # Policy
        if self.policy:
            try:
                model_state['policy'] = {
                    k: v.cpu() if isinstance(v, torch.Tensor) else v
                    for k, v in self.policy.state_dict().items()
                }
            except Exception as e:
                log.error(f"[{self.agent_id}] Failed to serialize policy: {e}")

        # World model — store both config and weights so load() round-trips
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

        # Vision vocab + feature extractor
        if hasattr(self, 'vision') and self.vision is not None:
            try:
                model_state['vision'] = self.vision.state_dict()
            except Exception as e:
                log.warning(f"[{self.agent_id}] Vision state not saved: {e}")

        # RewardSystem — RND + ICM curiosity networks.
        # Without this they reset on every restart, losing all novelty calibration.
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

        capsule.model_state = model_state
        capsule.save(path)
        log.info(f"[{self.agent_id}] Saved to {path}")

    def load(self, path: str):
        from ai_core.brain_capsule import BrainCapsule

        capsule = BrainCapsule.load(path)

        # Personality
        self.personality = Personality.from_dict(capsule.personality)

        # Emotions
        if capsule.emotion_snapshot:
            for emotion, value in capsule.emotion_snapshot.items():
                self.emotion.emotions[emotion] = value

        # Memory
        if capsule.memory_snapshot:
            for event in capsule.memory_snapshot:
                self.memory.remember(event, tags=event.get('tags', []))

        # Language
        if capsule.language_state and hasattr(self.brain, 'language'):
            try:
                self.brain.language.load_state_dict(capsule.language_state)
                log.info(f"[{self.agent_id}] Language restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Language restore failed: {e}")

        saved = capsule.model_state or {}

        # Policy
        if self.policy and 'policy' in saved:
            try:
                self.policy.load_state_dict(saved['policy'])
                log.info(f"[{self.agent_id}] Policy restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Policy restore failed: {e}")

        # World model — use stored config so constructor args match
        if 'world_model' in saved:
            try:
                from ai_core.world_model import WorldModel
                wm_entry = saved['world_model']

                if isinstance(wm_entry, dict) and 'config' in wm_entry:
                    # New format: {config, state}
                    config = wm_entry['config']
                    wm     = WorldModel(config)
                    wm.load_state_dict(wm_entry['state'])
                else:
                    # Legacy format: raw state_dict saved directly
                    # Re-use existing config if world model is already attached
                    if self.world_model is not None:
                        wm = WorldModel(self.world_model.config)
                        wm.load_state_dict(wm_entry, strict=False)
                    else:
                        raise ValueError(
                            "Legacy world model checkpoint but no config available. "
                            "Re-initialise the agent before loading."
                        )

                self.world_model = wm
                self.brain.set_world_model(wm)
                log.info(f"[{self.agent_id}] World model restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] World model restore failed: {e}")

        # Vision vocab
        if 'vision' in saved and hasattr(self, 'vision') and self.vision is not None:
            try:
                self.vision.load_state_dict(saved['vision'])
                log.info(f"[{self.agent_id}] Vision vocab restored.")
            except Exception as e:
                log.warning(f"[{self.agent_id}] Vision restore failed: {e}")

        # RewardSystem — restore RND + ICM so curiosity calibration survives restarts
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

        # Metadata
        self.step_count    = capsule.metadata.get('step_count', 0)
        self.custom_name   = capsule.metadata.get('custom_name', self.custom_name)
        self.agent_type    = capsule.metadata.get('agent_type', 'npc')
        self.mode          = capsule.metadata.get('mode', 'autonomous')
        self.autonomous_mode = capsule.metadata.get('autonomous', True)

        # Stash pregnancy state so the breeding system can re-register it
        # after load() returns.  The breeding system calls agent.resume_pregnancy()
        # when it re-attaches to the agent.
        if capsule.pregnancy_state is not None:
            self._pending_pregnancy = capsule.pregnancy_state
        else:
            self._pending_pregnancy = None

        log.info(f"[{self.agent_id}] Loaded from {path}")

    # =========================================================================
    # Neural stack (manual integration hook kept for external callers)
    # =========================================================================

    def integrate_neural_stack(self, force: bool = False):
        """Re-run world model init. No-op if already integrated."""
        if self._neural_integrated and not force:
            return
        self._init_world_model()
        self._neural_integrated = True
        log.info(f"[{self.agent_id}] Neural stack integrated.")

    # =========================================================================
    # Mental simulation & internal thought
    # =========================================================================

    def imagine_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Called by cognitive loop when it decides to visualise imagination.
        Returns data for frontend Mental Matrix widget.
        """
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
        """Generate internal monologue when cognitive loop requests it."""
        try:
            if not hasattr(self.brain, 'language'):
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
        """Gracefully stop the agent — saves brain, stops cognitive loop and vision."""
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
        """
        Create the appropriate policy for this agent type.

        NPC agents  → TransformerPolicy (11-dim action space)
        God agents  → GodTransformerPolicy (16-dim action space)
                      n_abilities is derived from the god's ability set so
                      the policy head exactly matches the action choices.
        """
        if self.policy is not None:
            return

        if self.god_type:
            from rl.policy import GodTransformerPolicy
            from ai_core.god_controls import GodControlSystem
            import gymnasium as gym

            n_abilities = len(GodControlSystem(self.god_type).abilities)

            # Build a 16-dim Box action space for the god policy
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
                f"({n_abilities} abilities, 16-dim action space)"
            )
        else:
            from rl.policy import TransformerPolicy
            self.policy = TransformerPolicy(
                observation_space=obs_space,
                action_space=action_space,
                lr_schedule=lambda _: 3e-4,
            )
            log.info(f"[{self.agent_id}] TransformerPolicy initialised (11-dim)")

    def decide(self, obs: np.ndarray,
               deterministic: bool = False) -> np.ndarray:
        """
        Run policy forward pass. Returns 11-dim for NPCs, 16-dim for gods.
        The extra 5 dims for gods are handled by act_god().
        """
        if self.policy is None:
            # Fallback: random base action; gods get zeros for ability dims
            base = np.clip(np.random.randn(11) * 0.3, -1.0, 1.0)
            return np.concatenate([base, np.zeros(5)]) if self.god_type else base

        with torch.no_grad():
            obs_t  = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
            action = self.policy._predict(obs_t, deterministic=deterministic)
            return action.squeeze().cpu().numpy()

    def act(self, action: np.ndarray) -> dict:
        """
        Convert a policy action array (dims 0-10) into a controls dict.

        Does NOT send directly to minecraft_client — the ActionFrame built
        in communication_protocol.handle_agent_websocket is the canonical
        send path. Keeping act() as a pure converter avoids double-sends
        for god agents where act_god() calls act() internally.
        """
        action   = np.clip(action[:11], -1.0, 1.0)
        controls = {
            'move_forward': float(action[0]),
            'move_strafe':  float(action[1]),
            'jump':         bool(action[2] > 0.5),
            'sneak':        bool(action[3] > 0.5),
            'attack':       bool(action[4] > 0.5),
            'use':          bool(action[5] > 0.5),
            'drop':         bool(action[6] > 0.5),
            'open_inv':     bool(action[7] > 0.5),
            'swap_hand':    bool(action[8] > 0.5),
            'yaw_delta':    float(action[9]  * 2.0),
            'pitch_delta':  float(action[10] * 1.2),
        }
        self.last_action  = action
        self.step_count  += 1
        return controls

    def act_god(self, action: np.ndarray) -> dict:
        """
        Execute a 16-dim god action.

        1. Converts dims 0-10 → movement controls dict via act().
        2. If dim 11 (trigger_flag) >= 0.5, reads the ability index from
           dim 12, selects the ability name, and calls use_god_ability().
        3. Adds god_ability + god_params to the returned dict so
           communication_protocol.py can include them in the ActionFrame
           that goes to the Minecraft mod.

        use_god_ability() routes the outcome through the RewardSystem when
        the mod responds. It does NOT send to minecraft_client directly —
        the ActionFrame is the canonical send path.
        """
        controls = self.act(action)   # pure conversion, no client send

        god_ability = None
        god_params  = None

        if (hasattr(self, 'god_controls') and
                len(action) >= 16 and
                float(action[11]) >= 0.5):

            names       = self.god_controls.ability_names()
            ability_idx = int(round(float(action[12])))

            if 0 <= ability_idx < len(names):
                god_ability = names[ability_idx]
                god_params  = {
                    'param1': float(action[13]),
                    'param2': float(action[14]),
                    'param3': float(action[15]),
                }
                # Dispatch through reward-system-aware API.
                # outcome=None here — updated when the mod responds.
                # The ability is also sent to the mod via the ActionFrame
                # (god_ability / god_params fields), not via minecraft_client
                # directly, so we pass send_to_client=False if supported.
                self.use_god_ability(
                    god_ability,
                    outcome=None,
                    **god_params,
                )
                log.debug(
                    f"[{self.agent_id}] 🔥 God ability: {god_ability} "
                    f"p=({god_params['param1']:.2f},"
                    f"{god_params['param2']:.2f},"
                    f"{god_params['param3']:.2f})"
                )

        # Add to controls dict so ActionFrame builder can read them
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
    agent_id:          str,
    mode:              str                        = 'autonomous',
    load_brain:        Optional[str]              = None,
    brain_save_path:   Optional[str]              = None,
    duration:          Optional[float]            = None,
    chat_interface:    bool                       = False,
    god_type:          Optional[str]              = None,
    gender:            Optional[Any]              = None,
    personality_traits:Optional[Dict[str, float]] = None,
    spawn_pos:         Optional[tuple]            = None,
    genesis_ancestor:  bool                       = False,
    port:              int                        = 8000,
    custom_name:       Optional[str]              = None,
):
    global global_agent

    print(f"\n{'='*70}")
    print(f"  🤖 STARTING AGENT: {agent_id}")
    print(f"{'='*70}")

    agent = NPCAgent(
        agent_id=agent_id,
        autonomous=(mode == 'autonomous'),
        mode=mode,
        god_type=god_type,
        gender=gender,
        persona_traits=personality_traits,
        custom_name=custom_name,
    )

    if brain_save_path:
        agent.metadata['brain_save_path'] = brain_save_path
    if spawn_pos:
        agent.metadata['spawn_pos'] = spawn_pos
    if genesis_ancestor:
        agent.metadata['genesis_ancestor'] = genesis_ancestor

    global_agent = agent

    server_task = asyncio.create_task(run_server(port=port))

    # Initial save
    initial_path = Path(
        brain_save_path or f"data/brains/{agent_id}/brain.pcap"
    )
    initial_path.parent.mkdir(parents=True, exist_ok=True)
    agent.save(str(initial_path))

    if load_brain and Path(load_brain).exists():
        try:
            agent.load(load_brain)
            print(f"✅ Brain loaded from {load_brain}")
        except Exception as e:
            print(f"⚠️  Brain load failed: {e}")

    print(f"\n📊 Agent Info:")
    print(f"  Personality: {agent.personality.to_dict()}")
    print(f"  Memory: {agent.memory.get_stats()['backend']}")
    if hasattr(agent.brain, 'language'):
        print(f"  Language stage: {agent.brain.language.language_stage}")
    print(f"  Memory events: {len(agent.memory.events)}")
    print(f"\n  🌐 API: http://127.0.0.1:{port}")
    print(f"  🔌 WS:  ws://127.0.0.1:{port}/ws\n")

    if mode == 'autonomous':
        await agent.start_autonomous_mode()
    elif mode == 'minecraft':
        # Uvicorn (server_task) must already be running before we wait —
        # the Minecraft mod connects TO our WebSocket, so the server has to
        # be listening first.  server_task was created above this block and
        # asyncio will start scheduling it once we yield here (await).
        
        # Check if we're in a packaged environment with UltimMC available
        ultimmc_path = Path(sys.argv[0]).parent / "UltimMC" / "bin" / "UltimMC"
        if not getattr(sys, 'frozen', False):
            # If not frozen, check if UltimMC exists in the agent directory
            ultimmc_path = Path(sys.argv[0]).parent / "UltimMC" / "bin" / "UltimMC"
        
        if ultimmc_path.exists():
            print("✅ Minecraft mode — waiting for mod connection (up to 120s)...")
            print("   (UltimMC detected, Minecraft should launch automatically)")
            try:
                connected = await asyncio.wait_for(
                    agent.minecraft_client.wait_for_connection(timeout=120.0),
                    timeout=125.0,   # 5s grace over the inner timeout
                )
                if connected:
                    print("✅ Minecraft connected!")
                else:
                    print("⚠️  Minecraft mod not yet connected — agent will connect "
                          "when the mod joins the server.")
            except asyncio.TimeoutError:
                print("⚠️  Connection wait timed out — continuing without Minecraft.")
        else:
            print("ℹ️  Minecraft mode (no UltimMC launcher detected)")
            print("   Manual Minecraft setup required or auto-packager will enable it")
            # Don't wait for connection if UltimMC setup hasn't happened yet
            # The agent will still accept Minecraft connections when the mod joins
            await asyncio.sleep(2)  # Give backend time to start

    start_time = time.time()
    chat_task  = asyncio.create_task(chat_loop(agent)) if chat_interface else None

    try:
        while True:
            if duration and (time.time() - start_time) >= duration:
                break
            if int(time.time() - start_time) % 300 == 0:
                sp = Path(
                    agent.metadata.get('brain_save_path',
                                       f"data/brains/{agent_id}/brain.pcap")
                )
                sp.parent.mkdir(parents=True, exist_ok=True)
                agent.save(str(sp))
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
                             agent_id:          str,
                             agent_type:        Literal['npc', 'god'] = 'npc',
                             god_type:          Optional[str]          = None,
                             gender:            Optional[GenderType]   = None,
                             personality_traits:Optional[Dict]         = None
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
                           port:         int           = 8001,
                           minecraft:    bool          = False,
                           ultimmc_path: Optional[str] = None
                           ) -> Optional[subprocess.Popen]:
        if not exe_path.exists():
            log.error(f"Not found: {exe_path}")
            return None
        cmd = [str(exe_path), '--port', str(port)]
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

    parser.add_argument('--agent-id',         default='demo')
    parser.add_argument('--port',             type=int, default=8000)
    parser.add_argument('--mode',             choices=['autonomous','chat','minecraft'],
                        default='autonomous')
    parser.add_argument('--god-type',
                        choices=['ender_dragon','wither','warden','oracle',
                                 'elder_guardian','creaking'])
    parser.add_argument('--load-brain')
    parser.add_argument('--brain-save-path')
    parser.add_argument('--duration',         type=float)
    parser.add_argument('--chat',             action='store_true')
    parser.add_argument('--log-level',
                        choices=['DEBUG','INFO','WARNING','ERROR'], default='INFO')
    parser.add_argument('--gender',           choices=['male','female','dual'])
    parser.add_argument('--personality')
    parser.add_argument('--spawn-x',          type=float)
    parser.add_argument('--spawn-y',          type=float)
    parser.add_argument('--spawn-z',          type=float)
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