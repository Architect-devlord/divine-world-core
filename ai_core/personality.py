# ai_core/personality.py - UNIFIED VERSION with Gender
"""
Single source of truth for personality system.
Includes Big Five traits, custom traits, and gender.
"""
import numpy as np
from typing import Dict, Optional, Any, Literal

GenderType = Literal['male', 'female', 'dual']


class Personality:
    """
    Unified personality system with gender support.
    
    Traits:
    - Big Five: openness, conscientiousness, extraversion, agreeableness, neuroticism
    - Custom: boldness, curiosity, sociability
    - Gender: male, female, or dual (for god entities)
    """
    
    # Default trait ranges
    TRAITS = [
        'openness',
        'conscientiousness', 
        'extraversion',
        'agreeableness',
        'neuroticism',
        'boldness',
        'curiosity',
        'sociability'
    ]
    
    def __init__(self, gender: GenderType = 'male', traits: Optional[Dict[str, float]] = None):
        """
        Initialize personality.
        
        Args:
            gender: 'male', 'female', or 'dual' (for gods)
            traits: Optional dict of trait values in [-1.0, 1.0]
        """
        self.gender = gender
        
        # Initialize traits with defaults or provided values
        self.traits = {trait: 0.0 for trait in self.TRAITS}
        
        if traits:
            for key, value in traits.items():
                if key in self.traits:
                    self.traits[key] = np.clip(float(value), -1.0, 1.0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict including gender"""
        return {
            'gender': self.gender,
            **self.traits
        }
    
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Personality':
        """Deserialize from dict"""
        gender = data.pop('gender', 'male')
        return Personality(gender=gender, traits=data)
    
    def as_array(self) -> np.ndarray:
        """Convert traits to numpy array for neural networks"""
        return np.array([self.traits[t] for t in self.TRAITS], dtype=np.float32)
    
    def apply_update(self, delta: np.ndarray, lr: float = 0.05):
        """Apply gradient update to personality traits"""
        current = self.as_array()
        updated = current + lr * delta
        updated = np.clip(updated, -1.0, 1.0)
        
        for i, trait in enumerate(self.TRAITS):
            self.traits[trait] = float(updated[i])
    
    def similarity(self, other: 'Personality') -> float:
        """Compute cosine similarity with another personality"""
        a = self.as_array()
        b = other.as_array()
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))
    
    def __repr__(self) -> str:
        return f"Personality(gender={self.gender}, traits={self.traits})"


# Gender utility functions
def assign_npc_gender() -> GenderType:
    """Randomly assign male or female to NPC"""
    import random
    return random.choice(['male', 'female'])


def assign_god_gender() -> GenderType:
    """Gods are always dual-gendered"""
    return 'dual'


def can_breed(gender_a: GenderType, gender_b: GenderType) -> bool:
    """
    Check if two genders can breed.
    
    Rules:
    - male + female = yes
    - dual + any = yes
    - same gender = no
    """
    if gender_a == 'dual' or gender_b == 'dual':
        return True
    return (gender_a == 'male' and gender_b == 'female') or \
           (gender_a == 'female' and gender_b == 'male')


def determine_child_gender(parent_a: GenderType, parent_b: GenderType) -> GenderType:
    """Child is always NPC (male or female), never dual"""
    import random
    return random.choice(['male', 'female'])