# py_backend/ai_core/policy_bridge.py
"""
Phase 2 — PolicyBridge
=======================
Connects TransformerPolicy (SB3/PPO) and ContinualLearner (Avalanche)
through a shared encoder.

Architecture:
    TransformerPolicy
      └── encoder (Transformer blocks)  ← shared, canonical representation
           ├── actor_head               ← normal decisions (fast path)
           └── [PolicyBridge]
                  └── cl_head (small MLP)  ← learning-task decisions only
                        ↑ trained by Avalanche on task-specific experience

Normal operation  : TransformerPolicy actor_head drives decisions.
Learning mode     : cl_head drives decisions when agent is practising a
                    specific task (curiosity > 0.65 and task active).

One-way soft sync : Every SYNC_EVERY forward calls, encoder weights are
                    soft-copied into cl_head input layer so the cl_head
                    stays aligned with the improving encoder without
                    overwriting task-specific learning.
"""

import torch
import torch.nn as nn
import logging
import numpy as np
from typing import Optional

log = logging.getLogger("policy_bridge")


class PolicyBridge(nn.Module):
    """
    Shared-encoder bridge between SB3 TransformerPolicy and Avalanche CL.

    Instantiate in agent.py AFTER both policy and continual_learner exist:

        self.policy_bridge = PolicyBridge(
            transformer_policy = self.policy,
            cl_policy_net      = self.continual_learner.policy_net,
            obs_dim            = self.obs_dim,
            action_dim         = self.action_dim,
        )
    """

    SYNC_EVERY = 200   # soft-sync encoder → cl_head every N forward calls

    def __init__(
        self,
        transformer_policy,
        cl_policy_net,
        obs_dim: int,
        action_dim: int,
    ):
        super().__init__()

        self.transformer_policy = transformer_policy
        self.cl_policy_net      = cl_policy_net
        self.obs_dim            = obs_dim

        # FIX Step 5: probe for the real encoder once at init time and keep
        # a direct reference to it, instead of re-deriving (and re-failing on)
        # a hardcoded SB3 MlpExtractor path on every single _encode() call.
        self._encoder, encoder_out_dim = self._find_encoder(transformer_policy, obs_dim)

        # CL head: TransformerPolicy latent embedding → action
        self.cl_head = nn.Sequential(
            nn.Linear(encoder_out_dim, 128), nn.ELU(),
            nn.Linear(128, action_dim),
        )

        self._call_count    = 0
        self._learning_mode = False
        self._active_task:  Optional[str] = None

        log.info(
            f"PolicyBridge ready — encoder={'found' if self._encoder is not None else 'NOT FOUND (passthrough)'} "
            f"encoder_out={encoder_out_dim} action_dim={action_dim}"
        )

    # ──────────────────────────────────────────────────────────────────────
    # Encoder helpers
    # ──────────────────────────────────────────────────────────────────────

    def _find_encoder(self, policy, obs_dim: int):
        """
        FIX Step 5: the original hardcoded
        `transformer_policy.policy.mlp_extractor.policy_net` — that path
        assumes (a) transformer_policy is a full SB3 model wrapper with a
        `.policy` sub-attribute (it's actually the policy object itself —
        agent.policy IS a TransformerPolicy/GodTransformerPolicy instance)
        and (b) SB3's default MlpExtractor, which TransformerPolicy never
        builds (_build_mlp_extractor() is overridden to set
        `self.features_extractor` = TransformerEncoder instead). Both
        assumptions are wrong, so every call silently fell through to the
        128-dim fallback and _encode() silently passed raw, unencoded obs
        into cl_head — meaning Phase 2 was training the CL head on a
        completely different representation than the policy actually uses.

        Probe known paths in order, verifying each one actually produces
        output before trusting it (just having the attribute isn't enough —
        it must be callable on a real obs tensor of the right shape).
        """
        candidates = [
            lambda p: p.features_extractor,                 # TransformerPolicy / GodTransformerPolicy (real path)
            lambda p: p.policy.features_extractor,           # full SB3 model wrapper, if ever passed instead
            lambda p: p.policy.mlp_extractor.policy_net,      # genuine SB3 default policy, if ever swapped in
            lambda p: p.mlp_extractor.policy_net,             # same, unwrapped
        ]
        for fn in candidates:
            try:
                enc = fn(policy)
                dummy = torch.zeros(1, obs_dim)
                with torch.no_grad():
                    out = enc(dummy)
                return enc, out.shape[-1]
            except Exception:
                continue

        log.warning(
            "PolicyBridge: no usable encoder found on the policy object — "
            "cl_head will train on raw (unencoded) observations as a "
            "last-resort passthrough. This is degraded, not broken: the cl_head "
            "still learns, just from a less structured input than intended."
        )
        return None, 128   # passthrough fallback — _encode() returns obs unchanged

    def _encode(self, obs_tensor: torch.Tensor) -> torch.Tensor:
        """Extract shared embedding from the policy's real encoder (no grad)."""
        if self._encoder is None:
            return obs_tensor
        try:
            with torch.no_grad():
                return self._encoder(obs_tensor)
        except Exception as e:
            log.debug(f"Encoder forward failed, using passthrough: {e}")
            return obs_tensor

    # ──────────────────────────────────────────────────────────────────────
    # Main prediction interface
    # ──────────────────────────────────────────────────────────────────────

    def predict_action(
        self,
        obs: np.ndarray,
        task_label: Optional[str] = None,
        deterministic: bool = False,
    ) -> np.ndarray:
        """
        Route to the correct head based on current mode.

          learning_mode=True AND task_label == active_task
              → cl_head  (agent is practising this skill)
          otherwise
              → TransformerPolicy actor head (normal operation)
        """
        self._call_count += 1
        if self._call_count % self.SYNC_EVERY == 0:
            self._soft_sync_cl_head()

        obs_tensor = torch.FloatTensor(obs).unsqueeze(0)

        use_cl = (
            self._learning_mode
            and task_label is not None
            and task_label == self._active_task
        )

        if use_cl:
            embedding = self._encode(obs_tensor)
            with torch.no_grad():
                action = self.cl_head(embedding).squeeze(0).numpy()
        else:
            action, _ = self.transformer_policy.predict(obs, deterministic=deterministic)

        return action

    # ──────────────────────────────────────────────────────────────────────
    # Learning mode control (called by CognitiveLoop)
    # ──────────────────────────────────────────────────────────────────────

    def set_learning_mode(self, active: bool, task_label: Optional[str] = None):
        """
        Switch bridge into/out of CL-head learning mode.

        Only called by CognitiveLoop when curiosity > 0.65 AND
        there is an active imitation task — never forced externally.
        """
        self._learning_mode = active
        self._active_task   = task_label if active else None
        log.debug(f"PolicyBridge: learning_mode={active}, task={task_label}")

    def get_cl_head_params(self):
        """Return cl_head parameters for Avalanche training."""
        return list(self.cl_head.parameters())

    def is_in_learning_mode(self) -> bool:
        return self._learning_mode

    def get_active_task(self) -> Optional[str]:
        return self._active_task

    # ──────────────────────────────────────────────────────────────────────
    # Soft encoder sync
    # ──────────────────────────────────────────────────────────────────────

    def _soft_sync_cl_head(self, tau: float = 0.05):
        """
        Soft-copy a compatible weight matrix from the real encoder into
        cl_head's input layer. tau=0.05 → 5% update per sync. Keeps cl_head
        tracking encoder improvements without overwriting task-specific
        learning.

        FIX Step 5: the original indexed
        `transformer_policy.policy.mlp_extractor.policy_net[-1]` — wrong
        path (see _find_encoder docstring) AND wrong assumption: even with
        the real encoder, TransformerEncoder is not an nn.Sequential, so
        `[-1]` indexing isn't valid on it at all. The real encoder's last
        operation is a LayerNorm (a per-channel scale, not a projection
        matrix), so there's no single "last layer" to copy from in the
        original sense — instead, search the encoder's named modules for
        the last nn.Linear whose out_features matches cl_head's input size,
        which is the layer that actually shaped the representation cl_head
        consumes. If none is found, skip the sync for this round rather
        than guessing.
        """
        if self._encoder is None:
            return
        try:
            cl_layer = self.cl_head[0]
            if not hasattr(cl_layer, 'in_features'):
                return

            target_in = cl_layer.in_features
            match = None
            for module in self._encoder.modules():
                if isinstance(module, nn.Linear) and module.out_features == target_in:
                    match = module   # keep the LAST matching Linear found

            if match is None:
                return

            with torch.no_grad():
                cl_layer.weight.data.mul_(1 - tau).add_(
                    match.weight.data[:cl_layer.out_features, :] * tau
                )
        except Exception as e:
            log.debug(f"Soft sync skipped: {e}")