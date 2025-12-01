"""
Divine World AI Core Package

Core components for embodied AI agents with personality, emotions, and learning.
"""

__version__ = "1.0.0"

# Core agent components (no circular dependencies)
from .personality import Personality
from .emotion import EmotionSystem
from .memory import Memory, EpisodicMemory
from .brain_capsule import BrainCapsule

# Perception & Action
from .vision import VisionAdapter
from .actuators import ForgeIPCClient, ActuatorAdapterIsaacSim

# Learning components
from .reward_system import ImprovedRewardSystem
from .brain_core import BrainCore
from .planner import CognitivePlanner

# Agent (imports last to avoid circular deps)
from .agent import NPCAgent

__all__ = [
    "NPCAgent",
    "Personality", 
    "EmotionSystem",
    "Memory",
    "EpisodicMemory",
    "BrainCapsule",
    "VisionAdapter",
    "ForgeIPCClient",
    "ActuatorAdapterIsaacSim",
    "ImprovedRewardSystem",
    "BrainCore",
    "CognitivePlanner",
]
