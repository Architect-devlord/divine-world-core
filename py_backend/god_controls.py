# god_controls.py - Add to py_backend
"""
God Agent Special Controls
Extends the action system for god entities with special abilities
"""

import numpy as np
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class GodAbility:
    """Represents a god-specific ability"""
    name: str
    cooldown: float = 0.0
    cost: float = 0.0  # Energy/mana cost
    last_used: float = 0.0


class GodControlSystem:
    """
    Manages god-specific abilities and controls
    Extends the base action system with god powers
    """
    
    def __init__(self, god_type: str):
        self.god_type = god_type
        self.abilities = self._initialize_abilities()
        self.current_form = "god"  # "god" or "player"
        
    def _initialize_abilities(self) -> Dict[str, GodAbility]:
        """Initialize abilities based on god type"""
        
        abilities = {}
        
        if self.god_type == "ender_dragon" or self.god_type == "dragon":
            abilities = {
                "dragon_breath": GodAbility("dragon_breath", cooldown=5.0),
                "fireball": GodAbility("fireball", cooldown=2.0),
                "perch": GodAbility("perch", cooldown=0.0),
                "fly": GodAbility("fly", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "transform_player": GodAbility("transform_player", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0)
            }
            
        elif self.god_type == "wither":
            abilities = {
                "wither_skull": GodAbility("wither_skull", cooldown=1.0),
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
                "revert": GodAbility("revert", cooldown=1.0),
                # Player abilities
                "mine_block": GodAbility("mine_block", cooldown=0.0),
                "place_block": GodAbility("place_block", cooldown=0.0),
                "use_item": GodAbility("use_item", cooldown=0.0)
            }
            
        elif self.god_type == "creaking":
            abilities = {
                "toggle_underground": GodAbility("toggle_underground", cooldown=1.0),
                "toggle_ceiling": GodAbility("toggle_ceiling", cooldown=1.0),
                "deploy_tentacles": GodAbility("deploy_tentacles", cooldown=0.5),
                "tentacle_whip": GodAbility("tentacle_whip", cooldown=0.8),
                "life_steal": GodAbility("life_steal", cooldown=2.0),
                "wall_climb": GodAbility("wall_climb", cooldown=0.0),
                "transform": GodAbility("transform", cooldown=5.0),
                "revert": GodAbility("revert", cooldown=1.0),
                # Player abilities
                "mine_block": GodAbility("mine_block", cooldown=0.0),
                "place_block": GodAbility("place_block", cooldown=0.0),
                "use_item": GodAbility("use_item", cooldown=0.0)
            }
            
        return abilities
    
    def use_ability(self, ability_name: str, current_time: float, **params) -> Dict[str, Any]:
        """
        Attempt to use an ability
        Returns command dict to send to Minecraft client
        """
        if ability_name not in self.abilities:
            return {"error": f"Unknown ability: {ability_name}"}
        
        ability = self.abilities[ability_name]
        
        # Check cooldown
        time_since_last = current_time - ability.last_used
        if time_since_last < ability.cooldown:
            return {"error": "Ability on cooldown", "remaining": ability.cooldown - time_since_last}
        
        # Mark as used
        ability.last_used = current_time
        
        # Build command
        command = {
            "type": "god_ability",
            "ability": ability_name,
            "params": params
        }
        
        return command
    
    def transform_form(self, target_form: str) -> Dict[str, Any]:
        """Transform between god and player form"""
        if target_form not in ["god", "player"]:
            return {"error": "Invalid form"}
        
        if target_form == self.current_form:
            return {"error": "Already in that form"}
        
        self.current_form = target_form
        
        return {
            "type": "transform",
            "target_form": target_form
        }
    
    def get_available_abilities(self, current_time: float) -> Dict[str, bool]:
        """Check which abilities are off cooldown"""
        available = {}
        
        for name, ability in self.abilities.items():
            time_since_last = current_time - ability.last_used
            available[name] = time_since_last >= ability.cooldown
        
        return available


class GodActionEncoder:
    """
    Encodes god actions into the binary protocol
    Extends the base ActionFrame with god-specific data
    """
    
    @staticmethod
    def encode_god_action(
        base_action: Dict[str, Any],
        god_commands: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Combine base movement/actions with god-specific commands
        """
        action = base_action.copy()
        action['god_commands'] = god_commands
        return action
    
    @staticmethod
    def create_god_action_array(
        movement: np.ndarray,  # Normal 11-dim action
        god_ability_idx: int = -1,  # Which ability to activate
        god_params: Dict[str, float] = None  # Additional parameters
    ) -> np.ndarray:
        """
        Create extended action array for god agents
        Base 11 dimensions + 5 god-specific dimensions
        """
        # Base action: [move_forward, move_strafe, jump, sneak, attack, 
        #                use, drop, open_inv, swap_hand, yaw_delta, pitch_delta]
        
        # God extension: [ability_trigger, ability_idx, param1, param2, param3]
        god_ext = np.zeros(5, dtype=np.float32)
        
        if god_ability_idx >= 0:
            god_ext[0] = 1.0  # Trigger flag
            god_ext[1] = float(god_ability_idx)
            
            # Fill in parameters
            if god_params:
                for i, (key, value) in enumerate(list(god_params.items())[:3]):
                    god_ext[2 + i] = value
        
        # Combine
        full_action = np.concatenate([movement, god_ext])
        return full_action


# Integration with existing agent.py
def integrate_god_controls(agent):
    """
    Add god control system to an NPCAgent
    """
    if hasattr(agent, 'agent_type') and agent.agent_type.startswith('god_'):
        god_type = agent.agent_type.replace('god_', '')
        agent.god_controls = GodControlSystem(god_type)
        
        # Override the act() method to include god abilities
        original_act = agent.act
        
        def act_with_god_powers(action: np.ndarray) -> Dict[str, Any]:
            # First get base actions
            base_controls = original_act(action[:11])
            
            # Check if god abilities should be used
            if len(action) >= 16:  # Extended action array
                god_extension = action[11:16]
                
                if god_extension[0] > 0.5:  # Ability trigger
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
                        
                        # Use ability
                        import time
                        god_command = agent.god_controls.use_ability(
                            ability_name,
                            time.time(),
                            **params
                        )
                        
                        # Merge with base controls
                        base_controls['god_ability'] = god_command
            
            return base_controls
        
        agent.act = act_with_god_powers


# Example usage in main.py or agent spawning
def spawn_god_with_controls(spawner, god_type: str, **kwargs):
    """
    Spawn a god agent and attach control system
    """
    agent = spawner.spawn_god(god_type, **kwargs)
    integrate_god_controls(agent)
    return agent


# Add to BrainCore for decision making
class GodBrainExtension:
    """
    Extends BrainCore with god-specific decision making
    """
    
    @staticmethod
    def decide_god_ability(
        brain,
        obs: np.ndarray,
        available_abilities: Dict[str, bool]
    ) -> int:
        """
        Decide which god ability to use based on observation
        Returns ability index or -1 for none
        """
        if not hasattr(brain, 'god_ability_policy'):
            return -1
        
        # Simple heuristic for now (can be learned)
        # Check if in combat
        nearby_enemies = obs[7] if len(obs) > 7 else 0.0
        health_percent = obs[0] if len(obs) > 0 else 1.0
        
        ability_names = list(available_abilities.keys())
        
        # Combat situation
        if nearby_enemies > 0.3:
            # Use offensive ability
            for i, name in enumerate(ability_names):
                if available_abilities[name] and 'attack' in name.lower():
                    return i
        
        # Low health
        if health_percent < 0.3:
            # Use defensive/healing ability
            for i, name in enumerate(ability_names):
                if available_abilities[name] and ('heal' in name.lower() or 'life' in name.lower()):
                    return i
        
        return -1  # No ability


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