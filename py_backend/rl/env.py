# ------------------------------------------------------------------------------
# rl/env.py - Gymnasium environment wrapper
# ------------------------------------------------------------------------------
"""
Gymnasium environment wrapper for NPCAgent.
No circular imports - uses agent as external dependency.
"""
import gymnasium as gym
import numpy as np
from gymnasium import spaces
from typing import Dict, Any, Optional

class DivineWorldEnv(gym.Env):
    """
    Gymnasium wrapper around NPCAgent.

    Observation: Box(50,) - concatenated state vector
    Action: Box(11,) - continuous actions
    """
    metadata = {'render_modes': ['human']}

    def __init__(self, agent, render_mode: Optional[str] = None):
        super().__init__()
        self.agent = agent
        self.render_mode = render_mode

        # Observation space
        self.observation_space = spaces.Box(
            low=-10.0, high=10.0,
            shape=(50,),
            dtype=np.float32
        )

        # Action space — must match TransformerPolicy.BASE_DIM = 13
        # [0]forward [1]strafe [2]jump [3]sneak [4]attack [5]use [6]drop
        # [7]open_inv [8]swap_hand [9]yaw_delta [10]pitch_delta [11]sprint [12]hotbar_slot
        # FIX: was shape=(11,) — missing sprint and hotbar_slot dims 11-12.
        # policy.py comment "13 when space is set correctly" confirms the intended size.
        self.action_space = spaces.Box(
            low=-1.0, high=1.0,
            shape=(13,),
            dtype=np.float32
        )

        # State tracking
        self._step_count = 0
        self._last_obs = None

    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None):
        """Reset environment"""
        super().reset(seed=seed)

        self._step_count = 0
        self._last_obs = None  # FIX: clear stale obs from previous episode

        # Build initial observation
        obs = self._build_obs()
        info = {'step': 0}

        return obs, info

    def step(self, action: np.ndarray):
        """Execute action and return (obs, reward, terminated, truncated, info)"""
        # Clip and execute action
        action = np.clip(action, -1.0, 1.0)
        controls = self.agent.act(action)

        # Simulate outcome (in production, get from environment)
        outcome = self._simulate_outcome(controls)

        # FIX M-04: update_emotion_memory() does not exist on NPCAgent.
        # Correct API: agent.learn() for the RL update, emotion.decay() for mood.
        obs_now = self._build_obs()
        if self._last_obs is not None:
            self.agent.learn(self._last_obs, action, obs_now, outcome)
        self.agent.emotion.decay()

        obs = obs_now  # reuse — avoids redundant second _build_obs() call

        # Compute reward (use outcome)
        reward = self._compute_reward(outcome)

        # Check termination
        terminated = outcome.get('is_dead', False)
        truncated = self._step_count >= 10000

        self._step_count += 1

        info = {
            'step': self._step_count,
            'outcome': outcome,
            'controls': controls
        }

        return obs, reward, terminated, truncated, info

    def _build_obs(self) -> np.ndarray:
        """Build observation vector"""
        obs_dict = self._get_obs_dict()
        obs = self.agent.perceive(obs_dict)
        self._last_obs = obs
        return obs

    def _get_obs_dict(self) -> Dict[str, Any]:
        """Get observation dictionary"""
        return {
            'health': self.agent.health,
            'hunger': self.agent.hunger,
            'saturation': 5.0,
            'position': {'x': 0, 'y': 64, 'z': 0},
            'yaw': 0.0,
            'pitch': 0.0,
            'entities': [],
            'inventory': {'slot_count': 0}
        }

    def _simulate_outcome(self, controls):
        """
        FIX RL-03: sprint (dim 11) and hotbar_slot (dim 12) were never
        rewarded — zero gradient signal for those policy output dims.
        """
        outcome = {}
        if controls.get("attack", False):
            if np.random.rand() < 0.2:
                outcome["killed_enemy"] = True
                outcome["task_reward"] = 1.0
            else:
                outcome["hurt_by_enemy"] = True
                self.agent.health = max(0.0, self.agent.health - 0.5)
        if controls.get("sprint", False):
            outcome["task_reward"] = outcome.get("task_reward", 0.0) + 0.01
        if controls.get("hotbar_slot") is not None:
            outcome["task_reward"] = outcome.get("task_reward", 0.0) + 0.001
        self.agent.hunger = max(0.0, self.agent.hunger - 0.01)
        if self.agent.health <= 0:
            outcome["is_dead"] = True
        outcome["health"]      = self.agent.health
        outcome["hunger"]      = self.agent.hunger
        outcome["task_reward"] = outcome.get("task_reward", 0.0)
        return outcome

    def _compute_reward(self, outcome: Dict[str, Any]) -> float:
        """
        Compute reward from outcome.
        Simple version - can be replaced by RewardSystem.
        """
        reward = 0.0

        # Task rewards
        reward += outcome.get('task_reward', 0.0)

        # Health change
        if 'hurt_by_enemy' in outcome:
            reward -= 0.5

        # Death penalty
        if outcome.get('is_dead', False):
            reward -= 10.0

        # Survival bonus
        if self._step_count % 100 == 0:
            reward += 0.1

        return reward

    def render(self):
        """Render environment state"""
        if self.render_mode == 'human':
            print(f"[ENV] Step {self._step_count}: "
                  f"Health={self.agent.health:.1f}, "
                  f"Hunger={self.agent.hunger:.1f}, "
                  f"Emotion={self.agent.emotion.dominant_emotion()}")

    def close(self):
        """Cleanup"""
        pass
