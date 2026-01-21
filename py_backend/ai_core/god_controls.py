# ai_core/god_controls.py - God Agent Special Controls
"""
God Agent Special Controls
Extends the action system for god entities with special abilities
"""

import numpy as np
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

log = logging.getLogger("god_controls")


@dataclass
class GodAbility:
    """Represents a god-specific ability"""
    name: str
    cooldown: float = 0.0
    cost: float = 0.0
    last_used: float = 0.0


class GodControlSystem:
    """
    Manages god-specific abilities and controls.
    Extends base action system with god powers.
    """
    
    def __init__(self, god_type: str):
        self.god_type = god_type
        self.abilities = self._initialize_abilities()
        self.current_form = "god"  # "god" or "player"
        
    def _initialize_abilities(self) -> Dict[str, GodAbility]:
        """Initialize abilities based on god type"""
        
        abilities = {}
        
        if self.god_type in ["ender_dragon", "dragon"]:
            abilities = {
                "dragon_breath": GodAbility("dragon_breath", cooldown=5.0),
                "fireball": GodAbility("fireball", cooldown=2.0),
                "perch": GodAbility("perch", cooldown=0.0),
                "fly": GodAbility("fly", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "wither":
            abilities = {
                "wither_skull": GodAbility("wither_skull", cooldown=1.0),
                "blue_skull": GodAbility("blue_skull", cooldown=1.0),
                "dash": GodAbility("dash", cooldown=3.0),
                "summon_wither_skeletons": GodAbility("summon_wither_skeletons", cooldown=10.0),
                "explosion": GodAbility("explosion", cooldown=8.0),
                "fly": GodAbility("fly", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "warden":
            abilities = {
                "sonic_boom": GodAbility("sonic_boom", cooldown=5.0),
                "darkness": GodAbility("darkness", cooldown=15.0),
                "sniff": GodAbility("sniff", cooldown=0.0),
                "burrow": GodAbility("burrow", cooldown=10.0),
                "emerge": GodAbility("emerge", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "oracle":
            abilities = {
                "wisdom_aura": GodAbility("wisdom_aura", cooldown=30.0),
                "foresight": GodAbility("foresight", cooldown=5.0),
                "teleport": GodAbility("teleport", cooldown=3.0),
                "healing_wave": GodAbility("healing_wave", cooldown=10.0),
                "knowledge_beam": GodAbility("knowledge_beam", cooldown=4.0),
                "fly": GodAbility("fly", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "elder_guardian":
            abilities = {
                "mining_fatigue": GodAbility("mining_fatigue", cooldown=60.0),
                "laser_beam": GodAbility("laser_beam", cooldown=3.0),
                "thorn_attack": GodAbility("thorn_attack", cooldown=5.0),
                "guardian_spikes": GodAbility("guardian_spikes", cooldown=20.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "creaking":
            abilities = {
                "toggle_underground": GodAbility("toggle_underground", cooldown=1.0),
                "toggle_ceiling": GodAbility("toggle_ceiling", cooldown=1.0),
                "deploy_tentacles": GodAbility("deploy_tentacles", cooldown=0.5),
                "tentacle_whip": GodAbility("tentacle_whip", cooldown=0.8),
                "life_steal": GodAbility("life_steal", cooldown=2.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        return abilities
    
    def use_ability(self, ability_name: str, **params) -> Optional[Dict[str, Any]]:
        """
        Attempt to use an ability.
        Returns None if on cooldown, otherwise returns ability command.
        """
        if ability_name not in self.abilities:
            log.warning(f"Unknown ability: {ability_name}")
            return None
        
        ability = self.abilities[ability_name]
        current_time = time.time()
        
        # Check cooldown
        time_since_last = current_time - ability.last_used
        if time_since_last < ability.cooldown:
            return None  # On cooldown
        
        # Mark as used
        ability.last_used = current_time
        
        # Build command (will be sent via minecraft_client)
        command = {
            "god_ability": ability_name,
            **params
        }
        
        log.debug(f"Using god ability: {ability_name}")
        return command
    
    def get_available_abilities(self) -> Dict[str, bool]:
        """Check which abilities are off cooldown"""
        current_time = time.time()
        available = {}
        
        for name, ability in self.abilities.items():
            time_since_last = current_time - ability.last_used
            available[name] = time_since_last >= ability.cooldown
        
        return available
    
    def encode_ability_to_action(
        self, 
        base_action: np.ndarray,
        ability_name: Optional[str] = None,
        params: Optional[Dict[str, float]] = None
    ) -> np.ndarray:
        """
        Extend base 11-dim action array with god ability data.
        Returns 16-dim array: [base(11) + ability_trigger + ability_idx + param1 + param2 + param3]
        """
        # God extension: 5 dimensions
        god_ext = np.zeros(5, dtype=np.float32)
        
        if ability_name and ability_name in self.abilities:
            # Get ability index
            ability_names = list(self.abilities.keys())
            ability_idx = ability_names.index(ability_name)
            
            god_ext[0] = 1.0  # Trigger flag
            god_ext[1] = float(ability_idx)
            
            # Fill in parameters
            if params:
                for i, (key, value) in enumerate(list(params.items())[:3]):
                    god_ext[2 + i] = float(value)
        
        # Combine with base action
        return np.concatenate([base_action, god_ext])


def integrate_god_controls(agent):
    """
    Integrate god control system into an NPCAgent.
    Wraps the act() method to handle god abilities.
    """
    if not hasattr(agent, 'god_type') or not agent.god_type:
        log.warning("Cannot integrate god controls: agent has no god_type")
        return
    
    # Create god control system
    agent.god_controls = GodControlSystem(agent.god_type)
    
    # Wrap the original act() method
    original_act = agent.act
    
    def act_with_god_abilities(action: np.ndarray) -> Dict[str, Any]:
        """Enhanced act() that handles god abilities"""
        
        # Base actions (first 11 dimensions)
        base_action = action[:11] if len(action) >= 11 else action
        base_controls = original_act(base_action)
        
        # Check for god ability trigger (if action is extended)
        if len(action) >= 16:
            god_extension = action[11:16]
            
            # Check if ability should be triggered
            if god_extension[0] > 0.5:  # Trigger flag
                ability_idx = int(god_extension[1])
                ability_names = list(agent.god_controls.abilities.keys())
                
                if 0 <= ability_idx < len(ability_names):
                    ability_name = ability_names[ability_idx]
                    
                    # Extract parameters
                    params = {
                        'param1': float(god_extension[2]),
                        'param2': float(god_extension[3]),
                        'param3': float(god_extension[4])
                    }
                    
                    # Try to use ability
                    god_command = agent.god_controls.use_ability(ability_name, **params)
                    
                    if god_command:
                        # Merge god command into controls
                        base_controls.update(god_command)
        
        return base_controls
    
    # Replace agent's act method
    agent.act = act_with_god_abilities
    
    log.info(f"God controls integrated for {agent.god_type}")
# Reward shaping for god abilities
def compute_god_ability_reward(
    ability_used: str,
    outcome: Dict[str, Any],
    god_type: str
) -> float:
    """
    Compute reward for using god abilities
    Helps train the AI to use abilities effectively
    """
    reward = 0.0
    
    # Successful ability use
    if outcome.get('ability_success', False):
        reward += 2.0
    
    # Damage dealt with ability
    damage = outcome.get('ability_damage', 0.0)
    reward += damage * 0.1
    
    # Healing from ability
    healing = outcome.get('ability_healing', 0.0)
    reward += healing * 0.15
    
    # Tactical positioning (e.g., creaking going underground to ambush)
    if 'underground' in ability_used or 'ceiling' in ability_used:
        if outcome.get('surprise_attack', False):
            reward += 5.0
    
    return reward