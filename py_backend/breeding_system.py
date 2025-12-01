# py_backend/breeding_system.py - FIXED VERSION
"""
Complete breeding implementation with:
- Adjacent bed detection (server-side check)
- 9 Minecraft day pregnancy (20 min/day = 180 min = 3 hours)
- Growth from baby to adult (30 days)
- Automatic .exe packaging for children
"""

import time
import random
import logging
from pathlib import Path
from typing import Tuple, Dict, Any, Optional
from dataclasses import dataclass
from collections import deque

# FIXED IMPORTS - Use personality module instead of gender_system
from ai_core.personality import can_breed, determine_child_gender, assign_npc_gender, GenderType
from auto_packager import EnhancedAgentSpawner

log = logging.getLogger("breeding")

# Minecraft time constants
MINECRAFT_DAY_SECONDS = 1200  # 20 real minutes
PREGNANCY_DAYS = 9
GROWTH_DAYS = 30

@dataclass
class PregnancyData:
    """Tracks pregnancy state"""
    female_id: str
    male_id: str
    conception_time: float
    due_time: float
    child_traits: Dict[str, float]
    child_gender: GenderType  # FIXED: Use GenderType from personality


class BreedingSystem:
    """
    Full breeding system with bed detection, pregnancy, growth, and packaging.
    """
    
    def __init__(self, spawner: EnhancedAgentSpawner):
        self.spawner = spawner
        self.pregnancies: Dict[str, PregnancyData] = {}
        self.growth_stages: Dict[str, float] = {}  # child_id -> birth_time
        self.breeding_cooldowns: Dict[str, float] = {}  # agent_id -> cooldown_end
    
    def check_can_breed(self, agent_a_id: str, agent_b_id: str, 
                        beds_adjacent: bool = True) -> Tuple[bool, str]:
        """
        Check if two agents can breed.
        
        For NPCs: Requires adjacent beds
        For Gods: Can breed without beds
        """
        agent_a = self.spawner.get_agent(agent_a_id)
        agent_b = self.spawner.get_agent(agent_b_id)
        
        if not agent_a or not agent_b:
            return False, "Agent not found"
            
        # Gods don't need beds
        needs_beds = not (agent_a.agent_type.startswith('god') or agent_b.agent_type.startswith('god'))
        
        if needs_beds and not beds_adjacent:
            return False, "Beds must be adjacent"
        
        # Must be NPCs (gods cannot breed with each other in traditional way)
        if agent_a.agent_type != 'npc' or agent_b.agent_type != 'npc':
            return False, "Only NPCs can breed traditionally"
        
        # Check genders - FIXED: Use personality module function
        if not can_breed(agent_a.personality.gender, agent_b.personality.gender):
            return False, f"Incompatible genders: {agent_a.personality.gender} + {agent_b.personality.gender}"
        
        # Check if already pregnant
        if agent_a_id in self.pregnancies or agent_b_id in self.pregnancies:
            return False, "One agent is already pregnant"
        
        # Check if children (still growing)
        if agent_a_id in self.growth_stages or agent_b_id in self.growth_stages:
            return False, "Children cannot breed"
        
        # Check cooldown (prevent spam breeding)
        current_time = time.time()
        if agent_a_id in self.breeding_cooldowns:
            if current_time < self.breeding_cooldowns[agent_a_id]:
                return False, f"{agent_a_id} on breeding cooldown"
        
        if agent_b_id in self.breeding_cooldowns:
            if current_time < self.breeding_cooldowns[agent_b_id]:
                return False, f"{agent_b_id} on breeding cooldown"
        
        return True, "Can breed"
    
    def initiate_breeding(self, agent_a_id: str, agent_b_id: str) -> Optional[PregnancyData]:
        """
        Start pregnancy after successful bed interaction.
        Returns PregnancyData if successful.
        """
        can_breed_result, reason = self.check_can_breed(agent_a_id, agent_b_id)
        
        if not can_breed_result:
            log.warning(f"Breeding failed: {reason}")
            return None
        
        agent_a = self.spawner.get_agent(agent_a_id)
        agent_b = self.spawner.get_agent(agent_b_id)
        
        # Determine female (for pregnancy tracking)
        if agent_a.personality.gender == 'female':
            female_id, male_id = agent_a_id, agent_b_id
            female, male = agent_a, agent_b
        elif agent_b.personality.gender == 'female':
            female_id, male_id = agent_b_id, agent_a_id
            female, male = agent_b, agent_a
        else:
            # dual + dual or dual + male (female becomes the dual)
            female_id, male_id = agent_a_id, agent_b_id
            female, male = agent_a, agent_b
        
        # Generate child traits (inherit with mutation)
        child_traits = self._generate_child_traits(
            female.personality.to_dict(),
            male.personality.to_dict()
        )
        
        # Determine child gender - FIXED: Use personality module function
        child_gender = determine_child_gender(
            female.personality.gender,
            male.personality.gender
        )
        
        # Create pregnancy
        conception_time = time.time()
        due_time = conception_time + (PREGNANCY_DAYS * MINECRAFT_DAY_SECONDS)
        
        pregnancy = PregnancyData(
            female_id=female_id,
            male_id=male_id,
            conception_time=conception_time,
            due_time=due_time,
            child_traits=child_traits,
            child_gender=child_gender
        )
        
        self.pregnancies[female_id] = pregnancy
        
        # Set cooldowns (24 Minecraft days = 8 real hours)
        cooldown_end = conception_time + (24 * MINECRAFT_DAY_SECONDS)
        self.breeding_cooldowns[agent_a_id] = cooldown_end
        self.breeding_cooldowns[agent_b_id] = cooldown_end
        
        log.info(f"Pregnancy started: {female_id} x {male_id}")
        log.info(f"  Due in: {PREGNANCY_DAYS} MC days ({(due_time - conception_time) / 60:.1f} real minutes)")
        log.info(f"  Child gender: {child_gender}")
        
        return pregnancy
    
    def _generate_child_traits(self, parent_a: Dict, parent_b: Dict) -> Dict[str, float]:
        """Inherit traits with mutation"""
        child_traits = {}
        mutation_rate = 0.15  # 15% mutation
        
        for key in parent_a.keys():
            if key == 'gender':
                continue
            
            val_a = parent_a.get(key, 0.0)
            val_b = parent_b.get(key, 0.0)
            
            # Weighted average (slight bias to dominant parent)
            weight = random.uniform(0.4, 0.6)
            base = val_a * weight + val_b * (1 - weight)
            
            # Add mutation
            mutation = (random.random() * 2 - 1) * mutation_rate
            
            # Clamp
            child_val = max(-1.0, min(1.0, base + mutation))
            child_traits[key] = float(child_val)
        
        return child_traits
    
    def update_pregnancies(self) -> list:
        """
        Check for births. Call this every tick.
        Returns list of (mother_id, child_agent) tuples.
        """
        current_time = time.time()
        births = []
        
        for female_id, pregnancy in list(self.pregnancies.items()):
            if current_time >= pregnancy.due_time:
                # Give birth!
                child = self._spawn_child(pregnancy)
                
                if child:
                    births.append((female_id, child))
                    log.info(f"Birth! {female_id} gave birth to {child.agent_id}")
                
                # Remove pregnancy
                del self.pregnancies[female_id]
        
        return births
    
    def _spawn_child(self, pregnancy: PregnancyData):
        """Spawn child agent with inherited traits"""
        child_id = f"npc_child_{int(time.time() * 1000)}"
        
        try:
            # Get parents for metadata
            mother = self.spawner.get_agent(pregnancy.female_id)
            father = self.spawner.get_agent(pregnancy.male_id)
            
            # Spawn child with enhanced spawner (auto-packages)
            child = self.spawner.spawn_npc(
                agent_id=child_id,
                persona_traits=pregnancy.child_traits,
                gender=pregnancy.child_gender  # FIXED: Pass gender directly
            )
            
            # Track growth (starts as baby)
            self.growth_stages[child_id] = time.time()
            
            # Set child metadata
            child.metadata = {
                'is_child': True,
                'size': 0.5,  # Baby zombie size
                'parent_a': pregnancy.female_id,
                'parent_b': pregnancy.male_id,
                'birth_time': time.time(),
                'gender': pregnancy.child_gender
            }
            
            log.info(f"Child spawned: {child_id}")
            log.info(f"  Gender: {pregnancy.child_gender}")
            log.info(f"  Parents: {pregnancy.female_id} x {pregnancy.male_id}")
            log.info(f"  Size: 0.5 (baby) -> 1.0 (adult) over {GROWTH_DAYS} MC days")
            
            return child
            
        except Exception as e:
            log.error(f"Failed to spawn child: {e}")
            return None
    
    def update_growth(self):
        """Update child growth stages. Call this every tick."""
        current_time = time.time()
        growth_duration = GROWTH_DAYS * MINECRAFT_DAY_SECONDS
        
        for child_id, birth_time in list(self.growth_stages.items()):
            age = current_time - birth_time
            
            if age >= growth_duration:
                # Fully grown
                child = self.spawner.get_agent(child_id)
                if child and hasattr(child, 'metadata'):
                    child.metadata['is_child'] = False
                    child.metadata['size'] = 1.0
                
                del self.growth_stages[child_id]
                log.info(f"{child_id} has fully grown to adult size")
            
            else:
                # Calculate current size (interpolate 0.5 -> 1.0)
                progress = age / growth_duration
                current_size = 0.5 + (0.5 * progress)
                
                child = self.spawner.get_agent(child_id)
                if child and hasattr(child, 'metadata'):
                    child.metadata['size'] = current_size
    
    def get_pregnancy_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get pregnancy information for an agent"""
        if agent_id not in self.pregnancies:
            return None
        
        pregnancy = self.pregnancies[agent_id]
        current_time = time.time()
        
        time_remaining = pregnancy.due_time - current_time
        days_remaining = time_remaining / MINECRAFT_DAY_SECONDS
        
        return {
            'female_id': pregnancy.female_id,
            'male_id': pregnancy.male_id,
            'conception_time': pregnancy.conception_time,
            'due_time': pregnancy.due_time,
            'days_remaining': days_remaining,
            'minutes_remaining': time_remaining / 60,
            'child_gender': pregnancy.child_gender,
            'child_traits': pregnancy.child_traits
        }
    
    def get_growth_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get growth information for a child"""
        if agent_id not in self.growth_stages:
            return None
        
        birth_time = self.growth_stages[agent_id]
        current_time = time.time()
        growth_duration = GROWTH_DAYS * MINECRAFT_DAY_SECONDS
        
        age = current_time - birth_time
        progress = age / growth_duration
        current_size = 0.5 + (0.5 * progress)
        
        return {
            'birth_time': birth_time,
            'age_seconds': age,
            'age_mc_days': age / MINECRAFT_DAY_SECONDS,
            'growth_progress': progress,
            'current_size': current_size,
            'is_adult': progress >= 1.0
        }