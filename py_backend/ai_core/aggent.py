# ai_core/agent.py - FULLY AUTONOMOUS VERSION
"""
Unified NPC Agent with TRUE autonomy.
Agent thinks, feels, remembers, and speaks on its own.
"""

import torch
import numpy as np
import time
import logging
import asyncio
from typing import Dict, Any, Optional, List
from pathlib import Path

from ai_core.personality import Personality, GenderType
from ai_core.emotion import EmotionSystem
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.brain_core import BrainCore
from ai_core.planner import CognitivePlanner

# NEW: Unified memory and enhanced language
from ai_core.unified_memory import UnifiedMemoryStore, EnhancedLanguageIntelligence

# NEW: Cognitive loop
from ai_core.cognitive_loop import CognitiveLoop

log = logging.getLogger("agent")


class NPCAgent:
    """
    Fully autonomous NPC agent that:
    - Thinks continuously (cognitive loop)
    - Speaks when it feels appropriate (not on command)
    - Learns from ALL experiences
    - Has unified memory across all systems
    """

    def __init__(self,
                 agent_id: str,
                 gender: Optional[GenderType] = None,
                 persona_traits: Optional[Dict[str, float]] = None,
                 client_process=None,
                 autonomous: bool = True):  # NEW: Enable autonomy by default
        
        self.agent_id = agent_id
        self.autonomous_mode = autonomous

        # Core components
        if gender is None:
            from ai_core.personality import assign_npc_gender
            gender = assign_npc_gender()

        self.personality = Personality(gender=gender, traits=persona_traits)
        self.emotion = EmotionSystem()
        
        # UNIFIED MEMORY - Single source of truth
        self.memory = UnifiedMemoryStore(
            agent_id=agent_id,
            capacity=10000,
            use_scylla=False,  # Set True when ScyllaDB is ready
            scylla_hosts=['127.0.0.1']
        )
        
        # Brain
        self.brain = BrainCore(agent_ref=self)
        self.planner = CognitivePlanner(brain=self.brain)
        
        # ENHANCED LANGUAGE - Uses unified memory
        self.brain.language = EnhancedLanguageIntelligence(
            agent_ref=self,
            memory_store=self.memory
        )

        # State
        self.health = 20.0
        self.hunger = 20.0
        self.last_obs = None
        self.last_action = None
        self.step_count = 0

        # Client process info
        self.client_process = client_process
        self.agent_type = 'npc'
        
        # AI components
        self.policy = None
        self.reward_system = None
        
        # Neural stack placeholders
        self.world_model = None
        self.world_model_trainer = None
        self.world_model_buffer = None
        self._neural_integrated = False
        
        # Metadata
        self.metadata = {}
        
        # AUTONOMOUS COGNITIVE LOOP
        self.cognitive_loop = None
        if self.autonomous_mode:
            self._init_cognitive_loop()
        
        log.info(f"NPCAgent initialized: {agent_id} (gender: {gender}, autonomous: {autonomous})")

    def _init_cognitive_loop(self):
        """Initialize autonomous cognitive loop"""
        from ai_core.cognitive_loop import CognitiveLoop
        
        self.cognitive_loop = CognitiveLoop(
            agent=self,
            loop_interval=0.5  # Think twice per second
        )
        
        log.info(f"🧠 Cognitive loop initialized for {self.agent_id}")

    # ================================================================
    # ==================== AUTONOMOUS CONTROL ========================
    # ================================================================

    async def start_autonomous_mode(self):
        """
        Start fully autonomous operation.
        Agent will think, speak, and act on its own.
        """
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
    # =============== PERCEPTION & ACTION (EXISTING) =================
    # ================================================================

    def perceive(self, raw_observation: Dict[str, Any]) -> np.ndarray:
        """Convert raw observation to feature vector"""
        obs_parts = []

        obs_parts.append(raw_observation.get('health', 20.0) / 20.0)
        obs_parts.append(raw_observation.get('hunger', 20.0) / 20.0)
        obs_parts.append(raw_observation.get('saturation', 5.0) / 20.0)

        pos = raw_observation.get('position', {'x': 0, 'y': 0, 'z': 0})
        obs_parts.extend([pos['x'] / 100.0, pos['y'] / 100.0, pos['z'] / 100.0])

        obs_parts.append(raw_observation.get('yaw', 0.0) / 360.0)
        obs_parts.append(raw_observation.get('pitch', 0.0) / 90.0)

        entities = raw_observation.get('entities', [])
        obs_parts.append(len(entities) / 10.0)

        inventory = raw_observation.get('inventory', {})
        obs_parts.append(inventory.get('slot_count', 0) / 36.0)

        obs_parts.extend(self.personality.as_array().tolist())
        obs_parts.extend(self.emotion.as_array().tolist())

        if self.reward_system and self.reward_system.reward_history:
            recent = list(self.reward_system.reward_history)[-20:]
            obs_parts.extend([
                np.mean(recent), np.std(recent), np.max(recent),
                np.min(recent), len([r for r in recent if r > 0]) / len(recent)
            ])
        else:
            obs_parts.extend([0.0] * 5)

        obs_parts.append(len(self.memory.events) / 1000.0)
        obs_parts.append(0.0)  # Placeholder for episodic memory

        while len(obs_parts) < 50:
            obs_parts.append(0.0)

        obs_array = np.array(obs_parts[:50], dtype=np.float32)
        self.last_obs = obs_array
        
        # FEED TO COGNITIVE LOOP
        if self.cognitive_loop and self.cognitive_loop.running:
            self.cognitive_loop.receive_state_update({
                'health': self.health,
                'hunger': self.hunger,
                'raw_observation': raw_observation
            })
        
        return obs_array

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
    # ======================= LEARNING ===============================
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
        }, tags=['learning', 'experience'])

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
    # ===================== INITIALIZATION ===========================
    # ================================================================

    def initialize_reward_system(self, obs_dim: int = 50, action_dim: int = 11):
        """Initialize reward system"""
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
        """Initialize policy network"""
        if self.policy is None:
            from rl.policy import TransformerPolicy
            self.policy = TransformerPolicy(
                observation_space=obs_space,
                action_space=action_space,
                lr_schedule=lambda _: 3e-4
            )
            log.info(f"[{self.agent_id}] Policy initialized")

    def integrate_neural_stack(self, force: bool = False):
        """Attach neural world model"""
        if self._neural_integrated and not force:
            return

        try:
            from ai_core import world_model as wm_module
        except Exception:
            wm_module = None

        try:
            if wm_module:
                if hasattr(wm_module, "integrate_world_model_with_agent"):
                    wm_module.integrate_world_model_with_agent(self)
                    log.info(f"[{self.agent_id}] WorldModel integrated.")
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to attach world_model: {e}")

        self._neural_integrated = True

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
            info['language'] = self.brain.language.get_language_progress()

        # Cognitive loop status
        if self.cognitive_loop:
            info['cognitive_status'] = self.cognitive_loop.get_status()

        if self.client_process:
            info['backend_url'] = self.client_process.backend_url
            info['server'] = self.client_process.server_addr

        if self.metadata:
            info['metadata'] = self.metadata

        return info

    # ================================================================
    # ======================== SAVE/LOAD =============================
    # ================================================================

    def save(self, path: str):
        """Save agent state"""
        from ai_core.brain_capsule import BrainCapsule
        import time

        # Get language state
        language_state = None
        if hasattr(self.brain, 'language'):
            language_state = {
                'vocabulary': dict(self.brain.language.vocab.word_to_id),
                'vocab_counts': dict(self.brain.language.vocab.word_counts),
                'vocab_next_id': self.brain.language.vocab.next_id,
                'language_stage': self.brain.language.language_stage,
                'vocabulary_size': self.brain.language.vocabulary_size,
                'model_state': self.brain.language.model.state_dict(),
                'optimizer_state': self.brain.language.optimizer.state_dict()
            }

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

        if self.policy:
            capsule.model_state = self.policy.state_dict()

        capsule.save(path)
        log.info(f"[{self.agent_id}] Saved to {path}")

    def load(self, path: str):
        """Load agent state"""
        from ai_core.brain_capsule import BrainCapsule

        capsule = BrainCapsule.load(path)

        self.personality = Personality.from_dict(capsule.personality)

        if capsule.emotion_snapshot:
            for emotion, value in capsule.emotion_snapshot.items():
                self.emotion.emotions[emotion] = value

        if capsule.memory_snapshot:
            for event in capsule.memory_snapshot:
                self.memory.remember(event, tags=event.get('tags', []))

        # Restore language
        if capsule.language_state:
            if hasattr(self.brain, 'language'):
                lang_state = capsule.language_state
                
                # Restore vocabulary
                self.brain.language.vocab.word_to_id = lang_state['vocabulary']
                self.brain.language.vocab.id_to_word = {
                    v: k for k, v in lang_state['vocabulary'].items()
                }
                self.brain.language.vocab.word_counts = defaultdict(int, lang_state['vocab_counts'])
                self.brain.language.vocab.next_id = lang_state['vocab_next_id']
                
                # Restore training state
                self.brain.language.language_stage = lang_state['language_stage']
                self.brain.language.vocabulary_size = lang_state['vocabulary_size']
                
                # Restore model weights
                self.brain.language.model.load_state_dict(lang_state['model_state'])
                self.brain.language.optimizer.load_state_dict(lang_state['optimizer_state'])
                
                log.info(f"[{self.agent_id}] Language restored: stage {lang_state['language_stage']}, vocab {lang_state['vocabulary_size']}")

        if capsule.model_state and self.policy:
            self.policy.load_state_dict(capsule.model_state)

        self.step_count = capsule.metadata.get('step_count', 0)
        self.agent_type = capsule.metadata.get('agent_type', 'npc')
        self.autonomous_mode = capsule.metadata.get('autonomous', True)

        log.info(f"[{self.agent_id}] Loaded from {path}")


# =============================================================================
# HELPER: Start agent in autonomous mode
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
    print(f"  Language Stage: {agent.brain.language.language_stage}")
    print(f"  Vocabulary: {agent.brain.language.vocabulary_size} words")
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
        await agent.stop_autonomous_mode()
        
        # Final save
        brain_path = Path(f"data/brains/{agent.agent_id}/brain.pcap")
        brain_path.parent.mkdir(parents=True, exist_ok=True)
        agent.save(str(brain_path))
        
        print(f"\n{'='*70}")
        print(f"  ✅ AGENT STOPPED: {agent.agent_id}")
        print(f"  Total runtime: {time.time() - start_time:.1f}s")
        print(f"  Final memory: {len(agent.memory.events)} events")
        print(f"  Final vocabulary: {agent.brain.language.vocabulary_size} words")
        print(f"{'='*70}\n")