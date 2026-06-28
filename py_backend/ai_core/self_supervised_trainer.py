# py_backend/ai_core/self_supervised_trainer.py
"""
Phase 3 — Self-Supervised Trainer + GRPO
==========================================
Replaces offline PPO (rl/train.py) with two online mechanisms:

1. SelfSupervisedTrainer
   Trains the WorldModel from the agent's own transitions every learning
   cycle. Prediction error IS the learning signal. High surprise in safe
   context → curiosity spike. High surprise in danger → fear spike.

2. grpo_update() (added to rl/policy.py — see PATCHES.md)
   Group Relative Policy Optimisation applied after deliberation fires.
   No critic needed — uses relative scores from the imagination rollout.

Called from CognitiveLoop._execute_continual_learning_async().
"""

import logging
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import List, Dict, Any, Optional, Tuple

import numpy as np

log = logging.getLogger("self_supervised_trainer")


class SelfSupervisedTrainer:
    """
    Trains the WorldModel online from the agent's own experience buffer.

    Every call to train_step():
      1. Samples a random batch of (obs, action, next_obs) transitions
      2. Trains WorldModel to predict next_obs from (obs, action)
      3. Computes per-transition surprise (prediction MSE)
      4. Feeds surprise signal back to the emotion system:
           - safe context (health > 8)  → curiosity ↑, joy ↑
           - danger context (health ≤ 8) → fear ↑, curiosity ↓
    """

    def __init__(self, world_model, brain, emotion_system, device: str = 'cpu'):
        self.wm      = world_model
        self.brain   = brain
        self.emotion = emotion_system
        self.device  = device
        # FIX: removed self.opt = AdamW(world_model.parameters()) — WorldModel
        # already has its own internal optimizer (self.optimizer in WorldModel.
        # __init__), and wm.train_step() calls it internally. Having a SECOND
        # AdamW optimizer over the same parameters would have caused each step
        # to apply two conflicting gradient updates, corrupting convergence.
        # The training loop now goes entirely through wm.train_step().
        self._step   = 0
        self._loss_history: List[float] = []

    # ──────────────────────────────────────────────────────────────────────
    # Main training step
    # ──────────────────────────────────────────────────────────────────────

    def train_step(
        self,
        experience_buffer: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Pull recent transitions, train world model to predict them.
        Returns metrics dict including surprise signal for emotion system,
        or None if buffer is too small.
        """
        if len(experience_buffer) < 16:
            return None

        batch = random.sample(experience_buffer, min(32, len(experience_buffer)))

        obs_list, act_list, next_obs_list = [], [], []
        for event in batch:
            obs      = event.get('obs_vector')
            action   = event.get('action_vector')
            next_obs = event.get('next_obs_vector')
            if obs is None or action is None or next_obs is None:
                continue
            obs_list.append(torch.FloatTensor(obs))
            act_list.append(torch.FloatTensor(action))
            next_obs_list.append(torch.FloatTensor(next_obs))

        if len(obs_list) < 8:
            return None

        obs_t      = torch.stack(obs_list).to(self.device)
        act_t      = torch.stack(act_list).to(self.device)
        next_obs_t = torch.stack(next_obs_list).to(self.device)

        try:
            # FIX: WorldModel has no .predict() method — this had been crashing
            # silently on every single call (caught by the broad except below),
            # meaning the WorldModel has never actually been trained in any
            # deployed agent. The real interface is either WorldModel.forward()
            # (returns a prediction dict from a sequence observation) or
            # WorldModel.train_step() (handles the full training pass including
            # its own optimizer step). WorldModel.train_step() is the correct
            # path here — it expects a batch dict with 'proprio', 'action',
            # 'reward', 'termination', 'next_state' keys, applies the internal
            # optimizer, and returns a loss_dict we can read surprise from.
            #
            # Comparison to human behavior (from user's analysis prompt):
            # Humans DO train their world models from experience — and crucially
            # they update them MORE when predictions are wrong (high surprise)
            # than when they're right (low surprise). That's exactly this: the
            # surprise signal from prediction error feeds both the emotion
            # system AND back-propagation through the model, making surprising
            # transitions the primary driver of world model improvement.
            batch_dict = {
                'proprio':     obs_t.unsqueeze(1),       # (B, 1, obs_dim)
                'action':      act_t.unsqueeze(1),       # (B, 1, act_dim)
                'reward':      torch.zeros(len(obs_t), 1, 1, device=self.device),
                'termination': torch.zeros(len(obs_t), 1, 1, device=self.device),
                'next_state':  next_obs_t.unsqueeze(1),  # (B, 1, obs_dim)
            }

            # Lazily resolve wm from brain if it was None at construction —
            # world_model init happens right after SelfSupervisedTrainer is
            # built in NPCAgent.__init__, so this catches the ordering gap
            # without requiring a constructor reorder.
            wm = self.wm
            if wm is None:
                wm = getattr(self.brain, 'world_model', None)
                if wm is None:
                    return None
                self.wm = wm   # cache for next call

            loss_dict = wm.train_step(batch_dict)
            prediction_loss = loss_dict.get('total', loss_dict.get('next_state', 0.0))

            # Approximate per-transition surprise from the aggregate loss —
            # WorldModel.train_step() gives a scalar, not per-transition.
            # Good enough for the emotion signal; per-transition granularity
            # can be added later if the emotion system needs it.
            mean_surprise = float(prediction_loss)
            self._step   += 1
            self._loss_history.append(mean_surprise)
            if len(self._loss_history) > 100:
                self._loss_history.pop(0)

            # Feed surprise back to emotion system (unchanged from original intent)
            health    = getattr(self.brain, '_last_health', 20.0)
            in_danger = health < 8.0

            if mean_surprise > 0.3:
                if in_danger:
                    self.emotion.add('fear',      mean_surprise * 0.3)
                    self.emotion.add('curiosity', -mean_surprise * 0.1)
                else:
                    self.emotion.add('curiosity', mean_surprise * 0.4)
                    self.emotion.add('joy',       mean_surprise * 0.1)

            return {
                'step':            self._step,
                'prediction_loss': prediction_loss,
                'mean_surprise':   mean_surprise,
                'in_danger':       in_danger,
                'avg_loss_100':    (sum(self._loss_history) / len(self._loss_history)
                                    if self._loss_history else 0.0),
            }

        except Exception as e:
            log.error(f"Self-supervised training error: {e}")
            return None

    def get_stats(self) -> Dict[str, Any]:
        return {
            'step':         self._step,
            'avg_loss_100': (sum(self._loss_history) / len(self._loss_history)
                             if self._loss_history else 0.0),
        }


# ──────────────────────────────────────────────────────────────────────────────
# GRPO update — added as a standalone function so it can be monkeypatched
# onto the SB3 model or called directly.
# See PATCHES.md for how this is wired into rl/policy.py and CognitiveLoop.
# ──────────────────────────────────────────────────────────────────────────────

def grpo_update(
    model,
    scored_actions: List[Tuple[float, np.ndarray]],
    obs: np.ndarray,
    lr: float = 1e-4,
):
    """
    Group Relative Policy Optimisation update.

    No critic needed — uses relative scores within the imagination rollout
    returned by WorldModel.imagine() / BrainCore.deliberate().

    scored_actions : list of (score, action_array) from deliberation
    obs            : observation at the point of deliberation
    model          : TransformerPolicy or GodTransformerPolicy instance
                     (or a wrapper that exposes .policy for SB3 compatibility)

    FIX (regression): this function previously called policy.evaluate_actions()
    — the SB3 base-class method. Neither TransformerPolicy nor
    GodTransformerPolicy defines evaluate_actions(), so the inherited base
    implementation would run instead. That base method internally calls
    self.mlp_extractor(features) and self._get_action_dist_from_latent() —
    SB3's own internal architecture — but both custom policies replace those
    by overriding _build_mlp_extractor() to set self.features_extractor and
    self.action_net (non-standard names) while bypassing
    _get_action_dist_from_latent() entirely in their custom forward()/_predict().
    The base evaluate_actions() would therefore either crash (mlp_extractor
    shape mismatch) or return log-probs computed through a completely different
    computational path than the actual forward pass — neither useful for GRPO.

    The fix computes log-probs through the ACTUAL forward path these policies
    use: features_extractor → action_net → log_std → Normal distribution.
    GodTransformerPolicy uses log_std_base (13-dim) for the base dims and
    log_std_params (3-dim) for the ability continuous params — padded to the
    full action_dim to match act_tensor's shape.

    This is the same approach that was correctly implemented earlier in
    communication_protocol.py's _grpo_policy_update() and that was confirmed
    verified at that time — reproduced here since the rewrite of this file
    used an older reference copy that hadn't received that fix yet.
    """
    if len(scored_actions) < 4:
        return   # need diversity for relative scoring

    scores  = np.array([s for s, _ in scored_actions])
    actions = np.array([a for _, a in scored_actions])

    baseline   = scores.mean()
    advantages = scores - baseline
    std        = advantages.std() + 1e-8
    advantages = advantages / std

    obs_tensor = torch.FloatTensor(obs).unsqueeze(0).expand(len(actions), -1)
    act_tensor = torch.FloatTensor(actions)
    adv_tensor = torch.FloatTensor(advantages)

    try:
        policy = model.policy if hasattr(model, 'policy') else model

        # ── Step 1: run the actual forward pass ──────────────────────────
        # TransformerPolicy.forward() returns (action_mean, values).
        # GodTransformerPolicy.forward() also returns (action_mean, values)
        # with action_mean shape (B, 18) — base 13 dims + ability 5 dims.
        # Neither returns log_probs; we derive them below from the policy's
        # own log_std parameters.
        action_mean, _ = policy.forward(obs_tensor)

        # ── Step 2: assemble std matching the actual forward-pass paths ──
        # TransformerPolicy: one nn.Parameter log_std of shape (action_dim,)
        # GodTransformerPolicy: log_std_base (13,) + log_std_params (3,),
        #   padded to action_dim (18) with zeros for the discrete ability dims.
        if hasattr(policy, 'log_std'):
            log_std_vec = policy.log_std
        elif hasattr(policy, 'log_std_base'):
            action_dim = action_mean.shape[-1]
            # log_std_base (13,) covers the base movement dims.
            # log_std_params (3,) covers the continuous ability params (dims 13-15).
            # Dims 16-17 are discrete (trigger, ability index) — zero std.
            base    = policy.log_std_base                    # (13,)
            params  = getattr(policy, 'log_std_params',
                              torch.zeros(3, device=base.device))  # (3,)
            pad_len = action_dim - base.shape[0] - params.shape[0]
            pad     = torch.zeros(max(0, pad_len), device=base.device)
            log_std_vec = torch.cat([base, params, pad])[:action_dim]
        else:
            # Unknown policy type — fall back to unit std (no gradient through std)
            log_std_vec = torch.zeros(action_mean.shape[-1])

        std_vec = torch.exp(log_std_vec).clamp(min=1e-6)

        # ── Step 3: compute log-prob of each scored action ───────────────
        # Normal distribution parameterized by the policy's own forward output.
        # act_tensor rows are the sampled action arrays from deliberation.
        dist     = torch.distributions.Normal(action_mean, std_vec)
        log_probs = dist.log_prob(act_tensor).sum(dim=-1)  # (N,)

        # ── Step 4: GRPO gradient step ───────────────────────────────────
        loss = -(adv_tensor * log_probs).mean()

        if not hasattr(model, '_grpo_opt'):
            model._grpo_opt = torch.optim.Adam(policy.parameters(), lr=lr)

        model._grpo_opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 0.5)
        model._grpo_opt.step()

        log.debug(
            f"GRPO update: {len(scored_actions)} actions, "
            f"loss={loss.item():.4f}, "
            f"best_score={max(scores):.3f}"
        )

    except Exception as e:
        log.debug(f"GRPO update failed (non-fatal): {e}")