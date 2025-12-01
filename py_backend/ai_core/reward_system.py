# ------------------------------------------------------------------------------
# ai_core/reward_system.py - Unified intrinsic reward with RND/ICM
# ------------------------------------------------------------------------------
"""
Unified reward system integrating:
- Random Network Distillation (RND) for curiosity
- Inverse/Forward models (ICM)
- Action entropy tracking
- Survival rewards
- TorchRL integration support
"""
import numpy as np
import torch
import torch.nn as nn
from collections import deque, defaultdict
from typing import Dict, Any, Tuple, Optional

class RandomNetworkDistillation(nn.Module):
    """
    RND for exploration bonus based on prediction error.
    """
    def __init__(self, obs_dim: int, hidden_dim: int = 256):
        super().__init__()
        
        # Target network (fixed, random)
        self.target_net = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2)
        )
        
        # Predictor network (trained)
        self.predictor_net = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2)
        )
        
        # Freeze target network
        for param in self.target_net.parameters():
            param.requires_grad = False
        
        self.optimizer = torch.optim.Adam(self.predictor_net.parameters(), lr=1e-4)
    
    def forward(self, obs: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Returns (target_features, predicted_features)"""
        with torch.no_grad():
            target = self.target_net(obs)
        predicted = self.predictor_net(obs)
        return target, predicted
    
    def compute_intrinsic_reward(self, obs: torch.Tensor) -> float:
        """Compute RND bonus (prediction error)"""
        target, predicted = self.forward(obs)
        error = torch.mean((target - predicted) ** 2)
        return error.item()
    
    def update(self, obs: torch.Tensor):
        """Train predictor network"""
        target, predicted = self.forward(obs)
        loss = nn.functional.mse_loss(predicted, target)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        return loss.item()


class ICMModule(nn.Module):
    """
    Intrinsic Curiosity Module with forward and inverse models.
    """
    def __init__(self, obs_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        
        # Feature encoder (shared)
        self.encoder = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2)
        )
        
        # Forward model: predicts next state features from current + action
        self.forward_model = nn.Sequential(
            nn.Linear(hidden_dim // 2 + action_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2)
        )
        
        # Inverse model: predicts action from state transition
        self.inverse_model = nn.Sequential(
            nn.Linear(hidden_dim, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, action_dim)
        )
        
        self.optimizer = torch.optim.Adam(self.parameters(), lr=1e-4)
    
    def encode(self, obs: torch.Tensor) -> torch.Tensor:
        """Encode observation to feature space"""
        return self.encoder(obs)
    
    def predict_next_state(self, obs_features: torch.Tensor, 
                          action: torch.Tensor) -> torch.Tensor:
        """Forward model: predict next state features"""
        x = torch.cat([obs_features, action], dim=-1)
        return self.forward_model(x)
    
    def predict_action(self, obs_features: torch.Tensor,
                      next_obs_features: torch.Tensor) -> torch.Tensor:
        """Inverse model: predict action from transition"""
        x = torch.cat([obs_features, next_obs_features], dim=-1)
        return self.inverse_model(x)
    
    def compute_intrinsic_reward(self, obs: torch.Tensor, action: torch.Tensor,
                                next_obs: torch.Tensor) -> float:
        """Compute curiosity bonus (forward model prediction error)"""
        obs_feat = self.encode(obs)
        next_obs_feat = self.encode(next_obs)
        pred_next_feat = self.predict_next_state(obs_feat, action)
        
        error = torch.mean((pred_next_feat - next_obs_feat) ** 2)
        return error.item()
    
    def update(self, obs: torch.Tensor, action: torch.Tensor,
              next_obs: torch.Tensor):
        """Train ICM (forward + inverse models)"""
        obs_feat = self.encode(obs)
        next_obs_feat = self.encode(next_obs)
        
        # Forward model loss
        pred_next_feat = self.predict_next_state(obs_feat, action)
        forward_loss = nn.functional.mse_loss(pred_next_feat, next_obs_feat)
        
        # Inverse model loss
        pred_action = self.predict_action(obs_feat, next_obs_feat)
        inverse_loss = nn.functional.mse_loss(pred_action, action)
        
        # Combined loss
        loss = forward_loss + 0.2 * inverse_loss
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        return {'total': loss.item(), 'forward': forward_loss.item(), 
                'inverse': inverse_loss.item()}


class ActionEntropyTracker:
    """Track action diversity for exploration bonus"""
    def __init__(self, window_size: int = 1000):
        self.action_counts = defaultdict(int)
        self.total_actions = 0
        self.window = deque(maxlen=window_size)
    
    def update(self, action: np.ndarray):
        """Record action"""
        action_key = tuple(np.round(action, 2))
        
        if len(self.window) == self.window.maxlen:
            old_action = self.window[0]
            self.action_counts[old_action] -= 1
            self.total_actions -= 1
        
        self.window.append(action_key)
        self.action_counts[action_key] += 1
        self.total_actions += 1
    
    def get_entropy_bonus(self, action: np.ndarray) -> float:
        """Higher bonus for rare actions"""
        if self.total_actions == 0:
            return 0.5
        
        action_key = tuple(np.round(action, 2))
        count = self.action_counts.get(action_key, 0)
        frequency = count / self.total_actions
        
        if frequency == 0:
            return 1.0
        
        entropy = -np.log(frequency + 1e-8)
        normalized = np.clip(entropy / 10.0, 0.0, 1.0)
        return normalized


class ImprovedRewardSystem:
    """
    Unified reward system combining:
    - RND curiosity
    - ICM forward/inverse models
    - Action entropy (exploration)
    - Survival rewards
    - Persona-weighted preferences
    """
    
    def __init__(self, obs_dim: int, action_dim: int, persona: np.ndarray,
                 use_rnd: bool = True, use_icm: bool = True):
        self.obs_dim = obs_dim
        self.action_dim = action_dim
        self.persona = persona
        
        # Curiosity modules
        self.use_rnd = use_rnd
        self.use_icm = use_icm
        
        if use_rnd:
            self.rnd = RandomNetworkDistillation(obs_dim)
        
        if use_icm:
            self.icm = ICMModule(obs_dim, action_dim)
        
        # Exploration tracking
        self.entropy_tracker = ActionEntropyTracker()
        
        # Survival tracking
        self.alive_ticks = 0
        self.last_health = 20.0
        
        # Persona influences reward weights
        self.curiosity_weight = 0.3 + 0.2 * persona[6]  # curiosity trait
        self.entropy_weight = 0.2
        self.survival_weight = 0.3
        self.task_weight = 0.2
        
        # History for emotion state
        self.reward_history = deque(maxlen=100)
    
    def compute_reward(self, obs: torch.Tensor, action: torch.Tensor,
                      next_obs: torch.Tensor, outcome: Dict[str, Any]) -> Tuple[float, Dict]:
        """
        Compute total reward with breakdown.
        
        Returns:
            total_reward: float
            info_dict: breakdown and emotion state
        """
        
        # 1. Curiosity rewards
        curiosity_reward = 0.0
        if self.use_rnd:
            rnd_bonus = self.rnd.compute_intrinsic_reward(next_obs)
            curiosity_reward += 0.5 * rnd_bonus
        
        if self.use_icm:
            icm_bonus = self.icm.compute_intrinsic_reward(obs, action, next_obs)
            curiosity_reward += 0.5 * icm_bonus
        
        curiosity_reward = self.curiosity_weight * np.tanh(curiosity_reward)
        
        # 2. Exploration bonus
        action_np = action.detach().cpu().numpy().flatten()
        self.entropy_tracker.update(action_np)
        entropy_bonus = self.entropy_tracker.get_entropy_bonus(action_np)
        entropy_reward = self.entropy_weight * entropy_bonus
        
        # 3. Survival reward
        health = outcome.get('health', self.last_health)
        is_dead = outcome.get('is_dead', False)
        
        survival_reward = 0.0
        if is_dead:
            survival_reward = -10.0
            self.alive_ticks = 0
        else:
            self.alive_ticks += 1
            health_delta = health - self.last_health
            survival_reward += health_delta * 0.1
            
            if self.alive_ticks % 1000 == 0:
                survival_reward += 1.0
        
        survival_reward = self.survival_weight * survival_reward
        self.last_health = health
        
        # 4. Task-specific reward
        task_reward = self.task_weight * outcome.get('task_reward', 0.0)
        
        # Total reward
        total_reward = curiosity_reward + entropy_reward + survival_reward + task_reward
        
        # Update curiosity modules
        if self.use_rnd:
            self.rnd.update(next_obs)
        if self.use_icm:
            self.icm.update(obs, action, next_obs)
        
        # Track history
        self.reward_history.append(total_reward)
        
        # Info dict
        info = {
            'total': total_reward,
            'curiosity': curiosity_reward,
            'exploration': entropy_reward,
            'survival': survival_reward,
            'task': task_reward,
            'emotion_state': self._compute_emotion_label()
        }
        
        return total_reward, info
    
    def _compute_emotion_label(self) -> str:
        """Label current state for debugging"""
        if not self.reward_history:
            return "neutral"
        
        recent_avg = np.mean(list(self.reward_history)[-20:])
        
        if recent_avg > 0.5:
            return "satisfied"
        elif recent_avg > 0.0:
            return "content"
        elif recent_avg > -0.5:
            return "struggling"
        else:
            return "distressed"
    
    def save(self, path: str):
        """Save reward system state"""
        state = {}
        if self.use_rnd:
            state['rnd'] = self.rnd.state_dict()
        if self.use_icm:
            state['icm'] = self.icm.state_dict()
        torch.save(state, path)
    
    def load(self, path: str):
        """Load reward system state"""
        state = torch.load(path, map_location='cpu')
        if self.use_rnd and 'rnd' in state:
            self.rnd.load_state_dict(state['rnd'])
        if self.use_icm and 'icm' in state:
            self.icm.load_state_dict(state['icm'])

