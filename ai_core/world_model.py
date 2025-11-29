# ai_core/world_model.py - NEURAL WORLD MODEL FOR AGI
"""
Transformer-based World Model for Divine World AGI
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
- Replaces rule-based brain_core.py evaluation
- Provides predictions for planner
- Enables imagination-based learning (dream training)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Normal, Categorical
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from collections import deque
import logging
from pathlib import Path
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
    action_dim: int = 11
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
# Multimodal Encoders
# ============================================================================

class VisionEncoder(nn.Module):
    """CNN encoder for visual observations"""
    
    def __init__(self, channels: int, output_dim: int):
        super().__init__()
        
        # ResNet-style CNN
        self.conv = nn.Sequential(
            # 84x84x3 -> 42x42x32
            nn.Conv2d(channels, 32, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(32),
            
            # 42x42x32 -> 21x21x64
            nn.Conv2d(32, 64, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(64),
            
            # 21x21x64 -> 11x11x128
            nn.Conv2d(64, 128, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(128),
            
            # 11x11x128 -> 6x6x256
            nn.Conv2d(128, 256, kernel_size=3, stride=2, padding=1),
            nn.ReLU(),
            nn.BatchNorm2d(256),
        )
        
        # Spatial pooling
        self.pool = nn.AdaptiveAvgPool2d((1, 1))
        
        # Project to output dimension
        self.fc = nn.Linear(256, output_dim)
    
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, T, C, H, W) or (B, C, H, W)
        Returns:
            features: (B, T, D) or (B, D)
        """
        has_time = len(x.shape) == 5
        
        if has_time:
            B, T = x.shape[:2]
            x = x.view(B * T, *x.shape[2:])
        
        # CNN
        x = self.conv(x)  # (B*T, 256, 6, 6)
        x = self.pool(x)  # (B*T, 256, 1, 1)
        x = x.flatten(1)  # (B*T, 256)
        x = self.fc(x)    # (B*T, D)
        
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
        """
        Args:
            x: (B, T, audio_dim) or (B, audio_dim)
        Returns:
            features: (B, T, D) or (B, D)
        """
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
        """
        Args:
            x: (B, T, proprio_dim) or (B, proprio_dim)
        Returns:
            features: (B, T, D) or (B, D)
        """
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
        """
        Args:
            x: (B, T, D)
            mask: (T, T) causal mask
        Returns:
            output: (B, T, D)
        """
        # Self-attention with residual
        attn_out, _ = self.attention(x, x, x, attn_mask=mask)
        x = self.norm1(x + attn_out)
        
        # Feedforward with residual
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
        """
        Args:
            encodings: (B, T, D) pre-encoded multimodal features
            mask: (T, T) causal attention mask
        Returns:
            output: (B, T, D) contextualized representations
        """
        B, T, D = encodings.shape
        
        # Add positional encoding
        x = encodings + self.pos_embedding[:, :T, :]
        
        # Transformer blocks
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
        """
        Args:
            x: (B, T, D)
        Returns:
            z: (B, T, latent_dim) sampled latent
            mu: (B, T, latent_dim)
            logvar: (B, T, latent_dim)
        """
        mu = self.fc_mu(x)
        logvar = self.fc_logvar(x)
        
        # Reparameterization trick
        std = torch.exp(0.5 * logvar)
        eps = torch.randn_like(std)
        z = mu + eps * std
        
        return z, mu, logvar


# ============================================================================
# Prediction Heads
# ============================================================================

class RewardPredictor(nn.Module):
    """Predict reward from latent state"""
    
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
        """
        Args:
            x: (B, T, D)
        Returns:
            reward: (B, T, 1)
        """
        return self.mlp(x)


class TerminationPredictor(nn.Module):
    """Predict episode termination probability"""
    
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
        """
        Args:
            x: (B, T, D)
        Returns:
            termination_prob: (B, T, 1)
        """
        return self.mlp(x)


