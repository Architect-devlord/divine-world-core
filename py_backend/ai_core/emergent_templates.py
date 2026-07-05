# ai_core/emergent_templates.py
"""
Emergent skill/template discovery — the action-space analogue of
vision.py's OnlineVisualVocabulary.

Philosophy (deliberately mirrors OnlineVisualVocabulary's docstring):

    No hand-authored action menu. The agent's own executed behaviour —
    the raw, continuous vectors that actually came out of the policy via
    agent.decide() — is clustered online. A cluster only "graduates" into
    something deliberate() and generate_plan() are allowed to imagine and
    score once it has been (a) repeated enough to be a real pattern and
    not noise, and (b) has paid off relative to the agent's own recent
    experience — not against a fixed, hand-picked number.

    Naming is a separate, later, optional step — exactly like
    OnlineVisualVocabulary.assign_name — so a skill can be tried, scored,
    and reinforced long before anything (a human, or the language system)
    calls it "collecting wood".

This module does NOT replace DEFAULT_TEMPLATES and does not decide the
seed/discovered blend — it only owns discovery and graduation. Graduated
skills are handed to CognitivePlanner.add_template(), the same extension
point god_controls.py already uses for god abilities, so both paths
merge into the one candidate list BrainCore.deliberate() actually scores.
"""
import logging
import threading
from typing import Any, Dict, List

import numpy as np

log = logging.getLogger("emergent_templates")


