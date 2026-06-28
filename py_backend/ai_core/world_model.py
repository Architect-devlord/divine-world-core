# ai_core/world_model.py - NEURAL WORLD MODEL FOR THE DW_AGENT
"""
Transformer-based World Model for Divine World AI Agents
====================================================

Core component for internal world simulation and prediction.
Inspired by: GATO, Dreamer, World Models, Decision Transformer

Architecture:
- Multimodal encoder (vision, audio, proprioception, language)
- Transformer-based sequence model
- Predictive heads (next state, reward, termination)
- Latent world simulation for planning

Usage:
    world_model = WorldModel(config)
    prediction = world_model.predict(observation, action)
    world_model.learn_from_experience(trajectory)

Integration:
- Provides predictions for planner
- Enables imagination-based learning (dream training)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal, Categorical
import numpy as np
from typing import Dict, Any, Optional, List, Tuple, Set, Callable
from dataclasses import dataclass, asdict, field
from collections import deque
import logging
from datetime import datetime
import asyncio
import json
from ai_core.config_loader import get_section, get_device

cfg = get_section("world_model", {})
device = cfg.get("device_override") or get_device()


log = logging.getLogger("world_model")


# ============================================================================
# Configuration
# ============================================================================

@dataclass
class WorldModelConfig:
    """World model configuration"""

    # Architecture
    d_model: int = 512
    n_heads: int = 8
    n_layers: int = 6
    d_ff: int = 2048
    dropout: float = 0.1

    # Input dimensions
    vision_channels: int = 3
    vision_size: int = 84  # 84x84 frames
    audio_dim: int = 128
    proprio_dim: int = 32  # Proprioception (health, hunger, position, etc.)
    action_dim: int = 13  # FIX INT-05: was 11, must match TransformerPolicy.BASE_DIM=13
    language_vocab: int = 10000

    # Latent space
    latent_dim: int = 256
    use_vae: bool = True  # Variational encoding for uncertainty
    kl_weight: float = 0.1

    # Training
    learning_rate: float = 3e-4
    batch_size: int = 32
    sequence_length: int = 64
    grad_clip: float = 1.0

    # Prediction
    predict_steps: int = 16  # How many steps to imagine ahead
    use_ensemble: bool = True  # Ensemble for uncertainty estimation
    n_ensemble: int = 5

    # Optimization
    use_mixed_precision: bool = True
    device: str = 'cuda' if torch.cuda.is_available() else 'cpu'


# ============================================================================
# Mental Matrix Simulation (Integrated)
# ============================================================================

@dataclass
class Vector3:
    """3D Vector representation for simulation"""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def to_dict(self):
        return {"x": self.x, "y": self.y, "z": self.z}

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class PhysicsBody:
    """Physics object for Mental Matrix simulation"""
    velocity: Vector3 = field(default_factory=lambda: Vector3())
    acceleration: Vector3 = field(default_factory=lambda: Vector3())
    mass: float = 1.0
    use_gravity: bool = True
    elasticity: float = 0.6
    show_velocity_vector: bool = False
    friction: float = 0.1

    def to_dict(self):
        return {
            "velocity": self.velocity.to_dict(),
            "acceleration": self.acceleration.to_dict(),
            "mass": self.mass,
            "use_gravity": self.use_gravity,
            "elasticity": self.elasticity,
            "show_velocity_vector": self.show_velocity_vector,
            "friction": self.friction,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            velocity=Vector3.from_dict(data.get("velocity", {})),
            acceleration=Vector3.from_dict(data.get("acceleration", {})),
            mass=data.get("mass", 1.0),
            use_gravity=data.get("use_gravity", True),
            elasticity=data.get("elasticity", 0.6),
            show_velocity_vector=data.get("show_velocity_vector", False),
            friction=data.get("friction", 0.1),
        )


@dataclass
class SimulatedObject:
    """Object in the Mental Matrix simulation"""
    id: str
    object_type: str
    position: Vector3 = field(default_factory=Vector3)
    rotation: Vector3 = field(default_factory=Vector3)
    scale: Vector3 = field(default_factory=lambda: Vector3(1, 1, 1))
    color: int = 0x4CAF50
    physics: PhysicsBody = field(default_factory=PhysicsBody)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(datetime.UTC).isoformat())

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.object_type,
            "position": self.position.to_dict(),
            "rotation": self.rotation.to_dict(),
            "scale": self.scale.to_dict(),
            "color": self.color,
            "physics": self.physics.to_dict(),
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data["id"],
            object_type=data.get("type", "cube"),
            position=Vector3.from_dict(data.get("position", {})),
            rotation=Vector3.from_dict(data.get("rotation", {})),
            scale=Vector3.from_dict(data.get("scale", {"x": 1, "y": 1, "z": 1})),
            color=data.get("color", 0x4CAF50),
            physics=PhysicsBody.from_dict(data.get("physics", {})),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.now(datetime.UTC).isoformat()),
        )


class MentalMatrixSimulation:
    """Agent's internal Mental Matrix simulation powered by world model predictions"""

    GRAVITY = 9.81
    GROUND_LEVEL = 0.0

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.objects: Dict[str, SimulatedObject] = {}
        self.is_running = False
        self.time_scale = 1.0
        self.elapsed_time = 0.0
        self.frame_count = 0
        self.observers: List[Callable] = []
        self.state_history: List[Dict] = []
        self.max_history = 1000

    def add_object(
        self,
        object_type: str = "cube",
        position: Optional[Vector3] = None,
        color: Optional[int] = None,
        physics: Optional[PhysicsBody] = None,
        metadata: Optional[Dict] = None,
    ) -> SimulatedObject:
        """Add object to simulation"""
        obj_id = f"{object_type}_{len(self.objects)}_{self.frame_count}"

        obj = SimulatedObject(
            id=obj_id,
            object_type=object_type,
            position=position or Vector3(0, 5, 0),
            color=color or 0x4CAF50,
            physics=physics or PhysicsBody(),
            metadata=metadata or {},
        )

        self.objects[obj_id] = obj
        log.info(f"[Mental Matrix] Added object: {obj_id}")
        self._notify_observers("object_added", obj.to_dict())
        return obj

    def remove_object(self, obj_id: str) -> bool:
        """Remove object from simulation"""
        if obj_id in self.objects:
            self.objects.pop(obj_id)
            log.info(f"[Mental Matrix] Removed object: {obj_id}")
            self._notify_observers("object_removed", {"id": obj_id})
            return True
        return False

    def apply_impulse(self, obj_id: str, force: Vector3) -> bool:
        """Apply impulse to object"""
        if obj_id not in self.objects:
            return False

        obj = self.objects[obj_id]
        obj.physics.velocity.x += force.x
        obj.physics.velocity.y += force.y
        obj.physics.velocity.z += force.z
        return True

    def update(self, dt: float = 1.0 / 60.0) -> None:
        """Update simulation by one frame"""
        if not self.is_running:
            return

        dt *= self.time_scale
        self.elapsed_time += dt
        self.frame_count += 1

        for obj in self.objects.values():
            if obj.physics.use_gravity:
                obj.physics.velocity.y -= self.GRAVITY * dt

            obj.position.x += obj.physics.velocity.x * dt
            obj.position.y += obj.physics.velocity.y * dt
            obj.position.z += obj.physics.velocity.z * dt

            friction_factor = 1.0 - (obj.physics.friction * dt)
            obj.physics.velocity.x *= friction_factor
            obj.physics.velocity.z *= friction_factor

            if obj.position.y <= self.GROUND_LEVEL + 1:
                obj.position.y = self.GROUND_LEVEL + 1
                obj.physics.velocity.y *= -obj.physics.elasticity

                if abs(obj.physics.velocity.y) < 0.1:
                    obj.physics.velocity.y = 0

        self._record_state()

    def _record_state(self) -> None:
        """Record current simulation state"""
        state = {
            "frame": self.frame_count,
            "elapsed_time": self.elapsed_time,
            "objects": [obj.to_dict() for obj in self.objects.values()],
        }
        self.state_history.append(state)
        if len(self.state_history) > self.max_history:
            self.state_history.pop(0)
        self._notify_observers("frame_update", state)

    def set_running(self, running: bool) -> None:
        """Start/stop simulation"""
        self.is_running = running
        self._notify_observers("state_changed", {"is_running": running})

    def reset(self) -> None:
        """Reset simulation"""
        self.objects.clear()
        self.elapsed_time = 0.0
        self.frame_count = 0
        self.state_history.clear()
        self._notify_observers("simulation_reset", {})

    def to_dict(self) -> Dict:
        """Export simulation state"""
        return {
            "agent_id": self.agent_id,
            "is_running": self.is_running,
            "frame": self.frame_count,
            "elapsed_time": self.elapsed_time,
            "time_scale": self.time_scale,
            "objects": [obj.to_dict() for obj in self.objects.values()],
            "object_count": len(self.objects),
        }

    def from_dict(self, data: Dict) -> None:
        """Import simulation state"""
        self.objects.clear()
        for obj_data in data.get("objects", []):
            self.objects[obj_data["id"]] = SimulatedObject.from_dict(obj_data)

    def subscribe(self, callback: Callable) -> None:
        """Subscribe to simulation events"""
        self.observers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """Unsubscribe from events"""
        if callback in self.observers:
            self.observers.remove(callback)

    def _notify_observers(self, event_type: str, data: Any) -> None:
        """Notify observers of event"""
        for callback in self.observers:
            try:
                callback({
                    "type": event_type,
                    "agent_id": self.agent_id,
                    "timestamp": datetime.now(datetime.UTC).isoformat(),
                    "data": data,
                })
            except Exception as e:
                log.error(f"Observer notification error: {e}")


