# ------------------------------------------------------------------------------
# ai_core/planner.py - Cognitive planning module
# ------------------------------------------------------------------------------
"""
Goal-oriented planning using learned value functions.
"""
import random
from typing import Any, Dict, List, Optional

from ai_core.brain_core import BrainCore

class CognitivePlanner:
    """
    Simple forward planner using value estimates.
    """
    def __init__(self, brain: BrainCore, 
                 action_templates: Optional[List[Dict]] = None):
        self.brain = brain
        self.templates = action_templates or [
            {'type': 'collect', 'target': 'wood'},
            {'type': 'collect', 'target': 'stone'},
            {'type': 'craft', 'item': 'plank'},
            {'type': 'craft', 'item': 'raft'},
            {'type': 'attack', 'target': 'nearest_enemy'},
            {'type': 'flee', 'direction': 'away'},
            {'type': 'use_item', 'item': 'pickaxe'}
        ]
    
    def generate_plan(self, obs: Dict[str, Any], memory, 
                     horizon: int = 3) -> List[Dict]:
        """
        Generate action sequence maximizing expected value.
        """
        scored = []
        for t in self.templates:
            est_value = self.brain.predict_value_of_action(t)
            
            # Novelty bonus
            key_type = t.get('type')
            count = 0
            try:
                for e in memory.events:
                    if isinstance(e, dict) and e.get('type') == key_type:
                        count += 1
            except Exception:
                pass
            
            novelty_bonus = 1.0 / (1.0 + count)
            score = est_value + 0.2 * novelty_bonus
            scored.append((score, t))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [t for _, t in scored[:5]]
        
        # Generate sequence
        best_seq = []
        best_score = -1e9
        trials = 20
        
        for _ in range(trials):
            seq = [random.choice(top) for _ in range(horizon)]
            seq_val = sum(self.brain.predict_value_of_action(s) for s in seq)
            
            # Penalize repetition
            unique = len(set(str(s) for s in seq))
            seq_val -= 0.05 * (len(seq) - unique)
            
            if seq_val > best_score:
                best_score = seq_val
                best_seq = seq
        
        return best_seq