# ai_core/agent.py - UNIFIED AGENT (NEURAL-ENABLED)
"""
Unified NPC Agent implementation with integrated neural stack:
- World Model (Dreamer-style)
- Transformer Language Model (GPT-style, nontraditional multimodal wrapper)
- Personality, Emotion, Memory, Cognitive Planning
- Full BrainCapsule persistence (world_model + transformer_lm)
"""
import torch
import numpy as np
import time
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from ai_core.personality import Personality, GenderType
from ai_core.emotion import EmotionSystem
from ai_core.memory import Memory, EpisodicMemory
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.brain_core import BrainCore
from ai_core.planner import CognitivePlanner
from ai_core.config_loader import get_section, get_device


# New import for LM integration
from ai_core.transformer_lm import TransformerLM

log = logging.getLogger("agent")


class NPCAgent:
    """
    Unified NPC agent with:
    - Personality (including gender)
    - Emotions
    - Memory
    - AI brain
    - Client process info (if spawned)
    - Neural stack (WorldModel + TransformerLM)
    """

    def __init__(self,
                 agent_id: str,
                 gender: Optional[GenderType] = None,
                 persona_traits: Optional[Dict[str, float]] = None,
                 client_process=None):
        self.agent_id = agent_id

        # Core components with gender
        if gender is None:
            from ai_core.personality import assign_npc_gender
            gender = assign_npc_gender()

        self.personality = Personality(gender=gender, traits=persona_traits)
        self.emotion = EmotionSystem()
        self.memory = Memory(capacity=10000)
        self.episodic_memory = EpisodicMemory(capacity=10000)

        # Cognitive components
        self.brain = BrainCore(agent_ref=self)
        self.planner = CognitivePlanner(brain=self.brain)

        # State
        self.health = 20.0
        self.hunger = 20.0
        self.last_obs = None
        self.last_action = None
        self.step_count = 0

        # Client process info (if spawned with Minecraft client)
        self.client_process = client_process
        self.agent_type = 'npc'  # or 'god_wither', etc.

        # AI components (lazy loading)
        self.policy = None
        self.reward_system = None

        # Neural stack placeholders
        self.world_model = None
        self.world_model_trainer = None
        self.world_model_buffer = None
        self.lm: Optional[TransformerLM] = None
        self._neural_integrated = False

        # Metadata for children/breeding
        self.metadata = {}

        log.info(f"NPCAgent initialized: {agent_id} (gender: {gender})")

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

    def integrate_neural_stack(self, lm_config: Optional[dict] = None, force: bool = False):
        """
        Attach world_model + transformer LM to this NPCAgent instance lazily.
        - lm_config: dict passed to TransformerLM(...) constructor.
        - force=True reinitializes even if already integrated.
        """
        if self._neural_integrated and not force:
            return

        # Lazy import to avoid circular deps
        try:
            from ai_core import world_model as wm_module
        except Exception:
            wm_module = None

        # ----------------- WORLD MODEL -----------------
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

        # ----------------- LANGUAGE MODEL --------------
        try:
            if self.lm is None or force:
                # Load LM config from global config.yml if not provided
                lm_cfg = get_section("language_model", {})
                if lm_config:
                    lm_cfg.update(lm_config)  # runtime overrides
                lm_cfg["device"] = get_device()

                self.lm = TransformerLM(**lm_cfg)


                # attach LM-based functions to brain
                if hasattr(self, "brain") and self.brain:
                    def generate_text(prompt, memory=None, world_model=None, **kwargs):
                        return self.lm.generate(prompt,
                                                memory=memory,
                                                world_model=world_model or self.world_model,
                                                **kwargs)

                    def summarize_memory(max_tokens=128):
                        mem = getattr(self, "brain", None) and getattr(self.brain, "memory", None)
                        if not mem:
                            return ""
                        last = list(mem)[-16:]
                        prompt = "Summarize the following memories briefly:\n\n" + "\n".join(last)
                        return generate_text(prompt, memory=None, max_new_tokens=max_tokens)

                    def fine_tune_on_texts(texts, output_dir, **kwargs):
                        return self.lm.fine_tune_on_texts(texts, output_dir, **kwargs)

                    def score_text(text, context=None):
                        return self.lm.score(text, context=context)

                    # attach to brain
                    self.brain.generate_text = generate_text
                    self.brain.summarize_memory = summarize_memory
                    self.brain.fine_tune_lm = fine_tune_on_texts
                    self.brain.score_text = score_text

                    log.info(f"[{self.agent_id}] TransformerLM attached.")
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to attach TransformerLM: {e}")

        self._neural_integrated = True
        log.info(f"[{self.agent_id}] Neural stack integrated (WorldModel + LM).")

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
        obs_parts.append(len(self.episodic_memory) / 1000.0)

        while len(obs_parts) < 50:
            obs_parts.append(0.0)

        obs_array = np.array(obs_parts[:50], dtype=np.float32)
        self.last_obs = obs_array
        return obs_array

    def decide(self, obs: np.ndarray, deterministic: bool = False) -> np.ndarray:
        """Make decision based on observation (11,)"""
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

        self.episodic_memory.store(
            obs=obs, action=action, reward=reward,
            next_obs=next_obs, done=outcome.get('is_dead', False),
            importance=abs(reward)
        )

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
            'dominant_emotion': self.emotion.dominant_emotion()
        }

        if self.client_process:
            info['backend_url'] = self.client_process.backend_url
            info['server'] = self.client_process.server_addr

        if self.metadata:
            info['metadata'] = self.metadata

        return info

    # ================================================================
    # ========================== SAVE ================================
    # ================================================================

    def save(self, path: str):
        """Save agent state with neural components and language persistence"""
        from ai_core.brain_capsule import BrainCapsule
        import time

        # Prepare language state
        language_state = None
        if hasattr(self.brain, 'language') and self.brain.language:
            language_state = {
                'language_stage': self.brain.language.language_stage,
                'vocabulary_size': self.brain.language.vocabulary_size,
                'language_experience_count': self.brain.language.language_experience_count,
                'word_frequencies': dict(self.brain.language.word_frequencies),
                'word_to_concept': {
                    word: [concept.tolist() for concept in concepts]
                    for word, concepts in self.brain.language.word_to_concept.items()
                },
                'sentence_patterns': [
                    pattern for pattern in self.brain.language.sentence_patterns
                ],
                'invented_symbols': {
                    symbol: concept.tolist()
                    for symbol, concept in self.brain.language.invented_symbols.items()
                },
                'symbol_counter': self.brain.language.symbol_counter,
                'pattern_count': len(self.brain.language.sentence_patterns)
            }

        capsule = BrainCapsule(
            metadata={
                'agent_id': self.agent_id,
                'agent_type': self.agent_type,
                'gender': self.personality.gender,
                'step_count': self.step_count,
                'saved_at': time.time()
            },
            personality=self.personality.to_dict(),
            emotion_snapshot=self.emotion.snapshot(),
            memory_snapshot=self.memory.recall(1000),
            language_state=language_state
        )

        # Save policy state
        if self.policy:
            capsule.model_state = self.policy.state_dict()

        # ----------------- Neural stack persistence -----------------
        extra_model_state = {}

        try:
            if getattr(self, "world_model", None) is not None:
                if hasattr(self.world_model, "state_dict"):
                    extra_model_state['world_model'] = {
                        k: v.cpu() for k, v in self.world_model.state_dict().items()
                    }
                elif hasattr(self.world_model, "export_to_braincapsule_dict"):
                    extra_model_state['world_model'] = self.world_model.export_to_braincapsule_dict()
                else:
                    extra_model_state['world_model'] = {"repr": repr(self.world_model)}
            if getattr(self, "lm", None) is not None:
                extra_model_state['transformer_lm'] = self.lm.state_dict()
        except Exception as e:
            log.exception(f"[{self.agent_id}] Error serializing neural stack: {e}")

        # merge into capsule
        try:
            capsule_model_state = getattr(capsule, "model_state", {}) or {}
            capsule_model_state.update(extra_model_state)
            capsule.model_state = capsule_model_state
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to attach extra model_state: {e}")

        capsule.save(path)
        log.info(f"[{self.agent_id}] Saved to {path}")

    # ================================================================
    # =========================== LOAD ===============================
    # ================================================================

    def load(self, path: str):
        """Load agent state with neural components"""
        from ai_core.brain_capsule import BrainCapsule
        import numpy as np

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
                self.memory.remember(event)

        # Restore language state
        if capsule.language_state:
            from ai_core.brain_language import add_language_to_brain
            if not hasattr(self.brain, 'language'):
                add_language_to_brain(self.brain)
            lang = self.brain.language
            lang.language_stage = capsule.language_state.get('language_stage', 0)
            lang.vocabulary_size = capsule.language_state.get('vocabulary_size', 0)
            lang.language_experience_count = capsule.language_state.get('language_experience_count', 0)
            lang.symbol_counter = capsule.language_state.get('symbol_counter', 0)
            for word, freq in capsule.language_state.get('word_frequencies', {}).items():
                lang.word_frequencies[word] = freq
            for word, concept_lists in capsule.language_state.get('word_to_concept', {}).items():
                lang.word_to_concept[word] = [
                    np.array(concept, dtype=np.float32) for concept in concept_lists
                ]
            lang.sentence_patterns = list(capsule.language_state.get('sentence_patterns', []))
            for symbol, concept_list in capsule.language_state.get('invented_symbols', {}).items():
                lang.invented_symbols[symbol] = np.array(concept_list, dtype=np.float32)
            log.info(f"[{self.agent_id}] Language restored.")

        # Restore model weights
        if capsule.model_state and self.policy:
            self.policy.load_state_dict(capsule.model_state)

        # Restore neural stack (world_model + LM)
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
            if 'transformer_lm' in saved_state:
                lm_state = saved_state['transformer_lm']
                model_name = lm_state.get("meta", {}).get("model_name_or_path", "gpt2")
                self.lm = TransformerLM(model_name_or_path=model_name,
                                        device=torch.device("cuda" if torch.cuda.is_available() else "cpu"))
                try:
                    self.lm.load_state_dict(lm_state)
                except Exception:
                    self.lm = TransformerLM.create_from_braincapsule_dict(lm_state)
        except Exception as e:
            log.exception(f"[{self.agent_id}] Failed to restore neural stack: {e}")

        # Metadata
        self.step_count = capsule.metadata.get('step_count', 0)
        self.agent_type = capsule.metadata.get('agent_type', 'npc')

        log.info(f"[{self.agent_id}] Loaded from {path}")
