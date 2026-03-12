# rl/policy.py - Transformer-based policy network
"""
Transformer policy with personality conditioning.
Integrates with Stable-Baselines3 and TorchRL.

Two policy classes
------------------
TransformerPolicy    — NPC agents, 13-dim continuous action space.
GodTransformerPolicy — God agents, 18-dim action space.
                       Dims  0-12 : base movement controls (same as NPC)
                       Dims 13-17 : god ability extension
                         [13] trigger_flag  — Bernoulli: use an ability this step?
                         [14] ability_idx   — which ability (softmax selection)
                         [15] param1        — tanh, e.g. target x delta
                         [16] param2        — tanh, e.g. target z delta
                         [17] param3        — tanh, e.g. intensity / duration

Action array layout (dims 0-12 shared between NPC and God)
───────────────────────────────────────────────────────────
  0  move_forward  -1.0 … 1.0
  1  move_strafe   -1.0 … 1.0
  2  jump          > 0.5 = True
  3  sneak         > 0.5 = True
  4  attack        > 0.5 = True
  5  use           > 0.5 = True
  6  drop          > 0.5 = True
  7  open_inv      > 0.5 = True
  8  swap_hand     > 0.5 = True
  9  yaw_delta     scaled × 2.0 → degrees
 10  pitch_delta   scaled × 1.2 → degrees
 11  sprint        > 0.5 = True
 12  hotbar_slot   > -0.5 → slot 0-8,  ≤ -0.5 → no change (None)

Why a subclass and not just a larger action space
-------------------------------------------------
God abilities have cooldowns and discrete selection semantics that are
fundamentally different from continuous movement dims. The god policy:
  - Uses a separate ability head with its own architecture
  - Learns a trigger threshold — don't spam abilities every step
  - Selects which ability via softmax over the agent's available set
  - Passes continuous params for spatial targeting

agent.act_god() reads dims 13-17 and dispatches to agent.use_god_ability()
only when dim 13 (trigger_flag) >= 0.5, so RL can learn when NOT to use
abilities (save cooldowns, avoid telegraphing) as naturally as when to use them.
"""

import torch
import torch.nn as nn
import numpy as np
from typing import Tuple, Optional
from stable_baselines3.common.policies import ActorCriticPolicy


# =============================================================================
# Shared encoder
# =============================================================================