class NextStatePredictor(nn.Module):
    """Predict next latent state"""
    
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
        """
        Args:
            x: (B, T, D)
        Returns:
            next_state: (B, T, D)
        """
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
        self.reward_head = RewardPredictor(pred_input_dim)
        self.termination_head = TerminationPredictor(pred_input_dim)
        self.next_state_head = NextStatePredictor(pred_input_dim + config.action_dim, pred_input_dim)
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(
            self.parameters(),
            lr=config.learning_rate,
            weight_decay=1e-5
        )
        
        # Loss tracking
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
                - 'action': (B, T, action_dim)
        
        Returns:
            encoding: (B, T, d_model)
        """
        encodings = []
        
        # Vision
        if 'vision' in observation and observation['vision'] is not None:
            vision_enc = self.transformer.vision_encoder(observation['vision'])
            encodings.append(vision_enc)
        
        # Audio
        if 'audio' in observation and observation['audio'] is not None:
            audio_enc = self.transformer.audio_encoder(observation['audio'])
            encodings.append(audio_enc)
        
        # Proprioception (always present)
        if 'proprio' in observation:
            proprio_enc = self.transformer.proprio_encoder(observation['proprio'])
            encodings.append(proprio_enc)
        
        # Action
        if 'action' in observation:
            action_enc = self.transformer.action_encoder(observation['action'])
            encodings.append(action_enc)
        
        # Combine encodings (sum for simplicity, could use learned weights)
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
            predictions: dict with:
                - 'reward': (B, T, 1)
                - 'termination': (B, T, 1)
                - 'next_state': (B, T, latent_dim) if VAE else (B, T, d_model)
                - 'latent': (B, T, latent_dim) if return_latent and VAE
                - 'mu', 'logvar': if VAE
        """
        # Encode observation
        encoding = self.encode_observation(observation)
        
        # Create causal mask
        T = encoding.shape[1]
        mask = torch.triu(torch.ones(T, T, device=self.device) * float('-inf'), diagonal=1)
        
        # Transformer
        context = self.transformer(encoding, mask)
        
        # Variational encoding (optional)
        if self.config.use_vae:
            latent, mu, logvar = self.vae_encoder(context)
            pred_input = latent
        else:
            pred_input = context
            mu, logvar = None, None
        
        # Predictions
        reward_pred = self.reward_head(pred_input)
        termination_pred = self.termination_head(pred_input)
        
        # Next state prediction (condition on action)
        if 'action' in observation:
            action = observation['action']
            next_state_input = torch.cat([pred_input, action], dim=-1)
            next_state_pred = self.next_state_head(next_state_input)
        else:
            next_state_pred = None
        
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
            initial_obs: starting observation
            actions: (B, steps, action_dim) planned actions
            steps: number of steps to imagine
        
        Returns:
            trajectory: dict with imagined rewards, terminations, states
        """
        B = actions.shape[0]
        device = actions.device
        
        imagined_rewards = []
        imagined_terminations = []
        imagined_states = []
        
        # Start with initial observation
        current_obs = {k: v[:, -1:, ...] for k, v in initial_obs.items()}  # Take last timestep
        
        for t in range(steps):
            # Add action to observation
            current_obs['action'] = actions[:, t:t+1, :]
            
            # Predict
            with torch.no_grad():
                pred = self.forward(current_obs, return_latent=True)
            
            imagined_rewards.append(pred['reward'])
            imagined_terminations.append(pred['termination'])
            
            if self.config.use_vae:
                imagined_states.append(pred['latent'])
                # Update observation with predicted next state
                current_obs['proprio'] = pred['next_state']  # Simplified
            else:
                imagined_states.append(pred['next_state'])
        
        return {
            'rewards': torch.cat(imagined_rewards, dim=1),  # (B, steps, 1)
            'terminations': torch.cat(imagined_terminations, dim=1),
            'states': torch.cat(imagined_states, dim=1)
        }
    
    def compute_loss(self, observation: Dict[str, torch.Tensor],
                     targets: Dict[str, torch.Tensor]) -> Tuple[torch.Tensor, Dict[str, float]]:
        """
        Compute training loss.
        
        Args:
            observation: multimodal observation dict
            targets: dict with:
                - 'reward': (B, T, 1) actual rewards
                - 'termination': (B, T, 1) actual terminations
                - 'next_state': (B, T, latent_dim) actual next states (if available)
        
        Returns:
            total_loss: scalar
            loss_dict: breakdown of losses
        """
        pred = self.forward(observation, return_latent=True)
        
        losses = {}
        
        # Reward prediction loss
        reward_loss = F.mse_loss(pred['reward'], targets['reward'])
        losses['reward'] = reward_loss.item()
        
        # Termination prediction loss
        termination_loss = F.binary_cross_entropy(
            pred['termination'], targets['termination']
        )
        losses['termination'] = termination_loss.item()
        
        # Next state prediction loss (if available)
        if pred['next_state'] is not None and 'next_state' in targets:
            next_state_loss = F.mse_loss(pred['next_state'], targets['next_state'])
            losses['next_state'] = next_state_loss.item()
        else:
            next_state_loss = 0.0
        
        # VAE KL divergence (if using VAE)
        if self.config.use_vae:
            mu = pred['mu']
            logvar = pred['logvar']
            kl_loss = -0.5 * torch.sum(1 + logvar - mu.pow(2) - logvar.exp(), dim=-1).mean()
            losses['kl'] = kl_loss.item()
        else:
            kl_loss = 0.0
        
        # Total loss
        total_loss = reward_loss + termination_loss + next_state_loss + self.config.kl_weight * kl_loss
        losses['total'] = total_loss.item()
        
        return total_loss, losses
    
    def train_step(self, batch: Dict[str, torch.Tensor]) -> Dict[str, float]:
        """
        Single training step.
        
        Args:
            batch: dict with observations and targets
        
        Returns:
            loss_dict: losses for logging
        """
        self.train()
        
        # Move batch to device
        batch = {k: v.to(self.device) if isinstance(v, torch.Tensor) else v 
                 for k, v in batch.items()}
        
        # Forward pass
        observation = {
            'vision': batch.get('vision'),
            'audio': batch.get('audio'),
            'proprio': batch['proprio'],
            'action': batch['action']
        }
        
        targets = {
            'reward': batch['reward'],
            'termination': batch['termination'],
            'next_state': batch.get('next_state')
        }
        
        loss, loss_dict = self.compute_loss(observation, targets)
        
        # Backward pass
        self.optimizer.zero_grad()
        loss.backward()
        
        # Gradient clipping
        torch.nn.utils.clip_grad_norm_(self.parameters(), self.config.grad_clip)
        
        self.optimizer.step()
        
        # Track loss
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
        """Get model statistics"""
        return {
            'parameters': sum(p.numel() for p in self.parameters()),
            'trainable_parameters': sum(p.numel() for p in self.parameters() if p.requires_grad),
            'avg_loss': np.mean(list(self.loss_history)) if self.loss_history else 0.0,
            'device': str(self.device),
            'config': {
                'd_model': self.config.d_model,
                'n_layers': self.config.n_layers,
                'use_vae': self.config.use_vae,
                'latent_dim': self.config.latent_dim
            }
        }


# ============================================================================
# Ensemble World Model (for uncertainty estimation)
# ============================================================================

class EnsembleWorldModel:
    """
    Ensemble of world models for uncertainty estimation.
    Used for exploration bonuses and safe decision making.
    """
    
    def __init__(self, config: WorldModelConfig, n_models: int = 5):
        self.config = config
        self.n_models = n_models
        self.models = [WorldModel(config) for _ in range(n_models)]
        
        log.info(f"EnsembleWorldModel initialized with {n_models} models")
    
    def forward(self, observation: Dict[str, torch.Tensor]) -> Dict[str, torch.Tensor]:
        """
        Forward pass through ensemble.
        
        Returns predictions with mean and std across ensemble.
        """
        predictions = [model(observation) for model in self.models]
        
        # Stack predictions
        rewards = torch.stack([p['reward'] for p in predictions], dim=0)
        terminations = torch.stack([p['termination'] for p in predictions], dim=0)
        
        # Compute mean and std
        ensemble_pred = {
            'reward_mean': rewards.mean(dim=0),
            'reward_std': rewards.std(dim=0),
            'termination_mean': terminations.mean(dim=0),
            'termination_std': terminations.std(dim=0),
        }
        
        return ensemble_pred
    
    def train_step(self, batch: Dict[str, torch.Tensor]) -> List[Dict[str, float]]:
        """Train all models in ensemble"""
        loss_dicts = []
        for model in self.models:
            loss_dict = model.train_step(batch)
            loss_dicts.append(loss_dict)
        return loss_dicts
    
    def save(self, path: str):
        """Save all models"""
        for i, model in enumerate(self.models):
            model.save(f"{path}_model_{i}.pt")
    
    @classmethod
    def load(cls, path: str, n_models: int = 5) -> 'EnsembleWorldModel':
        """Load all models"""
        models = []
        for i in range(n_models):
            model = WorldModel.load(f"{path}_model_{i}.pt")
            models.append(model)
        
        ensemble = cls.__new__(cls)
        ensemble.models = models
        ensemble.n_models = n_models
        ensemble.config = models[0].config
        
        return ensemble


# ============================================================================
# Utility Functions
# ============================================================================

def create_default_world_model(device: str = 'cuda') -> WorldModel:
    """Create world model with default configuration"""
    config = WorldModelConfig(device=device)
    return WorldModel(config)


def test_world_model():
    """Test world model with dummy data"""
    log.info("Testing WorldModel...")
    
    config = WorldModelConfig(device='cpu')
    model = WorldModel(config)
    
    # Create dummy batch
    B, T = 4, 16
    batch = {
        'vision': torch.randn(B, T, 3, 84, 84),
        'audio': torch.randn(B, T, 128),
        'proprio': torch.randn(B, T, 32),
        'action': torch.randn(B, T, 11),
        'reward': torch.randn(B, T, 1),
        'termination': torch.randint(0, 2, (B, T, 1)).float(),
    }
    
    # Forward pass
    log.info("Testing forward pass...")
    pred = model(batch)
    log.info(f"  Reward pred shape: {pred['reward'].shape}")
    log.info(f"  Termination pred shape: {pred['termination'].shape}")
    
    # Training step
    log.info("Testing training step...")
    loss_dict = model.train_step(batch)
    log.info(f"  Losses: {loss_dict}")
    
    # Imagination
    log.info("Testing imagination...")
    initial_obs = {k: v[:, :4, ...] for k, v in batch.items() if k not in ['reward', 'termination']}
    actions = torch.randn(B, 8, 11)
    imagined = model.imagine(initial_obs, actions, steps=8)
    log.info(f"  Imagined rewards shape: {imagined['rewards'].shape}")
    
    # Save/load
    log.info("Testing save/load...")
    model.save('test_world_model.pt')
    loaded = WorldModel.load('test_world_model.pt', device='cpu')
    log.info(f"  Loaded model stats: {loaded.get_stats()}")
    
    log.info("✅ WorldModel tests passed!")


# ============================================================================
# Experience Replay Buffer for World Model Training
# ============================================================================

class WorldModelReplayBuffer:
    """
    Replay buffer optimized for world model training.
    Stores trajectories with multimodal observations.
    """
    
    def __init__(self, capacity: int = 100000, sequence_length: int = 64):
        self.capacity = capacity
        self.sequence_length = sequence_length
        
        # Storage
        self.trajectories = deque(maxlen=capacity)
        self.current_trajectory = None
        
        log.info(f"WorldModelReplayBuffer initialized: capacity={capacity}, seq_len={sequence_length}")
    
    def start_trajectory(self):
        """Start collecting a new trajectory"""
        self.current_trajectory = {
            'vision': [],
            'audio': [],
            'proprio': [],
            'action': [],
            'reward': [],
            'termination': [],
        }
    
    def add_step(self, vision: Optional[np.ndarray] = None,
                 audio: Optional[np.ndarray] = None,
                 proprio: np.ndarray = None,
                 action: np.ndarray = None,
                 reward: float = 0.0,
                 termination: bool = False):
        """Add single step to current trajectory"""
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
        """Finish current trajectory and add to buffer"""
        if self.current_trajectory is None:
            return
        
        # Convert lists to arrays
        trajectory = {}
        for key in self.current_trajectory:
            if len(self.current_trajectory[key]) > 0:
                trajectory[key] = np.array(self.current_trajectory[key])
        
        # Only store if trajectory has minimum length
        if len(trajectory.get('reward', [])) >= self.sequence_length:
            self.trajectories.append(trajectory)
        
        self.current_trajectory = None
    
    def sample_batch(self, batch_size: int, device: str = 'cuda') -> Dict[str, torch.Tensor]:
        """
        Sample batch of sequences for training.
        
        Returns:
            batch: dict with (batch_size, sequence_length, ...) tensors
        """
        if len(self.trajectories) == 0:
            raise ValueError("Buffer is empty")
        
        batch = {
            'vision': [] if any('vision' in t for t in self.trajectories) else None,
            'audio': [] if any('audio' in t for t in self.trajectories) else None,
            'proprio': [],
            'action': [],
            'reward': [],
            'termination': [],
        }
        
        for _ in range(batch_size):
            # Sample random trajectory
            traj = self.trajectories[np.random.randint(len(self.trajectories))]
            
            # Sample random start index
            max_start = len(traj['reward']) - self.sequence_length
            if max_start <= 0:
                start_idx = 0
            else:
                start_idx = np.random.randint(max_start)
            
            end_idx = start_idx + self.sequence_length
            
            # Extract sequence
            if batch['vision'] is not None and 'vision' in traj:
                batch['vision'].append(traj['vision'][start_idx:end_idx])
            if batch['audio'] is not None and 'audio' in traj:
                batch['audio'].append(traj['audio'][start_idx:end_idx])
            
            batch['proprio'].append(traj['proprio'][start_idx:end_idx])
            batch['action'].append(traj['action'][start_idx:end_idx])
            batch['reward'].append(traj['reward'][start_idx:end_idx])
            batch['termination'].append(traj['termination'][start_idx:end_idx])
        
        # Convert to tensors
        batch_tensors = {}
        for key, value in batch.items():
            if value is not None and len(value) > 0:
                batch_tensors[key] = torch.tensor(
                    np.array(value), dtype=torch.float32, device=device
                )
        
        # Ensure reward and termination have correct shape
        batch_tensors['reward'] = batch_tensors['reward'].unsqueeze(-1)
        batch_tensors['termination'] = batch_tensors['termination'].unsqueeze(-1)
        
        return batch_tensors
    
    def __len__(self):
        return len(self.trajectories)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get buffer statistics"""
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
    """
    Trainer for world model with replay buffer management.
    Handles online learning from Minecraft and offline learning from replays.
    """
    
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
        """
        Train on replay buffer (offline learning).
        
        Args:
            num_steps: number of training steps
        
        Returns:
            training_stats: dict with losses and metrics
        """
        log.info(f"Starting offline training for {num_steps} steps...")
        
        if len(self.replay_buffer) == 0:
            log.warning("Replay buffer is empty, cannot train")
            return {}
        
        losses = []
        
        for step in range(num_steps):
            try:
                # Sample batch
                batch = self.replay_buffer.sample_batch(
                    self.batch_size, 
                    device=self.world_model.device
                )
                
                # Training step
                loss_dict = self.world_model.train_step(batch)
                losses.append(loss_dict)
                
                self.step_count += 1
                self.loss_history.append(loss_dict['total'])
                
                # Logging
                if (step + 1) % self.log_interval == 0:
                    avg_loss = np.mean([l['total'] for l in losses[-self.log_interval:]])
                    log.info(f"  Step {step+1}/{num_steps}: avg_loss={avg_loss:.4f}")
            
            except Exception as e:
                log.error(f"Training step failed: {e}")
                continue
        
        # Compute statistics
        stats = {
            'total_steps': num_steps,
            'avg_total_loss': np.mean([l['total'] for l in losses]),
            'avg_reward_loss': np.mean([l['reward'] for l in losses]),
            'avg_termination_loss': np.mean([l['termination'] for l in losses]),
            'buffer_stats': self.replay_buffer.get_stats()
        }
        
        if 'next_state' in losses[0]:
            stats['avg_next_state_loss'] = np.mean([l['next_state'] for l in losses])
        if 'kl' in losses[0]:
            stats['avg_kl_loss'] = np.mean([l['kl'] for l in losses])
        
        log.info(f"Offline training complete: {stats}")
        
        return stats
    
    def train_online_step(self, trajectory: Dict[str, np.ndarray]) -> Dict[str, float]:
        """
        Train on single trajectory (online learning).
        
        Args:
            trajectory: dict with vision, audio, proprio, action, reward, termination
        
        Returns:
            loss_dict: training losses
        """
        # Add to replay buffer
        self.replay_buffer.start_trajectory()
        
        T = len(trajectory['reward'])
        for t in range(T):
            self.replay_buffer.add_step(
                vision=trajectory.get('vision', [None] * T)[t] if 'vision' in trajectory else None,
                audio=trajectory.get('audio', [None] * T)[t] if 'audio' in trajectory else None,
                proprio=trajectory['proprio'][t],
                action=trajectory['action'][t],
                reward=trajectory['reward'][t],
                termination=trajectory['termination'][t]
            )
        
        self.replay_buffer.end_trajectory()
        
        # Train if buffer has enough data
        if len(self.replay_buffer) < 10:
            return {'total': 0.0}
        
        # Sample batch and train
        batch = self.replay_buffer.sample_batch(
            self.batch_size,
            device=self.world_model.device
        )
        
        loss_dict = self.world_model.train_step(batch)
        
        self.step_count += 1
        self.loss_history.append(loss_dict['total'])
        
        return loss_dict
    
    def save_checkpoint(self, path: str):
        """Save trainer checkpoint"""
        self.world_model.save(path)
        log.info(f"Trainer checkpoint saved to {path}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get trainer statistics"""
        return {
            'step_count': self.step_count,
            'avg_recent_loss': np.mean(list(self.loss_history)) if self.loss_history else 0.0,
            'buffer_size': len(self.replay_buffer),
            'model_stats': self.world_model.get_stats()
        }


# ============================================================================
# Integration with Existing Backend
# ============================================================================

def integrate_world_model_with_agent(agent):
    """
    Integrate world model into existing NPCAgent.
    
    This function adds world model to agent and replaces
    rule-based brain_core evaluation with neural predictions.
    
    Usage:
        from ai_core.world_model import integrate_world_model_with_agent
        integrate_world_model_with_agent(agent)
    """
    log.info(f"Integrating WorldModel with agent {agent.agent_id}...")
    
    # Create world model
    config = WorldModelConfig(device='cuda' if torch.cuda.is_available() else 'cpu')
    world_model = WorldModel(config)
    
    # Create replay buffer
    replay_buffer = WorldModelReplayBuffer(capacity=50000, sequence_length=64)
    
    # Create trainer
    trainer = WorldModelTrainer(world_model, replay_buffer, batch_size=16)
    
    # Attach to agent
    agent.world_model = world_model
    agent.world_model_buffer = replay_buffer
    agent.world_model_trainer = trainer
    
    # Replace brain evaluation with world model predictions
    original_evaluate = agent.brain.evaluate_event
    
    def neural_evaluate(event, context=None):
        """Neural evaluation using world model"""
        try:
            # Build observation from event and context
            observation = _build_observation_from_context(agent, context)
            
            # Get world model prediction
            with torch.no_grad():
                pred = world_model(observation)
            
            # Extract reward prediction
            reward = pred['reward'][0, -1, 0].item()
            
            # Get emotion delta from reward
            emotion_delta = agent.brain._reward_to_emotion_delta(reward, event)
            
            return reward, emotion_delta
            
        except Exception as e:
            log.warning(f"World model evaluation failed, using fallback: {e}")
            return original_evaluate(event, context)
    
    # Monkey-patch evaluation
    agent.brain.evaluate_event = neural_evaluate
    
    log.info(f"✅ WorldModel integrated with {agent.agent_id}")


def _build_observation_from_context(agent, context: Optional[Dict] = None) -> Dict[str, torch.Tensor]:
    """Build world model observation from agent context"""
    if context is None:
        context = {}
    
    device = agent.world_model.device if hasattr(agent, 'world_model') else 'cpu'
    
    # Proprioception (always available)
    proprio = np.array([
        context.get('health', agent.health) / 20.0,
        context.get('hunger', agent.hunger) / 20.0,
        context.get('saturation', 5.0) / 20.0,
        # Position
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['x'] / 100.0,
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['y'] / 100.0,
        context.get('position', {'x': 0, 'y': 64, 'z': 0})['z'] / 100.0,
        # Emotions
        *agent.emotion.as_array().tolist(),
        # Personality
        *agent.personality.as_array().tolist(),
    ], dtype=np.float32)
    
    # Pad to proprio_dim (32)
    if len(proprio) < 32:
        proprio = np.pad(proprio, (0, 32 - len(proprio)))
    
    observation = {
        'proprio': torch.tensor(proprio, dtype=torch.float32, device=device).unsqueeze(0).unsqueeze(0),
    }
    
    # Vision (if available)
    if 'visual' in context and context['visual'] is not None:
        visual = context['visual']
        if isinstance(visual, np.ndarray):
            # Resize to 84x84 if needed
            if visual.shape[:2] != (84, 84):
                import cv2
                visual = cv2.resize(visual, (84, 84))
            
            # Convert to tensor (C, H, W)
            if len(visual.shape) == 2:  # Grayscale
                visual = visual[:, :, np.newaxis]
            
            visual = torch.tensor(visual, dtype=torch.float32, device=device)
            visual = visual.permute(2, 0, 1) / 255.0  # Normalize
            observation['vision'] = visual.unsqueeze(0).unsqueeze(0)
    
    # Audio (if available)
    if 'audio' in context and context['audio'] is not None:
        audio = context['audio']
        if isinstance(audio, np.ndarray):
            # Ensure correct shape (128,)
            if len(audio) < 128:
                audio = np.pad(audio, (0, 128 - len(audio)))
            elif len(audio) > 128:
                audio = audio[:128]
            
            observation['audio'] = torch.tensor(
                audio, dtype=torch.float32, device=device
            ).unsqueeze(0).unsqueeze(0)
    
    # Action (last action)
    if hasattr(agent, 'last_action') and agent.last_action is not None:
        observation['action'] = torch.tensor(
            agent.last_action, dtype=torch.float32, device=device
        ).unsqueeze(0).unsqueeze(0)
    else:
        observation['action'] = torch.zeros(1, 1, 11, dtype=torch.float32, device=device)
    
    return observation


# ============================================================================
# Export
# ============================================================================

__all__ = [
    'WorldModel',
    'WorldModelConfig',
    'EnsembleWorldModel',
    'WorldModelReplayBuffer',
    'WorldModelTrainer',
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
    
    print("\n" + "="*70)
    print("  🌍 WORLD MODEL - Neural World Simulation")
    print("="*70 + "\n")
    
    # Run tests
    test_world_model()
    
    print("\n" + "="*70)
    print("  ✅ WorldModel ready for AGI integration")
    print("="*70 + "\n")