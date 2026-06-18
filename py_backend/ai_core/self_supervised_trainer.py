# py_backend/ai_core/self_supervised_trainer.py
"""
Phase 3 — Self-Supervised Trainer + GRPO
==========================================
Replaces offline PPO (rl/train.py) with two online mechanisms:

1. SelfSupervisedTrainer
   Trains the WorldModel from the agent's own transitions every learning
   cycle. Prediction error IS the learning signal. High surprise in safe
   context → curiosity spike. High surprise in danger → fear spike.

2. grpo_update() — monkeypatched onto the live policy instance by
   agent_runner.py (`agent.policy.grpo_update = types.MethodType(...)`),
   NOT added as a method on the TransformerPolicy/GodTransformerPolicy
   classes themselves. This keeps those classes completely untouched while
   still giving the policy object a working grpo_update(scored_actions, obs).

Called from CognitiveLoop._continual_learning_worker() (see Step 7 wiring).

──────────────────────────────────────────────────────────────────────────
FIX Step 4 — API mismatch corrected
──────────────────────────────────────────────────────────────────────────
The original train_step() called `self.wm.predict(obs_t, act_t)`, which does
not exist on WorldModel — silently caught by a blanket except, so the SST
ran every cycle and trained nothing.

The plan's suggested replacement (`wm.imagine(...)`) was investigated and
found to be the WRONG fix too: imagine() wraps its own forward() call in
`torch.no_grad()` (it's built for deliberation rollouts, not training), so
backpropagating through it is not possible — loss.backward() would raise
"element 0 of tensors does not require grad", or silently produce zero
gradients depending on the call shape. Using it here would have replaced
one silent no-op with another.

The actual fix: WorldModel already has a gradient-enabled
`train_step(batch) -> Dict[str, float]` method (used by WorldModelTrainer)
that does its own forward → compute_loss → zero_grad → backward → clip →
optimizer.step() internally, with its own `self.optimizer` (AdamW). That is
the correct, already-implemented entry point — SST below builds a `batch`
dict and calls it directly. SST no longer owns its own optimizer, since one
already exists inside WorldModel and creating a second one stepping the
same parameters would double-count Adam's momentum state.

`batch['proprio']` must be `(B, 1, config.proprio_dim)` — WorldModel's
proprioception space (32-dim by default) is smaller than and DIFFERENT
from the agent's policy observation (128-dim, obs_builder.py). The first
`proprio_dim` elements of the 128-dim observation are used as a deliberate,
documented "physical-state prefix": vitals + position/orientation +
environment are exactly the proprioceptive quantities WorldModel's
ProprioceptionEncoder expects, so slicing the front of the vector is a
principled mapping, not an arbitrary truncation.

`next_state` is intentionally NOT passed as a training target: the buffer's
next_obs is currently always identical to obs (a pre-existing, separate
data-collection bug in continual_learner.collect_experiences(), out of
scope for this fix) — training against it would just teach the model to
predict its own input. Omitting the key makes compute_loss() skip that term
cleanly (it's already designed to do so) rather than training on bad data.
"""

import logging
import random
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

log = logging.getLogger("self_supervised_trainer")


