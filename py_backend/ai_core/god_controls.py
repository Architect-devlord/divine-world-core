# ai_core/god_controls.py
"""
God Agent Special Controls
==========================
Manages god-specific abilities and action space extension.

Design rules (aligned with brain_core / reward_system)
-------------------------------------------------------
- GodControlSystem owns ability state (cooldowns, definitions).
- Ability outcomes are evaluated through the agent's RewardSystem as
  regular events with 'god_ability' tags — NOT through a separate
  compute_god_ability_reward() function (removed).
- integrate_god_controls() no longer monkey-patches agent.act().
  Instead it:
    1. Attaches agent.god_controls = GodControlSystem(god_type)
    2. Adds agent.use_god_ability(name, **params) as a clean API
    3. Stores the extended action dim on the agent so the planner and
       policy know the god has a larger action space.
- The cognitive loop / planner call agent.use_god_ability() explicitly
  when the brain decides an ability is worth using — same deliberate
  pattern as all other decisions.
"""

import numpy as np
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

log = logging.getLogger("god_controls")


# ============================================================================
# Ability definition
# ============================================================================

@dataclass
class GodAbility:
    """A single god-specific ability with cooldown tracking."""
    name:      str
    cooldown:  float = 0.0   # seconds between uses
    last_used: float = 0.0   # timestamp of most recent use

    def is_available(self) -> bool:
        return (time.time() - self.last_used) >= self.cooldown

    def seconds_until_ready(self) -> float:
        remaining = self.cooldown - (time.time() - self.last_used)
        return max(0.0, remaining)

    def mark_used(self):
        self.last_used = time.time()


# ============================================================================
# God Control System
# ============================================================================

