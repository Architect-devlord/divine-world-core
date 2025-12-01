# ------------------------------------------------------------------------------
# ai_core/emotion.py - Emotion system (no circular deps)
# ------------------------------------------------------------------------------
import numpy as np
from typing import Dict
from collections import defaultdict

class EmotionSystem:
    """
    Multi-dimensional emotion state with decay.
    Based on Plutchik's wheel + custom gaming emotions.
    """
    def __init__(self):
        self.emotions = {
            'joy': 0.0,
            'sadness': 0.0,
            'anger': 0.0,
            'fear': 0.0,
            'trust': 0.0,
            'surprise': 0.0,
            'anticipation': 0.0,
            'disgust': 0.0,
        }
        self.decay_rate = 0.95  # Per step
    
    def add(self, emotion: str, value: float):
        """Add emotional intensity"""
        if emotion in self.emotions:
            self.emotions[emotion] = np.clip(
                self.emotions[emotion] + value,
                -1.0, 1.0
            )
    
    def decay(self):
        """Emotions naturally decay toward neutral"""
        for key in self.emotions:
            self.emotions[key] *= self.decay_rate
    
    def snapshot(self) -> Dict[str, float]:
        """Get current emotion state"""
        return self.emotions.copy()
    
    def as_array(self) -> np.ndarray:
        """Convert to array for neural network"""
        return np.array(list(self.emotions.values()), dtype=np.float32)
    
    def dominant_emotion(self) -> str:
        """Get strongest current emotion"""
        return max(self.emotions.items(), key=lambda x: abs(x[1]))[0]
