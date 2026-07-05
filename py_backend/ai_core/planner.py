# ai_core/planner.py - Cognitive planning module
"""
Goal-oriented planning using learned value functions + world model imagination.

The planner gives the agent complete autonomy over its thought space.
It can imagine any outcome including its own death, failure, or harm,
and uses those trajectories to make decisions.

Self-preservation, risk-aversion, or recklessness all emerge from what
the agent has LEARNED about consequences — nothing is hardcoded away.
The planner imagines faithfully. The agent chooses freely.
"""
import random
import numpy as np
import torch
from typing import Any, Callable, Dict, List, Optional
from ai_core.brain_core import BrainCore


DEFAULT_TEMPLATES: List[Dict] = [
    {'type': 'collect',  'target': 'wood'},
    {'type': 'collect',  'target': 'stone'},
    {'type': 'craft',    'item':   'plank'},
    {'type': 'craft',    'item':   'raft'},
    {'type': 'attack',   'target': 'nearest_enemy'},
    {'type': 'flee',     'direction': 'away'},
    {'type': 'use_item', 'item':   'pickaxe'},
    {'type': 'explore',  'direction': 'forward'},
    {'type': 'eat',      'item':   'bread'},
    {'type': 'build',    'block':  'dirt'},
]

ACTION_TYPE_INDEX: Dict[str, int] = {
    'collect': 0, 'craft': 1, 'attack': 2, 'flee': 3,
    'use_item': 4, 'explore': 5, 'eat': 6, 'sleep': 7,
    'build': 8, 'trade': 9, 'interact': 10,
}


# ============================================================================
# Imagination Result
# ============================================================================

class ImagineResult:
    """
    Full result of imagining a plan sequence through the world model.

    Contains everything the agent predicted — reward, risk, death probability,
    latent states at each step. Nothing is filtered or pre-penalised.
    The agent inspects this and decides what it values.
    """

    def __init__(self, sequence: List[Dict],
                 rewards: np.ndarray,
                 termination_probs: np.ndarray,
                 states: Optional[np.ndarray] = None):
        self.sequence          = sequence
        self.rewards           = rewards            # (horizon,) reward at each step
        self.termination_probs = termination_probs  # (horizon,) death prob at each step
        self.states            = states             # (horizon, latent_dim) imagined states

    @property
    def total_reward(self) -> float:
        """Discounted cumulative reward across the horizon."""
        gammas = np.array([0.95 ** t for t in range(len(self.rewards))])
        return float((self.rewards * gammas).sum())

    @property
    def peak_death_probability(self) -> float:
        """Highest single-step death probability in the sequence."""
        return float(self.termination_probs.max()) if len(self.termination_probs) else 0.0

    @property
    def expected_survival(self) -> float:
        """Probability of surviving the entire sequence."""
        return float(np.prod(1.0 - self.termination_probs))

    @property
    def dies_in_imagination(self) -> bool:
        """True if any step has >50% predicted death probability."""
        return bool((self.termination_probs > 0.5).any())

    def summary(self) -> Dict[str, Any]:
        return {
            'total_reward':        self.total_reward,
            'peak_death_prob':     self.peak_death_probability,
            'expected_survival':   self.expected_survival,
            'dies_in_imagination': self.dies_in_imagination,
            'step_rewards':        self.rewards.tolist(),
            'step_death_probs':    self.termination_probs.tolist(),
            'horizon':             len(self.rewards),
            'sequence':            [a.get('type') for a in self.sequence],
        }


# ============================================================================
# Planner
# ============================================================================

