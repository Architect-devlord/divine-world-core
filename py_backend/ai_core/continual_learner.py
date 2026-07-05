# ai_core/continual_learner.py
"""
Avalanche Continual Learning Integration
=========================================
Implements lifelong learning using Avalanche library.
Prevents catastrophic forgetting while learning new tasks.

Uses:
- Experience Replay (ER)
- Elastic Weight Consolidation (EWC)
- Learning without Forgetting (LwF)
- Progressive Neural Networks (PNN)
"""

import torch
import torch.nn as nn
import numpy as np
from collections import deque
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import logging

try:
    from avalanche.benchmarks.utils import AvalancheTensorDataset
    from avalanche.training.supervised.strategy_wrappers import Naive, Replay, EWC, LwF
    from avalanche.models import SimpleMLP
    from avalanche.evaluation.metrics import loss_metrics
    from avalanche.logging import InteractiveLogger
    from avalanche.training.plugins import EvaluationPlugin
    AVALANCHE_AVAILABLE = True
except ImportError:
    AVALANCHE_AVAILABLE = False

log = logging.getLogger("continual_learner")


class PolicyNetwork(nn.Module):
    """
    Policy network compatible with Avalanche.
    Predicts actions from observations.
    """

    def __init__(self, obs_dim: int = 50, action_dim: int = 13, hidden_dim: int = 256):  # FIX RL-05: was 11
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),

            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),
            nn.Dropout(0.1),

            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),

            nn.Linear(hidden_dim // 2, action_dim),
            nn.Tanh()  # Actions in [-1, 1]
        )

    def forward(self, x):
        return self.network(x)


class ValueNetwork(nn.Module):
    """Value function for critic"""

    def __init__(self, obs_dim: int = 50, hidden_dim: int = 256):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.LayerNorm(hidden_dim),

            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),

            nn.Linear(hidden_dim // 2, 1)
        )

    def forward(self, x):
        return self.network(x)


