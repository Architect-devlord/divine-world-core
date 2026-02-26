# ai_core/agent.py - UNIFIED AGENT RUNTIME & BOOTSTRAP
"""
Unified Agent Runtime - Primary Agent Implementation
===================================================
Fully integrated standalone agent with WebSocket support and executable generation.
Handles NPCs, God agents, and dynamic spawning (breeding, genesis, spawning commands).

Unified Structure:
- Agent class: Core NPC/God agent logic
- Executable generation: PyInstaller bundling for spawned agents
- WebSocket server: Real-time agent communication
- Personality system: Gender-based, not name-dependent

Usage as Python Script:
    python -m ai_core.agent --agent-id alice --mode autonomous
    python -m ai_core.agent --agent-id bob --mode chat --load-brain data/brains/bob/brain.pcap

Usage as PyInstaller Executable:
    ./DW_Agent_alice --agent-id alice --port 8001
    ./DW_Agent_god_agent --agent-id god_agent --god-type creation
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
from typing import Optional, Dict, Any, Literal
import json

import torch
import numpy as np

from ai_core.personality import Personality, GenderType, assign_npc_gender, assign_god_gender
from ai_core.emotion import EmotionSystem
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.brain_core import BrainCore
from ai_core.planner import CognitivePlanner
from ai_core.unified_memory import UnifiedMemoryStore
from ai_core.cognitive_loop import CognitiveLoop
from ai_core.communication_protocol import handle_agent_websocket
from ai_core.config import Config

from fastapi import FastAPI, Form, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

log = logging.getLogger("agent")

# Configure logging early if running as script
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
    )

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

global_agent = None
global_server = None
active_websockets = []

# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "agent_id": global_agent.agent_id if global_agent else "unknown",
            "protocol": "json",
            "version": "1.0.0"
        })

        log.info(f"[WS] Client connected. Active connections: {len(active_websockets)}")

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            log.info(f"[WS] Received: {message.get('type', 'unknown')}")

            if message.get("type") == "chat":
                user_message = message.get("message", "")

                if global_agent and user_message:
                    # Process with agent
                    response = await global_agent.process_chat(user_message)

                    # Send agent response back
                    await websocket.send_json({
                        "type": "chat",
                        "from": "agent",
                        "text": response,
                        "timestamp": time.time()
                    })

                    log.info(f"[WS] Sent response: {response[:50]}...")

    except WebSocketDisconnect:
        log.info("[WS] Client disconnected")
    except Exception as e:
        log.error(f"[WS] Error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


# WebSocket endpoint for perception/action communication (Minecraft client)
@app.websocket("/ws/agent")
async def agent_perception_ws(websocket: WebSocket):
    """WebSocket endpoint for agent perception/action communication with Minecraft client"""
    try:
        await websocket.accept()
        data = await websocket.receive_json()
        agent_id = data.get("agent_id")

        if not agent_id:
            log.warning("WebSocket connection attempt without agent_id")
            await websocket.close(code=4000, reason="Missing agent_id")
            return

        log.info(f"WebSocket connection accepted for agent: {agent_id}")
        await handle_agent_websocket(websocket, agent_id, global_agent)

    except Exception as e:
        log.error(f"WebSocket error: {e}")
        try:
            await websocket.close(code=4001, reason=str(e))
        except:
            pass


async def broadcast_to_clients(message: dict):
    """Broadcast message to all connected WebSocket clients"""
    dead_sockets = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except:
            dead_sockets.append(ws)

    for ws in dead_sockets:
        active_websockets.remove(ws)

@app.get("/status")
async def get_status():
    if global_agent:
        return global_agent.get_info()
    return {"error": "Agent not running"}

@app.get("/thoughts")
async def get_thoughts():
    if global_agent:
        return {"thoughts": global_agent.thoughts[-20:]}
    return {"thoughts": []}

@app.post("/chat")
async def chat(message: str = Form(...), agent_id: str = Form(None), allowed_websites: str = Form(None)):
    if global_agent:
        # Update allowed websites if provided in chat request
        if allowed_websites:
            try:
                websites_data = json.loads(allowed_websites)
                formatted_websites = []
                for item in websites_data:
                    if isinstance(item, str):
                        formatted_websites.append({'url': item, 'enabled': True, 'type': 'url'})
                    else:
                        formatted_websites.append(item)

                if hasattr(global_agent, 'web_browser'):
                    global_agent.web_browser.update_allowed_websites(formatted_websites)
            except Exception as e:
                log.error(f"Error updating allowed websites from chat: {e}")

        response = await global_agent.process_chat(message)

        # Broadcast to WebSocket clients
        await broadcast_to_clients({
            "type": "chat",
            "from": "agent",
            "text": response,
            "timestamp": time.time()
        })

        return {"response": response}
    return {"error": "Agent not running"}

@app.post("/api/agents/{agent_id}/web/allow")
async def allow_websites(agent_id: str, data: Dict[str, Any]):
    if global_agent:
        websites = data.get('websites', [])
        if hasattr(global_agent, 'web_browser'):
            global_agent.web_browser.update_allowed_websites(websites)
            return {"status": "success", "message": f"Updated allowed websites for {agent_id}"}
    return {"error": "Agent not running"}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), agent_id: str = Form(...), filetype: str = Form(...), sync: bool = Form(False)):
    if not global_agent:
        return {"error": "Agent not running"}

    try:
        content = await file.read()
        text_content = content.decode('utf-8')

        # Add file content to memory
        global_agent.memory.remember({
            'type': 'file_upload',
            'filename': file.filename,
            'filetype': filetype,
            'content': text_content,
            'size': len(content)
        }, tags=['file', 'upload', 'learning'])

        # If sync, process immediately
        if sync:
            thought = f"I received and processed file: {file.filename} ({filetype})"
            global_agent.thoughts.append({"timestamp": time.time(), "thought": thought})
            if len(global_agent.thoughts) > 100:
                global_agent.thoughts = global_agent.thoughts[-100:]

        return {"success": True, "filename": file.filename, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


class NPCAgent:
    """
    Fully autonomous NPC agent with standalone runtime.
    Can run independently without backend server.
    """

    def __init__(self,
                agent_id: str,
                gender: Optional[GenderType] = None,
                persona_traits: Optional[Dict[str, float]] = None,
                client_process=None,
                autonomous: bool = True,
                use_scylla: bool = True,
                mode: str = 'autonomous',
                god_type: Optional[str] = None,
                custom_name: Optional[str] = None):

        self.agent_id = agent_id
        self.custom_name = custom_name
        self.autonomous_mode = autonomous
        self.mode = mode
        self.god_type = god_type

        # Core components
        if gender is None:
            from ai_core.personality import assign_npc_gender
            gender = assign_npc_gender()

        self.personality = Personality(gender=gender, traits=persona_traits)
        self.emotion = EmotionSystem()

        # UNIFIED MEMORY with ScyllaDB
        self.memory = UnifiedMemoryStore(
            agent_id=agent_id,
            capacity=10000,
            use_scylla=use_scylla,
            scylla_hosts=['127.0.0.1']
        )

        # Brain
        self.brain = BrainCore(agent_ref=self)
        self.planner = CognitivePlanner(brain=self.brain)

        # Initialize language intelligence
        self._init_language()

        # Attach continual learning (Avalanche) if available
        try:
            from ai_core.continual_learner import add_continual_learning
            # Default strategy 'replay' provides memory-based continual updates
            add_continual_learning(self, strategy='replay')
            log.info(f"[{self.agent_id}] Continual learning attached (strategy=replay)")
        except Exception as e:
            log.warning(f"[{self.agent_id}] Continual learning not available: {e}")

        # State
        self.health = 20.0
        self.hunger = 20.0
        self.last_obs = None
        self.last_action = None
        self.step_count = 0

        # Client process info (optional - only for Minecraft mode)
        self.client_process = client_process
        self.agent_type = 'npc'

        # AI components (lazy loading)
        self.policy = None
        self.reward_system = None

        # Neural stack placeholders
        self.world_model = None
        self.world_model_trainer = None
        self.world_model_buffer = None
        self._neural_integrated = False

        # Metadata
        self.metadata = {}

        # Thoughts for frontend sync
        self.thoughts = [
            {"timestamp": time.time(), "thought": "Initializing agent systems..."},
            {"timestamp": time.time(), "thought": "Memory system online"},
            {"timestamp": time.time(), "thought": "Ready to interact and learn"}
        ]

        # COGNITIVE LOOP
        self.cognitive_loop = None
        self._init_world_model()
        self._init_audio_processor()

        if self.autonomous_mode:
            self._init_cognitive_loop()

        log.info(f"NPCAgent initialized: {agent_id} (mode: {mode}, autonomous: {autonomous})")

        # Initialize web browsing if available
        try:
            from ai_core.web_browser import add_web_browsing_to_agent
            add_web_browsing_to_agent(self)
            log.info(f"[{self.agent_id}] Web browsing initialized")
        except Exception as e:
            log.warning(f"Web browsing not available: {e}")

        # Initialize Minecraft client
        from ai_core.actuators import MinecraftClient
        self.minecraft_client = MinecraftClient(
            agent_id=agent_id,
            tcp_host='127.0.0.1',
            tcp_port=8765,
            ws_host='127.0.0.1',
            ws_port=11400,
            prefer_tcp=True
        )
        log.info(f"[{agent_id}] Minecraft client initialized (TCP+WebSocket)")

        if god_type:
            try:
                from ai_core.god_controls import integrate_god_controls
                integrate_god_controls(self)
                log.info(f"[{agent_id}] God controls initialized for {god_type}")
            except Exception as e:
                log.warning(f"God controls not available: {e}")

    def _init_language(self):
        """Initialize transformer-based language learning"""
        from ai_core.brain_language import add_language_to_brain
        add_language_to_brain(self.brain)
        log.info(f"[{self.agent_id}] Transformer language learning initialized")

    def _init_cognitive_loop(self):
        """Initialize autonomous cognitive loop"""
        self.cognitive_loop = CognitiveLoop(
            agent=self,
            loop_interval=0.5
        )
        log.info(f"🧠 Cognitive loop initialized for {self.agent_id}")

    def _init_world_model(self):
        """Initialize world model for mental simulation"""
        try:
            from ai_core.world_model import integrate_world_model_with_agent
            integrate_world_model_with_agent(self)
            log.info(f"[{self.agent_id}] World model integrated")
        except Exception as e:
            log.warning(f"World model not available: {e}")

    def _init_audio_processor(self):
        """Initialize audio processing for listening"""
        try:
            from ai_core.audio_processors import add_audio_processing_to_agent
            add_audio_processing_to_agent(self)
            log.info(f"[{self.agent_id}] Audio processing initialized")
        except Exception as e:
            log.warning(f"Audio processing not available: {e}")

    # ==================== AUTONOMOUS CONTROL ====================

    async def start_autonomous_mode(self):
        """Start fully autonomous operation"""
        if not self.cognitive_loop:
            self._init_cognitive_loop()

        await self.cognitive_loop.start()
        log.info(f"✅ {self.agent_id} is now FULLY AUTONOMOUS")

    async def stop_autonomous_mode(self):
        """Stop autonomous operation"""
        if self.cognitive_loop:
            await self.cognitive_loop.stop()
        log.info(f"🛑 {self.agent_id} autonomous mode stopped")

    def is_autonomous(self) -> bool:
        """Check if agent is running autonomously"""
        return self.cognitive_loop and self.cognitive_loop.running

    async def broadcast(self, message: dict):
        """Broadcast message to all connected WebSocket clients"""
        await broadcast_to_clients(message)

    # ==================== PERCEPTION & ACTION ====================

    def perceive(self, raw_observation: Dict[str, Any]) -> np.ndarray:
        """Convert raw observation to feature vector"""
        obs_parts = []

        # Basic stats (3)
        obs_parts.append(raw_observation.get('health', 20.0) / 20.0)
        obs_parts.append(raw_observation.get('hunger', 20.0) / 20.0)
        obs_parts.append(raw_observation.get('saturation', 5.0) / 20.0)

        # Position (3)
        pos = raw_observation.get('position', {'x': 0, 'y': 0, 'z': 0})
        obs_parts.extend([pos['x'] / 100.0, pos['y'] / 100.0, pos['z'] / 100.0])

        # Look direction (2)
        obs_parts.append(raw_observation.get('yaw', 0.0) / 360.0)
        obs_parts.append(raw_observation.get('pitch', 0.0) / 90.0)

        # Entities (1)
        entities = raw_observation.get('entities', [])
        obs_parts.append(len(entities) / 10.0)

        # Inventory (1)
        inventory = raw_observation.get('inventory', {})
        obs_parts.append(inventory.get('slot_count', 0) / 36.0)

        # Personality (8)
        obs_parts.extend(self.personality.as_array().tolist())

        # Emotions (8)
        obs_parts.extend(self.emotion.as_array().tolist())

        # Reward history stats (5)
        if self.reward_system and self.reward_system.reward_history:
            recent = list(self.reward_system.reward_history)[-20:]
            obs_parts.extend([
                np.mean(recent), np.std(recent), np.max(recent),
                np.min(recent), len([r for r in recent if r > 0]) / len(recent)
            ])
        else:
            obs_parts.extend([0.0] * 5)

        # Memory state (2)
        obs_parts.append(len(self.memory.events) / 1000.0)
        obs_parts.append(0.0)

        while len(obs_parts) < 50:
            obs_parts.append(0.0)

        obs_array = np.array(obs_parts[:50], dtype=np.float32)
        self.last_obs = obs_array

        # Feed to cognitive loop
        if self.cognitive_loop and self.cognitive_loop.running:
            self.cognitive_loop.receive_state_update({
                'health': self.health,
                'hunger': self.hunger,
                'raw_observation': raw_observation
            })

        return obs_array

    def observe(self, image: np.ndarray, info: Dict[str, Any] = None) -> np.ndarray:
        """Process visual observation and store in memory"""
        try:
            from ai_core.vision import VisionAdapter

            # Initialize vision adapter if needed
            if not hasattr(self, 'vision_adapter'):
                self.vision_adapter = VisionAdapter()

            # Preprocess image
            processed_image = self.vision_adapter.preprocess(image)

            # Store visual observation in memory
            memory_data = {
                'type': 'visual_observation',
                'image_shape': image.shape,
                'processed_shape': processed_image.shape,
                'description': info.get('description', 'Visual observation'),
                'source': info.get('source', 'unknown'),
                'filename': info.get('filename', ''),
                'timestamp': time.time()
            }

            # Add emotional context if available
            if hasattr(self, 'emotion'):
                memory_data['emotional_context'] = self.emotion.snapshot()

            self.memory.remember(memory_data, tags=['vision', 'observation', 'visual'])

            # Generate a thought about the observation
            thought = f"I observed a visual scene: {memory_data['description']}"
            self.thoughts.append({"timestamp": time.time(), "thought": thought})
            if len(self.thoughts) > 100:
                self.thoughts = self.thoughts[-100:]

            # Return processed observation for potential use by other systems
            return processed_image

        except Exception as e:
            log.error(f"Error processing visual observation: {e}")
            # Return a dummy observation
            return np.zeros((3, 84, 84), dtype=np.float32)

    def decide(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        """Make decision based on observation"""
        if self.policy is None:
            action = np.random.randn(11) * 0.3
            return np.clip(action, -1.0, 1.0)

        with torch.no_grad():
            obs_tensor = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
            action = self.policy._predict(obs_tensor, deterministic=deterministic)
            action = action.squeeze().cpu().numpy()

        return action

    def act(self, action: np.ndarray) -> Dict[str, Any]:
        """Convert action array to control dictionary and send to Minecraft"""
        action = np.clip(action, -1.0, 1.0)

        controls = {
            'move_forward': float(action[0]),
            'move_strafe': float(action[1]),
            'jump': bool(action[2] > 0.5),
            'sneak': bool(action[3] > 0.5),
            'attack': bool(action[4] > 0.5),
            'use': bool(action[5] > 0.5),
            'drop': bool(action[6] > 0.5),
            'open_inv': bool(action[7] > 0.5),
            'swap_hand': bool(action[8] > 0.5),
            'yaw_delta': float(action[9] * 2.0),
            'pitch_delta': float(action[10] * 1.2)
        }

        self.last_action = action
        self.step_count += 1

        # Send to Minecraft
        self.minecraft_client.send_action(controls)

        return controls

    # ==================== LEARNING ====================

    def learn(self, obs: np.ndarray, action: np.ndarray,
              next_obs: np.ndarray, outcome: Dict[str, Any]):
        """Learn from experience"""
        if self.reward_system is None:
            self.initialize_reward_system()

        obs_t = torch.tensor(obs, dtype=torch.float32).unsqueeze(0)
        action_t = torch.tensor(action, dtype=torch.float32).unsqueeze(0)
        next_obs_t = torch.tensor(next_obs, dtype=torch.float32).unsqueeze(0)

        reward, reward_info = self.reward_system.compute_reward(
            obs_t, action_t, next_obs_t, outcome
        )

        # Store in UNIFIED MEMORY
        self.memory.remember({
            'type': 'experience',
            'obs': obs.tolist(),
            'action': action.tolist(),
            'reward': reward,
            'outcome': outcome
        }, tags=['learning', 'experience', 'rl'])

        self._update_emotions(reward, reward_info)
        self.emotion.decay()

    def _update_emotions(self, reward: float, reward_info: Dict[str, Any]):
        """Update emotional state based on reward"""
        if reward > 0:
            self.emotion.add('joy', min(0.2, reward * 0.1))
            self.emotion.add('trust', min(0.1, reward * 0.05))
        else:
            self.emotion.add('fear', min(0.2, -reward * 0.1))
            self.emotion.add('sadness', min(0.1, -reward * 0.05))

        exploration = reward_info.get('exploration', 0.0)
        if exploration > 0.1:
            self.emotion.add('surprise', min(0.15, exploration * 0.1))

    # ==================== STATUS ====================

    def is_alive(self) -> bool:
        if self.client_process:
            return self.client_process.is_alive
        return True

    def get_info(self) -> Dict[str, Any]:
        info = {
            'agent_id': self.agent_id,
            'custom_name': self.custom_name,
            'agent_type': self.agent_type,
            'mode': self.mode,
            'gender': self.personality.gender,
            'is_alive': self.is_alive(),
            'step_count': self.step_count,
            'health': self.health,
            'hunger': self.hunger,
            'personality': self.personality.to_dict(),
            'emotions': self.emotion.snapshot(),
            'memory_size': len(self.memory.events),
            'dominant_emotion': self.emotion.dominant_emotion(),
            'autonomous': self.is_autonomous()
        }

        # Language progress
        if hasattr(self.brain, 'language'):
            info['language'] = self.brain.get_language_progress()

        # Cognitive loop status
        if self.cognitive_loop:
            info['cognitive_status'] = self.cognitive_loop.get_status()

        # Memory stats
        info['memory_stats'] = self.memory.get_stats()

        if self.client_process:
            info['backend_url'] = self.client_process.backend_url
            info['server'] = self.client_process.server_addr

        if self.metadata:
            info['metadata'] = self.metadata

        return info

    async def process_chat(self, message: str) -> str:
        """Process a chat message and return response, learning from it"""
        # Add user message to memory
        self.memory.remember({
            'type': 'chat_message',
            'sender': 'user',
            'message': message
        }, tags=['chat', 'user', 'learning'])

        # Check for URLs in message and queue for browsing if allowed
        if hasattr(self, 'web_browser'):
            import re
            urls = re.findall(r'(https?://[^\s]+)', message)
            # Also detect domain-like strings
            domains = re.findall(r'(?<![/\w])(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}(?![/\w])', message)

            for url in urls:
                self.web_browser.add_url_to_queue(url)

            for domain in domains:
                # Try both http and https if no protocol specified
                self.web_browser.add_url_to_queue(f"https://{domain}")

        # Try to generate a response using brain/language
        response = f"I am {self.agent_id}. You said: {message}"

        try:
            if hasattr(self.brain, 'language') and self.brain.language.language_stage >= 1:
                # Use language system to generate response
                context = {
                    'current_message': message,
                    'personality': self.personality.to_dict(),
                    'emotions': self.emotion.snapshot(),
                    'recent_memory': self.memory.recall(5)
                }
                response = self.brain.language.generate_speech(context)
                if not response or len(response.strip()) < 3:
                    response = f"I am {self.agent_id}. I received your message: {message}"
        except Exception as e:
            log.warning(f"Brain response generation failed: {e}")

        # Add agent response to memory
        self.memory.remember({
            'type': 'chat_message',
            'sender': 'agent',
            'message': response
        }, tags=['chat', 'agent', 'response'])

        # Generate a thought about the conversation
        thought = f"I just chatted with a user. They said: {message[:50]}..."
        self.thoughts.append({"timestamp": time.time(), "thought": thought})
        if len(self.thoughts) > 100:
            self.thoughts = self.thoughts[-100:]

        # Broadcast thought to WebSocket clients
        await broadcast_to_clients({
            "type": "agent_thought",
            "internal_thought": thought,
            "timestamp": time.time()
        })

        return response

    # ==================== SAVE/LOAD ====================

    def save(self, path: str):
        """Save agent state with neural components"""
        from ai_core.brain_capsule import BrainCapsule

        # Get language state
        language_state = None
        if hasattr(self.brain, 'language'):
            language_state = self.brain.language.state_dict()

        # Prepare metadata (merging current metadata)
        metadata = {
            'agent_id': self.agent_id,
            'custom_name': self.custom_name,
            'agent_type': self.agent_type,
            'mode': self.mode,
            'gender': self.personality.gender,
            'step_count': self.step_count,
            'saved_at': time.time(),
            'autonomous': self.autonomous_mode
        }
        metadata.update(self.metadata)

        capsule = BrainCapsule(
            metadata=metadata,
            personality=self.personality.to_dict(),
            emotion_snapshot=self.emotion.snapshot(),
            memory_snapshot=self.memory.recall(1000),
            language_state=language_state
        )

        # Neural stack persistence
        model_state = {}

        # 1. Save policy state (with portability fix)
        if self.policy:
            # Move to CPU for portability
            try:
                model_state['policy'] = {
                    k: v.cpu() if isinstance(v, torch.Tensor) else v
                    for k, v in self.policy.state_dict().items()
                }
            except Exception as e:
                log.error(f"[{self.agent_id}] Failed to serialize policy: {e}")

        # 2. Save world model state
        try:
            if getattr(self, "world_model", None) is not None:
                if hasattr(self.world_model, "state_dict"):
                    model_state['world_model'] = {
                        k: v.cpu() if isinstance(v, torch.Tensor) else v
                        for k, v in self.world_model.state_dict().items()
                    }
        except Exception as e:
            log.exception(f"[{self.agent_id}] Error serializing world model: {e}")

        capsule.model_state = model_state
        capsule.save(path)
        log.info(f"[{self.agent_id}] Saved to {path}")

    def load(self, path: str):
        """Load agent state with neural components"""
        from ai_core.brain_capsule import BrainCapsule

        capsule = BrainCapsule.load(path)

        # Restore personality
        self.personality = Personality.from_dict(capsule.personality)

        # Restore emotions
        if capsule.emotion_snapshot:
            for emotion, value in capsule.emotion_snapshot.items():
                self.emotion.emotions[emotion] = value

        # Restore memory
        if capsule.memory_snapshot:
            for event in capsule.memory_snapshot:
                self.memory.remember(event, tags=event.get('tags', []))

        # Restore language
        if capsule.language_state:
            if hasattr(self.brain, 'language'):
                try:
                    self.brain.language.load_state_dict(capsule.language_state)
                    log.info(f"[{self.agent_id}] Language restored.")
                except Exception as e:
                    log.warning(f"[{self.agent_id}] Language restore failed: {e}")

        # Restore model weights
        saved_model_state = capsule.model_state or {}

        if self.policy:
            if 'policy' in saved_model_state:
                try:
                    self.policy.load_state_dict(saved_model_state['policy'])
                    log.info(f"[{self.agent_id}] Policy restored from capsule.")
                except Exception as e:
                    log.warning(f"[{self.agent_id}] Policy load failed: {e}")
            elif saved_model_state:
                # Fallback for old format
                try:
                    self.policy.load_state_dict(saved_model_state, strict=False)
                    log.info(f"[{self.agent_id}] Policy restored from legacy state (non-strict).")
                except Exception as e:
                    log.warning(f"[{self.agent_id}] Legacy policy restore failed: {e}")

        # Restore neural stack (world model)
        try:
            if 'world_model' in saved_model_state:
                try:
                    from ai_core import world_model as wm_module
                except Exception:
                    wm_module = None

                wm_state = saved_model_state['world_model']
                if wm_module and hasattr(wm_module, "WorldModel"):
                    self.world_model = wm_module.WorldModel(agent_id=self.agent_id)
                    if hasattr(self.world_model, "load_state_dict"):
                        try:
                            self.world_model.load_state_dict(wm_state)
                            log.info(f"[{self.agent_id}] World model restored.")
                        except Exception as e:
                            log.warning(f"[{self.agent_id}] World model load failed: {e}")
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to restore neural stack: {e}")

        # Metadata
        self.step_count = capsule.metadata.get('step_count', 0)
        self.custom_name = capsule.metadata.get('custom_name', self.custom_name)
        self.agent_type = capsule.metadata.get('agent_type', 'npc')
        self.mode = capsule.metadata.get('mode', 'autonomous')
        self.autonomous_mode = capsule.metadata.get('autonomous', True)

        log.info(f"[{self.agent_id}] Loaded from {path}")

    # ==================== INITIALIZATION METHODS ====================

    def initialize_reward_system(self, obs_dim: int = 50, action_dim: int = 11):
        """Initialize reward system (lazy loading)"""
        if self.reward_system is None:
            self.reward_system = ImprovedRewardSystem(
                obs_dim=obs_dim,
                action_dim=action_dim,
                persona=self.personality.as_array(),
                use_rnd=True,
                use_icm=True
            )
            log.info(f"[{self.agent_id}] Reward system initialized")

    def initialize_policy(self, obs_space, action_space):
        """Initialize policy network (lazy loading)"""
        if self.policy is None:
            from rl.policy import TransformerPolicy
            self.policy = TransformerPolicy(
                observation_space=obs_space,
                action_space=action_space,
                lr_schedule=lambda _: 3e-4
            )
            log.info(f"[{self.agent_id}] Policy initialized")

    # ==================== NEURAL STACK INTEGRATION ==================

    def integrate_neural_stack(self, force: bool = False):
        """Attach world_model to this NPCAgent instance"""
        if self._neural_integrated and not force:
            return

        try:
            from ai_core import world_model as wm_module
        except Exception:
            wm_module = None

        # World Model
        try:
            if wm_module:
                if hasattr(wm_module, "integrate_world_model_with_agent"):
                    wm_module.integrate_world_model_with_agent(self)
                    log.info(f"[{self.agent_id}] WorldModel integrated via helper.")
                elif hasattr(wm_module, "WorldModel"):
                    self.world_model = wm_module.WorldModel(agent_id=self.agent_id)
                    log.info(f"[{self.agent_id}] WorldModel instantiated directly.")
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to attach world_model: {e}")

        self._neural_integrated = True
        log.info(f"[{self.agent_id}] Neural stack integrated.")

    # ==================== MENTAL SIMULATION ==================

    def imagine_scenario(self, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """
        Use world model to mentally simulate a scenario.
        Returns visualization data for frontend.
        Called ONLY when cognitive loop decides to simulate.
        """
        if not hasattr(self, 'world_model'):
            return {'type': 'thought_flow', 'label': 'No World Model'}

        try:
            # Get mental workspace from world model
            workspace = None

            # Try world model first
            if hasattr(self.world_model, 'mental_workspace'):
                workspace = self.world_model.mental_workspace
            # Fallback to reasoning core
            elif hasattr(self.brain, 'reasoning') and hasattr(self.brain.reasoning, 'mental_workspace'):
                workspace = self.brain.reasoning.mental_workspace

            if workspace:
                # Extract objects for visualization
                objects = []
                for obj in workspace.objects:
                    objects.append({
                        'id': obj.get('id'),
                        'type': obj.get('type', 'unknown'),
                        'position': obj.get('position', [0, 0, 0]),
                        'properties': obj.get('properties', {})
                    })

                return {'type': 'world_model','label': 'Mental Simulation','objects': objects}

        except Exception as e:
            log.error(f"Mental simulation error: {e}")

        return {'type': 'thought_flow', 'label': 'Thinking...'}

    def generate_internal_thought(self, context: Dict[str, Any]) -> Optional[str]:
        """
        Generate internal monologue when cognitive loop decides agent should think.
        Returns None if agent decides not to think in words.
        """
        try:
            # Only if language system exists and is advanced enough
            if not hasattr(self.brain, 'language'):
                return None

            if self.brain.language.language_stage < 1:
                return None  # Pre-linguistic, can't think in words yet

            # Agent autonomously decides if it wants to think in words
            # Based on personality and situation
            sociability = self.personality.traits.get('sociability', 0.5)
            openness = self.personality.traits.get('openness', 0.5)

            # Introverted agents think more internally
            think_probability = (1.0 - sociability + openness) / 2.0

            if np.random.rand() > think_probability:
                return None  # Agent chooses not to verbalize thoughts

            # Generate internal thought
            internal = self.brain.language.generate_speech(context)

            # Only return if meaningful
            if internal and len(internal.strip()) > 2:
                self.thoughts.append({"timestamp": time.time(), "thought": internal})
                if len(self.thoughts) > 100:
                    self.thoughts = self.thoughts[-100:]
                return internal

        except Exception as e:
            log.error(f"Internal thought generation error: {e}")

        return None

    # ==================== CLEANUP ====================

    async def shutdown(self):
        """Graceful shutdown"""
        # Stop cognitive loop
        if self.cognitive_loop:
            await self.stop_autonomous_mode()

        # Save state - use provided path if available, otherwise use relative path
        brain_save_path = self.metadata.get('brain_save_path')

        if brain_save_path:
            # Use absolute path provided from backend
            brain_path = Path(brain_save_path)
        else:
            # Fallback to relative path (for standalone execution)
            brain_path = Path(f"data/brains/{self.agent_id}/brain.pcap")

        brain_path.parent.mkdir(parents=True, exist_ok=True)
        self.save(str(brain_path))

        # Close memory backend
        if hasattr(self.memory, 'close'):
            self.memory.close()

        log.info(f"[{self.agent_id}] Shutdown complete")


# =============================================================================
# STANDALONE RUNTIME
# =============================================================================

async def run_server(port: int = 8000):
    """Run the FastAPI web server for frontend connections"""
    global global_server
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    global_server = uvicorn.Server(config)
    await global_server.serve()

async def run_standalone_agent(agent_id: str, mode: str = 'autonomous',
                               load_brain: Optional[str] = None,
                               brain_save_path: Optional[str] = None,
                               duration: Optional[float] = None,
                               chat_interface: bool = False,
                               god_type: Optional[str] = None,
                               gender: Optional[Any] = None,
                               personality_traits: Optional[Dict[str, float]] = None,
                               spawn_pos: Optional[tuple] = None,
                               genesis_ancestor: bool = False,
                               port: int = 8000,
                               custom_name: Optional[str] = None):
    """
    Run agent in standalone mode without backend server.

    Args:
        agent_id: Unique identifier
        mode: 'autonomous', 'chat', or 'minecraft'
        load_brain: Path to brain.pcap to load
        brain_save_path: Path where brain should be saved (absolute path from backend)
        duration: How long to run (None = indefinite)
        chat_interface: Enable terminal chat interface
        god_type: Type of god agent (if applicable)
        gender: Agent gender (GenderType)
        personality_traits: Dictionary of personality traits
        spawn_pos: Tuple of (x, y, z) spawn coordinates
        genesis_ancestor: Whether this is a genesis ancestor
    """
    global global_agent

    print(f"\n{'='*70}")
    print(f"  🤖 STARTING STANDALONE AGENT: {agent_id}")
    print(f"{'='*70}")
    print(f"  Mode: {mode}")
    print(f"  Chat Interface: {'Enabled' if chat_interface else 'Disabled'}")
    if load_brain:
        print(f"  Loading Brain: {load_brain}")
    print(f"{'='*70}\n")

    # Create agent
    agent = NPCAgent(
        agent_id=agent_id,
        autonomous=(mode == 'autonomous'),
        mode=mode,
        god_type=god_type,
        gender=gender,
        persona_traits=personality_traits,
        custom_name=custom_name
    )

    # Store brain save path if provided (from backend)
    if brain_save_path:
        agent.metadata['brain_save_path'] = brain_save_path

    global_agent = agent

    # Store spawn position and genesis info
    if spawn_pos:
        agent.metadata['spawn_pos'] = spawn_pos
        agent.metadata['spawn_x'], agent.metadata['spawn_y'], agent.metadata['spawn_z'] = spawn_pos
    if genesis_ancestor:
        agent.metadata['genesis_ancestor'] = genesis_ancestor

    # Start web server for frontend connection
    server_task = asyncio.create_task(run_server(port=port))

    # Save initial brain state to ensure file exists for packager
    initial_save_path = brain_save_path or agent.metadata.get('brain_save_path')
    if initial_save_path:
        initial_brain_path = Path(initial_save_path)
        initial_brain_path.parent.mkdir(parents=True, exist_ok=True)
        agent.save(str(initial_brain_path))
        log.info(f"💾 Initial brain saved for {agent.agent_id}")

    # Load brain if specified
    if load_brain and Path(load_brain).exists():
        try:
            agent.load(load_brain)
            print(f"✅ Brain loaded from {load_brain}")
        except Exception as e:
            print(f"⚠️  Failed to load brain: {e}")

    # Print agent info
    print(f"\n📊 Agent Info:")
    print(f"  Personality: {agent.personality.to_dict()}")
    print(f"  Memory Backend: {agent.memory.get_stats()['backend']}")
    if hasattr(agent.brain, 'language'):
        print(f"  Language Stage: {agent.brain.language.language_stage}")
        print(f"  Vocabulary: {agent.brain.language.vocab.next_id} words")
    print(f"  Memory: {len(agent.memory.events)} events")
    print()

    print(f"  🌐 API Server: http://127.0.0.1:8000")
    print(f"  🔌 WebSocket: ws://127.0.0.1:8000/ws")
    print(f"  📡 Endpoints: /status, /thoughts, /chat")
    print()


    # Start modes
    if mode == 'autonomous':
        await agent.start_autonomous_mode()
    elif mode == 'minecraft':
        print(f"✅ Minecraft mode active")
        print(f"   TCP Server: {agent.minecraft_client.tcp_client.host}:{agent.minecraft_client.tcp_client.port}")
        print(f"   WebSocket: ws://{agent.minecraft_client.ws_client.uri}")
        print(f"   Waiting for Minecraft to connect...")
        await agent.minecraft_client.wait_for_connection()
        print(f"✅ Minecraft connected!")

    start_time = time.time()

    # Chat interface task
    chat_task = None
    if chat_interface:
        chat_task = asyncio.create_task(chat_loop(agent))

    try:
        while True:
            # Check duration
            if duration and (time.time() - start_time) >= duration:
                break

            # Auto-save every 5 minutes
            if (time.time() - start_time) % 300 < 1:
                brain_save_path = agent.metadata.get('brain_save_path')

                if brain_save_path:
                    brain_path = Path(brain_save_path)
                else:
                    brain_path = Path(f"data/brains/{agent.agent_id}/brain.pcap")

                brain_path.parent.mkdir(parents=True, exist_ok=True)
                agent.save(str(brain_path))
                log.info(f"💾 Auto-saved {agent.agent_id}")

            await asyncio.sleep(1)

    except KeyboardInterrupt:
        print("\n\n🛑 Stopping agent...")

    finally:
        if chat_task:
            chat_task.cancel()

        # Shutdown web server
        if global_server:
            global_server.should_exit = True
            try:
                await asyncio.wait_for(global_server.shutdown(), timeout=5.0)
            except:
                pass

        await agent.shutdown()

        print(f"\n{'='*70}")
        print(f"  ✅ AGENT STOPPED: {agent.agent_id}")
        print(f"  Total runtime: {time.time() - start_time:.1f}s")
        print(f"  Final memory: {len(agent.memory.events)} events")
        if hasattr(agent.brain, 'language'):
            print(f"  Final vocabulary: {agent.brain.language.vocab.next_id} words")
        print(f"{'='*70}\n")


async def chat_loop(agent):
    """Interactive chat loop for terminal interface"""
    print("\n💬 Chat Mode: Type messages (Ctrl+C to exit)")
    print("=" * 70)

    while True:
        try:
            # Get user input (non-blocking)
            user_input = await asyncio.to_thread(input, "You: ")

            if not user_input.strip():
                continue

            # Build context
            context = {
                'health': agent.health,
                'hunger': agent.hunger,
                'emotions': agent.emotion.snapshot(),
                'dominant_emotion': agent.emotion.dominant_emotion()
            }

            # Process input
            response = agent.brain.process_language_input(user_input, context)

            if response:
                print(f"{agent.agent_id}: {response}")
            else:
                print(f"{agent.agent_id}: [Learning...]")

        except EOFError:
            break
        except Exception as e:
            log.error(f"Chat error: {e}")


# =============================================================================
# EXECUTABLE GENERATION FOR SPAWNED AGENTS (Breeding, Genesis, Spawning)
# =============================================================================

class AgentExecutableGenerator:
    """Generate standalone PyInstaller executables for dynamically spawned agents"""

    def __init__(self, output_dir: str = "build/agents/dist"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.build_temp = Path("build/agents/build_temp")
        self.build_temp.mkdir(parents=True, exist_ok=True)

    def generate_executable(self, agent_id: str, agent_type: Literal['npc', 'god'] = 'npc',
                           god_type: Optional[str] = None, gender: Optional[GenderType] = None,
                           personality_traits: Optional[Dict[str, float]] = None) -> Optional[Path]:
        """
        Generate a PyInstaller executable for a spawned agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: 'npc' or 'god'
            god_type: Type of god agent (if agent_type='god')
            gender: gender assignment (auto-assigned if None)
            personality_traits: custom personality traits

        Returns:
            Path to generated executable or None on error
        """

        # Auto-assign gender if not provided
        if gender is None:
            if agent_type == 'god':
                gender = assign_god_gender()
            else:
                gender = assign_npc_gender()

        # Create wrapper script for this specific agent
        wrapper_script = self.build_temp / f"{agent_id}_wrapper.py"

        # Personality as JSON string
        personality_json = json.dumps(personality_traits or {})
        god_arg = f" --god-type {god_type}" if god_type else ""

        wrapper_content = f'''
#!/usr/bin/env python3
"""
Auto-generated wrapper for {agent_id} executable
Generated: {time.time()}
Agent Type: {agent_type}
Gender: {gender}
"""

import sys
from ai_core.agent import main

# Override sys.argv for this specific agent
sys.argv = [
    sys.argv[0],
    '--agent-id', '{agent_id}',
    '--mode', 'autonomous',
    '--gender', '{gender}',
    '--personality', '{personality_json}'{god_arg}
]

if __name__ == '__main__':
    main()
'''

        wrapper_script.write_text(wrapper_content)
        log.info(f"📝 Generated wrapper: {wrapper_script}")

        # Build PyInstaller command
        exe_name = f"DW_Agent_{agent_id.replace(' ', '_')}" if agent_type == 'npc' else f"DW_God_{agent_id.replace(' ', '_')}"

        try:
            import PyInstaller.__main__
        except ImportError:
            log.error("PyInstaller not installed. Cannot generate executable.")
            log.info("Install with: pip install PyInstaller")
            return None

        # PyInstaller arguments
        pyinstaller_args = [
            '--onefile',
            f'--name={exe_name}',
            f'--distpath={self.output_dir}',
            f'--buildpath={self.build_temp}',
            f'--specpath={self.build_temp}',
            '--hidden-import=torch',
            '--hidden-import=numpy',
            '--hidden-import=fastapi',
            '--hidden-import=uvicorn',
            '--hidden-import=websockets',
            '--hidden-import=ai_core',
            '--collect-all=ai_core',
            '--collect-all=torch',
            '--console',
            str(wrapper_script)
        ]

        log.info(f"🔨 Building executable: {exe_name}")
        log.info(f"   Agent ID: {agent_id}")
        log.info(f"   Type: {agent_type}")
        log.info(f"   Gender: {gender}")

        try:
            # Run PyInstaller
            PyInstaller.__main__.run(pyinstaller_args)

            exe_path = self.output_dir / exe_name
            if exe_path.exists():
                log.info(f"✅ Executable created: {exe_path}")
                return exe_path
            else:
                log.error(f"❌ Executable not found: {exe_path}")
                return None

        except Exception as e:
            log.error(f"❌ Failed to generate executable: {e}")
            return None

    def launch_executable(self, exe_path: Path, port: int = 8001,
                         minecraft: bool = False, ultimmc_path: Optional[str] = None) -> Optional[subprocess.Popen]:
        """
        Launch a generated executable.

        Args:
            exe_path: Path to the executable
            port: WebSocket port
            minecraft: Enable Minecraft launching
            ultimmc_path: Path to UltimMC

        Returns:
            subprocess.Popen object or None on error
        """

        if not exe_path.exists():
            log.error(f"Executable not found: {exe_path}")
            return None

        cmd = [str(exe_path), '--port', str(port)]

        if minecraft:
            cmd.append('--minecraft')
            if ultimmc_path:
                cmd.extend(['--ultimmc-path', ultimmc_path])

        log.info(f"🚀 Launching: {exe_path.name}")
        log.info(f"   Command: {' '.join(cmd)}")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            log.info(f"✅ Process started (PID: {process.pid})")
            return process
        except Exception as e:
            log.error(f"Failed to launch executable: {e}")
            return None


# =============================================================================
# CLI ENTRY POINT

def main():
    """CLI entry point for standalone agent execution"""
    parser = argparse.ArgumentParser(
        description="Divine World Standalone Agent Runtime"
    )

    parser.add_argument(
        '--agent-id',
        type=str,
        default='demo',
        help='Agent identifier (default: demo)'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=8000,
        help='FastAPI server port (default: 8000)'
    )

    parser.add_argument(
        '--mode',
        type=str,
        choices=['autonomous', 'chat', 'minecraft'],
        default='autonomous',
        help='Agent mode (default: autonomous)'
    )

    parser.add_argument(
        '--god-type',
        type=str,
        choices=['ender_dragon', 'wither', 'warden', 'oracle', 'elder_guardian', 'creaking'],
        help='God type (if this is a god agent)'
    )

    parser.add_argument(
        '--load-brain',
        type=str,
        help='Path to brain.pcap to load'
    )

    parser.add_argument(
        '--brain-save-path',
        type=str,
        help='Path where brain should be saved (absolute path)'
    )

    parser.add_argument(
        '--duration',
        type=float,
        help='Run duration in seconds (default: indefinite)'
    )

    parser.add_argument(
        '--chat',
        action='store_true',
        help='Enable terminal chat interface'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    # Genesis spawn arguments
    parser.add_argument(
        '--gender',
        type=str,
        choices=['male', 'female', 'dual'],
        help='Agent gender for personality'
    )

    parser.add_argument(
        '--personality',
        type=str,
        help='JSON string of personality traits'
    )

    parser.add_argument(
        '--spawn-x',
        type=float,
        help='Spawn position X coordinate'
    )

    parser.add_argument(
        '--spawn-y',
        type=float,
        help='Spawn position Y coordinate'
    )

    parser.add_argument(
        '--spawn-z',
        type=float,
        help='Spawn position Z coordinate'
    )

    parser.add_argument(
        '--genesis-ancestor',
        type=str,
        help='Whether this is a genesis ancestor agent'
    )

    parser.add_argument(
        '--custom-name',
        type=str,
        help='Custom display name for the agent'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
    )

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n\n🛑 Received interrupt signal, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Run agent
    try:
        # Parse personality if provided
        personality_traits = None
        if args.personality:
            try:
                personality_traits = json.loads(args.personality)
            except json.JSONDecodeError:
                print(f"⚠️  Invalid personality JSON: {args.personality}")
                personality_traits = None

        # Parse gender (GenderType is a Literal['male', 'female', 'dual'])
        gender = None
        if args.gender:
            gender = args.gender  # Just pass the string directly

        asyncio.run(run_standalone_agent(
            agent_id=args.agent_id,
            mode=args.mode,
            load_brain=args.load_brain,
            brain_save_path=args.brain_save_path,
            duration=args.duration,
            chat_interface=args.chat,
            god_type=args.god_type,
            gender=gender,
            personality_traits=personality_traits,
            spawn_pos=(args.spawn_x, args.spawn_y, args.spawn_z) if args.spawn_x is not None else None,
            genesis_ancestor=args.genesis_ancestor == 'true' if args.genesis_ancestor else False,
            port=args.port,
            custom_name=args.custom_name
        ))
    except KeyboardInterrupt:
        print("\n✅ Agent stopped")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        logging.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
