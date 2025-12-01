# ------------------------------------------------------------------------------
# rl/policy.py - Transformer-based policy network
# ------------------------------------------------------------------------------
"""
Transformer policy with personality conditioning.
Integrates with Stable-Baselines3 and TorchRL.
"""
import torch
import torch.nn as nn
from typing import Tuple, Optional
from stable_baselines3.common.policies import ActorCriticPolicy
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor


class TransformerEncoder(nn.Module):
    """
    Transformer encoder for observation processing.
    """
    def __init__(self, obs_dim: int, d_model: int = 128, 
                 nhead: int = 4, num_layers: int = 2, 
                 dim_feedforward: int = 256, dropout: float = 0.1):
        super().__init__()
        
        self.obs_proj = nn.Linear(obs_dim, d_model)
        self.pos_encoding = nn.Parameter(torch.randn(1, 10, d_model))
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            activation='gelu',
            batch_first=True
        )
        
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm = nn.LayerNorm(d_model)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x: (B, obs_dim)
        returns: (B, d_model)
        """
        # Project to d_model
        x = self.obs_proj(x).unsqueeze(1)  # (B, 1, d_model)
        
        # Add positional encoding
        x = x + self.pos_encoding[:, :1, :]
        
        # Encode
        x = self.encoder(x)  # (B, 1, d_model)
        
        # Pool
        x = x.squeeze(1)  # (B, d_model)
        x = self.norm(x)
        
        return x


class TransformerPolicy(ActorCriticPolicy):
    """
    Transformer-based actor-critic policy for SB3.
    """
    def __init__(self, observation_space, action_space, lr_schedule, 
                 d_model: int = 128, nhead: int = 4, num_layers: int = 2,
                 *args, **kwargs):
        
        self.d_model = d_model
        self.nhead = nhead
        self.num_layers = num_layers
        
        super().__init__(observation_space, action_space, lr_schedule, 
                        *args, **kwargs)
    
    def _build_mlp_extractor(self) -> None:
        """Build transformer feature extractor"""
        obs_dim = self.observation_space.shape[0]
        
        # Transformer encoder
        self.features_extractor = TransformerEncoder(
            obs_dim=obs_dim,
            d_model=self.d_model,
            nhead=self.nhead,
            num_layers=self.num_layers
        )
        
        # Actor head
        self.action_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2),
            nn.Tanh(),
            nn.Linear(self.d_model // 2, self.action_space.shape[0])
        )
        
        # Critic head
        self.value_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2),
            nn.Tanh(),
            nn.Linear(self.d_model // 2, 1)
        )
        
        # Log std for action distribution
        self.log_std = nn.Parameter(
            torch.zeros(self.action_space.shape[0])
        )
    
    def forward(self, obs: torch.Tensor, deterministic: bool = False):
        """
        Forward pass.
        Returns: actions, values, log_probs
        """
        # Extract features
        features = self.features_extractor(obs)
        
        # Actor
        action_mean = self.action_net(features)
        action_mean = torch.tanh(action_mean)  # Bound to [-1, 1]
        
        # Critic
        values = self.value_net(features).squeeze(-1)
        
        return action_mean, values
    
    def _predict(self, observation: torch.Tensor, 
                deterministic: bool = False) -> torch.Tensor:
        """Predict action"""
        action_mean, _ = self.forward(observation, deterministic)
        
        if deterministic:
            return action_mean
        
        # Sample from distribution
        std = torch.exp(self.log_std)
        dist = torch.distributions.Normal(action_mean, std)
        action = dist.sample()
        
        return torch.tanh(action)