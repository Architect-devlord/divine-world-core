# py_backend/utils/action_format_sync.py
"""
Action format synchronization between Python backend and Java client.

Converts between NPCAgent action arrays and the controls dict consumed by
BinaryProtocol.pack_action / dict_to_action_flags in communication_protocol.py.

Action array layout (13-dim NPC / 18-dim god)
─────────────────────────────────────────────
 0  move_forward  -1.0 … 1.0
 1  move_strafe   -1.0 … 1.0
 2  jump          > 0.5 = True
 3  sneak         > 0.5 = True
 4  attack        > 0.5 = True
 5  use           > 0.5 = True
 6  drop          > 0.5 = True
 7  open_inv      > 0.5 = True
 8  swap_hand     > 0.5 = True
 9  yaw_delta     scaled × 2.0 → degrees
10  pitch_delta   scaled × 1.2 → degrees
11  sprint        > 0.5 = True
12  hotbar_slot   > -0.5 → slot 0-8,
                  ≤ -0.5 → no change (None)

God agents add dims 13-17:
13  trigger_flag  > 0.5 → use dim 14 as ability index
14  ability_idx   0-N, maps to ability name via GOD_ABILITY_NAMES[god_type]
15  param1        float, ability-specific parameter
16  param2        float, ability-specific parameter
17  param3        float, ability-specific parameter

Wire format
───────────
Actions travel as a binary ActionFrame (DWAI magic + FRAME_ACTION = 0x02).
JSON is NOT used — the Java mod only reads the binary frame structure.
Use BinaryProtocol.pack_action() / communication_protocol.handle_agent_websocket
as the canonical send path.  Do NOT send JSON action messages to the mod.
"""

import numpy as np
from typing import Dict, Any, Optional, List


# ---------------------------------------------------------------------------
# God ability name tables — must match BaseGodEntity subclass ability lists
# (AIWither, AIEnderDragon, AIWarden, AIElderGuardian, AIOracle, AICreaking)
# Index order matches ability_idx dim 14 in the god action array.
# ---------------------------------------------------------------------------

