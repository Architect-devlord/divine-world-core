# ai_core/emotion.py
import numpy as np
from typing import Dict

class EmotionSystem:
    EMOTIONS = ['joy','sadness','anger','fear','trust','surprise','anticipation','disgust']

    def __init__(self, decay_rate: float = 0.95):
        self.emotions: Dict[str, float] = {e: 0.0 for e in self.EMOTIONS}
        self.decay_rate = decay_rate

    def add(self, emotion: str, value: float):
        if emotion in self.emotions:
            self.emotions[emotion] = float(np.clip(self.emotions[emotion] + value, -1.0, 1.0))

    def set(self, emotion: str, value: float):
        if emotion in self.emotions:
            self.emotions[emotion] = float(np.clip(value, -1.0, 1.0))

    def decay(self):
        for k in self.emotions: self.emotions[k] *= self.decay_rate

    def reset(self):
        for k in self.emotions: self.emotions[k] = 0.0

    def snapshot(self) -> Dict[str, float]:
        return self.emotions.copy()

    def as_array(self) -> np.ndarray:
        return np.array([self.emotions[e] for e in self.EMOTIONS], dtype=np.float32)

    def dominant_emotion(self) -> str:
        return max(self.emotions.items(), key=lambda x: abs(x[1]))[0]

    def intensity(self) -> float:
        """Overall arousal — max absolute value across all emotions."""
        return float(max(abs(v) for v in self.emotions.values()))

    def valence(self) -> float:
        """Net positive/negative tone."""
        pos = self.emotions['joy'] + self.emotions['trust'] + self.emotions['anticipation']
        neg = self.emotions['sadness'] + self.emotions['anger'] + self.emotions['fear'] + self.emotions['disgust']
        return float(np.clip((pos - neg) / 3.0, -1.0, 1.0))

    def is_calm(self, threshold: float = 0.1) -> bool:
        return self.intensity() < threshold

    def __repr__(self):
        return f"EmotionSystem(dominant={self.dominant_emotion()}, intensity={self.intensity():.2f})"