class SelfSupervisedTrainer:
    """
    Trains the WorldModel online from the agent's own experience buffer.

    Every call to train_step():
      1. Samples a random batch of (obs, action, reward, done) transitions
         from the ContinualLearner's experience_buffer (List[Tuple]).
      2. Slices each obs down to WorldModel's proprio_dim and calls the
         model's own train_step(batch) — gradient-enabled, single call.
      3. Feeds the reward-prediction error back to the emotion system as a
         surprise signal:
           safe context  (health > 8)  → curiosity ↑, joy ↑
           danger context (health ≤ 8) → fear ↑, curiosity ↓

    `world_model` is accepted at construction for convenience but is NOT
    cached — agent.brain.world_model is frequently still None at spawn time
    (the brain capsule loads asynchronously after Phase 2–5 attachment).
    The real WorldModel is resolved fresh from `self.brain` on every call to
    train_step(), so SST works correctly however late the capsule loads.
    """

    MIN_BUFFER_SIZE = 16
    BATCH_SIZE      = 32

    def __init__(self, world_model, brain, emotion_system, device: str = 'cpu'):
        self.brain    = brain
        self._wm_hint = world_model   # construction-time value, may be None
        self.emotion  = emotion_system
        self.device   = device
        self._step    = 0
        self._loss_history: List[float] = []

    # ──────────────────────────────────────────────────────────────────────
    # Lazy WorldModel resolution (FIX Step 4 / Bug-5 from the earlier report)
    # ──────────────────────────────────────────────────────────────────────

    def _get_wm(self):
        wm = getattr(self.brain, 'world_model', None) if self.brain is not None else None
        return wm if wm is not None else self._wm_hint

    # ──────────────────────────────────────────────────────────────────────
    # Main training step
    # ──────────────────────────────────────────────────────────────────────

    def train_step(
        self,
        experience_buffer: List[Tuple],
    ) -> Optional[Dict[str, Any]]:
        """
        Pull recent transitions from the ContinualLearner's tuple buffer
        `(obs, action, reward, next_obs, done, task_id)` and run one
        gradient-enabled WorldModel training step.

        Returns a metrics dict (including 'mean_surprise' for the N=5
        learning-mode counter in CognitiveLoop) or None if skipped.
        """
        wm = self._get_wm()
        if wm is None:
            log.debug("SST.train_step: world model not loaded yet — skipping")
            return None

        if len(experience_buffer) < self.MIN_BUFFER_SIZE:
            return None

        try:
            return self._train_step_impl(wm, experience_buffer)
        except Exception as e:
            log.error(f"Self-supervised training error: {e}", exc_info=True)
            return None

    def _train_step_impl(self, wm, buf: List[Tuple]) -> Optional[Dict[str, Any]]:
        proprio_dim = wm.config.proprio_dim
        action_dim  = wm.config.action_dim

        batch_entries = random.sample(buf, min(self.BATCH_SIZE, len(buf)))

        proprio_list, action_list, reward_list, done_list = [], [], [], []
        for entry in batch_entries:
            if len(entry) < 5:
                continue
            obs, action, reward, _next_obs, done = entry[0], entry[1], entry[2], entry[3], entry[4]
            if obs is None or action is None:
                continue

            obs_t    = obs    if isinstance(obs,    torch.Tensor) else torch.as_tensor(np.asarray(obs),    dtype=torch.float32)
            action_t = action if isinstance(action, torch.Tensor) else torch.as_tensor(np.asarray(action), dtype=torch.float32)

            proprio_list.append(_fit_dim(obs_t, proprio_dim))
            action_list.append(_fit_dim(action_t, action_dim))
            reward_list.append(float(reward) if reward is not None else 0.0)
            done_list.append(1.0 if done else 0.0)

        if len(proprio_list) < 4:
            return None

        device = getattr(wm, 'device', self.device)

        proprio_t = torch.stack(proprio_list).unsqueeze(1).to(device)   # (B,1,proprio_dim)
        action_t  = torch.stack(action_list).unsqueeze(1).to(device)    # (B,1,action_dim)
        reward_t  = torch.tensor(reward_list, dtype=torch.float32,
                                 device=device).view(-1, 1, 1)           # (B,1,1)
        done_t    = torch.tensor(done_list, dtype=torch.float32,
                                 device=device).view(-1, 1, 1)           # (B,1,1)

        batch = {
            'proprio':     proprio_t,
            'action':      action_t,
            'reward':      reward_t,
            'termination': done_t,
            # 'next_state' deliberately omitted — see module docstring.
        }

        # FIX Step 4: the real, gradient-enabled training entry point.
        # WorldModel.train_step() does forward → compute_loss → zero_grad →
        # backward → clip_grad_norm_ → optimizer.step() internally, using its
        # own self.optimizer — SST does not need (and must not create) a
        # second optimizer over the same parameters.
        loss_dict = wm.train_step(batch)
        self._step += 1

        # Reward-prediction error doubles as the "surprise" signal: it's the
        # one well-typed, dimensionally-unambiguous scalar this model exposes
        # regardless of use_vae / latent_dim / d_model configuration — unlike
        # the raw 'states' output of imagine(), which lives in a different
        # space depending on those settings.
        mean_surprise = float(loss_dict.get('reward', 0.0))

        self._loss_history.append(mean_surprise)
        if len(self._loss_history) > 100:
            self._loss_history.pop(0)

        # ── Feed surprise back to the emotion system ───────────────────────
        agent_ref = getattr(self.brain, 'agent', None)
        health    = float(getattr(agent_ref, 'health', 20.0)) if agent_ref is not None else 20.0
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
            'prediction_loss': float(loss_dict.get('total', mean_surprise)),
            'mean_surprise':   mean_surprise,
            'in_danger':       in_danger,
            'avg_loss_100':    (sum(self._loss_history) / len(self._loss_history)
                                if self._loss_history else 0.0),
            'wm_loss_dict':    loss_dict,
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            'step':         self._step,
            'avg_loss_100': (sum(self._loss_history) / len(self._loss_history)
                             if self._loss_history else 0.0),
        }


def _fit_dim(t: torch.Tensor, target_dim: int) -> torch.Tensor:
    """Flatten, then truncate or zero-pad a 1-D tensor to exactly target_dim."""
    t = t.flatten().float()
    n = t.shape[0]
    if n == target_dim:
        return t
    if n > target_dim:
        return t[:target_dim]
    return F.pad(t, (0, target_dim - n))