class TransformerEncoder(nn.Module):
    """Transformer encoder for observation feature extraction."""

    def __init__(self, obs_dim: int, d_model: int = 128,
                 nhead: int = 4, num_layers: int = 2,
                 dim_feedforward: int = 256, dropout: float = 0.1):
        super().__init__()
        self.obs_proj     = nn.Linear(obs_dim, d_model)
        self.pos_encoding = nn.Parameter(torch.randn(1, 10, d_model))
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout, activation='gelu', batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.norm    = nn.LayerNorm(d_model)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, obs_dim) → (B, d_model)"""
        x = self.obs_proj(x).unsqueeze(1)
        x = x + self.pos_encoding[:, :1, :]
        x = self.encoder(x).squeeze(1)
        return self.norm(x)


# =============================================================================
# NPC policy  (13-dim)
# =============================================================================

class TransformerPolicy(ActorCriticPolicy):
    """
    Transformer actor-critic for NPC agents.
    Action space: 13-dim continuous [-1, 1].

    Dim layout: see module docstring (dims 0-12).
    """

    def __init__(self, observation_space, action_space, lr_schedule,
                 d_model: int = 128, nhead: int = 4, num_layers: int = 2,
                 *args, **kwargs):
        self.d_model    = d_model
        self.nhead      = nhead
        self.num_layers = num_layers
        super().__init__(observation_space, action_space, lr_schedule,
                         *args, **kwargs)

    def _build_mlp_extractor(self) -> None:
        obs_dim    = self.observation_space.shape[0]
        action_dim = self.action_space.shape[0]   # 13 when space is set correctly
        self.features_extractor = TransformerEncoder(
            obs_dim=obs_dim, d_model=self.d_model,
            nhead=self.nhead, num_layers=self.num_layers,
        )
        self.action_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2), nn.Tanh(),
            nn.Linear(self.d_model // 2, action_dim),
        )
        self.value_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2), nn.Tanh(),
            nn.Linear(self.d_model // 2, 1),
        )
        self.log_std = nn.Parameter(torch.zeros(action_dim))

    def forward(self, obs: torch.Tensor,
                deterministic: bool = False) -> Tuple[torch.Tensor, torch.Tensor]:
        features    = self.features_extractor(obs)
        action_mean = torch.tanh(self.action_net(features))
        values      = self.value_net(features).squeeze(-1)
        return action_mean, values

    def _predict(self, observation: torch.Tensor,
                 deterministic: bool = False) -> torch.Tensor:
        action_mean, _ = self.forward(observation, deterministic)
        if deterministic:
            return action_mean
        std = torch.exp(self.log_std)
        return torch.tanh(torch.distributions.Normal(action_mean, std).sample())


# =============================================================================
# God ability head
# =============================================================================

class GodAbilityHead(nn.Module):
    """
    Separate network head that outputs god ability decisions.

    Outputs (raw, before decoding):
      trigger_logit   (B, 1)           — sigmoid → P(use ability this step)
      ability_logits  (B, n_abilities) — softmax → which ability to use
      params          (B, 3)           — tanh → continuous targeting params
    """

    def __init__(self, d_model: int, n_abilities: int):
        super().__init__()
        self.n_abilities = n_abilities
        trunk_out = d_model // 4
        self.trunk = nn.Sequential(
            nn.Linear(d_model, d_model // 2), nn.GELU(),
            nn.Linear(d_model // 2, trunk_out), nn.GELU(),
        )
        self.trigger_head = nn.Linear(trunk_out, 1)
        self.ability_head = nn.Linear(trunk_out, n_abilities)
        self.param_head   = nn.Linear(trunk_out, 3)

    def forward(self, features: torch.Tensor
                ) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = self.trunk(features)
        return (
            self.trigger_head(h),           # (B, 1)  raw logit
            self.ability_head(h),           # (B, N)  raw logits
            torch.tanh(self.param_head(h))  # (B, 3)  bounded params
        )

    def decode(self,
               trigger_logit:  torch.Tensor,
               ability_logits: torch.Tensor,
               params:         torch.Tensor,
               deterministic:  bool  = False,
               threshold:      float = 0.5) -> torch.Tensor:
        """
        Produce the 5-dim god extension vector.

        Layout: [trigger_flag, ability_idx, param1, param2, param3]
        These map to action dims 13-17 consumed by agent.act_god().

        Stochastic: trigger ~ Bernoulli(sigmoid); ability ~ Categorical(softmax)
        Deterministic: trigger = sigmoid > threshold; ability = argmax
        """
        trigger_prob = torch.sigmoid(trigger_logit).squeeze(-1)  # (B,)

        if deterministic:
            trigger_flag = (trigger_prob > threshold).float()
            ability_idx  = ability_logits.argmax(dim=-1).float()
        else:
            trigger_flag = torch.bernoulli(trigger_prob)
            ability_idx  = torch.distributions.Categorical(
                logits=ability_logits
            ).sample().float()

        return torch.stack([
            trigger_flag,
            ability_idx,
            params[:, 0],
            params[:, 1],
            params[:, 2],
        ], dim=-1)   # (B, 5)


# =============================================================================
# God policy  (18-dim)
# =============================================================================

class GodTransformerPolicy(ActorCriticPolicy):
    """
    Transformer actor-critic for God agents.  Action space: 18-dim.

    dims  0-12 : base movement  (same as TransformerPolicy, 13-dim)
    dims 13-17 : god ability extension  (from GodAbilityHead)

    Construction
    ------------
    n_abilities must match the god type's ability count:

        from ai_core.god_controls import GodControlSystem
        from rl.policy import GodTransformerPolicy
        import gymnasium as gym

        n_ab = len(GodControlSystem(agent.god_type).abilities)
        god_action_space = gym.spaces.Box(
            low=-1.0, high=1.0,
            shape=(GodTransformerPolicy.TOTAL_DIM,),   # (18,)
            dtype=np.float32,
        )
        policy = GodTransformerPolicy(
            observation_space=obs_space,   # shape (50,) for default agents
            action_space=god_action_space,
            lr_schedule=lambda _: 3e-4,
            n_abilities=n_ab,
        )

    act_god() integration in agent.py
    -----------------------------------
    act_god(action_18dim) handles the full 18-dim vector:
      - Passes dims 0-12 to the base act() for movement + hotbar + sprint
      - If action[13] >= 0.5:
          ability_idx = int(round(action[14]))
          name = god_controls.ability_names()[ability_idx]
          use_god_ability(name, param1=action[15], param2=action[16],
                                param3=action[17])
    """

    BASE_DIM  = 13   # dims 0-12: movement + sprint + hotbar_slot
    GOD_DIM   = 5    # dims 13-17: trigger + ability_idx + 3 params
    TOTAL_DIM = 18   # BASE_DIM + GOD_DIM

    def __init__(self, observation_space, action_space, lr_schedule,
                 n_abilities: int = 6,
                 d_model: int = 128, nhead: int = 4, num_layers: int = 2,
                 trigger_threshold: float = 0.5,
                 *args, **kwargs):
        self.n_abilities       = n_abilities
        self.d_model           = d_model
        self.nhead             = nhead
        self.num_layers        = num_layers
        self.trigger_threshold = trigger_threshold
        super().__init__(observation_space, action_space, lr_schedule,
                         *args, **kwargs)

    def _build_mlp_extractor(self) -> None:
        obs_dim = self.observation_space.shape[0]

        self.features_extractor = TransformerEncoder(
            obs_dim=obs_dim, d_model=self.d_model,
            nhead=self.nhead, num_layers=self.num_layers,
        )

        # Base movement head  (dims 0-12: movement + sprint + hotbar_slot)
        self.action_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2), nn.Tanh(),
            nn.Linear(self.d_model // 2, self.BASE_DIM),
        )

        # God ability head  (dims 13-17)
        self.ability_head = GodAbilityHead(self.d_model, self.n_abilities)

        # Critic
        self.value_net = nn.Sequential(
            nn.Linear(self.d_model, self.d_model // 2), nn.Tanh(),
            nn.Linear(self.d_model // 2, 1),
        )

        # Separate log_std for base continuous dims vs ability continuous params.
        # BASE_DIM = 13 so log_std_base correctly covers all 13 movement dims.
        self.log_std_base   = nn.Parameter(torch.zeros(self.BASE_DIM))
        self.log_std_params = nn.Parameter(torch.zeros(3))

    def forward(self, obs: torch.Tensor,
                deterministic: bool = False) -> Tuple[torch.Tensor, torch.Tensor]:
        features  = self.features_extractor(obs)
        base_mean = torch.tanh(self.action_net(features))            # (B, 13)
        tl, al, params = self.ability_head(features)
        god_ext   = self.ability_head.decode(
            tl, al, params,
            deterministic=deterministic,
            threshold=self.trigger_threshold,
        )                                                             # (B, 5)
        action = torch.cat([base_mean, god_ext], dim=-1)             # (B, 18)
        values = self.value_net(features).squeeze(-1)
        return action, values

    def _predict(self, observation: torch.Tensor,
                 deterministic: bool = False) -> torch.Tensor:
        features = self.features_extractor(observation)

        # Base movement (13 dims)
        base_mean = torch.tanh(self.action_net(features))
        if deterministic:
            base_action = base_mean
        else:
            std = torch.exp(self.log_std_base)   # shape (13,) — matches base_mean
            base_action = torch.tanh(
                torch.distributions.Normal(base_mean, std).sample()
            )

        # God ability (dims 13-17)
        tl, al, params = self.ability_head(features)
        if not deterministic:
            std_p  = torch.exp(self.log_std_params)
            params = torch.tanh(params + torch.randn_like(params) * std_p)

        god_ext = self.ability_head.decode(
            tl, al, params,
            deterministic=deterministic,
            threshold=self.trigger_threshold,
        )
        return torch.cat([base_action, god_ext], dim=-1)   # (B, 18)

    def get_ability_probabilities(
        self, obs: torch.Tensor
    ) -> Tuple[float, np.ndarray]:
        """
        Diagnostic — (trigger_prob, per_ability_probs) for one observation.
        """
        with torch.no_grad():
            features = self.features_extractor(obs)
            tl, al, _ = self.ability_head(features)
            trigger_prob  = float(torch.sigmoid(tl).item())
            ability_probs = torch.softmax(al, dim=-1).squeeze().cpu().numpy()
        return trigger_prob, ability_probs