class MentalMatrixService:
    """Service managing agent mental matrix simulations"""

    def __init__(self):
        self.simulations: Dict[str, MentalMatrixSimulation] = {}
        self.update_interval = 1.0 / 60.0
        self.update_task = None

    def get_or_create_simulation(self, agent_id: str) -> MentalMatrixSimulation:
        """Get or create simulation for agent"""
        if agent_id not in self.simulations:
            sim = MentalMatrixSimulation(agent_id)
            self.simulations[agent_id] = sim
        return self.simulations[agent_id]

    def get_simulation(self, agent_id: str) -> Optional[MentalMatrixSimulation]:
        """Get existing simulation"""
        return self.simulations.get(agent_id)

    def remove_simulation(self, agent_id: str) -> bool:
        """Remove simulation"""
        if agent_id in self.simulations:
            self.simulations.pop(agent_id)
            return True
        return False

    async def start_update_loop(self) -> None:
        """Start update loop for all simulations"""
        while True:
            try:
                for sim in self.simulations.values():
                    sim.update(self.update_interval)
                await asyncio.sleep(self.update_interval)
            except Exception as e:
                log.error(f"Update loop error: {e}")
                await asyncio.sleep(0.1)

    def export_simulation(self, agent_id: str, output_path: Path) -> bool:
        """Export simulation to file"""
        sim = self.get_simulation(agent_id)
        if not sim:
            return False
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(sim.to_dict(), f, indent=2)
            return True
        except Exception as e:
            log.error(f"Export error: {e}")
            return False

    def import_simulation(self, agent_id: str, input_path: Path) -> bool:
        """Import simulation from file"""
        if not input_path.exists():
            return False
        try:
            with open(input_path, "r") as f:
                data = json.load(f)
            sim = self.get_or_create_simulation(agent_id)
            sim.from_dict(data)
            return True
        except Exception as e:
            log.error(f"Import error: {e}")
            return False


# Global Mental Matrix service
_mental_matrix_service = None

def get_mental_matrix_service() -> MentalMatrixService:
    """Get or create global Mental Matrix service"""
    global _mental_matrix_service
    if _mental_matrix_service is None:
        _mental_matrix_service = MentalMatrixService()
    return _mental_matrix_service


# ============================================================================
# Mental Matrix WebSocket Manager
# ============================================================================

