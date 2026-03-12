# ai_core/personality.py
import numpy as np
from typing import Dict, Optional, Any, Literal
GenderType = Literal['male', 'female', 'dual']

class Personality:
    TRAITS = ['openness','conscientiousness','extraversion','agreeableness',
              'neuroticism','boldness','curiosity','sociability']

    def __init__(self, gender: GenderType = 'male', traits: Optional[Dict[str, float]] = None):
        self.gender = gender
        self.traits: Dict[str, float] = {t: 0.0 for t in self.TRAITS}
        if traits:
            for k, v in traits.items():
                if k in self.traits:
                    self.traits[k] = float(np.clip(float(v), -1.0, 1.0))

    def to_dict(self) -> Dict[str, Any]:
        return {'gender': self.gender, **self.traits}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Personality':
        data = dict(data)  # never mutate caller's dict
        gender = data.pop('gender', 'male')
        return Personality(gender=gender, traits=data)

    def as_array(self) -> np.ndarray:
        return np.array([self.traits[t] for t in self.TRAITS], dtype=np.float32)

    def apply_update(self, delta: np.ndarray, lr: float = 0.05):
        updated = np.clip(self.as_array() + lr * delta, -1.0, 1.0)
        for i, t in enumerate(self.TRAITS):
            self.traits[t] = float(updated[i])

    def similarity(self, other: 'Personality') -> float:
        a, b = self.as_array(), other.as_array()
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

    def get(self, trait: str, default: float = 0.0) -> float:
        """Convenience — avoids .traits[key] everywhere."""
        return self.traits.get(trait, default)

    def __repr__(self):
        return f"Personality(gender={self.gender}, traits={self.traits})"

def assign_npc_gender() -> GenderType:
    import random; return random.choice(['male', 'female'])
def assign_god_gender() -> GenderType:
    return 'dual'
def can_breed(a: GenderType, b: GenderType) -> bool:
    if a == 'dual' or b == 'dual': return True
    return {a, b} == {'male', 'female'}
def determine_child_gender(a: GenderType, b: GenderType) -> GenderType:
    import random; return random.choice(['male', 'female'])