class ContinualLearner:
    """
    Avalanche-based continual learning for NPCAgent.
    Manages lifelong learning without catastrophic forgetting.
    """

    def __init__(self, agent, strategy: str = 'replay',
                 hidden_dim: int = 256, memory_size: int = 2000):

        if not AVALANCHE_AVAILABLE:
            raise RuntimeError("Avalanche not installed. Install with: pip install avalanche-lib")

        self.agent = agent
        self.strategy_name = strategy
        self.hidden_dim = hidden_dim
        self.memory_size = memory_size

        # Dimensions
        # FIX Step 2h: was 50 — must match Phase 6 obs_builder.OBS_DIM (128)
        self.obs_dim = 128
        self.action_dim = 13   # FIX: must match TransformerPolicy.BASE_DIM

        # Networks
        self.policy_net = PolicyNetwork(self.obs_dim, self.action_dim, hidden_dim)
        self.value_net = ValueNetwork(self.obs_dim, hidden_dim)

        # Avalanche components
        self.strategy = None
        self.eval_plugin = None

        # Task tracking
        self.current_task_id = 0
        self.task_history: List[int] = []

        # Experience buffer for Avalanche
        self.experience_buffer: List[Tuple] = []

        # FIX (template-ceiling): discovers new candidate templates from
        # real (action, reward) experience, the same way vision.py's
        # OnlineVisualVocabulary discovers visual categories — see
        # emergent_templates.py. Graduated skills are pushed into
        # agent.planner.templates via the existing add_template() hook.
        from ai_core.emergent_templates import EmergentSkillPool
        self.skill_pool = EmergentSkillPool(action_dim=self.action_dim)

        # Statistics
        self.stats = {
            'tasks_learned': 0,
            'total_updates': 0,
            'avg_loss': 0.0,
            'forgetting_measure': 0.0
        }

        self._init_avalanche_strategy()

        log.info(f"ContinualLearner initialized with {strategy} strategy")

    def _init_avalanche_strategy(self):
        """Initialize Avalanche training strategy"""

        # Optimizer
        optimizer = torch.optim.Adam([
            {'params': self.policy_net.parameters(), 'lr': 3e-4},
            {'params': self.value_net.parameters(), 'lr': 1e-3}
        ])

        # Loss criterion
        criterion = nn.MSELoss()

        # Evaluation plugin
        # FIX Step 2g: accuracy_metrics() is a classification metric (argmax
        # comparison) — meaningless for our continuous 13-dim action vectors
        # and a source of silent exceptions on some output shapes. Replaced
        # with a plain rolling MSE deque the agent/cognitive_loop can read
        # directly via get_recent_mse() / get_avg_mse().
        self._mse_history: deque = deque(maxlen=100)
        self.eval_plugin = EvaluationPlugin(
            loss_metrics(minibatch=True, epoch=True, experience=True, stream=True),
            loggers=[InteractiveLogger()]
        )

        # Select strategy
        if self.strategy_name == 'naive':
            self.strategy = Naive(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )

        elif self.strategy_name == 'replay':
            self.strategy = Replay(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                mem_size=self.memory_size,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )

        elif self.strategy_name == 'ewc':
            self.strategy = EWC(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                ewc_lambda=0.4,  # EWC regularization strength
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )

        elif self.strategy_name == 'lwf':
            self.strategy = LwF(
                model=self.policy_net,
                optimizer=optimizer,
                criterion=criterion,
                alpha=1.0,  # Distillation weight
                temperature=2.0,
                train_mb_size=32,
                eval_mb_size=32,
                device='cuda' if torch.cuda.is_available() else 'cpu',
                evaluator=self.eval_plugin
            )
        else:
            raise ValueError(f"Unknown strategy: {self.strategy_name}")

        log.info(f"Avalanche strategy initialized: {self.strategy_name}")

    def collect_experiences(self, min_batch_size: int = 32) -> bool:
        """
        Convert brain.continual_buffer entries into (obs, action, reward) tensors.

        FIX: The old implementation built obs as [health/20, hunger/20, 0…0] —
        48 zeros regardless of what the agent actually perceived. Every training
        sample was near-identical, so the policy network learned nothing useful.

        Now: use agent.last_obs (the cached 50-dim perception vector from the
        most recent agent.perceive() call) when the buffer entry does not carry
        a stored observation, and fall back to a context-derived vector only when
        last_obs is unavailable. Also use the stored raw action array when present.
        """
        buffer = list(getattr(self.agent.brain, 'continual_buffer', []))
        if len(buffer) < min_batch_size:
            return False

        import numpy as _np

        # Snapshot agent.last_obs once — used as fallback for entries without obs
        agent_last_obs = getattr(self.agent, 'last_obs', None)

        templates = ['collect','craft','attack','flee','use_item',
                     'explore','eat','sleep','build','trade','interact']

        for exp in buffer:
            context = exp.get('context') or {}
            event   = exp.get('event', {})
            reward  = float(exp.get('reward', 0.0))
            task_id = exp.get('task', self.current_task_id)

            # ── Observation ───────────────────────────────────────────────
            # Priority: stored obs in memory event → agent.last_obs → context stub
            stored_obs = event.get('obs')   # agent.learn() stores obs.tolist()
            if stored_obs is not None:
                obs_arr = _np.array(stored_obs, dtype=_np.float32)[:self.obs_dim]
                if len(obs_arr) < self.obs_dim:
                    obs_arr = _np.pad(obs_arr, (0, self.obs_dim - len(obs_arr)))
            elif agent_last_obs is not None:
                obs_arr = _np.array(agent_last_obs, dtype=_np.float32)[:self.obs_dim]
                if len(obs_arr) < self.obs_dim:
                    obs_arr = _np.pad(obs_arr, (0, self.obs_dim - len(obs_arr)))
            else:
                # Last resort: build a minimal but normalised context vector
                obs_list = [
                    context.get('health', 20.0) / 20.0,
                    context.get('hunger', 20.0) / 20.0,
                    float(context.get('novelty', 0.0)),
                    float(context.get('urgency', 0.0)),
                ] + [0.0] * (self.obs_dim - 4)
                obs_arr = _np.array(obs_list[:self.obs_dim], dtype=_np.float32)

            obs = torch.tensor(obs_arr, dtype=torch.float32)

            # ── Action ────────────────────────────────────────────────────
            # Priority: stored raw action array → event-type one-hot
            stored_action = event.get('action')  # agent.learn() stores action.tolist()
            if stored_action is not None:
                act_arr = _np.array(stored_action, dtype=_np.float32)[:self.action_dim]
                if len(act_arr) < self.action_dim:
                    act_arr = _np.pad(act_arr, (0, self.action_dim - len(act_arr)))
                action = torch.tensor(act_arr, dtype=torch.float32)
            else:
                action_vec = [0.0] * self.action_dim
                etype = event.get('type', '')
                if etype in templates:
                    action_vec[templates.index(etype) % self.action_dim] = 1.0
                action = torch.tensor(action_vec, dtype=torch.float32)

            self.experience_buffer.append((obs, action, reward, obs, False, task_id))

        return len(self.experience_buffer) >= min_batch_size

    def _sync_weights_from_live_policy(self) -> None:
        """
        FIX RL-05: ContinualLearner.PolicyNetwork (2-layer MLP) and
        TransformerPolicy (attention encoder) have different architectures
        so direct weight copying is impossible.

        Instead, run policy distillation: feed stored observations through
        the live TransformerPolicy to get action targets, then add those
        (obs, target_action) pairs to the experience buffer alongside the
        stored rewards. This causes the continual learner to track the live
        policy's behaviour rather than drifting independently.
        """
        import torch as _torch
        try:
            live_policy = getattr(self.agent, 'policy', None)
            if live_policy is None:
                return
            last_obs = getattr(self.agent, 'last_obs', None)
            if last_obs is None:
                return

            obs_t = _torch.tensor(last_obs, dtype=_torch.float32).unsqueeze(0)
            with _torch.no_grad():
                action_t = live_policy._predict(obs_t, deterministic=True)
                action_np = action_t.squeeze().cpu().numpy()

            # Inject a distillation experience: obs from live game, action from
            # live policy, zero reward (distillation target, not game reward)
            obs_tensor    = _torch.tensor(last_obs[:self.obs_dim], dtype=_torch.float32)
            action_tensor = _torch.tensor(action_np[:self.action_dim], dtype=_torch.float32)
            self.experience_buffer.append(
                (obs_tensor, action_tensor, 0.0, obs_tensor, False, self.current_task_id)
            )
        except Exception as e:
            log.debug(f"[ContinualLearner] weight sync failed: {e}")

    def learn_from_buffer(self, epochs: int = 1) -> Dict[str, float]:
        """
        Perform continual learning update from collected experiences.
        Includes policy distillation from live TransformerPolicy (FIX RL-05).
        Returns metrics dict.
        """
        self._sync_weights_from_live_policy()  # FIX RL-05: add distillation target
        if not self.collect_experiences():
            return {'status': 'insufficient_data'}

        # ── FIX (template-ceiling): emergent skill discovery ────────────
        # Fold this batch's real (action, reward) pairs into the skill
        # pool, then push any newly-graduated skills into the live planner
        # template list via add_template() — the same hook god_controls.py
        # already uses for god abilities. Runs before training so a failure
        # here never blocks the actual learning step below.
        try:
            for _obs, _action, _reward, *_rest in self.experience_buffer:
                act_np = (_action.detach().cpu().numpy()
                          if hasattr(_action, 'detach') else np.asarray(_action))
                self.skill_pool.observe(act_np, float(_reward))

            planner = getattr(self.agent, 'planner', None)
            if planner is not None:
                for tmpl in self.skill_pool.drain_newly_graduated():
                    planner.add_template(tmpl)
        except Exception as _sp_e:
            log.debug(f"Skill pool update skipped: {_sp_e}")

        try:
            # Convert buffer to Avalanche dataset
            dataset = self._create_avalanche_dataset()

            # Train on experience
            results = self.strategy.train(dataset, num_workers=0)

            # FIX Step 2g: record a plain rolling MSE value from whatever loss
            # metric Avalanche logged this round. Avalanche's exact key naming
            # varies by version, so search defensively rather than hardcoding
            # one key — this is read by get_recent_mse()/get_avg_mse() instead
            # of the removed accuracy_metrics().
            try:
                loss_vals = [
                    float(v) for k, v in (results or {}).items()
                    if 'loss' in k.lower() and isinstance(v, (int, float))
                ]
                if loss_vals:
                    self._mse_history.append(sum(loss_vals) / len(loss_vals))
            except Exception as _me:
                log.debug(f"MSE history update skipped: {_me}")

            # Update statistics
            self.stats['total_updates'] += 1

            # Extract metrics
            metrics = {
                'status': 'success',
                'updates': self.stats['total_updates'],
                'task_id': self.current_task_id,
                'buffer_size': len(self.experience_buffer)
            }

            # Clear processed experiences
            self.experience_buffer.clear()

            log.info(f"Continual learning update complete: {metrics}")

            return metrics

        except Exception as e:
            log.error(f"Continual learning failed: {e}", exc_info=True)
            return {'status': 'error', 'error': str(e)}

    def _create_avalanche_dataset(self):
        """Create Avalanche dataset from experience buffer"""
        # Extract observations and actions
        observations = []
        actions = []
        task_labels = []

        for obs, action, reward, next_obs, done, task_id in self.experience_buffer:
            observations.append(obs)
            actions.append(action)
            task_labels.append(task_id)

        # Stack into tensors
        obs_tensor = torch.stack(observations)
        action_tensor = torch.stack(actions)
        task_tensor = torch.tensor(task_labels, dtype=torch.long)

        # Create Avalanche dataset
        dataset = AvalancheTensorDataset(
            obs_tensor,
            action_tensor,
            task_labels=task_tensor
        )

        return dataset

    def switch_task(self, new_task_id: int):
        """Switch to a new learning task"""
        if new_task_id != self.current_task_id:
            log.info(f"Switching task: {self.current_task_id} → {new_task_id}")

            # Store old task
            self.task_history.append(self.current_task_id)

            # Update task
            self.current_task_id = new_task_id
            self.agent.brain.current_task = new_task_id

            # Update statistics
            self.stats['tasks_learned'] = len(set(self.task_history))

    def predict_action(self, observation: torch.Tensor) -> torch.Tensor:
        """Use learned policy to predict action"""
        self.policy_net.eval()
        with torch.no_grad():
            action = self.policy_net(observation)
        return action

    def predict_value(self, observation: torch.Tensor) -> torch.Tensor:
        """Use value network to estimate state value"""
        self.value_net.eval()
        with torch.no_grad():
            value = self.value_net(observation)
        return value

    def save(self, path: str):
        """Save continual learning state"""
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        state = {
            'policy_net': self.policy_net.state_dict(),
            'value_net': self.value_net.state_dict(),
            'current_task_id': self.current_task_id,
            'task_history': self.task_history,
            'stats': self.stats,
            'strategy_name': self.strategy_name
        }

        torch.save(state, save_path)
        log.info(f"Continual learner saved to {save_path}")

    def load(self, path: str):
        """Load continual learning state"""
        save_path = Path(path)

        if not save_path.exists():
            log.warning(f"No saved state found at {save_path}")
            return

        state = torch.load(save_path, map_location='cpu')

        self.policy_net.load_state_dict(state['policy_net'])
        self.value_net.load_state_dict(state['value_net'])
        self.current_task_id = state['current_task_id']
        self.task_history = state['task_history']
        self.stats = state['stats']

        log.info(f"Continual learner loaded from {save_path}")

    def get_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return {
            **self.stats,
            'current_task': self.current_task_id,
            'tasks_seen': len(set(self.task_history)),
            'buffer_size': len(self.experience_buffer),
            'strategy': self.strategy_name
        }

    def get_recent_mse(self) -> List[float]:
        """FIX Step 2g: rolling MSE values (replaces removed accuracy_metrics)."""
        return list(self._mse_history)

    def get_avg_mse(self) -> float:
        """Mean of the rolling MSE window, or 0.0 if no updates recorded yet."""
        return (sum(self._mse_history) / len(self._mse_history)
                if self._mse_history else 0.0)


# Convenience function for agent integration
def add_continual_learning(agent, strategy: str = 'replay', **kwargs):
    """
    Add continual learning capabilities to an agent.

    Usage:
        from ai_core.continual_learner import add_continual_learning
        add_continual_learning(agent, strategy='replay')
    """
    if not AVALANCHE_AVAILABLE:
        log.warning("Avalanche not available - continual learning disabled")
        return None

    learner = ContinualLearner(agent, strategy=strategy, **kwargs)
    agent.continual_learner = learner

    log.info(f"Continual learning added to {agent.agent_id}")
    return learner