GOD_ABILITY_NAMES: Dict[str, List[str]] = {
    "wither": [
        "wither_skull",             # 0  — 1 s CD
        "dash",                     # 1  — 3 s CD
        "summon_wither_skeletons",  # 2  — 10 s CD
        "explosion",                # 3  — 8 s CD
        "fly",                      # 4  — FIX JC-01: Java AIWither dispatches "fly"
    ],
    "ender_dragon": [
        "dragon_breath",            # 0  — 5 s CD
        "fireball",                 # 1
        "perch",                    # 2
        "fly",                      # 3  — FIX JC-01: Java AIEnderDragon dispatches "fly"
    ],
    "warden": [
        "sonic_boom",               # 0  — 5 s CD (ignores armor)
        "darkness",                 # 1  — 15 s CD
        "sniff",                    # 2  — 2 s CD
        "burrow",                   # 3
        "emerge",                   # 4
    ],
    "elder_guardian": [
        "mining_fatigue",           # 0  — 60 s CD
        "laser_beam",               # 1  — 3 s CD
        "thorn_attack",             # 2
        "guardian_spikes",          # 3  — 20 s CD
    ],
    "oracle": [
        "wisdom_aura",              # 0
        "foresight",                # 1
        "teleport",                 # 2  — 3 s CD
        "healing_wave",             # 3
        "knowledge_beam",           # 4
        "fly",                      # 5  — FIX JC-01: Java AIOracle dispatches "fly"
        # FIX: oracle's boss body is EntityType.EVOKER (GodSpawnHandler.java), but
        # every Mob god body gets setNoAi(true) unconditionally — so vanilla
        # Evoker's own SummonSpellGoal/EvokerAttackSpell (the AI Goals that would
        # normally cast these automatically in combat) never run; a Goal-based
        # behavior requires the goalSelector to tick, which setNoAi(true) stops
        # entirely. ServerGodAbilityExecutor.executeOracleAbility() already has
        # real, working "summon_vexes"/"summon_fangs" cases — this is the ONLY
        # path that can ever trigger them, and until now this list (the only
        # thing that determines what index the trained ability_idx output head
        # can even select) had no entry for either, so the policy could never
        # reach them regardless of what it output.
        #
        # Appended at the END, not inserted alongside the semantically-similar
        # abilities above — inserting mid-list would silently reassign the
        # index of every ability after the insertion point (e.g. "fly" would
        # stop being index 5), scrambling the learned index↔ability mapping
        # for any already-trained oracle policy. Appending preserves every
        # existing index exactly; only the two new slots (6, 7) are new.
        "summon_vexes",             # 6  — 10 s CD (matches ServerGodAbilityExecutor)
        "summon_fangs",             # 7  — 4 s CD  (matches ServerGodAbilityExecutor)
    ],
    "creaking": [
        "toggle_underground",       # 0
        "toggle_ceiling",           # 1
        "deploy_tentacles",         # 2
        "life_steal",               # 3
        "tentacle_whip",            # 4  — 8-block range
        # FIX (same audit category as oracle's summon_vexes/summon_fangs above):
        # ServerGodAbilityExecutor.executeCreakingAbility() has real, working
        # "retract_tentacles" and "emerge" cases — genuinely separate,
        # one-directional actions, NOT toggles: deploy_tentacles only ever
        # turns tentacles ON, retract_tentacles is the only thing that turns
        # them OFF; likewise "toggle_underground"/"burrow" only ever goes
        # DOWN — the Java code's own comments say "AI controls emerge" / "AI
        # sends this when ready to surface", confirming emerge was always
        # meant to be a deliberate, separate agent decision. Neither name
        # was in this list, so the trained ability_idx output could never
        # select either — worse than the oracle gap, since a Creaking agent
        # that burrows has NO way to voluntarily surface again: it would
        # stay underground and invulnerable indefinitely, since nothing else
        # in the pipeline calls "emerge" on its behalf.
        # Appended at the end for the same index-preservation reason as
        # oracle's fix above — see that entry's comment for the full rationale.
        "retract_tentacles",        # 5  — 2 s CD (matches ServerGodAbilityExecutor)
        "emerge",                   # 6  — no artificial CD; gated by the
                                     #      dw_burrowed state flag itself,
                                     #      same convention as "fly" (0.0 CD)
    ],
}