class EmergentSkillPool:
    """
    Incrementally clusters *executed* action vectors, weighted by the
    reward they actually earned, and promotes recurring, above-average
    clusters into candidate action templates.

    Usage (see ContinualLearner.learn_from_buffer):

        pool.observe(action_vec, reward)            # one call per experience
        ...
        new = pool.drain_newly_graduated()           # once per batch
        for tmpl in new:
            agent.planner.add_template(tmpl)          # reuse the existing hook
    """

    def __init__(self,
                 action_dim: int,
                 max_skills: int = 64,
                 lr: float = 0.08,
                 min_obs_to_graduate: int = 40,
                 min_obs_to_split: int = 15,
                 reward_margin: float = 0.02):
        self.action_dim          = action_dim
        self.max_skills          = max_skills
        self.lr                  = lr
        self.min_obs_to_graduate = min_obs_to_graduate
        self.min_obs_to_split    = min_obs_to_split
        self.reward_margin       = reward_margin

        # Cluster centres: (n_skills, action_dim) — real points in action
        # space, NOT restricted to one-hot basis vectors.
        self._centres:    np.ndarray = np.zeros((0, action_dim), dtype=np.float32)
        self._counts:     np.ndarray = np.zeros(0, dtype=np.int64)
        self._reward_sum: np.ndarray = np.zeros(0, dtype=np.float64)
        self._graduated:  List[bool] = []
        self._names:      Dict[int, str] = {}

        # Running mean reward across ALL experience — graduation is
        # relative to this, so the bar rises/falls with the agent's own
        # lifetime, instead of being a magic absolute constant.
        self._running_reward_mean = 0.0
        self._running_reward_n    = 0

        self._pending_graduates: List[int] = []
        self._total_obs = 0
        self._lock = threading.Lock()

    # ── public ──────────────────────────────────────────────────────────

    @property
    def n_skills(self) -> int:
        return len(self._centres)

    def observe(self, action: np.ndarray, reward: float) -> int:
        """
        Fold one executed (action, reward) pair into the pool.
        Returns the skill token this action was assigned to.
        """
        with self._lock:
            self._total_obs += 1
            self._running_reward_n += 1
            self._running_reward_mean += (
                (reward - self._running_reward_mean) / self._running_reward_n
            )

            action = np.asarray(action, dtype=np.float32).reshape(-1)[: self.action_dim]
            if action.shape[0] < self.action_dim:
                action = np.pad(action, (0, self.action_dim - action.shape[0]))

            if self.n_skills == 0:
                self._new_cluster(action, reward)
                return 0

            dists    = np.linalg.norm(self._centres - action, axis=1)
            nearest  = int(np.argmin(dists))
            min_dist = float(dists[nearest])

            # Online k-means update — identical rule to OnlineVisualVocabulary
            self._centres[nearest]    += self.lr * (action - self._centres[nearest])
            self._counts[nearest]     += 1
            self._reward_sum[nearest] += reward

            # Consider growing the pool (same trigger shape as the visual
            # vocabulary: over-observed AND meaningfully far from its centre)
            if (self.n_skills < self.max_skills and
                    self._counts[nearest] >= self.min_obs_to_split and
                    min_dist > self._mean_intra_dist() * 1.5):
                self._new_cluster(action, reward)
                nearest = self.n_skills - 1

            self._maybe_graduate(nearest)
            return nearest

    def drain_newly_graduated(self) -> List[Dict[str, Any]]:
        """
        Return template dicts for skills that graduated since the last
        call, then clear the pending list. Call once per learning batch.
        """
        with self._lock:
            tokens, self._pending_graduates = self._pending_graduates, []
        return [self._as_template(t) for t in tokens]

    def graduated_templates(self) -> List[Dict[str, Any]]:
        """All currently-graduated templates (not just newly graduated)."""
        return [self._as_template(t) for t, g in enumerate(self._graduated) if g]

    def name_of(self, token: int) -> str:
        return self._names.get(token, f"skill_{token}")

    def assign_name(self, token: int, name: str):
        """Optional, later labelling — e.g. once SkillTracker or the
        language system notices this skill correlates with a named
        outcome. Never required for the skill to be tried or scored."""
        self._names[token] = name
        log.info(f"Skill pool: token {token} named '{name}'")

    def get_stats(self) -> Dict[str, Any]:
        return {
            'n_skills':       self.n_skills,
            'n_graduated':    int(sum(self._graduated)),
            'total_obs':      self._total_obs,
            'running_reward': self._running_reward_mean,
            'named':          dict(self._names),
        }

    # ── persistence (mirrors OnlineVisualVocabulary) ───────────────────

    def state_dict(self) -> Dict:
        return {
            'centres':             self._centres.tolist(),
            'counts':              self._counts.tolist(),
            'reward_sum':          self._reward_sum.tolist(),
            'graduated':           self._graduated,
            'names':               self._names,
            'total_obs':           self._total_obs,
            'running_reward_mean': self._running_reward_mean,
            'running_reward_n':    self._running_reward_n,
        }

    def load_state_dict(self, state: Dict):
        with self._lock:
            self._centres    = np.array(state['centres'], dtype=np.float32)
            self._counts     = np.array(state['counts'], dtype=np.int64)
            self._reward_sum = np.array(state['reward_sum'], dtype=np.float64)
            self._graduated  = list(state['graduated'])
            self._names      = {int(k): v for k, v in state.get('names', {}).items()}
            self._total_obs  = state.get('total_obs', 0)
            self._running_reward_mean = state.get('running_reward_mean', 0.0)
            self._running_reward_n    = state.get('running_reward_n', 0)

    # ── private ─────────────────────────────────────────────────────────

    def _mean_reward(self, token: int) -> float:
        c = self._counts[token]
        return float(self._reward_sum[token] / c) if c > 0 else 0.0

    def _mean_intra_dist(self) -> float:
        if self.n_skills < 2:
            return 1.0
        idx    = np.random.choice(self.n_skills, size=min(self.n_skills, 20), replace=False)
        sample = self._centres[idx]
        diffs  = sample[:, np.newaxis] - sample[np.newaxis, :]
        dists  = np.linalg.norm(diffs, axis=-1)
        return float(dists[dists > 0].mean()) if (dists > 0).any() else 1.0

    def _new_cluster(self, action: np.ndarray, reward: float):
        self._centres    = np.vstack([self._centres, action[np.newaxis]])
        self._counts     = np.append(self._counts, 1)
        self._reward_sum = np.append(self._reward_sum, reward)
        self._graduated.append(False)
        log.debug(f"EmergentSkillPool: new cluster {self.n_skills - 1} (total={self.n_skills})")

    def _maybe_graduate(self, token: int):
        if self._graduated[token]:
            return
        if self._counts[token] < self.min_obs_to_graduate:
            return
        if self._mean_reward(token) <= self._running_reward_mean + self.reward_margin:
            return
        self._graduated[token] = True
        self._pending_graduates.append(token)
        log.info(
            f"EmergentSkillPool: {self.name_of(token)} graduated "
            f"(n={self._counts[token]}, mean_reward={self._mean_reward(token):.3f} "
            f"vs running_avg={self._running_reward_mean:.3f})"
        )

    def _as_template(self, token: int) -> Dict[str, Any]:
        return {
            'type':          self.name_of(token),
            'action_vector': self._centres[token].tolist(),
            'discovered':    True,
            'skill_token':   token,
        }