class GodControlSystem:
    """
    Manages the ability set for a specific god type.
    Pure data/logic — no direct agent references here.
    """

    _ABILITY_DEFS: Dict[str, Dict[str, GodAbility]] = {
        "ender_dragon": {
            "dragon_breath": GodAbility("dragon_breath", cooldown=5.0),
            "fireball":      GodAbility("fireball",      cooldown=2.0),
            "perch":         GodAbility("perch",         cooldown=0.0),
            "fly":           GodAbility("fly",           cooldown=0.0),
            "transform":     GodAbility("transform",     cooldown=5.0),
            "revert":        GodAbility("revert",        cooldown=1.0),
        },
        "dragon": {   # alias
            "dragon_breath": GodAbility("dragon_breath", cooldown=5.0),
            "fireball":      GodAbility("fireball",      cooldown=2.0),
            "perch":         GodAbility("perch",         cooldown=0.0),
            "fly":           GodAbility("fly",           cooldown=0.0),
            "transform":     GodAbility("transform",     cooldown=5.0),
            "revert":        GodAbility("revert",        cooldown=1.0),
        },
        "wither": {
            # FIX: blue_skull removed — no Java client case and no ServerGodAbilityExecutor
            # case exists for it. It was causing an index mismatch (wither idx 1 was
            # blue_skull in god_controls but dash in action_format_sync — wrong ability
            # selected on every index-1 output from the policy).
            "wither_skull":            GodAbility("wither_skull",            cooldown=1.0),
            "dash":                    GodAbility("dash",                    cooldown=3.0),
            "summon_wither_skeletons": GodAbility("summon_wither_skeletons", cooldown=10.0),
            "explosion":               GodAbility("explosion",               cooldown=8.0),
            "fly":                     GodAbility("fly",                     cooldown=0.0),
            "transform":               GodAbility("transform",               cooldown=5.0),
            "revert":                  GodAbility("revert",                  cooldown=1.0),
        },
        "warden": {
            "sonic_boom": GodAbility("sonic_boom", cooldown=5.0),
            "darkness":   GodAbility("darkness",   cooldown=15.0),
            "sniff":      GodAbility("sniff",       cooldown=0.0),
            "burrow":     GodAbility("burrow",      cooldown=10.0),
            "emerge":     GodAbility("emerge",      cooldown=0.0),
            "transform":  GodAbility("transform",   cooldown=5.0),
            "revert":     GodAbility("revert",      cooldown=1.0),
        },
        "oracle": {
            "wisdom_aura":    GodAbility("wisdom_aura",    cooldown=30.0),
            "foresight":      GodAbility("foresight",      cooldown=5.0),
            "teleport":       GodAbility("teleport",       cooldown=3.0),
            "healing_wave":   GodAbility("healing_wave",   cooldown=10.0),
            "knowledge_beam": GodAbility("knowledge_beam", cooldown=4.0),
            "fly":            GodAbility("fly",            cooldown=0.0),
            "transform":      GodAbility("transform",      cooldown=5.0),
            "revert":         GodAbility("revert",         cooldown=1.0),
            # FIX: oracle's boss body is EntityType.EVOKER, but setNoAi(true)
            # (applied unconditionally to every Mob god body — see
            # GodSpawnHandler.spawnGodBody()) stops vanilla Evoker's own
            # goalSelector-driven spell casting from ever running on its own.
            # ServerGodAbilityExecutor.executeOracleAbility() already has real
            # "summon_vexes"/"summon_fangs" cases — the only path that can ever
            # trigger them — but this dict is what gates two separate things
            # that were both silently blocking it before this fix:
            #   1. try_use()'s cooldown/existence check — without an entry
            #      here, try_use("summon_vexes") would log "Unknown ability"
            #      and refuse to even attempt it, regardless of what
            #      ServerGodAbilityExecutor.java supports.
            #   2. integrate_god_controls()'s agent.planner.add_template() loop
            #      (below), which is what makes the PLANNER consider an
            #      ability as a candidate during deliberation at all — an
            #      ability missing from this dict is invisible to planning,
            #      not just uncallable.
            # Appended at the end (after transform/revert, not grouped with
            # the other "god powers" above) for the same reason as
            # action_format_sync.py's GOD_ABILITY_NAMES["oracle"]: this dict's
            # insertion order is also this SAME class's own ability_names()
            # index space (used by encode_ability_to_action()/decode_action()
            # below) — inserting mid-dict would shift "transform"/"revert"
            # to new indices for oracle specifically, scrambling any already-
            # trained oracle policy's learned index↔ability mapping.
            # Cooldowns (10.0s / 4.0s) match ServerGodAbilityExecutor.java's
            # setCooldown(player, "summon_vexes", 200) / (..., "summon_fangs", 80)
            # exactly (200/80 ticks ÷ 20 ticks-per-second) — Python and Java
            # track cooldowns independently (dataclass timestamp vs. NBT tick
            # counter), so keeping the numbers matched is what keeps the two
            # sides from disagreeing about whether an ability is ready.
            "summon_vexes":   GodAbility("summon_vexes",   cooldown=10.0),
            "summon_fangs":   GodAbility("summon_fangs",   cooldown=4.0),
        },
        "elder_guardian": {
            "mining_fatigue":   GodAbility("mining_fatigue",   cooldown=60.0),
            "laser_beam":       GodAbility("laser_beam",       cooldown=3.0),
            "thorn_attack":     GodAbility("thorn_attack",     cooldown=5.0),
            "guardian_spikes":  GodAbility("guardian_spikes",  cooldown=20.0),
            "transform":        GodAbility("transform",        cooldown=5.0),
            "revert":           GodAbility("revert",           cooldown=1.0),
        },
        "creaking": {
            # FIX: life_steal and tentacle_whip swapped to match action_format_sync index order
            # action_format_sync: [..., "life_steal"(3), "tentacle_whip"(4)]
            # Old god_controls had tentacle_whip(3), life_steal(4) — policy selected wrong ability
            "toggle_underground": GodAbility("toggle_underground", cooldown=1.0),
            "toggle_ceiling":     GodAbility("toggle_ceiling",     cooldown=1.0),
            "deploy_tentacles":   GodAbility("deploy_tentacles",   cooldown=0.5),
            "life_steal":         GodAbility("life_steal",         cooldown=2.0),
            "tentacle_whip":      GodAbility("tentacle_whip",      cooldown=0.8),
            "transform":          GodAbility("transform",          cooldown=5.0),
            "revert":             GodAbility("revert",             cooldown=1.0),
            # FIX: same audit category as oracle's summon_vexes/summon_fangs —
            # ServerGodAbilityExecutor.executeCreakingAbility() has real,
            # working "retract_tentacles"/"emerge" cases that were reachable
            # from neither this dict nor action_format_sync.py's
            # GOD_ABILITY_NAMES["creaking"]. Missing "emerge" in particular
            # meant a burrowed Creaking agent had no voluntary way to
            # surface again — see action_format_sync.py's matching comment
            # for the full explanation. Appended after transform/revert (not
            # grouped with the other tentacle/underground abilities above)
            # for the same index-preservation reason as every other addition
            # in this dict: this class's own ability_names() insertion order
            # is also this SAME class's encode_ability_to_action()/
            # decode_action() index space.
            # Cooldowns match ServerGodAbilityExecutor.java exactly:
            # retract_tentacles = 40 ticks ÷ 20 = 2.0s. emerge has NO
            # setCooldown() call in Java at all — it's gated entirely by the
            # dw_burrowed state flag, so 0.0s here matches that (same
            # convention as "fly" elsewhere in this file: state/permission-
            # gated abilities get cooldown=0.0, not an arbitrary timer).
            "retract_tentacles":  GodAbility("retract_tentacles",  cooldown=2.0),
            "emerge":             GodAbility("emerge",             cooldown=0.0),
        },
    }

    def __init__(self, god_type: str):
        self.god_type = god_type
        template = self._ABILITY_DEFS.get(god_type, {})
        # Make fresh copies so instances don't share cooldown state
        from copy import deepcopy
        self.abilities: Dict[str, GodAbility] = deepcopy(template)

        if not self.abilities:
            log.warning(f"Unknown god_type '{god_type}' — no abilities defined")

        log.info(
            f"GodControlSystem: {god_type} "
            f"({len(self.abilities)} abilities: {list(self.abilities)})"
        )

    # ── Ability access ────────────────────────────────────────────────────

    def get_available_abilities(self) -> Dict[str, bool]:
        """Return {ability_name: is_ready} for all abilities."""
        return {name: ab.is_available() for name, ab in self.abilities.items()}

    def ability_names(self) -> list:
        return list(self.abilities.keys())

    def try_use(self, ability_name: str,
                **params) -> Optional[Dict[str, Any]]:
        """
        Attempt to activate an ability.

        Returns a command dict if the ability is ready, None if on cooldown
        or unknown.  The caller is responsible for sending the command to
        the Minecraft client AND routing the outcome through the reward system.
        """
        if ability_name not in self.abilities:
            log.warning(f"Unknown ability '{ability_name}' for {self.god_type}")
            return None

        ability = self.abilities[ability_name]
        if not ability.is_available():
            log.debug(
                f"Ability '{ability_name}' on cooldown "
                f"({ability.seconds_until_ready():.1f}s remaining)"
            )
            return None

        ability.mark_used()
        command = {"god_ability": ability_name, **params}
        log.debug(f"God ability activated: {ability_name}")
        return command

    # ── Action encoding ───────────────────────────────────────────────────

    def encode_ability_to_action(
        self,
        base_action:   np.ndarray,
        ability_name:  Optional[str]         = None,
        params:        Optional[Dict[str, float]] = None,
    ) -> np.ndarray:
        """
        Extend a base 13-dim action vector with 5 god-ability dimensions.

        FIX: was concatenating base_action[:11] + 5 god dims = 16-dim.
        GodTransformerPolicy.TOTAL_DIM = 18 (13 base + 5 god).
        Dims 11-12 are sprint/hotbar (base dims), dims 13-17 are god dims.
        Old code placed trigger at dim 11 (sprint) and ability_idx at dim 12
        (hotbar) — abilities never triggered because act_god() reads trigger
        at dim 13 and ability_idx at dim 14.

        Result shape: (18,)
        Dimensions 13-17: [trigger_flag, ability_idx, param1, param2, param3]
        """
        god_ext = np.zeros(5, dtype=np.float32)

        if ability_name and ability_name in self.abilities:
            names       = self.ability_names()
            ability_idx = names.index(ability_name)
            god_ext[0]  = 1.0                   # trigger flag  → dim 13
            god_ext[1]  = float(ability_idx)    # ability index → dim 14
            if params:
                for i, v in enumerate(list(params.values())[:3]):
                    god_ext[2 + i] = float(v)

        return np.concatenate([base_action[:13], god_ext])  # FIX: [:13] not [:11]

    def decode_action(
        self, extended_action: np.ndarray
    ) -> Optional[str]:
        """
        Decode an 18-dim god action vector back to an ability name.

        FIX: was reading trigger at dim 11 and ability_idx at dim 12.
        GodTransformerPolicy layout: dims 0-12 = base (13), dims 13-17 = god.
        Trigger is at dim 13, ability_idx at dim 14.
        """
        if len(extended_action) < 18:
            return None
        if extended_action[13] < 0.5:   # trigger flag at dim 13
            return None
        idx   = int(round(extended_action[14]))   # ability_idx at dim 14
        names = self.ability_names()
        if 0 <= idx < len(names):
            return names[idx]
        return None

    def get_params_from_action(
        self, extended_action: np.ndarray
    ) -> Dict[str, float]:
        """Extract param1/2/3 from an 18-dim action vector (dims 15-17)."""
        if len(extended_action) < 18:
            return {}
        return {
            'param1': float(extended_action[15]),
            'param2': float(extended_action[16]),
            'param3': float(extended_action[17]),
        }