class ActionFormatter:
    """
    Converts NPCAgent action arrays ↔ controls dicts.

    The controls dict is the intermediate format consumed by:
      - BinaryProtocol.dict_to_action_flags()
      - ActionFrame fields (move_forward, move_strafe, yaw_delta, pitch_delta,
        action_flags, hotbar_slot, god_ability, god_params)

    This class is a utility for testing, logging, and replay only.
    Production actions flow through agent.act() → ActionFrame → pack_action().
    """

    # ── Array → controls dict ─────────────────────────────────────────────

    @staticmethod
    def npc_to_controls(action_array: np.ndarray) -> Dict[str, Any]:
        """
        Convert a 13-dim NPCAgent action array to a controls dict.

        The controls dict is directly usable as kwargs to ActionFrame and
        as input to BinaryProtocol.dict_to_action_flags().

        Clips all dims to [-1, 1] before conversion.
        """
        action = np.clip(action_array[:13], -1.0, 1.0)

        # hotbar: active when dim 12 > -0.5, maps [-0.5..1] → slots 0-8
        raw_slot = float(action[12])
        if raw_slot > -0.5:
            hotbar: Optional[int] = max(0, min(8, int(round(
                (raw_slot + 1.0) / 2.0 * 8.0
            ))))
        else:
            hotbar = None

        return {
            # Continuous movement
            'move_forward': float(action[0]),
            'move_strafe':  float(action[1]),

            # Camera rotation (degrees)
            'yaw_delta':    float(action[9]  * 2.0),
            'pitch_delta':  float(action[10] * 1.2),

            # Boolean actions
            'jump':         bool(action[2]  > 0.5),
            'sneak':        bool(action[3]  > 0.5),
            'attack':       bool(action[4]  > 0.5),
            'use':          bool(action[5]  > 0.5),
            'drop':         bool(action[6]  > 0.5),
            'open_inv':     bool(action[7]  > 0.5),
            'swap_hand':    bool(action[8]  > 0.5),
            'sprint':       bool(action[11] > 0.5),

            # Inventory
            'hotbar_slot':  hotbar,
        }

    # Alias kept for call-site compatibility with old name
    npc_to_forge = npc_to_controls

    @staticmethod
    def god_to_controls(action_array: np.ndarray,
                        god_type: str) -> Dict[str, Any]:
        """
        Convert an 18-dim god action array to a controls dict.

        Dims 0-12 are handled identically to npc_to_controls.
        Dims 13-17 are the ability trigger + params added by act_god():
          13  trigger_flag  > 0.5 → look up ability name from god_type table
          14  ability_idx   integer index into GOD_ABILITY_NAMES[god_type]
          15  param1
          16  param2
          17  param3

        If trigger_flag ≤ 0.5, 'god_ability' and 'god_params' are omitted
        from the returned dict so BinaryProtocol writes a 0-length ability
        section (no-op on the Java side).
        """
        controls = ActionFormatter.npc_to_controls(action_array)

        if len(action_array) < 18:
            import logging
            logging.getLogger("action_format_sync").warning(
                "god_to_controls: array is %d dims, expected 18. "
                "Ability dims missing — treating as no-ability frame.",
                len(action_array)
            )
            return controls

        trigger = float(np.clip(action_array[13], -1.0, 1.0))
        if trigger <= 0.5:
            return controls

        ability_names = GOD_ABILITY_NAMES.get(god_type, [])
        if not ability_names:
            import logging
            logging.getLogger("action_format_sync").warning(
                "god_to_controls: unknown god_type '%s'. "
                "No ability dispatched.", god_type
            )
            return controls

        # FIX DIM-03: GodAbilityHead.decode() outputs ability_idx as a raw integer
        # (argmax cast to float: 0.0, 1.0, 2.0, ...).  The old code treated it as
        # a continuous [-1..1] value and applied a range-mapping formula, selecting
        # the wrong ability every time. Use direct round() to recover the integer.
        raw_idx     = float(action_array[14])
        ability_idx = max(0, min(len(ability_names) - 1, int(round(raw_idx))))

        controls['god_ability'] = ability_names[ability_idx]
        controls['god_params']  = {
            'param1': float(action_array[15]),
            'param2': float(action_array[16]),
            'param3': float(action_array[17]),
        }
        return controls

    # ── Controls dict → array ─────────────────────────────────────────────

    @staticmethod
    def controls_to_npc(controls: Dict[str, Any]) -> np.ndarray:
        """
        Convert a controls dict back to a 13-dim action array.

        Useful for testing, replay recording, and imitation learning.

        hotbar_slot None → dim 12 = -1.0 (inactive sentinel)
        hotbar_slot 0-8 → dim 12 mapped back to [-0.5, 1.0]
        """
        hotbar_raw: float
        slot = controls.get('hotbar_slot')
        if slot is None:
            hotbar_raw = -1.0
        else:
            # Inverse of the forward mapping: slot 0→-0.5, slot 8→1.0
            hotbar_raw = float(slot) / 8.0 * 1.5 - 0.5

        return np.array([
            controls.get('move_forward', 0.0),
            controls.get('move_strafe',  0.0),
            1.0 if controls.get('jump',      False) else 0.0,
            1.0 if controls.get('sneak',     False) else 0.0,
            1.0 if controls.get('attack',    False) else 0.0,
            1.0 if controls.get('use',       False) else 0.0,
            1.0 if controls.get('drop',      False) else 0.0,
            1.0 if controls.get('open_inv',  False) else 0.0,
            1.0 if controls.get('swap_hand', False) else 0.0,
            controls.get('yaw_delta',   0.0) / 2.0,
            controls.get('pitch_delta', 0.0) / 1.2,
            1.0 if controls.get('sprint',    False) else 0.0,
            hotbar_raw,
        ], dtype=np.float32)

    # Alias kept for call-site compatibility with old name
    forge_to_npc = controls_to_npc

    @staticmethod
    def controls_to_god(controls: Dict[str, Any],
                        god_type: str) -> np.ndarray:
        """
        Convert a controls dict back to an 18-dim god action array.

        Inverse of god_to_controls. Dims 13-17 are reconstructed from
        'god_ability' and 'god_params' keys when present.
        """
        base = ActionFormatter.controls_to_npc(controls)
        ability_names = GOD_ABILITY_NAMES.get(god_type, [])
        god_ability   = controls.get('god_ability')

        if god_ability and ability_names and god_ability in ability_names:
            trigger    = 1.0
            idx        = ability_names.index(god_ability)
            # FIX DIM-03: ability_idx is a raw integer in the output vector, not [-1..1]
            raw_idx    = float(idx)
            god_params = controls.get('god_params') or {}
            p1 = float(god_params.get('param1', 0.0))
            p2 = float(god_params.get('param2', 0.0))
            p3 = float(god_params.get('param3', 0.0))
        else:
            trigger = -1.0
            raw_idx = -1.0
            p1 = p2 = p3 = 0.0

        return np.concatenate([
            base,
            np.array([trigger, raw_idx, p1, p2, p3], dtype=np.float32),
        ])

    # ── Action flags byte ─────────────────────────────────────────────────

    @staticmethod
    def controls_to_flags(controls: Dict[str, Any]) -> int:
        """
        Pack boolean action fields into the single-byte action_flags value
        sent inside the binary ActionFrame.

        Bit layout (matches ActionExecutor.java and communication_protocol.py):
          7 (MSB)  jump
          6        sneak
          5        attack
          4        use
          3        drop
          2        open_inv
          1        swap_hand
          0 (LSB)  sprint
        """
        flags = 0
        if controls.get('jump'):      flags |= 0b10000000
        if controls.get('sneak'):     flags |= 0b01000000
        if controls.get('attack'):    flags |= 0b00100000
        if controls.get('use'):       flags |= 0b00010000
        if controls.get('drop'):      flags |= 0b00001000
        if controls.get('open_inv'):  flags |= 0b00000100
        if controls.get('swap_hand'): flags |= 0b00000010
        if controls.get('sprint'):    flags |= 0b00000001
        return flags

    # ── Validation helpers ────────────────────────────────────────────────

    @staticmethod
    def validate_array(action_array: np.ndarray) -> bool:
        """
        Return True if the array has the expected 13-dim NPC shape.
        God arrays (18-dim) also pass (superset).
        Logs a warning for stale 11-dim arrays from old code.
        """
        import logging
        log = logging.getLogger("action_format_sync")
        n = len(action_array)
        if n < 11:
            log.error("action_array too short (%d dims); minimum is 13.", n)
            return False
        if n == 11:
            log.warning(
                "action_array is 11 dims (old layout). "
                "sprint (dim 11) and hotbar_slot (dim 12) will be missing. "
                "Update policy to output 13 dims."
            )
        if n == 12:
            log.warning(
                "action_array is 12 dims — sprint present but hotbar_slot missing."
            )
        return True

    @staticmethod
    def validate_god_ability(god_ability: str, god_type: str) -> bool:
        """
        Return True if god_ability is a known ability for this god_type.
        Logs a warning when the ability name is unrecognised (prevents silent
        no-ops where the Java side receives an unknown name and discards it).
        """
        import logging
        log = logging.getLogger("action_format_sync")
        names = GOD_ABILITY_NAMES.get(god_type)
        if names is None:
            log.warning("validate_god_ability: unknown god_type '%s'.", god_type)
            return False
        if god_ability not in names:
            log.warning(
                "validate_god_ability: '%s' is not a known ability for "
                "god_type '%s'. Known: %s", god_ability, god_type, names
            )
            return False
        return True