class MentalMatrixWebSocketManager:
    """Manages WebSocket connections for real-time mental matrix updates"""

    def __init__(self):
        self.active_connections: Dict[str, Dict[str, Any]] = {}
        self.subscriptions: Dict[str, Set[str]] = {}
        # FIX: track per-client callbacks so we can unsubscribe on disconnect
        self._callbacks: Dict[str, Dict[str, Callable]] = {}
        self.service = get_mental_matrix_service()

    async def connect(self, websocket, agent_id: str, client_id: str):
        """Register new WebSocket connection"""
        await websocket.accept()

        if agent_id not in self.active_connections:
            self.active_connections[agent_id] = {}
            self.subscriptions[agent_id] = set()
            self._callbacks[agent_id] = {}

        self.active_connections[agent_id][client_id] = websocket
        self.subscriptions[agent_id].add(client_id)

        sim = self.service.get_or_create_simulation(agent_id)

        # FIX: store the callback reference so we can unsubscribe it later
        def on_simulation_event(event):
            asyncio.create_task(self.broadcast(agent_id, event))

        self._callbacks[agent_id][client_id] = on_simulation_event
        sim.subscribe(on_simulation_event)

        log.info(f"[Mental Matrix] Connected: {agent_id}/{client_id}")

        await websocket.send_json({
            "type": "connected",
            "agent_id": agent_id,
            "message": "Connected to Mental Matrix",
            "simulation": sim.to_dict(),
        })

    async def disconnect(self, agent_id: str, client_id: str):
        """Unregister WebSocket connection"""
        # FIX: unsubscribe the stored callback to prevent memory/callback leak
        if agent_id in self._callbacks and client_id in self._callbacks[agent_id]:
            callback = self._callbacks[agent_id].pop(client_id)
            sim = self.service.get_simulation(agent_id)
            if sim:
                sim.unsubscribe(callback)

        if agent_id in self.active_connections:
            self.active_connections[agent_id].pop(client_id, None)
            self.subscriptions[agent_id].discard(client_id)

            if not self.active_connections[agent_id]:
                self.active_connections.pop(agent_id)
                self.subscriptions.pop(agent_id, None)
                self._callbacks.pop(agent_id, None)

        log.info(f"[Mental Matrix] Disconnected: {agent_id}/{client_id}")

    async def broadcast(self, agent_id: str, message: Dict[str, Any]):
        """Broadcast message to all clients"""
        if agent_id not in self.active_connections:
            return

        disconnected = []
        for client_id, websocket in self.active_connections[agent_id].items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                log.warning(f"Error broadcasting to {client_id}: {e}")
                disconnected.append(client_id)

        for client_id in disconnected:
            await self.disconnect(agent_id, client_id)

    async def handle_message(self, agent_id: str, client_id: str, message: Dict[str, Any]):
        """Handle incoming command"""
        try:
            msg_type = message.get("type")
            data = message.get("data", {})

            sim = self.service.get_simulation(agent_id)
            if not sim:
                await self.send_error(agent_id, client_id, "Simulation not found")
                return

            if msg_type == "add_object":
                await self._handle_add_object(sim, agent_id, data)
            elif msg_type == "remove_object":
                await self._handle_remove_object(sim, agent_id, data)
            elif msg_type == "apply_impulse":
                await self._handle_apply_impulse(sim, agent_id, data)
            elif msg_type == "set_running":
                sim.set_running(data.get("running", False))
            elif msg_type == "reset":
                sim.reset()
            elif msg_type == "set_time_scale":
                sim.time_scale = data.get("time_scale", 1.0)
            elif msg_type == "update_object":
                await self._handle_update_object(sim, agent_id, data)
            elif msg_type == "export":
                await self._handle_export(sim, agent_id, data)
            elif msg_type == "import":
                await self._handle_import(sim, agent_id, data)
            else:
                await self.send_error(agent_id, client_id, f"Unknown command: {msg_type}")
        except Exception as e:
            log.error(f"Error handling message: {e}")
            await self.send_error(agent_id, client_id, str(e))

    async def _handle_add_object(self, sim, agent_id: str, data: Dict):
        obj_type = data.get("type", "cube")
        position = Vector3.from_dict(data.get("position", {}))
        color = data.get("color", 0x4CAF50)
        physics_data = data.get("physics", {})
        physics = PhysicsBody.from_dict(physics_data) if physics_data else PhysicsBody()

        obj = sim.add_object(
            object_type=obj_type,
            position=position,
            color=color,
            physics=physics,
            metadata=data.get("metadata", {}),
        )

        await self.broadcast(agent_id, {
            "type": "object_added",
            "agent_id": agent_id,
            "object": obj.to_dict(),
        })

    async def _handle_remove_object(self, sim, agent_id: str, data: Dict):
        obj_id = data.get("id")
        if sim.remove_object(obj_id):
            await self.broadcast(agent_id, {
                "type": "object_removed",
                "agent_id": agent_id,
                "id": obj_id,
            })

    async def _handle_apply_impulse(self, sim, agent_id: str, data: Dict):
        obj_id = data.get("id")
        force = Vector3.from_dict(data.get("force", {}))
        sim.apply_impulse(obj_id, force)

    async def _handle_update_object(self, sim, agent_id: str, data: Dict):
        obj_id = data.get("id")
        if obj_id in sim.objects:
            obj = sim.objects[obj_id]
            if "position" in data:
                obj.position = Vector3.from_dict(data["position"])
            if "velocity" in data:
                obj.physics.velocity = Vector3.from_dict(data["velocity"])
            if "color" in data:
                obj.color = data["color"]

            await self.broadcast(agent_id, {
                "type": "object_updated",
                "agent_id": agent_id,
                "object": obj.to_dict(),
            })

    async def _handle_export(self, sim, agent_id: str, data: Dict):
        await self.broadcast(agent_id, {
            "type": "export_data",
            "agent_id": agent_id,
            "data": sim.to_dict(),
        })

    async def _handle_import(self, sim, agent_id: str, data: Dict):
        sim.from_dict(data.get("data", {}))
        await self.broadcast(agent_id, {
            "type": "import_complete",
            "agent_id": agent_id,
            "simulation": sim.to_dict(),
        })

    async def send_error(self, agent_id: str, client_id: str, error: str):
        """Send error message"""
        if (agent_id in self.active_connections and
            client_id in self.active_connections[agent_id]):
            try:
                await self.active_connections[agent_id][client_id].send_json({
                    "type": "error",
                    "agent_id": agent_id,
                    "error": error,
                })
            except Exception as e:
                log.error(f"Error sending error message: {e}")


_mental_matrix_websocket_manager = None


def get_mental_matrix_manager() -> MentalMatrixWebSocketManager:
    """Get or create global WebSocket manager instance"""
    global _mental_matrix_websocket_manager
    if _mental_matrix_websocket_manager is None:
        _mental_matrix_websocket_manager = MentalMatrixWebSocketManager()
    return _mental_matrix_websocket_manager


# ============================================================================
# Mental Matrix Agent Client
# ============================================================================

