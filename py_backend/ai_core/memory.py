# ------------------------------------------------------------------------------
# ai_core/memory.py - Memory systems (no circular deps)
# ------------------------------------------------------------------------------
import time
from typing import List, Dict, Any, Optional
from collections import deque
import numpy as np

class Memory:
    """
    Simple short-term memory for events.
    For compatibility with existing code.
    """
    def __init__(self, capacity: int = 1000):
        self.events = deque(maxlen=capacity)
        self.capacity = capacity
    
    def remember(self, event: Dict[str, Any], tags: Optional[List[str]] = None):
        """Store event in memory"""
        if not isinstance(event, dict):
            event = {'text': str(event), 'type': 'unknown'}
        
        event.setdefault('timestamp', time.time())
        event.setdefault('tags', tags or [])
        self.events.append(event)
    
    def recall(self, n: int = 10) -> List[Dict]:
        """Recall last n events"""
        return list(self.events)[-n:]
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Simple text search in memory"""
        results = []
        query_lower = query.lower()
        for event in reversed(self.events):
            text = str(event.get('text', ''))
            if query_lower in text.lower():
                results.append(event)
                if len(results) >= limit:
                    break
        return results
    
    def novelty_score(self, text: str) -> float:
        """Compute novelty of text vs memory"""
        if not self.events:
            return 1.0
        
        text_lower = text.lower()[:200]
        matches = sum(1 for e in self.events 
                     if text_lower in str(e.get('text', '')).lower())
        return 1.0 / (1.0 + matches)


class EpisodicMemory:
    """
    Advanced episodic memory with importance weighting.
    Uses Avalanche for continual learning support.
    """
    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)
        self.importance_weights = deque(maxlen=capacity)
    
    def store(self, obs: np.ndarray, action: np.ndarray, 
              reward: float, next_obs: np.ndarray, done: bool,
              importance: float = 1.0):
        """Store experience tuple"""
        self.buffer.append((obs, action, reward, next_obs, done))
        self.importance_weights.append(importance)
    
    def sample(self, batch_size: int = 32) -> tuple:
        """Sample batch with importance weighting"""
        if len(self.buffer) < batch_size:
            indices = range(len(self.buffer))
        else:
            # Weighted sampling
            weights = np.array(self.importance_weights)
            weights = weights / weights.sum()
            indices = np.random.choice(
                len(self.buffer), 
                size=batch_size, 
                replace=False,
                p=weights
            )
        
        batch = [self.buffer[i] for i in indices]
        obs, actions, rewards, next_obs, dones = zip(*batch)
        
        return (
            np.array(obs),
            np.array(actions),
            np.array(rewards),
            np.array(next_obs),
            np.array(dones)
        )
    
    def __len__(self):
        return len(self.buffer)