# ============================================================================
# Integration
# ============================================================================

def integrate_god_controls(agent) -> None:
    """
    Attach GodControlSystem to an NPCAgent.

    What this does
    --------------
    1. Creates agent.god_controls = GodControlSystem(agent.god_type)
    2. Adds agent.use_god_ability(name, **params) — clean call-site API
       that tries the ability, sends it to Minecraft, AND routes the
       outcome through the RewardSystem so the brain learns from it.
    3. Records agent.god_action_dim = 16 so the planner/policy can
       produce the right action shape for this agent.

    What this does NOT do
    ---------------------
    - Does NOT monkey-patch agent.act() — act() still handles base 13-dim
      controls. God abilities are triggered explicitly by the cognitive loop
      or planner via agent.use_god_ability().
    """
    if not getattr(agent, 'god_type', None):
        log.warning("Cannot integrate god controls: agent has no god_type")
        return

    agent.god_controls  = GodControlSystem(agent.god_type)
    agent.god_action_dim = 18   # FIX: 13 base + 5 god extension (GodTransformerPolicy.TOTAL_DIM)

    def use_god_ability(ability_name: str,
                        outcome: Optional[Dict[str, Any]] = None,
                        **params) -> bool:
        """
        Activate a god ability and route the outcome through the reward system.

        Args:
            ability_name — name of the ability to use
            outcome      — dict of outcome data from the Minecraft mod response
                           (ability_success, ability_damage, ability_healing, etc.)
                           Pass None when firing; call again with outcome when
                           the mod responds.
            **params     — ability-specific parameters (param1, param2, param3,
                           or named: x, y, z, target, etc.)

        Returns True if the ability was activated (not on cooldown).

        NOTE: This does NOT send to minecraft_client directly.
        The ability name and params are returned in the controls dict from
        act_god(), which the ActionFrame builder in communication_protocol.py
        uses to populate god_ability / god_params in the binary frame sent
        to the mod. Sending here would cause a double-send.
        """
        command = agent.god_controls.try_use(ability_name, **params)
        if command is None:
            return False   # on cooldown or unknown

        # Route through RewardSystem so the brain learns from ability use
        if agent.reward_system is not None and outcome is not None:
            event = {
                'type':    'god_ability',
                'tags':    ['god_ability', 'action', agent.god_type],
                'payload': {
                    'ability':         ability_name,
                    'success':         outcome.get('ability_success', False),
                    'ability_damage':  outcome.get('ability_damage',  0.0),
                    'ability_healing': outcome.get('ability_healing', 0.0),
                    'surprise_attack': outcome.get('surprise_attack', False),
                    **params,
                },
            }
            signal = agent.reward_system.compute_reward(event=event, outcome=outcome)
            agent.reward_system.apply_signal(signal)

            agent.memory.remember({
                'type':     'god_ability_used',
                'ability':  ability_name,
                'god_type': agent.god_type,
                'outcome':  outcome,
                'reward':   signal.total,
            }, tags=['god_ability', 'action', 'learning'])

        return True

    agent.use_god_ability = use_god_ability

    # Add god abilities as planner action templates so deliberation can
    # consider them alongside regular actions
    if hasattr(agent, 'planner') and agent.planner is not None:
        for ability_name in agent.god_controls.ability_names():
            agent.planner.add_template({
                'type':    'god_ability',
                'ability': ability_name,
            })

    log.info(
        f"God controls integrated for {agent.god_type} "
        f"({len(agent.god_controls.abilities)} abilities)"
    )