class MentalMatrixAgentClient:
    """Client for agents to interact with Mental Matrix simulation"""

    def __init__(self, agent_id: str, backend_url: str = "http://127.0.0.1:8000"):
        self.agent_id = agent_id
        self.backend_url = backend_url
        self.ws_url = backend_url.replace("http", "ws")
        self.websocket = None
        self.session = None

    async def connect(self) -> bool:
        """Connect to Mental Matrix WebSocket"""
        try:
            import aiohttp
            self.session = aiohttp.ClientSession()
            ws_endpoint = f"{self.ws_url}/mental-matrix/ws"
            self.websocket = await self.session.ws_connect(ws_endpoint)

            await self.websocket.send_json({
                "type": "connect",
                "agent_id": self.agent_id,
            })

            msg = await self.websocket.receive_json()
            log.info(f"[Mental Matrix] Connected: {msg}")
            return True
        except Exception as e:
            log.error(f"Failed to connect to Mental Matrix: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Mental Matrix"""
        if self.websocket:
            await self.websocket.close()
        if self.session:
            await self.session.close()

    async def add_object(
        self,
        object_type: str = "cube",
        position: Optional[Dict[str, float]] = None,
        color: Optional[int] = None,
        physics: Optional[Dict] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Add object to mental simulation"""
        try:
            command = {
                "type": "add_object",
                "data": {
                    "type": object_type,
                    "position": position or {"x": 0, "y": 5, "z": 0},
                    "color": color or 0x4CAF50,
                    "physics": physics or {},
                    "metadata": metadata or {},
                },
            }
            await self.send_command(command)
            return True
        except Exception as e:
            log.error(f"Error adding object: {e}")
            return False

    async def simulate_scenario(
        self,
        scenario_name: str,
        duration_seconds: float = 5.0,
        objects: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Run a simulation scenario"""
        try:
            await self.send_command({"type": "reset"})

            if objects:
                for obj in objects:
                    await self.add_object(**obj)

            await self.send_command({"type": "set_running", "data": {"running": True}})
            await asyncio.sleep(duration_seconds)
            await self.send_command({"type": "set_running", "data": {"running": False}})

            results = await self.send_command({"type": "export"})
            return results
        except Exception as e:
            log.error(f"Error running scenario: {e}")
            return {}

    async def test_physics_interaction(
        self,
        object1_type: str = "cube",
        object2_type: str = "sphere",
    ) -> Dict[str, Any]:
        """Test how two objects interact physically"""
        try:
            await self.send_command({"type": "reset"})

            await self.add_object(
                object_type=object1_type,
                position={"x": -5, "y": 2, "z": 0},
                color=0xFF6B6B,
            )
            await self.add_object(
                object_type=object2_type,
                position={"x": 5, "y": 2, "z": 0},
                color=0x4ECDC4,
            )

            await self.send_command({"type": "set_running", "data": {"running": True}})
            await asyncio.sleep(3.0)

            results = await self.send_command({"type": "export"})
            return results
        except Exception as e:
            log.error(f"Error testing physics: {e}")
            return {}

    async def send_command(self, command: Dict[str, Any]) -> Optional[Dict]:
        """Send command to Mental Matrix"""
        try:
            if not self.websocket:
                log.error("WebSocket not connected")
                return None

            await self.websocket.send_json(command)
            response = await self.websocket.receive_json()
            return response
        except Exception as e:
            log.error(f"Error sending command: {e}")
            return None

    async def listen_for_updates(self, callback):
        """Listen for simulation updates"""
        try:
            while self.websocket and not self.websocket.closed:
                msg = await self.websocket.receive_json()
                callback(msg)
        except Exception as e:
            log.error(f"Error listening for updates: {e}")

    async def export_simulation(self, output_path: Path) -> bool:
        """Export simulation to file"""
        try:
            result = await self.send_command({"type": "export"})
            if result and "data" in result:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "w") as f:
                    json.dump(result["data"], f, indent=2)
                log.info(f"Exported simulation to {output_path}")
                return True
        except Exception as e:
            log.error(f"Error exporting simulation: {e}")
        return False

    async def import_simulation(self, input_path: Path) -> bool:
        """Import simulation from file"""
        try:
            if not input_path.exists():
                log.error(f"File not found: {input_path}")
                return False

            with open(input_path, "r") as f:
                data = json.load(f)

            command = {"type": "import", "data": data}
            result = await self.send_command(command)
            log.info(f"Imported simulation from {input_path}")
            return result is not None
        except Exception as e:
            log.error(f"Error importing simulation: {e}")
        return False


# ============================================================================
# Multimodal Encoders
# ============================================================================

class VisionEncoder(nn.Module):
    """CNN encoder for visual observations"""

    def __init__(self, channels: int, output_dim: int):
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv2d(channels, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(32),

            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(64),

            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(128),

            nn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(256),
        )

        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(256, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        has_time = len(x.shape) == 5

        if has_time:
            B, T = x.shape[:2]
            x = x.view(B * T, *x.shape[2:])

        x = self.conv(x)
        x = self.pool(x)
        x = x.flatten(1)
        x = self.fc(x)

        if has_time:
            x = x.view(B, T, -1)

        return x


class AudioEncoder(nn.Module):
    """1D CNN encoder for audio spectrograms"""

    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=8, stride=4, padding=2),
            nn.ReLU(),
            nn.BatchNorm1d(32),

            nn.Conv1d(32, 64, kernel_size=4, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm1d(64),

            nn.Conv1d(64, 128, kernel_size=4, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm1d(128),
        )

        self.pool = nn.AdaptiveAvgPool1d(1)
        self.fc = nn.Linear(128, output_dim)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        has_time = len(x.shape) == 3

        if has_time:
            B, T = x.shape[:2]
            x = x.view(B * T, 1, -1)
        else:
            x = x.unsqueeze(1)

        x = self.conv(x)
        x = self.pool(x)
        x = x.flatten(1)
        x = self.fc(x)

        if has_time:
            x = x.view(B, T, -1)

        return x


class ProprioceptionEncoder(nn.Module):
    """MLP encoder for proprioceptive state (health, position, etc.)"""

    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()

        self.mlp = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.LayerNorm(128),
            nn.Linear(128, 256),
            nn.ReLU(),
            nn.LayerNorm(256),
            nn.Linear(256, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)


class ActionEncoder(nn.Module):
    """Encoder for actions"""

    def __init__(self, action_dim: int, output_dim: int):
        super().__init__()

        self.mlp = nn.Sequential(
            nn.Linear(action_dim, 128),
            nn.ReLU(),
            nn.Linear(128, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)


# ============================================================================
# Transformer Core
# ============================================================================

class TransformerBlock(nn.Module):
    """Transformer block with causal masking"""

    def __init__(self, d_model: int, n_heads: int, d_ff: int, dropout: float):
        super().__init__()

        self.attention = nn.MultiheadAttention(
            d_model, n_heads, dropout=dropout, batch_first=True
        )
        self.norm1 = nn.LayerNorm(d_model)

        self.ff = nn.Sequential(
            nn.Linear(d_model, d_ff),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(d_ff, d_model),
            nn.Dropout(dropout)
        )
        self.norm2 = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        attn_out, _ = self.attention(x, x, x, attn_mask=mask)
        x = self.norm1(x + attn_out)

        ff_out = self.ff(x)
        x = self.norm2(x + ff_out)

        return x


class WorldModelTransformer(nn.Module):
    """Transformer-based sequence model for world dynamics"""

    def __init__(self, config: WorldModelConfig):
        super().__init__()

        self.config = config
        self.d_model = config.d_model

        # Multimodal encoders
        self.vision_encoder = VisionEncoder(config.vision_channels, config.d_model)
        self.audio_encoder = AudioEncoder(config.audio_dim, config.d_model)
        self.proprio_encoder = ProprioceptionEncoder(config.proprio_dim, config.d_model)
        self.action_encoder = ActionEncoder(config.action_dim, config.d_model)

        # Positional encoding
        self.pos_embedding = nn.Parameter(
            torch.randn(1, 1000, config.d_model) * 0.02
        )

        # Transformer layers
        self.blocks = nn.ModuleList([
            TransformerBlock(config.d_model, config.n_heads, config.d_ff, config.dropout)
            for _ in range(config.n_layers)
        ])

        self.norm = nn.LayerNorm(config.d_model)

    def forward(self, encodings: torch.Tensor, mask: Optional[torch.Tensor] = None) -> torch.Tensor:
        B, T, D = encodings.shape

        x = encodings + self.pos_embedding[:, :T, :]

        for block in self.blocks:
            x = block(x, mask)

        x = self.norm(x)

        return x


# ============================================================================
# Variational Latent Space (Optional)
# ============================================================================

class VariationalEncoder(nn.Module):
    """VAE encoder for stochastic latent states"""

    def __init__(self, input_dim: int, latent_dim: int):
        super().__init__()

        self.fc_mu = nn.Linear(input_dim, latent_dim)
        self.fc_logvar = nn.Linear(input_dim, latent_dim)

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mu = self.fc_mu(x)
        logvar = self.fc_logvar(x)

        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std

        return z, mu, logvar


# ============================================================================
# Prediction Heads
# ============================================================================

class RewardPredictor(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)


class TerminationPredictor(nn.Module):
    def __init__(self, input_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
            nn.Sigmoid()
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)


class NextStatePredictor(nn.Module):
    # FIX: input_dim is pred_input_dim + action_dim, output_dim is pred_input_dim
    def __init__(self, input_dim: int, output_dim: int):
        super().__init__()
        self.mlp = nn.Sequential(
            nn.Linear(input_dim, 512),
            nn.ReLU(),
            nn.LayerNorm(512),
            nn.Linear(512, 512),
            nn.ReLU(),
            nn.LayerNorm(512),
            nn.Linear(512, output_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.mlp(x)


# ============================================================================
# Main World Model
# ============================================================================

class WorldModel(nn.Module):
    """
    Complete neural world model for AGI.

    Features:
    - Multimodal encoding (vision, audio, proprioception, actions)
    - Transformer sequence model
    - Predictive heads (reward, termination, next state)
    - Optional variational latent space
    - Ensemble for uncertainty estimation
    """

    def __init__(self, config: WorldModelConfig):
        super().__init__()

        self.config = config
        self.device = config.device

        # Core transformer
        self.transformer = WorldModelTransformer(config)

        # Variational encoding (optional)
        if config.use_vae:
            self.vae_encoder = VariationalEncoder(config.d_model, config.latent_dim)
            pred_input_dim = config.latent_dim
        else:
            self.vae_encoder = None
            pred_input_dim = config.d_model

        # Prediction heads
        # FIX: next_state_head input = pred_input_dim + raw action_dim (not re-encoded)
        self.reward_head = RewardPredictor(pred_input_dim)
        self.termination_head = TerminationPredictor(pred_input_dim)
        self.next_state_head = NextStatePredictor(
            pred_input_dim + config.action_dim, pred_input_dim
        )

        self.optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=config.learning_rate,
            weight_decay=1e-5
        )

        self.loss_history = deque(maxlen=1000)

        self.to(self.device)

        log.info(f"WorldModel initialized: {sum(p.numel() for p in self.parameters())/1e6:.2f}M parameters")

    def encode_observation(self, observation: Dict[str, torch.Tensor]) -> torch.Tensor:
        """
        Encode multimodal observation into unified representation.

        Args:
            observation: dict with keys:
                - 'vision': (B, T, C, H, W) or None
                - 'audio': (B, T, audio_dim) or None
                - 'proprio': (B, T, proprio_dim)
                - 'action': (B, T, action_dim)  -- encoded here via action_encoder

        Returns:
            encoding: (B, T, d_model)
        """
        encodings = []

        if 'vision' in observation and observation['vision'] is not None:
            encodings.append(self.transformer.vision_encoder(observation['vision']))

        if 'audio' in observation and observation['audio'] is not None:
            encodings.append(self.transformer.audio_encoder(observation['audio']))

        if 'proprio' in observation:
            encodings.append(self.transformer.proprio_encoder(observation['proprio']))

        if 'action' in observation:
            encodings.append(self.transformer.action_encoder(observation['action']))

        # Sum encoded modalities into single representation
        encoding = torch.stack(encodings, dim=0).sum(dim=0)

        return encoding

    def forward(self, observation: Dict[str, torch.Tensor],
                return_latent: bool = False) -> Dict[str, torch.Tensor]:
        """
        Forward pass: predict rewards, termination, next states.

        Args:
            observation: multimodal observation dict
            return_latent: whether to return latent states

        Returns:
            predictions dict with 'reward', 'termination', 'next_state',
            and optionally 'latent', 'mu', 'logvar'.
        """
        encoding = self.encode_observation(observation)

        T = encoding.shape[1]
        mask = torch.triu(torch.ones(T, T, device=self.device) * float('-inf'), diagonal=1)

        context = self.transformer(encoding, mask)

        if self.config.use_vae:
            latent, mu, logvar = self.vae_encoder(context)
            pred_input = latent
        else:
            pred_input = context
            mu, logvar = None, None

        reward_pred = self.reward_head(pred_input)
        termination_pred = self.termination_head(pred_input)

        # FIX: concatenate raw action tensor (not re-encoded) with pred_input.
        # The action has already been encoded into pred_input via encode_observation;
        # here we pass the raw action so the next-state head can condition on the
        # exact intended action without going through another learned transform.
        next_state_pred = None
        if 'action' in observation:
            raw_action = observation['action']  # (B, T, action_dim)
            next_state_input = torch.cat([pred_input, raw_action], dim=-1)
            next_state_pred = self.next_state_head(next_state_input)

        predictions = {
            'reward': reward_pred,
            'termination': termination_pred,
            'next_state': next_state_pred,
        }

        if return_latent and self.config.use_vae:
            predictions['latent'] = latent
            predictions['mu'] = mu
            predictions['logvar'] = logvar

        return predictions

    def imagine(self, initial_obs: Dict[str, torch.Tensor],
                actions: torch.Tensor, steps: int) -> Dict[str, torch.Tensor]:
        """
        Imagine future trajectories by rolling out the world model.

        Args:
            initial_obs: starting observation dict (each value shaped [B, T, ...])
            actions: (B, steps, action_dim) planned actions
            steps: number of steps to imagine

        Returns:
            trajectory dict with imagined rewards, terminations, states
        """
        imagined_rewards = []
        imagined_terminations = []
        imagined_states = []

        # Take the last timestep of each modality as the starting context
        current_obs = {k: v[:, -1:, ...] for k, v in initial_obs.items()
                       if k not in ('reward', 'termination')}

        for t in range(steps):
            current_obs['action'] = actions[:, t:t+1, :]

            with torch.no_grad():
                pred = self.forward(current_obs, return_latent=True)

            imagined_rewards.append(pred['reward'])
            imagined_terminations.append(pred['termination'])

            # FIX: use next_state_pred to update the proprio-equivalent slot.
            # next_state is (B, 1, pred_input_dim). We project it back to proprio_dim
            # via a separate projection, OR — simpler and correct — we store the full
            # latent as the new 'latent_state' key and rebuild proprio from it.
            # Here we store the raw latent and feed it back as the new proprio by
            # zero-padding / truncating to proprio_dim so ProprioceptionEncoder
            # sees the right shape.  A learned projection head is the right long-term
            # solution; this keeps the loop runnable without extra parameters.
            next_state = pred['next_state']  # (B, 1, pred_input_dim)
            proprio_dim = self.config.proprio_dim

            if next_state is not None:
                if next_state.shape[-1] >= proprio_dim:
                    # Truncate to proprio_dim
                    current_obs['proprio'] = next_state[..., :proprio_dim]
                else:
                    # Pad to proprio_dim
                    pad_size = proprio_dim - next_state.shape[-1]
                    current_obs['proprio'] = F.pad(next_state, (0, pad_size))

            imagined_states.append(next_state if next_state is not None
                                   else pred.get('latent', pred['reward']))

        return {
            'rewards': torch.cat(imagined_rewards, dim=1),
            'terminations': torch.cat(imagined_terminations, dim=1),
            'states': torch.cat(imagined_states, dim=1),
        }

    def compute_loss(self, observation: Dict[str, torch.Tensor],
                     targets: Dict[str, torch.Tensor]) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Compute training loss.

        Args:
            observation: multimodal observation dict
            targets: dict with 'reward', 'termination', optionally 'next_state'

        Returns:
            total_loss, loss_dict
        """
        pred = self.forward(observation, return_latent=True)

        losses = {}

        # Reward loss
        reward_loss = F.mse_loss(pred['reward'], targets['reward'])
        losses['reward'] = reward_loss.item()

        # Termination loss
        termination_loss = F.binary_cross_entropy(
            pred['termination'], targets['termination']
        )
        losses['termination'] = termination_loss.item()

        # FIX: keep next_state_loss as a tensor (zeros_like) so the sum stays
        # in the autograd graph and dtype is consistent.
        if pred['next_state'] is not None and 'next_state' in targets:
            next_state_loss = F.mse_loss(pred['next_state'], targets['next_state'])
            losses['next_state'] = next_state_loss.item()
        else:
            next_state_loss = torch.zeros(1, device=self.device, dtype=reward_loss.dtype)

        # FIX: same treatment for kl_loss — keep as tensor.
        if self.config.use_vae and pred.get('mu') is not None:
            mu = pred['mu']
            logvar = pred['logvar']
            kl_loss = -0.5 * torch.sum(
                1 + logvar - mu.pow(2) - logvar.exp(), dim=-1
            ).mean()
            losses['kl'] = kl_loss.item()
        else:
            kl_loss = torch.zeros(1, device=self.device, dtype=reward_loss.dtype)

        total_loss = (reward_loss + termination_loss
                      + next_state_loss + self.config.kl_weight * kl_loss)
        losses['total'] = total_loss.item()

        return total_loss, losses

    def train_step(self, batch: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """Single training step."""
        self.train()

        batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v
                 for k, v in batch.items()}

        observation = {
            'vision': batch.get('vision'),
            'audio': batch.get('audio'),
            'proprio': batch['proprio'],
            'action': batch['action'],
        }

        targets = {
            'reward': batch['reward'],
            'termination': batch['termination'],
            'next_state': batch.get('next_state'),
        }

        loss, loss_dict = self.compute_loss(observation, targets)

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.parameters(), self.config.grad_clip)
        self.optimizer.step()

        self.loss_history.append(loss_dict['total'])

        return loss_dict

    def save(self, path: str):
        """Save model checkpoint"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)

        torch.save({
            'config': self.config,
            'model_state_dict': self.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'loss_history': list(self.loss_history)
        }, path)

        log.info(f"WorldModel saved to {path}")

    @classmethod
    def load(cls, path: str, device: Optional[str] = None) -> 'WorldModel':
        """Load model checkpoint"""
        checkpoint = torch.load(path, map_location='cpu')

        config = checkpoint['config']
        if device:
            config.device = device

        model = cls(config)
        model.load_state_dict(checkpoint['model_state_dict'])
        model.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        model.loss_history = deque(checkpoint.get('loss_history', []), maxlen=1000)

        log.info(f"WorldModel loaded from {path}")

        return model

    def get_stats(self) -> Dict[str, Any]:
        return {
            'parameters': sum(p.numel() for p in self.parameters()),
            'trainable_parameters': sum(p.numel() for p in self.parameters() if p.requires_grad),
            'avg_loss': np.mean(list(self.loss_history)) if self.loss_history else 0.0,
            'device': str(self.device),
            'config': {
                'd_model': self.config.d_model,
                'n_layers': self.config.n_layers,
                'use_vae': self.config.use_vae,
                'latent_dim': self.config.latent_dim,
            }
        }


# ============================================================================
# Ensemble World Model
# ============================================================================

class EnsembleWorldModel:
    """Ensemble of world models for uncertainty estimation."""

    def __init__(self, config: WorldModelConfig, n_models: int = 5):
        self.config = config
        self.n_models = n_models
        self.models = [WorldModel(config) for _ in range(n_models)]
        log.info(f"EnsembleWorldModel initialized with {n_models} models")

    def forward(self, observation: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """Forward pass through ensemble, returning mean and std."""
        predictions = [model(observation) for model in self.models]

        rewards = torch.stack([p['reward'] for p in predictions], dim=0)
        terminations = torch.stack([p['termination'] for p in predictions], dim=0)

        ensemble_pred = {
            'reward_mean': rewards.mean(dim=0),
            'reward_std': rewards.std(dim=0),
            'termination_mean': terminations.mean(dim=0),
            'termination_std': terminations.std(dim=0),
        }

        # FIX: guard against next_state being None before stacking
        next_states = [p['next_state'] for p in predictions if p['next_state'] is not None]
        if len(next_states) == len(predictions):
            ns = torch.stack(next_states, dim=0)
            ensemble_pred['next_state_mean'] = ns.mean(dim=0)
            ensemble_pred['next_state_std'] = ns.std(dim=0)

        return ensemble_pred

    def train_step(self, batch: Dict[str, torch.Tensor]) -> List[Dict[str, float]]:
        return [model.train_step(batch) for model in self.models]

    def save(self, path: str):
        for i, model in enumerate(self.models):
            model.save(f"{path}_model_{i}.pt")

    @classmethod
    def load(cls, path: str, n_models: int = 5) -> 'EnsembleWorldModel':
        models = [WorldModel.load(f"{path}_model_{i}.pt") for i in range(n_models)]

        ensemble = cls.__new__(cls)
        ensemble.models = models
        ensemble.n_models = n_models
        ensemble.config = models[0].config

        return ensemble


# ============================================================================
# Utility Functions
# ============================================================================

def create_default_world_model(device: str = 'cuda') -> WorldModel:
    config = WorldModelConfig(device=device)
    return WorldModel(config)


def test_world_model():
    """Test world model with dummy data"""
    log.info("Testing WorldModel...")

    config = WorldModelConfig(device='cpu')
    model = WorldModel(config)

    B, T = 4, 16
    batch = {
        'vision': torch.randn(B, T, 3, 84, 84),
        'audio': torch.randn(B, T, 128),
        'proprio': torch.randn(B, T, 32),
        'action': torch.randn(B, T, 11),
        'reward': torch.randn(B, T, 1),
        'termination': torch.randint(0, 2, (B, T, 1)).float(),
    }

    log.info("Testing forward pass...")
    pred = model(batch)
    log.info(f"  Reward pred shape: {pred['reward'].shape}")
    log.info(f"  Termination pred shape: {pred['termination'].shape}")

    log.info("Testing training step...")
    loss_dict = model.train_step(batch)
    log.info(f"  Losses: {loss_dict}")

    log.info("Testing imagination...")
    initial_obs = {k: v[:, :4, ...] for k, v in batch.items()
                   if k not in ('reward', 'termination')}
    actions = torch.randn(B, 8, 11)
    imagined = model.imagine(initial_obs, actions, steps=8)
    log.info(f"  Imagined rewards shape: {imagined['rewards'].shape}")

    log.info("Testing save/load...")
    model.save('test_world_model.pt')
    loaded = WorldModel.load('test_world_model.pt', device='cpu')
    log.info(f"  Loaded model stats: {loaded.get_stats()}")

    log.info("✅ WorldModel tests passed!")


# ============================================================================
# Experience Replay Buffer
# ============================================================================

class WorldModelReplayBuffer:
    """Replay buffer optimized for world model training."""

    def __init__(self, capacity: int = 100000, sequence_length: int = 64):
        self.capacity = capacity
        self.sequence_length = sequence_length
        self.trajectories = deque(maxlen=capacity)
        self.current_trajectory = None
        log.info(f"WorldModelReplayBuffer initialized: capacity={capacity}, seq_len={sequence_length}")

    def start_trajectory(self):
        self.current_trajectory = {
            'vision': [], 'audio': [], 'proprio': [],
            'action': [], 'reward': [], 'termination': [],
        }

    def add_step(self, vision=None, audio=None, proprio=None,
                 action=None, reward=0.0, termination=False):
        if self.current_trajectory is None:
            self.start_trajectory()

        if vision is not None:
            self.current_trajectory['vision'].append(vision)
        if audio is not None:
            self.current_trajectory['audio'].append(audio)
        if proprio is not None:
            self.current_trajectory['proprio'].append(proprio)
        if action is not None:
            self.current_trajectory['action'].append(action)

        self.current_trajectory['reward'].append(reward)
        self.current_trajectory['termination'].append(float(termination))

    def end_trajectory(self):
        if self.current_trajectory is None:
            return

        trajectory = {}
        for key in ('proprio', 'action', 'reward', 'termination'):
            if self.current_trajectory[key]:
                trajectory[key] = np.array(self.current_trajectory[key])

        # FIX: only store vision/audio if ALL steps have them, preventing
        # mixed None/array lists that break np.array() later.
        for key in ('vision', 'audio'):
            items = self.current_trajectory[key]
            if items and len(items) == len(self.current_trajectory['reward']):
                trajectory[key] = np.array(items)

        if len(trajectory.get('reward', [])) >= self.sequence_length:
            self.trajectories.append(trajectory)

        self.current_trajectory = None

    def sample_batch(self, batch_size: int, device: str = 'cuda') -> Dict[str, torch.Tensor]:
        """Sample batch of sequences for training."""
        if len(self.trajectories) == 0:
            raise ValueError("Buffer is empty")

        # FIX: determine modality availability once, from the full buffer,
        # then only include a sample if that trajectory actually has the modality.
        has_vision = any('vision' in t for t in self.trajectories)
        has_audio = any('audio' in t for t in self.trajectories)

        batch: Dict[str, List] = {
            'proprio': [], 'action': [], 'reward': [], 'termination': [],
        }
        if has_vision:
            batch['vision'] = []
        if has_audio:
            batch['audio'] = []

        for _ in range(batch_size):
            traj = self.trajectories[np.random.randint(len(self.trajectories))]

            max_start = len(traj['reward']) - self.sequence_length
            start_idx = np.random.randint(max(max_start, 1)) if max_start > 0 else 0
            end_idx = start_idx + self.sequence_length

            batch['proprio'].append(traj['proprio'][start_idx:end_idx])
            batch['action'].append(traj['action'][start_idx:end_idx])
            batch['reward'].append(traj['reward'][start_idx:end_idx])
            batch['termination'].append(traj['termination'][start_idx:end_idx])

            if has_vision and 'vision' in traj:
                batch['vision'].append(traj['vision'][start_idx:end_idx])
            if has_audio and 'audio' in traj:
                batch['audio'].append(traj['audio'][start_idx:end_idx])

        batch_tensors = {}
        for key, value in batch.items():
            # FIX: skip modality lists that ended up empty (sparse trajectories)
            if value:
                batch_tensors[key] = torch.tensor(
                    np.array(value), dtype=torch.float32, device=device
                )

        batch_tensors['reward'] = batch_tensors['reward'].unsqueeze(-1)
        batch_tensors['termination'] = batch_tensors['termination'].unsqueeze(-1)

        return batch_tensors

    def __len__(self):
        return len(self.trajectories)

    def get_stats(self) -> Dict[str, Any]:
        if len(self.trajectories) == 0:
            return {'size': 0}

        lengths = [len(t['reward']) for t in self.trajectories]
        return {
            'size': len(self.trajectories),
            'avg_trajectory_length': np.mean(lengths),
            'max_trajectory_length': np.max(lengths),
            'min_trajectory_length': np.min(lengths),
            'total_steps': np.sum(lengths),
        }


# ============================================================================
# World Model Trainer
# ============================================================================

class WorldModelTrainer:
    """Trainer for world model with replay buffer management."""

    def __init__(self, world_model: WorldModel,
                 replay_buffer: WorldModelReplayBuffer,
                 batch_size: int = 32,
                 log_interval: int = 100):
        self.world_model = world_model
        self.replay_buffer = replay_buffer
        self.batch_size = batch_size
        self.log_interval = log_interval

        self.step_count = 0
        self.loss_history = deque(maxlen=1000)

        log.info("WorldModelTrainer initialized")

    def train_offline(self, num_steps: int = 1000) -> Dict[str, Any]:
        log.info(f"Starting offline training for {num_steps} steps...")

        if len(self.replay_buffer) == 0:
            log.warning("Replay buffer is empty, cannot train")
            return {}

        losses = []

        for step in range(num_steps):
            try:
                batch = self.replay_buffer.sample_batch(
                    self.batch_size, device=self.world_model.device
                )
                loss_dict = self.world_model.train_step(batch)
                losses.append(loss_dict)

                self.step_count += 1
                self.loss_history.append(loss_dict['total'])

                if (step + 1) % self.log_interval == 0:
                    avg_loss = np.mean([l['total'] for l in losses[-self.log_interval:]])
                    log.info(f"  Step {step+1}/{num_steps}: avg_loss={avg_loss:.4f}")

            except Exception as e:
                log.error(f"Training step failed: {e}")
                continue

        stats = {
            'total_steps': num_steps,
            'avg_total_loss': np.mean([l['total'] for l in losses]),
            'avg_reward_loss': np.mean([l['reward'] for l in losses]),
            'avg_termination_loss': np.mean([l['termination'] for l in losses]),
            'buffer_stats': self.replay_buffer.get_stats(),
        }

        if losses and 'next_state' in losses[0]:
            stats['avg_next_state_loss'] = np.mean([l['next_state'] for l in losses])
        if losses and 'kl' in losses[0]:
            stats['avg_kl_loss'] = np.mean([l['kl'] for l in losses])

        log.info(f"Offline training complete: {stats}")
        return stats

    def train_online_step(self, trajectory: Dict[str, np.ndarray] = None) -> Dict[str, float]:
        """
        Run one gradient step using buffered trajectories.

        FIX: The old implementation called start_trajectory() / end_trajectory()
        on self.replay_buffer before training.  self.replay_buffer is the SAME
        object as agent.world_model_buffer which _feed_world_model() continuously
        fills with live Minecraft frames.  Calling start_trajectory() reset the
        ongoing episode, discarding all steps accumulated since the last game death.

        The trajectory parameter is now ignored (kept for API compatibility).
        Training uses whatever complete episodes are already in the shared buffer.
        _feed_world_model() owns the write path; this method owns the read path.
        """
        if len(self.replay_buffer) < 1:
            return {'total': 0.0, 'skipped': 'buffer_empty'}

        try:
            batch = self.replay_buffer.sample_batch(
                self.batch_size, device=self.world_model.device
            )
            loss_dict = self.world_model.train_step(batch)
            self.step_count += 1
            self.loss_history.append(loss_dict['total'])
            return loss_dict
        except Exception as e:
            return {'total': 0.0, 'error': str(e)}

    def save_checkpoint(self, path: str):
        self.world_model.save(path)
        log.info(f"Trainer checkpoint saved to {path}")

    def get_stats(self) -> Dict[str, Any]:
        return {
            'step_count': self.step_count,
            'avg_recent_loss': np.mean(list(self.loss_history)) if self.loss_history else 0.0,
            'buffer_size': len(self.replay_buffer),
            'model_stats': self.world_model.get_stats(),
        }


# ============================================================================
# Integration with Existing Backend
# ============================================================================

def integrate_world_model_with_agent(agent):
    """Integrate world model into existing NPCAgent."""
    log.info(f"Integrating WorldModel with agent {agent.agent_id}...")

    config = WorldModelConfig(device='cuda' if torch.cuda.is_available() else 'cpu')
    world_model = WorldModel(config)
    replay_buffer = WorldModelReplayBuffer(capacity=50000, sequence_length=64)
    trainer = WorldModelTrainer(world_model, replay_buffer, batch_size=16)

    agent.world_model = world_model
    agent.world_model_buffer = replay_buffer
    agent.world_model_trainer = trainer

    original_evaluate = agent.brain.evaluate_event

    def neural_evaluate(event, context=None):
        try:
            observation = _build_observation_from_context(agent, context)
            with torch.no_grad():
                pred = world_model(observation)
            reward = pred['reward'][0, -1, 0].item()
            emotion_delta = agent.brain._reward_to_emotion_delta(reward, event)
            return reward, emotion_delta
        except Exception as e:
            log.warning(f"World model evaluation failed, using fallback: {e}")
            return original_evaluate(event, context)

    agent.brain.evaluate_event = neural_evaluate

    log.info(f"✅ WorldModel integrated with {agent.agent_id}")


def _build_observation_from_context(agent, context: Optional[Dict] = None) -> Dict[str, torch.Tensor]:
    """Build world model observation from agent context"""
    if context is None:
        context = {}

    device = agent.world_model.device if hasattr(agent, 'world_model') else 'cpu'

    proprio = np.array([
        context.get('health', agent.health) / 20.0,
        context.get('hunger', agent.hunger) / 20.0,
        context.get('saturation', 5.0) / 20.0,
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['x'] / 100.0,
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['y'] / 100.0,
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['z'] / 100.0,
        *agent.emotion.as_array().tolist(),
        *agent.personality.as_array().tolist(),
    ], dtype=np.float32)

    if len(proprio) < 32:
        proprio = np.pad(proprio, (0, 32 - len(proprio)))

    observation = {
        'proprio': torch.tensor(proprio, dtype=torch.float32, device=device).unsqueeze(0).unsqueeze(0),
    }

    if 'visual' in context and context['visual'] is not None:
        visual = context['visual']
        if isinstance(visual, np.ndarray):
            if visual.shape[:2] != (84, 84):
                import cv2
                visual = cv2.resize(visual, (84, 84))
            if len(visual.shape) == 2:
                visual = visual[:, :, np.newaxis]
            visual = torch.tensor(visual, dtype=torch.float32, device=device)
            visual = visual.permute(2, 0, 1) / 255.0
            observation['vision'] = visual.unsqueeze(0).unsqueeze(0)

    if 'audio' in context and context['audio'] is not None:
        audio = context['audio']
        if isinstance(audio, np.ndarray):
            if len(audio) < 128:
                audio = np.pad(audio, (0, 128 - len(audio)))
            elif len(audio) > 128:
                audio = audio[:128]
            observation['audio'] = torch.tensor(
                audio, dtype=torch.float32, device=device
            ).unsqueeze(0).unsqueeze(0)

    if hasattr(agent, 'last_action') and agent.last_action is not None:
        observation['action'] = torch.tensor(
            agent.last_action, dtype=torch.float32, device=device
        ).unsqueeze(0).unsqueeze(0)
    else:
        observation['action'] = torch.zeros(1, 1, 11, dtype=torch.float32, device=device)

    return observation


# ============================================================================
# Mental Matrix API Routes (FastAPI Integration)
# ============================================================================

def get_mental_matrix_router():
    """Get FastAPI router for Mental Matrix endpoints"""
    from fastapi import APIRouter, WebSocket, HTTPException, WebSocketDisconnect
    import uuid

    router = APIRouter(prefix="/mental-matrix", tags=["mental-matrix"])

    # FIX: resolve service/manager here so they're in scope for all route handlers
    service = get_mental_matrix_service()
    ws_manager = get_mental_matrix_manager()

    @router.post("/simulate/{agent_id}")
    async def simulate(agent_id: str, scenario: dict):
        try:
            sim = service.get_or_create_simulation(agent_id)

            objects = scenario.get("objects", [])
            duration = scenario.get("duration", 5.0)
            time_scale = scenario.get("time_scale", 1.0)

            sim.time_scale = time_scale
            sim.reset()

            for obj_data in objects:
                sim.add_object(
                    object_type=obj_data.get("type", "cube"),
                    position=Vector3.from_dict(obj_data.get("position", {})),
                    color=obj_data.get("color", 0x4CAF50),
                    physics=PhysicsBody.from_dict(obj_data.get("physics", {})),
                    metadata=obj_data.get("metadata", {}),
                )

            sim.set_running(True)
            frames = int(duration / (1.0 / 60.0))
            for _ in range(frames):
                sim.update(1.0 / 60.0)
                await asyncio.sleep(0.001)

            sim.set_running(False)
            return {"success": True, "agent_id": agent_id, "simulation": sim.to_dict()}
        except Exception as e:
            log.error(f"Simulation error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/status/{agent_id}")
    async def get_status(agent_id: str):
        try:
            sim = service.get_simulation(agent_id)
            if not sim:
                raise HTTPException(status_code=404, detail="Simulation not found")
            return {
                "agent_id": agent_id,
                "status": "running" if sim.is_running else "stopped",
                "simulation": sim.to_dict(),
            }
        except Exception as e:
            log.error(f"Status error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/add-object/{agent_id}")
    async def add_object(agent_id: str, obj_data: dict):
        try:
            sim = service.get_or_create_simulation(agent_id)
            obj = sim.add_object(
                object_type=obj_data.get("type", "cube"),
                position=Vector3.from_dict(obj_data.get("position", {})),
                color=obj_data.get("color", 0x4CAF50),
                physics=PhysicsBody.from_dict(obj_data.get("physics", {})),
                metadata=obj_data.get("metadata", {}),
            )
            return {"success": True, "agent_id": agent_id, "object": obj.to_dict()}
        except Exception as e:
            log.error(f"Add object error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/remove-object/{agent_id}/{obj_id}")
    async def remove_object(agent_id: str, obj_id: str):
        try:
            sim = service.get_simulation(agent_id)
            if not sim:
                raise HTTPException(status_code=404, detail="Simulation not found")
            success = sim.remove_object(obj_id)
            return {"success": success, "agent_id": agent_id, "object_id": obj_id}
        except Exception as e:
            log.error(f"Remove object error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/impulse/{agent_id}/{obj_id}")
    async def apply_impulse(agent_id: str, obj_id: str, force: dict):
        try:
            sim = service.get_simulation(agent_id)
            if not sim:
                raise HTTPException(status_code=404, detail="Simulation not found")
            success = sim.apply_impulse(obj_id, Vector3.from_dict(force))
            return {"success": success, "agent_id": agent_id, "object_id": obj_id}
        except Exception as e:
            log.error(f"Impulse error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/control/{agent_id}")
    async def control_simulation(agent_id: str, command: dict):
        try:
            sim = service.get_or_create_simulation(agent_id)
            cmd = command.get("command", "")

            if cmd == "start":
                sim.set_running(True)
            elif cmd == "stop":
                sim.set_running(False)
            elif cmd == "reset":
                sim.reset()
            elif cmd == "set_time_scale":
                sim.time_scale = command.get("value", 1.0)
            else:
                raise HTTPException(status_code=400, detail=f"Unknown command: {cmd}")

            return {"success": True, "agent_id": agent_id, "command": cmd}
        except Exception as e:
            log.error(f"Control error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        agent_id = None
        client_id = str(uuid.uuid4())

        try:
            initial_msg = await websocket.receive_json()
            agent_id = initial_msg.get("agent_id")

            if not agent_id:
                await websocket.send_json({"type": "error", "error": "agent_id required"})
                await websocket.close(code=1008)
                return

            await ws_manager.connect(websocket, agent_id, client_id)

            while True:
                msg = await websocket.receive_json()
                await ws_manager.handle_message(agent_id, client_id, msg)

        except WebSocketDisconnect:
            if agent_id:
                await ws_manager.disconnect(agent_id, client_id)
                log.info(f"[WebSocket] Disconnected: {agent_id}/{client_id}")
        except Exception as e:
            log.error(f"WebSocket error: {e}")
            if agent_id:
                await ws_manager.disconnect(agent_id, client_id)

    @router.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "active_simulations": len(service.simulations),
        }

    return router


def register_mental_matrix_api(app):
    """Register Mental Matrix routes with FastAPI app"""
    router = get_mental_matrix_router()
    app.include_router(router)

    # FIX: resolve service inside this function's scope, not from the router closure
    service = get_mental_matrix_service()

    @app.on_event("startup")
    async def startup():
        log.info("[Mental Matrix] Starting service update loop...")
        asyncio.create_task(service.start_update_loop())

    log.info("[Mental Matrix] API registered")


# ============================================================================
# Export
# ============================================================================

__all__ = [
    # World Model
    'WorldModel',
    'WorldModelConfig',
    'EnsembleWorldModel',
    'WorldModelReplayBuffer',
    'WorldModelTrainer',

    # Mental Matrix (integrated)
    'MentalMatrixSimulation',
    'MentalMatrixService',
    'MentalMatrixWebSocketManager',
    'MentalMatrixAgentClient',
    'SimulatedObject',
    'PhysicsBody',
    'Vector3',
    'get_mental_matrix_service',
    'get_mental_matrix_manager',
    'get_mental_matrix_router',
    'register_mental_matrix_api',

    # Integration
    'integrate_world_model_with_agent',
    'create_default_world_model',
    'test_world_model',
]


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
    )

    print("\n" + "=" * 70)
    print("  🌍 WORLD MODEL - Neural World Simulation")
    print("=" * 70 + "\n")

    test_world_model()

    print("\n" + "=" * 70)
    print("  ✅ WorldModel ready for AGI integration")
    print("=" * 70 + "\n")