# ──────────────────────────────────────────────────────────────────────────────
# GRPO update — standalone function, monkeypatched onto the live policy
# instance by agent_runner.py. Never added to the TransformerPolicy /
# GodTransformerPolicy class definitions themselves (those stay untouched
# per the plan's "don't touch" list).
# ──────────────────────────────────────────────────────────────────────────────

def grpo_update(
    model,
    scored_actions: List[Tuple[float, np.ndarray]],
    obs: np.ndarray,
    lr: float = 1e-4,
) -> Optional[Dict[str, float]]:
    """
    Group Relative Policy Optimisation update.

    No critic needed — uses relative scores from the same imagination
    rollout BrainCore.deliberate() already ran
    (DeliberationResult.all_scored_actions).

    FIX (discovered while wiring Step 7): the original implementation called
    `policy.evaluate_actions(obs_tensor, act_tensor)` — an SB3
    ActorCriticPolicy base-class method that assumes the standard
    mlp_extractor/action_dist plumbing. TransformerPolicy and
    GodTransformerPolicy both override _build_mlp_extractor()/forward()/
    _predict() directly and never populate that internal state, so
    evaluate_actions() does not produce a meaningful log-prob here — wrapped
    in the original's blanket try/except, it would have failed silently on
    every call, making GRPO a permanent no-op exactly like the class of bug
    this whole effort exists to fix.

    Fixed by computing the log-prob directly from the policy's own public
    attributes (features_extractor + action_net + log_std), which both
    policy classes already expose, instead of relying on SB3 machinery they
    don't use. Only the shared BASE_DIM movement dims are scored — that's
    also all all_scored_actions' one-hot vectors populate (god ability
    dims 13-17 aren't part of the ACTION_TYPE_INDEX one-hot scheme), so
    scoring the rest would just be measuring untouched zeros.

    Returns a metrics dict with 'mean_advantage' so the caller can persist
    it as agent._last_grpo_mean_advantage for the specialisation-detection
    history in CognitiveLoop (Step 9) — or None if the update was skipped.
    """
    if len(scored_actions) < 4:
        return None   # need diversity for relative scoring

    try:
        policy = model.policy if hasattr(model, 'policy') else model

        encoder    = getattr(policy, 'features_extractor', None)
        action_net = getattr(policy, 'action_net', None)
        log_std    = getattr(policy, 'log_std', None)
        if log_std is None:
            log_std = getattr(policy, 'log_std_base', None)   # GodTransformerPolicy

        if encoder is None or action_net is None or log_std is None:
            log.debug("grpo_update: policy missing encoder/action_net/log_std — skipping")
            return None

        base_dim = log_std.shape[0]   # 13 for both NPC and God policies

        scores  = np.array([s for s, _ in scored_actions], dtype=np.float32)
        actions = np.array([a[:base_dim] if len(a) >= base_dim
                            else np.pad(a, (0, base_dim - len(a)))
                            for _, a in scored_actions], dtype=np.float32)

        baseline   = scores.mean()
        advantages = scores - baseline
        std        = advantages.std() + 1e-8
        advantages = advantages / std

        obs_tensor = torch.as_tensor(obs, dtype=torch.float32).unsqueeze(0)
        obs_batch  = obs_tensor.expand(len(actions), -1)
        act_tensor = torch.as_tensor(actions, dtype=torch.float32)
        adv_tensor = torch.as_tensor(advantages, dtype=torch.float32)

        features    = encoder(obs_batch)
        action_mean = torch.tanh(action_net(features))[:, :base_dim]
        std_t       = torch.exp(log_std)
        dist        = torch.distributions.Normal(action_mean, std_t)
        log_probs   = dist.log_prob(act_tensor).sum(dim=-1)

        # GRPO loss: push log-prob mass toward above-baseline actions.
        loss = -(adv_tensor * log_probs).mean()

        if not hasattr(model, '_grpo_opt'):
            params = list(encoder.parameters()) + list(action_net.parameters()) + [log_std]
            model._grpo_opt = torch.optim.Adam(params, lr=lr)

        model._grpo_opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(
            list(encoder.parameters()) + list(action_net.parameters()) + [log_std], 0.5
        )
        model._grpo_opt.step()

        mean_advantage = float(scores.mean())

        log.debug(
            f"GRPO update: {len(scored_actions)} actions, "
            f"loss={loss.item():.4f}, best_score={float(scores.max()):.3f}"
        )

        return {
            'loss':            float(loss.item()),
            'mean_advantage':  mean_advantage,
            'best_score':      float(scores.max()),
            'n_actions':       len(scored_actions),
        }

    except Exception as e:
        log.debug(f"GRPO update failed (non-fatal): {e}")
        return None