# ai_core/brain_core.py - ENHANCED VERSION
"""
Enhanced Brain Core with:
- Integrated language intelligence (default)
- General pattern recognition (behavior, visual, audio)
- Avalanche continual learning hooks
- Multi-modal learning support
"""
import time
import numpy as np
from typing import Any, Dict, Tuple, Optional, List
from collections import defaultdict, deque


class PatternRecognizer:
    """
    General pattern recognition for behavior, vision, audio, and language.
    Uses statistical clustering and frequency analysis.
    """
    
    def __init__(self, pattern_types: List[str] = None):
        if pattern_types is None:
            pattern_types = ['behavior', 'visual', 'audio', 'language', 'state']
        
        self.pattern_types = pattern_types
        
        # Pattern storage: {pattern_type: {pattern_hash: [occurrences, last_seen, context]}}
        self.patterns: Dict[str, Dict[str, List]] = {pt: {} for pt in pattern_types}
        
        # Sequence patterns: {pattern_type: [(sequence, count)]}
        self.sequences: Dict[str, List[Tuple[tuple, int]]] = {pt: [] for pt in pattern_types}
        
        # Pattern transitions: {pattern_type: {(pattern_a, pattern_b): count}}
        self.transitions: Dict[str, Dict[Tuple[str, str], int]] = {
            pt: defaultdict(int) for pt in pattern_types
        }
        
        # Recent patterns for sequence detection
        self.recent_patterns: Dict[str, deque] = {
            pt: deque(maxlen=10) for pt in pattern_types
        }
    
    def observe_pattern(self, pattern_type: str, pattern_data: Any, 
                       context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Observe and record a pattern.
        Returns analysis: {novelty, frequency, related_patterns}
        """
        if pattern_type not in self.pattern_types:
            return {'novelty': 0.0, 'frequency': 0, 'related_patterns': []}
        
        # Hash the pattern
        pattern_hash = self._hash_pattern(pattern_data)
        
        # Record occurrence
        if pattern_hash not in self.patterns[pattern_type]:
            self.patterns[pattern_type][pattern_hash] = [0, time.time(), context or {}]
            novelty = 1.0
        else:
            novelty = 1.0 / (1.0 + self.patterns[pattern_type][pattern_hash][0])
        
        self.patterns[pattern_type][pattern_hash][0] += 1
        self.patterns[pattern_type][pattern_hash][1] = time.time()
        
        frequency = self.patterns[pattern_type][pattern_hash][0]
        
        # Update recent patterns for sequence detection
        self.recent_patterns[pattern_type].append(pattern_hash)
        
        # Detect transitions
        if len(self.recent_patterns[pattern_type]) >= 2:
            prev_pattern = self.recent_patterns[pattern_type][-2]
            self.transitions[pattern_type][(prev_pattern, pattern_hash)] += 1
        
        # Find related patterns
        related = self._find_related_patterns(pattern_type, pattern_hash)
        
        return {
            'novelty': novelty,
            'frequency': frequency,
            'related_patterns': related,
            'pattern_hash': pattern_hash
        }
    
    def detect_sequences(self, pattern_type: str, min_length: int = 2, 
                        min_occurrences: int = 2) -> List[Tuple[tuple, int]]:
        """
        Detect recurring sequences of patterns.
        Returns [(sequence, count), ...]
        """
        if pattern_type not in self.pattern_types:
            return []
        
        recent = list(self.recent_patterns[pattern_type])
        
        if len(recent) < min_length:
            return []
        
        # Sliding window to find sequences
        sequence_counts = defaultdict(int)
        
        for length in range(min_length, len(recent)):
            for i in range(len(recent) - length + 1):
                seq = tuple(recent[i:i+length])
                sequence_counts[seq] += 1
        
        # Filter by minimum occurrences
        sequences = [
            (seq, count) for seq, count in sequence_counts.items()
            if count >= min_occurrences
        ]
        
        # Sort by count
        sequences.sort(key=lambda x: x[1], reverse=True)
        
        return sequences[:10]  # Top 10
    
    def predict_next_pattern(self, pattern_type: str) -> Optional[str]:
        """
        Predict next likely pattern based on current context.
        Uses transition probabilities.
        """
        if pattern_type not in self.pattern_types:
            return None
        
        if not self.recent_patterns[pattern_type]:
            return None
        
        current_pattern = self.recent_patterns[pattern_type][-1]
        
        # Find most likely next pattern
        candidates = {}
        for (prev, next_p), count in self.transitions[pattern_type].items():
            if prev == current_pattern:
                candidates[next_p] = count
        
        if not candidates:
            return None
        
        # Return most frequent
        return max(candidates.items(), key=lambda x: x[1])[0]
    
    def _hash_pattern(self, pattern_data: Any) -> str:
        """Create hash from pattern data"""
        if isinstance(pattern_data, np.ndarray):
            # For arrays, round and hash
            rounded = np.round(pattern_data.flatten()[:20], 2)
            return '_'.join(str(x) for x in rounded)
        elif isinstance(pattern_data, dict):
            # For dicts, hash key-value pairs
            items = sorted(pattern_data.items())[:10]
            return '_'.join(f"{k}:{v}" for k, v in items)
        else:
            # For strings/primitives
            return str(pattern_data)[:100]
    
    def _find_related_patterns(self, pattern_type: str, 
                               pattern_hash: str, limit: int = 5) -> List[str]:
        """Find patterns that frequently co-occur"""
        related = []
        
        # Look at transition probabilities
        for (prev, next_p), count in self.transitions[pattern_type].items():
            if prev == pattern_hash or next_p == pattern_hash:
                other = next_p if prev == pattern_hash else prev
                if other != pattern_hash:
                    related.append((other, count))
        
        # Sort by frequency and return top
        related.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in related[:limit]]
    
    def get_pattern_stats(self, pattern_type: str) -> Dict[str, Any]:
        """Get statistics for pattern type"""
        if pattern_type not in self.pattern_types:
            return {}
        
        total_patterns = len(self.patterns[pattern_type])
        total_observations = sum(p[0] for p in self.patterns[pattern_type].values())
        
        # Most frequent patterns
        frequent = sorted(
            self.patterns[pattern_type].items(),
            key=lambda x: x[1][0],
            reverse=True
        )[:10]
        
        return {
            'total_unique_patterns': total_patterns,
            'total_observations': total_observations,
            'most_frequent': [
                {'hash': h[:50], 'count': data[0]} 
                for h, data in frequent
            ],
            'recent_sequence_length': len(self.recent_patterns[pattern_type])
        }


class BrainCore:
    """
    Enhanced brain with integrated language and pattern recognition.
    Complements neural network policies.
    """
    
    def __init__(self, agent_ref=None):
        self.agent = agent_ref
        
        # Value learning (existing)
        self.value_table = {}
        self.forward_model = {}
        self.curiosity_weight = 0.5
        self.predictability_weight = 0.2
        
        # Pattern recognition (NEW)
        self.pattern_recognizer = PatternRecognizer()
        
        # Language intelligence (INTEGRATED)
        from ai_core.brain_language import LanguageIntelligence
        self.language = LanguageIntelligence(agent_ref=agent_ref)
        
        # Avalanche continual learning buffer (NEW)
        self.continual_buffer = deque(maxlen=10000)
        self.task_labels = {}  # For task-aware continual learning
        self.current_task = 0
    
    def evaluate_event(self, event: Dict[str, Any], 
                      context: Optional[Dict[str, Any]] = None) -> Tuple[float, Dict[str, float]]:
        """
        Enhanced event evaluation with pattern recognition.
        """
        try:
            etype = event.get('type', 'unknown')
            tags = event.get('tags', [])
            payload = event.get('payload', {})
            
            # Detect pattern type
            pattern_type = self._classify_event_pattern_type(event)
            
            # Observe pattern
            pattern_analysis = self.pattern_recognizer.observe_pattern(
                pattern_type=pattern_type,
                pattern_data=event,
                context=context
            )
            
            # Compute reward components
            drive_reward = self._drive_reward(payload)
            novelty = pattern_analysis['novelty']
            curiosity_bonus = self.curiosity_weight * novelty
            learned_val = self._lookup_learned_value(event)
            predict_err = self._prediction_error(event)
            predictability_bonus = -self.predictability_weight * predict_err
            
            # Pattern recognition bonus
            pattern_bonus = 0.0
            if novelty > 0.7:
                pattern_bonus = 0.1  # Reward for discovering new patterns
            
        except Exception as e:
            return 0.0, {"surprise": 0.1}
        
        reward = (drive_reward + curiosity_bonus + learned_val + 
                 predictability_bonus + pattern_bonus)
        
        emo_delta = self._reward_to_emotion_delta(reward, event)
        
        # Update learning
        self._update_learning(event, payload, reward)
        
        # Store in continual learning buffer
        self._store_continual_experience(event, reward, context)
        
        return reward, emo_delta
    
    def _classify_event_pattern_type(self, event: Dict[str, Any]) -> str:
        """Classify event into pattern type"""
        etype = event.get('type', '')
        tags = event.get('tags', [])
        
        if 'vision' in tags or 'visual' in etype:
            return 'visual'
        elif 'audio' in tags or 'sound' in etype:
            return 'audio'
        elif 'chat' in tags or 'language' in tags:
            return 'language'
        elif 'action' in tags or 'movement' in etype:
            return 'behavior'
        else:
            return 'state'
    
    def _drive_reward(self, payload: Dict[str, Any]) -> float:
        """Compute drive-based reward"""
        r = 0.0
        
        if 'health_delta' in payload:
            r += float(payload['health_delta']) * 1.0
        
        if 'hunger_delta' in payload:
            r += float(payload['hunger_delta']) * 0.25
        
        if payload.get('danger_increased', False):
            r -= 0.5
        
        if payload.get('success', False):
            r += 0.5
        
        return r
    
    def _novelty_for_event(self, event: Dict[str, Any]) -> float:
        """Compute novelty score using pattern recognizer"""
        pattern_type = self._classify_event_pattern_type(event)
        
        # Use pattern recognizer's novelty
        analysis = self.pattern_recognizer.observe_pattern(
            pattern_type, event
        )
        
        return analysis['novelty']
    
    def _lookup_learned_value(self, event: Dict[str, Any]) -> float:
        """Get learned value for event type"""
        key = (event.get('type'), event.get('tags', [None])[0])
        v = self.value_table.get(key)
        if v:
            total, cnt = v
            return total / max(1, cnt)
        return 0.0
    
    def _prediction_error(self, event: Dict[str, Any]) -> float:
        """Compute prediction error"""
        a = event.get('type')
        if a in self.forward_model:
            model = self.forward_model[a]
            actual = event.get('tags', [])
            if actual:
                tag = actual[0]
                prob = model.get(tag, 0.0)
                return 1.0 - prob
        return 0.0
    
    def _reward_to_emotion_delta(self, reward: float, 
                                 event: Dict[str, Any]) -> Dict[str, float]:
        """Convert reward to emotion changes"""
        joy = max(0.0, reward) * 0.2
        fear = max(0.0, -reward) * 0.3
        surprise = self._novelty_for_event(event) * 0.2
        return {'joy': joy, 'fear': fear, 'surprise': surprise}
    
    def _update_learning(self, event: Dict[str, Any], 
                        payload: Dict[str, Any], reward: float):
        """Update value table and forward model"""
        key = (event.get('type'), event.get('tags', [None])[0])
        if key not in self.value_table:
            self.value_table[key] = [0.0, 0]
        self.value_table[key][0] += reward
        self.value_table[key][1] += 1
        
        # Update forward model
        action = event.get('type')
        outcome_tag = event.get('tags', ['none'])[0]
        if action not in self.forward_model:
            self.forward_model[action] = {}
        
        self.forward_model[action][outcome_tag] = \
            self.forward_model[action].get(outcome_tag, 0) + 1
        
        total = sum(self.forward_model[action].values())
        for k in self.forward_model[action]:
            self.forward_model[action][k] = self.forward_model[action][k] / total
    
    def _store_continual_experience(self, event: Dict[str, Any], 
                                   reward: float, 
                                   context: Optional[Dict] = None):
        """Store experience for continual learning (Avalanche)"""
        experience = {
            'event': event,
            'reward': reward,
            'context': context,
            'task': self.current_task,
            'timestamp': time.time()
        }
        
        self.continual_buffer.append(experience)
    
    def _event_key(self, event: Dict[str, Any]) -> str:
        """Generate unique key for event"""
        et = event.get('type', '')
        tags = ','.join(event.get('tags', []))
        return f"{et}|{tags}"
    
    def predict_value_of_action(self, action: Dict[str, Any]) -> float:
        """Predict value of an action (for planning)"""
        action_type = action.get('type')
        if action_type in self.forward_model:
            total_value = 0.0
            for outcome, prob in self.forward_model[action_type].items():
                key = (action_type, outcome)
                if key in self.value_table:
                    val, cnt = self.value_table[key]
                    avg_val = val / max(1, cnt)
                    total_value += prob * avg_val
            return total_value
        return 0.0
    
    def get_continual_buffer(self, task: Optional[int] = None, 
                            limit: Optional[int] = None) -> List[Dict]:
        """Get experiences for continual learning replay"""
        if task is None:
            experiences = list(self.continual_buffer)
        else:
            experiences = [
                exp for exp in self.continual_buffer 
                if exp['task'] == task
            ]
        
        if limit:
            experiences = experiences[-limit:]
        
        return experiences
    
    def switch_task(self, new_task: int):
        """Switch to new task (for continual learning)"""
        self.current_task = new_task
        self.task_labels[new_task] = time.time()
    
    def get_pattern_summary(self) -> Dict[str, Any]:
        """Get summary of all recognized patterns"""
        summary = {}
        
        for pattern_type in self.pattern_recognizer.pattern_types:
            summary[pattern_type] = self.pattern_recognizer.get_pattern_stats(
                pattern_type
            )
        
        return summary
    
    # ... existing code above

    def process_language_input(self, text, context):
        """
        Wrapper: routes language processing through existing subsystems.
        Returns an empty string if no valid response is produced.
        """
        try:
            # if you already have something like self.language.process_input or self.language_model
            if hasattr(self, "language") and hasattr(self.language, "process_input"):
                response = self.language.process_input(text, context)
            elif hasattr(self, "language_model"):
                response = self.language_model.generate_response(text, context)
            else:
                response = None

            # Return empty string if no response (agent stays silent)
            return response if response else ""
        except Exception as e:
            print(f"[BrainCore] Language input error: {e}")
            return ""

    