class CognitivePlanner:
    """
    Goal-oriented planner with complete imaginative autonomy.

    When a world model is attached, the agent imagines candidate sequences
    playing out step by step — including death. The planner reports everything
    it sees and scores plans however the agent has been configured to value things.

    scoring_fn: callable(ImagineResult) -> float
        Controls what the agent treats as 'good'. Examples:

        Pure reward (default — values what it learned to value):
            lambda r: r.total_reward

        Survival-weighted (cautious):
            lambda r: r.total_reward * r.expected_survival

        Reckless (ignores death entirely):
            lambda r: r.total_reward

        Balanced risk/reward:
            lambda r: r.total_reward * (0.5 + 0.5 * r.expected_survival)

        Death-curious (seeks dangerous situations to learn from them):
            lambda r: r.total_reward + r.peak_death_probability * 5

        Pure survival instinct:
            lambda r: r.expected_survival * 10

    The scoring_fn can be swapped at runtime — the agent's risk personality
    can evolve as it learns.
    """

    def __init__(self, brain: BrainCore,
                 action_templates: Optional[List[Dict]] = None,
                 scoring_fn: Optional[Callable] = None):
        self.brain      = brain
        self.templates  = action_templates or DEFAULT_TEMPLATES
        # Default: pure value — the agent values what experience taught it
        self.scoring_fn = scoring_fn or (lambda r: r.total_reward)

    # ------------------------------------------------------------------ #
    #  Main planning                                                       #
    # ------------------------------------------------------------------ #

    def generate_plan(self, obs: Dict[str, Any], memory,
                      horizon: int = 3,
                      n_trials: int = 20,
                      context: Optional[Dict[str, Any]] = None) -> List[Dict]:
        """
        Generate the best action sequence the agent can imagine.
        Uses world model rollouts when available, table fallback otherwise.
        """
        if self.brain.world_model is not None and context is not None:
            return self._plan_with_world_model(obs, memory, horizon, n_trials, context)
        return self._plan_with_table(obs, memory, horizon, n_trials, context)

    # ------------------------------------------------------------------ #
    #  Explicit imagination API                                            #
    # ------------------------------------------------------------------ #

    def imagine_sequence(self, sequence: List[Dict],
                         context: Dict[str, Any]) -> Optional[ImagineResult]:
        """
        Imagine a specific sequence and return the full result.
        The agent can inspect predicted rewards, death probabilities,
        and latent states at each step.

        Returns None if the world model is not available.
        """
        if self.brain.world_model is None or not context:
            return None
        return self._run_imagination(sequence, context)

    def imagine_death(self, context: Dict[str, Any],
                      n_samples: int = 10) -> List[ImagineResult]:
        """
        Sample random sequences and return them sorted by predicted death
        probability (highest first).

        This lets the agent deliberately think about what kills it —
        essential for building genuine survival intuition from experience
        rather than having avoidance baked in by the programmer.
        """
        if self.brain.world_model is None:
            return []

        results = []
        for _ in range(n_samples):
            seq    = [random.choice(self.templates) for _ in range(3)]
            result = self._run_imagination(seq, context)
            if result is not None:
                results.append(result)

        results.sort(key=lambda r: r.peak_death_probability, reverse=True)
        return results

    def imagine_many(self, n: int, horizon: int,
                     context: Dict[str, Any]) -> List[ImagineResult]:
        """
        Imagine n random sequences and return all results unsorted.
        Useful for the agent to survey the full space of possibilities
        including both great outcomes and catastrophic ones.
        """
        results = []
        for _ in range(n):
            seq    = [random.choice(self.templates) for _ in range(horizon)]
            result = self._run_imagination(seq, context)
            if result is not None:
                results.append(result)
        return results

    def set_scoring_fn(self, fn: Callable):
        """Swap the scoring function — changes the agent's risk personality."""
        self.scoring_fn = fn

    def add_template(self, action: Dict[str, Any]):
        """Register a new action template at runtime."""
        if action not in self.templates:
            self.templates.append(action)

    def get_best_single_action(self, context=None) -> Dict[str, Any]:
        """Return the highest-value single action right now."""
        return max(self._score_templates(context), key=lambda x: x[0])[1]

    # ------------------------------------------------------------------ #
    #  World-model imagination planner                                     #
    # ------------------------------------------------------------------ #

    def _plan_with_world_model(self, obs, memory, horizon,
                                n_trials, context) -> List[Dict]:
        template_scores = self._score_templates(context)
        top_templates   = [t for _, t in sorted(template_scores, reverse=True)[:5]]

        best_seq   = []
        best_score = -1e9

        for _ in range(n_trials):
            seq    = [random.choice(top_templates) for _ in range(horizon)]
            result = self._run_imagination(seq, context)

            if result is None:
                # Rollout failed — use table as fallback for this trial
                score = sum(self.brain.predict_value_of_action(a, context) for a in seq)
            else:
                # Agent scores this trajectory however it values things
                # No external penalties — death is just another data point
                score = self.scoring_fn(result)

            # Exploration: bonus for trying things not often done before
            score += self._novelty_bonus(seq, memory) * 0.2

            # Mild repetition penalty to encourage diverse plans
            unique = len({str(a) for a in seq})
            score -= 0.05 * (horizon - unique)

            if score > best_score:
                best_score = score
                best_seq   = seq

        return best_seq if best_seq else self.templates[:horizon]

    def _run_imagination(self, sequence: List[Dict],
                          context: Dict[str, Any]) -> Optional[ImagineResult]:
        """
        Roll a sequence through the world model.

        The rollout is completely unconstrained. Death outcomes, large negative
        rewards, high termination probabilities — all are preserved in the
        ImagineResult exactly as the world model predicted them.
        The agent sees everything.
        """
        wm         = self.brain.world_model
        device     = wm.device
        action_dim = wm.config.action_dim
        horizon    = len(sequence)

        try:
            from ai_core.world_model import _build_observation_from_context
            from ai_core.brain_core import _action_to_vector
            initial_obs = _build_observation_from_context(self.brain.agent, context)

            # FIX (template-ceiling): discovered skills carry their own
            # 'action_vector' (a real point in action space) rather than a
            # 'type' string in ACTION_TYPE_INDEX. _action_to_vector uses it
            # when present and falls back to the original one-hot encoding
            # for hand-authored templates, so this is a no-op for anything
            # that isn't a discovered skill.
            action_matrix = np.zeros((1, horizon, action_dim), dtype=np.float32)
            for t, action in enumerate(sequence):
                action_matrix[0, t, :] = _action_to_vector(action, action_dim)

            actions_tensor = torch.tensor(action_matrix, dtype=torch.float32, device=device)

            with torch.no_grad():
                imagined = wm.imagine(initial_obs, actions_tensor, steps=horizon)

            return ImagineResult(
                sequence=sequence,
                rewards=imagined['rewards'][0, :, 0].cpu().numpy(),
                termination_probs=imagined['terminations'][0, :, 0].cpu().numpy(),
                states=imagined['states'][0].cpu().numpy(),
            )

        except Exception as e:
            import logging
            logging.getLogger("planner").warning(f"Imagination rollout failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Table-based fallback                                                #
    # ------------------------------------------------------------------ #

    def _plan_with_table(self, obs, memory, horizon,
                          n_trials, context) -> List[Dict]:
        template_scores = self._score_templates(context)
        top_templates   = [t for _, t in sorted(template_scores, reverse=True)[:5]]

        best_seq   = []
        best_score = -1e9

        for _ in range(n_trials):
            seq   = [random.choice(top_templates) for _ in range(horizon)]
            score = sum(self.brain.predict_value_of_action(a, context) for a in seq)
            score += self._novelty_bonus(seq, memory) * 0.2
            unique = len({str(a) for a in seq})
            score -= 0.05 * (horizon - unique)
            if score > best_score:
                best_score = score
                best_seq   = seq

        return best_seq if best_seq else self.templates[:horizon]

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    def _score_templates(self, context):
        return [(self.brain.predict_value_of_action(t, context), t)
                for t in self.templates]

    def _novelty_bonus(self, seq: List[Dict], memory) -> float:
        total = 0.0
        for action in seq:
            count = 0
            try:
                for e in memory.events:
                    if isinstance(e, dict) and e.get('type') == action.get('type'):
                        count += 1
            except Exception:
                pass
            total += 1.0 / (1.0 + count)
        return total / max(1, len(seq))