"""
Divine World AI Core Package

Core components for embodied AI agents with personality, emotions, and learning.
All modules are self-contained for PyInstaller standalone agent executables.
"""
import sys
from pathlib import Path
# Add parent directory to path so ai_core can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

__version__ = "1.0.0"

# Configuration & Communication (must be first)
from ai_core.config import Config
from ai_core.communication_protocol import (
    PerceptionFrame, 
    ActionFrame, 
    compress_frame_to_jpeg,
    decompress_jpeg_to_frame
)
from ai_core import validation

# Core agent components (no circular dependencies)
from ai_core.personality import Personality
from ai_core.emotion import EmotionSystem
from ai_core.memory import Memory, EpisodicMemory
from ai_core.brain_capsule import BrainCapsule

# Perception & Action
from ai_core.vision import VisionAdapter
from ai_core.actuators import ForgeIPCClient, ActuatorAdapterIsaacSim
from ai_core.audio_processors import AudioProcessor
from ai_core.web_browser import WebBrowser, WebPage

# Learning components
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.brain_core import BrainCore
from ai_core.planner import CognitivePlanner

# Agent (imports last to avoid circular deps)
from ai_core.agent import NPCAgent

__all__ = [
    # Configuration
    "Config",
    
    # Communication
    "PerceptionFrame",
    "ActionFrame",
    "compress_frame_to_jpeg",
    "decompress_jpeg_to_frame",
    
    # Validation
    "validation",
    
    # Core
    "NPCAgent",
    "Personality", 
    "EmotionSystem",
    "Memory",
    "EpisodicMemory",
    "BrainCapsule",
    
    # Perception & Action
    "VisionAdapter",
    "ForgeIPCClient",
    "ActuatorAdapterIsaacSim",
    "ImprovedRewardSystem",
    "BrainCore",
    "CognitivePlanner",
    "WebBrowser",
    "WebPage",
    "AudioProcessor"
]