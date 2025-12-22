# ai_core/agent.py - COMPLETE UNIFIED VERSION
"""
Unified NPC Agent with Full Integration
========================================
Merges agent.py and aggent.py into single comprehensive implementation:
- UnifiedMemoryStore (ScyllaDB backend)
- Complete autonomous cognitive loop
- Transformer language learning
- World model integration
- Full persistence with BrainCapsule
"""

import torch
import numpy as np
import time
import logging
import asyncio
import sys
from typing import Dict, Any, Optional, List
from pathlib import Path

# Add parent directory to path so ai_core can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_core.personality import Personality, GenderType
from ai_core.emotion import EmotionSystem
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.brain_core import BrainCore
from ai_core.planner import CognitivePlanner

# UNIFIED MEMORY
from ai_core.unified_memory import UnifiedMemoryStore

# COGNITIVE LOOP
from ai_core.cognitive_loop import CognitiveLoop

log = logging.getLogger("agent")


class NPCAgent:
    """
    Fully autonomous NPC agent with:
    - UnifiedMemoryStore (ScyllaDB backend)
    - Cognitive loop (autonomous thinking)
    - Transformer language learning
    - World model integration
    - Complete persistence
    """

    def __init__(self,
                 agent_id: str,
                 gender: Optional[GenderType] = None,
                 persona_traits: Optional[Dict[str, float]] = None,
                 client_process=None,
                 autonomous: bool = True,
                 use_scylla: bool = True):
        
        self.agent_id = agent_id
        self.autonomous_mode = autonomous

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

        # State
        self.health = 20.0
        self.hunger = 20.0
        self.last_obs = None
        self.last_action = None
        self.step_count = 0

        # Client process info
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
        
        # COGNITIVE LOOP
        self.cognitive_loop = None
        self._init_world_model()
        self._init_audio_processor()
        if self.autonomous_mode:
            self._init_cognitive_loop()
        
        log.info(f"NPCAgent initialized: {agent_id} (gender: {gender}, autonomous: {autonomous})")
        
        try:
            from ai_core.web_browser import add_web_browsing_to_agent
            add_web_browsing_to_agent(self)
            log.info(f"[{self.agent_id}] Web browsing initialized")
        except Exception as e:
            log.warning(f"Web browsing not available: {e}")

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

    # ================================================================
    # ==================== AUTONOMOUS CONTROL ========================
    # ================================================================

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

    # ================================================================
    # =============== CORE INITIALIZATION METHODS ====================
    # ================================================================

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

    # ================================================================
    # ==================== NEURAL STACK INTEGRATION ==================
    # ================================================================

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

    # ================================================================
    # ===================== PERCEPTION & ACTION ======================
    # ================================================================

    def perceive(self, raw_observation: Dict[str, Any]) -> np.ndarray:
        """Convert raw observation to feature vector (50,)"""
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
        obs_parts.append(0.0)  # Placeholder for episodic memory

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
                return internal

        except Exception as e:
            log.error(f"Internal thought generation error: {e}")

        return None    
    
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
        """Convert action array to control dictionary"""
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
        return controls

    # ================================================================
    # ========================= LEARNING =============================
    # ================================================================

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

    # ================================================================
    # ========================= STATUS ===============================
    # ================================================================

    def is_alive(self) -> bool:
        if self.client_process:
            return self.client_process.is_alive
        return True

    def get_info(self) -> Dict[str, Any]:
        info = {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
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

    # ================================================================
    # ========================== SAVE/LOAD ===========================
    # ================================================================

    def save(self, path: str):
        """Save agent state with neural components"""
        from ai_core.brain_capsule import BrainCapsule

        # Get language state
        language_state = None
        if hasattr(self.brain, 'language'):
            language_state = self.brain.language.state_dict()

        capsule = BrainCapsule(
            metadata={
                'agent_id': self.agent_id,
                'agent_type': self.agent_type,
                'gender': self.personality.gender,
                'step_count': self.step_count,
                'saved_at': time.time(),
                'autonomous': self.autonomous_mode
            },
            personality=self.personality.to_dict(),
            emotion_snapshot=self.emotion.snapshot(),
            memory_snapshot=self.memory.recall(1000),
            language_state=language_state
        )

        # Save policy state
        if self.policy:
            capsule.model_state = self.policy.state_dict()

        # Neural stack persistence
        extra_model_state = {}

        try:
            if getattr(self, "world_model", None) is not None:
                if hasattr(self.world_model, "state_dict"):
                    extra_model_state['world_model'] = {
                        k: v.cpu() for k, v in self.world_model.state_dict().items()
                    }
        except Exception as e:
            log.exception(f"[{self.agent_id}] Error serializing neural stack: {e}")

        # Merge into capsule
        try:
            capsule_model_state = getattr(capsule, "model_state", {}) or {}
            capsule_model_state.update(extra_model_state)
            capsule.model_state = capsule_model_state
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to attach extra model_state: {e}")

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
                self.brain.language.load_state_dict(capsule.language_state)
                log.info(f"[{self.agent_id}] Language restored.")

        # Restore model weights
        if capsule.model_state and self.policy:
            self.policy.load_state_dict(capsule.model_state)

        # Restore neural stack
        try:
            saved_state = getattr(capsule, "model_state", {}) or {}
            if 'world_model' in saved_state:
                try:
                    from ai_core import world_model as wm_module
                except Exception:
                    wm_module = None
                
                wm_state = saved_state['world_model']
                if wm_module and hasattr(wm_module, "WorldModel"):
                    self.world_model = wm_module.WorldModel(agent_id=self.agent_id)
                    if hasattr(self.world_model, "load_state_dict"):
                        self.world_model.load_state_dict(wm_state)
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to restore neural stack: {e}")

        # Metadata
        self.step_count = capsule.metadata.get('step_count', 0)
        self.agent_type = capsule.metadata.get('agent_type', 'npc')
        self.autonomous_mode = capsule.metadata.get('autonomous', True)

        log.info(f"[{self.agent_id}] Loaded from {path}")

    # ================================================================
    # ====================== CLEANUP =================================
    # ================================================================

    async def shutdown(self):
        """Graceful shutdown"""
        # Stop cognitive loop
        if self.cognitive_loop:
            await self.stop_autonomous_mode()
        
        # Save state
        brain_path = Path(f"data/brains/{self.agent_id}/brain.pcap")
        brain_path.parent.mkdir(parents=True, exist_ok=True)
        self.save(str(brain_path))
        
        # Close memory backend
        if hasattr(self.memory, 'close'):
            self.memory.close()
        
        log.info(f"[{self.agent_id}] Shutdown complete")


# =============================================================================
# HELPER: Run agent autonomously
# =============================================================================

async def run_autonomous_agent(agent: NPCAgent, duration: Optional[float] = None):
    """
    Run agent in fully autonomous mode.
    
    Args:
        agent: NPCAgent instance
        duration: How long to run (None = indefinite)
    """
    print(f"\n{'='*70}")
    print(f"  🧠 STARTING AUTONOMOUS AGENT: {agent.agent_id}")
    print(f"{'='*70}")
    print(f"  Personality: {agent.personality.to_dict()}")
    print(f"  Memory Backend: {agent.memory.get_stats()['backend']}")
    if hasattr(agent.brain, 'language'):
        print(f"  Language Stage: {agent.brain.language.language_stage}")
        print(f"  Vocabulary: {agent.brain.language.vocab.next_id} words")
    print(f"  Memory: {len(agent.memory.events)} events")
    print(f"{'='*70}\n")
    
    await agent.start_autonomous_mode()
    
    start_time = time.time()
    
    try:
        while True:
            # Check duration
            if duration and (time.time() - start_time) >= duration:
                break
            
            # Auto-save every 5 minutes
            if (time.time() - start_time) % 300 < 1:
                brain_path = Path(f"data/brains/{agent.agent_id}/brain.pcap")
                brain_path.parent.mkdir(parents=True, exist_ok=True)
                agent.save(str(brain_path))
                log.info(f"💾 Auto-saved {agent.agent_id}")
            
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping agent...")
    
    finally:
        await agent.shutdown()
        
        print(f"\n{'='*70}")
        print(f"  ✅ AGENT STOPPED: {agent.agent_id}")
        print(f"  Total runtime: {time.time() - start_time:.1f}s")
        print(f"  Final memory: {len(agent.memory.events)} events")
        if hasattr(agent.brain, 'language'):
            print(f"  Final vocabulary: {agent.brain.language.vocab.next_id} words")
        print(f"{'='*70}\n")