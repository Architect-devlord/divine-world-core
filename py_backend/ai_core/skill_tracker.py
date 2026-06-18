# py_backend/ai_core/skill_tracker.py
"""
Phase 5 — Avalanche Skill Tracker
===================================
Tracks per-task learning progress using Avalanche's replay buffer
and MSE loss against an imagined target distribution.

Paste the SkillTracker class into continual_learner.py OR import it from here.
See PATCHES.md for wiring into CognitiveLoop.

The learning cycle:
  1. Agent decides to focus on a task — either via sustained curiosity+
     surprise (CognitiveLoop's N=5 streak, Step 8) resolving to the weakest
     tracked skill, or via a specialisation signal from GRPO reward history
     (Step 9). No external/imitation trigger — see PATCHES.md for why
     ObservationImitator was removed entirely.
  2. WorldModel deliberation produces an imagined "target" action
  3. Each real attempt is compared to the target via MSE
  4. Score feeds back to emotion system:
       improving → joy ↑, curiosity ↑
       stagnant  → frustration ↑
       frustrated + low persistence → give up (clear active_focus_task)
"""

import logging
import torch
import torch.nn as nn
from typing import Dict, Any, Optional, List

log = logging.getLogger("skill_tracker")


class SkillTracker:
    """
    Per-task learning progress tracker.

    Usage in CognitiveLoop (see PATCHES.md):

        result = self.agent.skill_tracker.record_attempt(
            task_label      = active_task,
            obs_vector      = current_obs,
            action_taken    = action_taken,
            imagined_target = deliberation.best_action_vector,
        )

        if result['improving']:
            self.agent.emotion.add('joy',       0.15)
            self.agent.emotion.add('curiosity', 0.10)
        else:
            self.agent.emotion.add('frustration', 0.10)
            persistence = self.agent.personality.traits.get('persistence', 0.5)
            if (self.agent.emotion.snapshot().get('frustration', 0)
                    > 0.7 * persistence):
                self.agent.active_focus_task = None
                self.agent.policy_bridge.set_learning_mode(False)
    """

    def __init__(self, continual_learner):
        self.cl         = continual_learner
        self.task_stats: Dict[str, Dict] = {}

    def record_attempt(
        self,
        task_label:       str,
        obs_vector:       Any,
        action_taken:     Any,
        imagined_target:  Any,
    ) -> Dict[str, Any]:
        """
        Record one real attempt at a task against an imagined target.
        Returns progress metrics including loss, score (0–1), and improving flag.
        """
        obs_t = torch.FloatTensor(obs_vector).unsqueeze(0)
        act_t = torch.FloatTensor(action_taken).unsqueeze(0)
        tgt_t = torch.FloatTensor(imagined_target).unsqueeze(0)

        # FIX: removed dead code that computed `_embedding` from the CL
        # policy net's first layer and never used it for anything — pure
        # wasted forward pass on every single attempt. obs_t isn't even
        # needed for the loss itself (kept as a parameter for API symmetry
        # and so a future, real embedding-based score can be added later).
        with torch.no_grad():
            loss = nn.MSELoss()(act_t, tgt_t).item()

        stats = self.task_stats.setdefault(
            task_label, {'losses': [], 'attempts': 0}
        )
        stats['losses'].append(loss)
        stats['attempts'] += 1

        # Keep rolling window of 50 losses
        if len(stats['losses']) > 50:
            stats['losses'].pop(0)

        losses    = stats['losses']
        avg_loss  = sum(losses) / len(losses)
        improving = len(losses) > 1 and losses[-1] < losses[-2]

        result = {
            'task':      task_label,
            'loss':      loss,
            'avg_loss':  avg_loss,
            'attempts':  stats['attempts'],
            'improving': improving,
            # Score 0–1 where 1 = perfect (MSE ≈ 0)
            'score':     max(0.0, 1.0 - min(1.0, avg_loss)),
        }

        log.debug(
            f"Skill '{task_label}': loss={loss:.4f} avg={avg_loss:.4f} "
            f"{'↑' if improving else '↓'} attempts={stats['attempts']}"
        )
        return result

    def get_all_scores(self) -> Dict[str, float]:
        """Return score (0–1) for every tracked task."""
        return {
            task: max(0.0, 1.0 - min(1.0,
                        sum(s['losses']) / len(s['losses'])))
            for task, s in self.task_stats.items()
            if s['losses']
        }

    def get_best_task(self) -> Optional[str]:
        """Return task with highest current score."""
        scores = self.get_all_scores()
        return max(scores, key=scores.get) if scores else None

    def get_weakest_task(self) -> Optional[str]:
        """Return task with lowest score — good candidate for focused practice."""
        scores = self.get_all_scores()
        return min(scores, key=scores.get) if scores else None

    def summary(self) -> List[Dict]:
        return [
            {
                'task':     task,
                'score':    max(0.0, 1.0 - min(1.0, sum(s['losses'])/len(s['losses']))),
                'attempts': s['attempts'],
                'trend':    ('↑' if len(s['losses']) > 1 and s['losses'][-1] < s['losses'][-2]
                             else '↓'),
            }
            for task, s in sorted(
                self.task_stats.items(),
                key=lambda x: -x[1]['attempts'],
            )
            if s['losses']
        ]