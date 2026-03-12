# py_backend/breeding_system.py
"""
Agent Breeding System
=====================
Manages reproduction between NPC agents:
  - Adjacent bed detection (Minecraft mechanic)
  - 9 Minecraft-day pregnancy (20 min/day = 3 real hours)
  - Growth from baby (0.5×) to adult (1.0×) over 30 MC days
  - Child trait inheritance with mutation
  - Automatic .exe packaging for newborn children

Reward design
-------------
Successful breeding fires a 'breeding' event through each parent's
RewardSystem, not as a hardcoded value.  The actual reward is computed
by compute_reward() and scaled by the agent's own personality:
  - High sociability + agreeableness → stronger reward
  - High neuroticism → reward partially offset by mild anxiety spike
  - Current joy/trust mood amplifies the reward
  - Hard cap at 0.15 so breeding never dominates survival signals

This means a naturally social, agreeable, happy agent genuinely wants
to have children while a withdrawn or fearful one is at best indifferent.
"""

import time
import random
import logging
from dataclasses import dataclass, asdict
from typing import Tuple, Dict, Any, Optional, List
from collections import deque

from ai_core.personality import can_breed, determine_child_gender, assign_npc_gender, GenderType

log = logging.getLogger("breeding")

# ---------------------------------------------------------------------------
# Minecraft time constants
# ---------------------------------------------------------------------------
MINECRAFT_DAY_SECONDS = 1200   # 20 real minutes per MC day
PREGNANCY_DAYS        = 9      # 9 MC days = 3 real hours
GROWTH_DAYS           = 30     # 30 MC days to reach adult size
BREEDING_COOLDOWN_DAYS = 24    # 24 MC days = 8 real hours


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PregnancyData:
    """Tracks one pregnancy."""
    female_id:       str
    male_id:         str
    conception_time: float
    due_time:        float
    child_traits:    Dict[str, float]
    child_gender:    GenderType

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to plain dict for brain_capsule storage."""
        d = asdict(self)
        d['child_gender'] = str(self.child_gender)
        return d

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "PregnancyData":
        """Restore from brain_capsule dict."""
        return PregnancyData(
            female_id       = d['female_id'],
            male_id         = d['male_id'],
            conception_time = d['conception_time'],
            due_time        = d['due_time'],
            child_traits    = d['child_traits'],
            child_gender    = d['child_gender'],   # kept as string — GenderType is a str enum
        )


# ---------------------------------------------------------------------------
# BreedingSystem
# ---------------------------------------------------------------------------

class BreedingSystem:
    """
    Full breeding lifecycle: eligibility → pregnancy → birth → growth.

    Usage
    -----
        breeding = BreedingSystem(spawner)
        # attach to agents so they can restore state after a load()
        breeding.attach_to_agent(agent)
        # call every game tick
        breeding.tick()
    """

    def __init__(self, spawner):
        """
        Args:
            spawner: EnhancedAgentSpawner (from auto_packager) that can
                     spawn new agents and look up existing ones.
        """
        self.spawner = spawner

        # female_id → PregnancyData
        self.pregnancies: Dict[str, PregnancyData] = {}

        # child_id → birth_time (float)
        self.growth_stages: Dict[str, float] = {}

        # agent_id → cooldown end time
        self.breeding_cooldowns: Dict[str, float] = {}

        log.info("BreedingSystem initialised")

    # ------------------------------------------------------------------
    # Agent attachment / pregnancy restoration
    # ------------------------------------------------------------------

    def attach_to_agent(self, agent) -> None:
        """
        Register the breeding system on the agent so save() can serialise
        pregnancy state, and restore any pending pregnancy from a previous run.

        Call this after spawning or loading every NPC agent.
        """
        agent._breeding_system = self

        # Restore pregnancy that was saved in the brain capsule
        pending = getattr(agent, '_pending_pregnancy', None)
        if pending is not None:
            try:
                preg = PregnancyData.from_dict(pending)
                # Only re-register if due time is still in the future
                if preg.due_time > time.time():
                    self.pregnancies[preg.female_id] = preg
                    log.info(
                        f"[{agent.agent_id}] Pregnancy restored — "
                        f"due in {(preg.due_time - time.time()) / 60:.1f} min"
                    )
                else:
                    log.info(
                        f"[{agent.agent_id}] Overdue pregnancy detected — "
                        f"triggering birth immediately"
                    )
                    self.pregnancies[preg.female_id] = preg
            except Exception as e:
                log.warning(f"[{agent.agent_id}] Could not restore pregnancy: {e}")
            agent._pending_pregnancy = None

    # ------------------------------------------------------------------
    # Eligibility check
    # ------------------------------------------------------------------

    def check_can_breed(
        self,
        agent_a_id: str,
        agent_b_id: str,
        beds_adjacent: bool = True,
    ) -> Tuple[bool, str]:
        """
        Check all preconditions for breeding.
          - Adjacent beds required for NPCs (gods exempt)
          - Both must be NPCs
          - Compatible genders (via personality.can_breed)
          - Neither already pregnant
          - Neither still a child
          - Neither on cooldown
        """
        agent_a = self.spawner.get_agent(agent_a_id)
        agent_b = self.spawner.get_agent(agent_b_id)

        if not agent_a or not agent_b:
            return False, "Agent not found"

        is_god_a = agent_a.agent_type.startswith('god')
        is_god_b = agent_b.agent_type.startswith('god')

        if is_god_a or is_god_b:
            return False, "Only NPCs can breed traditionally"

        if needs_beds := not (is_god_a or is_god_b):
            if not beds_adjacent:
                return False, "Beds must be adjacent"

        if not can_breed(agent_a.personality.gender, agent_b.personality.gender):
            return False, (
                f"Incompatible genders: "
                f"{agent_a.personality.gender} + {agent_b.personality.gender}"
            )

        if agent_a_id in self.pregnancies or agent_b_id in self.pregnancies:
            return False, "One agent is already pregnant"

        if agent_a_id in self.growth_stages or agent_b_id in self.growth_stages:
            return False, "Children cannot breed"

        now = time.time()
        for aid in (agent_a_id, agent_b_id):
            if self.breeding_cooldowns.get(aid, 0.0) > now:
                remaining = (self.breeding_cooldowns[aid] - now) / 60
                return False, f"{aid} on cooldown ({remaining:.0f} min remaining)"

        return True, "Can breed"

    # ------------------------------------------------------------------
    # Initiate breeding
    # ------------------------------------------------------------------

    def initiate_breeding(
        self,
        agent_a_id: str,
        agent_b_id: str,
    ) -> Optional[PregnancyData]:
        """
        Start a pregnancy after successful bed interaction.

        Fires a 'breeding' event through BOTH parents' reward systems.
        The reward is computed by RewardSystem.compute_reward() — it is
        personality-dependent and cannot be hardcoded here.

        Returns PregnancyData on success, None on failure.
        """
        ok, reason = self.check_can_breed(agent_a_id, agent_b_id)
        if not ok:
            log.warning(f"Breeding refused: {reason}")
            return None

        agent_a = self.spawner.get_agent(agent_a_id)
        agent_b = self.spawner.get_agent(agent_b_id)

        # Determine which agent carries the pregnancy
        if agent_a.personality.gender == 'female':
            female_id, male_id = agent_a_id, agent_b_id
            female, male = agent_a, agent_b
        elif agent_b.personality.gender == 'female':
            female_id, male_id = agent_b_id, agent_a_id
            female, male = agent_b, agent_a
        else:
            # dual × dual or dual × male — first agent carries
            female_id, male_id = agent_a_id, agent_b_id
            female, male = agent_a, agent_b

        child_traits  = self._generate_child_traits(
            female.personality.to_dict(),
            male.personality.to_dict(),
        )
        child_gender  = determine_child_gender(
            female.personality.gender,
            male.personality.gender,
        )

        now      = time.time()
        due_time = now + PREGNANCY_DAYS * MINECRAFT_DAY_SECONDS

        pregnancy = PregnancyData(
            female_id       = female_id,
            male_id         = male_id,
            conception_time = now,
            due_time        = due_time,
            child_traits    = child_traits,
            child_gender    = child_gender,
        )
        self.pregnancies[female_id] = pregnancy

        # Cooldowns
        cooldown_end = now + BREEDING_COOLDOWN_DAYS * MINECRAFT_DAY_SECONDS
        self.breeding_cooldowns[agent_a_id] = cooldown_end
        self.breeding_cooldowns[agent_b_id] = cooldown_end

        # ── Fire reward event through each parent's reward system ─────
        # The event type 'breeding' is handled by reward_system.compute_reward()
        # which applies personality weights, mood scaling, and the hard cap.
        # We pass is_breeding=True in the payload so _emotion_deltas can also
        # produce the correct trust/joy/fear deltas for this event type.
        for agent in (female, male):
            self._fire_breeding_reward(agent, partner_id=male_id if agent is female else female_id)

        log.info(
            f"✅ Pregnancy: {female_id} × {male_id} | "
            f"due {PREGNANCY_DAYS} MC days "
            f"({(due_time - now) / 60:.1f} real min) | "
            f"child gender: {child_gender}"
        )
        return pregnancy

    def _fire_breeding_reward(self, agent, partner_id: str) -> None:
        """Route a breeding event through the agent's reward system."""
        reward_system = getattr(agent, 'reward_system', None)
        if reward_system is None:
            # Fallback: try via brain
            reward_system = getattr(getattr(agent, 'brain', None), 'reward_system', None)
        if reward_system is None:
            log.debug(f"[{agent.agent_id}] No reward system — skipping breeding reward")
            return

        event = {
            'type':  'breeding',
            'tags':  ['breeding', 'social', 'bonding'],
            'payload': {
                'partner_id':  partner_id,
                'is_breeding': True,   # used by _emotion_deltas
                'success':     True,
            },
        }
        try:
            signal = reward_system.compute_reward(event)
            reward_system.apply_signal(signal)
            log.debug(
                f"[{agent.agent_id}] Breeding reward: {signal.bonding:.3f} "
                f"(total={signal.total:.3f})"
            )
        except Exception as e:
            log.warning(f"[{agent.agent_id}] Breeding reward failed: {e}")

    # ------------------------------------------------------------------
    # Tick — call every game cycle
    # ------------------------------------------------------------------

    def tick(self) -> List[Tuple[str, Any]]:
        """
        Process births and growth.  Call once per game tick.

        Returns list of (mother_id, child_agent) for each birth this tick.
        """
        births = self.update_pregnancies()
        self.update_growth()
        return births

    # ------------------------------------------------------------------
    # Pregnancies
    # ------------------------------------------------------------------

    def update_pregnancies(self) -> List[Tuple[str, Any]]:
        """Check for due births. Returns (mother_id, child_agent) pairs."""
        births = []
        now    = time.time()

        for female_id, pregnancy in list(self.pregnancies.items()):
            if now >= pregnancy.due_time:
                child = self._spawn_child(pregnancy)
                if child:
                    births.append((female_id, child))
                    log.info(f"🍼 Birth: {female_id} → {child.agent_id}")
                del self.pregnancies[female_id]

        return births

    def _spawn_child(self, pregnancy: PregnancyData):
        """Spawn the newborn agent with inherited traits."""
        child_id = f"npc_child_{int(time.time() * 1000)}"
        try:
            child = self.spawner.spawn_npc(
                agent_id    = child_id,
                persona_traits = pregnancy.child_traits,
                gender      = pregnancy.child_gender,
            )

            self.growth_stages[child_id] = time.time()

            child.metadata.update({
                'is_child':  True,
                'size':      0.5,
                'parent_a':  pregnancy.female_id,
                'parent_b':  pregnancy.male_id,
                'birth_time':time.time(),
                'gender':    pregnancy.child_gender,
            })

            # Attach breeding system to child immediately
            self.attach_to_agent(child)

            log.info(
                f"  Child {child_id}: gender={pregnancy.child_gender} | "
                f"parents={pregnancy.female_id} × {pregnancy.male_id}"
            )
            return child
        except Exception as e:
            log.error(f"Failed to spawn child: {e}")
            return None

    # ------------------------------------------------------------------
    # Growth
    # ------------------------------------------------------------------

    def update_growth(self) -> None:
        """Interpolate child size from 0.5 → 1.0 over GROWTH_DAYS MC days."""
        now             = time.time()
        growth_duration = GROWTH_DAYS * MINECRAFT_DAY_SECONDS

        for child_id, birth_time in list(self.growth_stages.items()):
            age      = now - birth_time
            progress = min(1.0, age / growth_duration)
            size     = 0.5 + 0.5 * progress

            child = self.spawner.get_agent(child_id)
            if child and hasattr(child, 'metadata'):
                child.metadata['size'] = size
                if progress >= 1.0:
                    child.metadata['is_child'] = False
                    del self.growth_stages[child_id]
                    log.info(f"🧑 {child_id} has grown to adult size")

    # ------------------------------------------------------------------
    # Trait inheritance
    # ------------------------------------------------------------------

    def _generate_child_traits(
        self,
        parent_a: Dict[str, Any],
        parent_b: Dict[str, Any],
        mutation_rate: float = 0.15,
    ) -> Dict[str, float]:
        """Blend parent traits with random weighting and mild mutation."""
        child: Dict[str, float] = {}
        for key in parent_a:
            if key == 'gender':
                continue
            val_a  = float(parent_a.get(key, 0.0))
            val_b  = float(parent_b.get(key, 0.0))
            w      = random.uniform(0.4, 0.6)
            base   = val_a * w + val_b * (1.0 - w)
            mut    = (random.random() * 2.0 - 1.0) * mutation_rate
            child[key] = max(-1.0, min(1.0, base + mut))
        return child

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def get_pregnancy_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return pregnancy info dict or None."""
        preg = self.pregnancies.get(agent_id)
        if preg is None:
            return None
        now = time.time()
        remaining = preg.due_time - now
        return {
            'female_id':        preg.female_id,
            'male_id':          preg.male_id,
            'conception_time':  preg.conception_time,
            'due_time':         preg.due_time,
            'days_remaining':   remaining / MINECRAFT_DAY_SECONDS,
            'minutes_remaining':remaining / 60,
            'child_gender':     preg.child_gender,
            'child_traits':     preg.child_traits,
        }

    def get_serialisable_pregnancy(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Return a clean serialisable dict suitable for storing in BrainCapsule.
        Uses PregnancyData.to_dict() so only stable fields are saved — no
        ephemeral fields like days_remaining that would be stale on restore.
        """
        preg = self.pregnancies.get(agent_id)
        if preg is None:
            return None
        return preg.to_dict()

    def get_growth_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Return growth info dict or None."""
        birth_time = self.growth_stages.get(agent_id)
        if birth_time is None:
            return None
        now             = time.time()
        growth_duration = GROWTH_DAYS * MINECRAFT_DAY_SECONDS
        age             = now - birth_time
        progress        = min(1.0, age / growth_duration)
        return {
            'birth_time':      birth_time,
            'age_seconds':     age,
            'age_mc_days':     age / MINECRAFT_DAY_SECONDS,
            'growth_progress': progress,
            'current_size':    0.5 + 0.5 * progress,
            'is_adult':        progress >= 1.0,
        }