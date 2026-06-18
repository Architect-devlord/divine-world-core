# py_backend/ai_core/los_filter.py
"""
Line-of-Sight Filtering for Entity Perception
================================================
The agent should not "know" the relative position of a mob, player, or other
agent it cannot actually see. This module filters world_state['nearby_entities']
before obs_builder converts it into the observation vector.

Authoritative path (recommended)
---------------------------------
The Java mod has full world geometry and can raycast cheaply via
`Level.clip()` / `ClipContext`, or a simple `LivingEntity`-to-target check.
If each entity dict in the perception payload carries an explicit boolean
flag — any of 'los', 'in_los', or 'visible' — this module trusts it
unconditionally. This is the only way to get *correct* long-range occlusion,
since Python only ever receives whatever the Java side chooses to send.

Recommended Java-side addition (sketch, not wired by this module):

    public static boolean hasLineOfSight(LivingEntity viewer, Entity target) {
        Vec3 eye = viewer.getEyePosition();
        Vec3 aim = target.getPosition(1.0f).add(0, target.getBbHeight() * 0.5, 0);
        ClipContext ctx = new ClipContext(eye, aim,
            ClipContext.Block.COLLIDER, ClipContext.Fluid.NONE, viewer);
        BlockHitResult hit = viewer.level().clip(ctx);
        return hit.getType() == HitResult.Type.MISS;
    }

    // When serialising nearby_entities for the perception frame:
    entityJson.addProperty("los", hasLineOfSight(self, target));

Fallback path (best-effort, Python-only)
------------------------------------------
When no explicit flag is present, this module passes entities through
UNFILTERED rather than guessing. Reasoning: the only block data available
on the Python side at this point is the agent's own 3x3x3 immediate
neighbourhood (touch range), which is far too small to test occlusion for
anything beyond a couple of blocks away. A geometric fallback built on that
data would be wrong far more often than it's right, and — critically — it
would fail *closed*, silently blinding the agent to entities in plain sight
any time the Java mod hasn't been updated yet. Passing through is the more
honest default until the authoritative flag exists; once Java sends it,
filtering activates automatically with no further Python changes needed.
"""

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("los_filter")

_LOS_KEYS = ('los', 'in_los', 'visible')

_warned_once = False


def filter_entities_by_los(entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return only entities the agent can actually see.

    Each entity dict is checked for an explicit LOS flag (los / in_los /
    visible). If ANY entity in the list carries one of these keys, the whole
    list is treated as LOS-aware and entities without a truthy flag are
    dropped. If NONE of the entities carry any such key (Java side not yet
    updated), the list passes through unchanged — see module docstring.
    """
    global _warned_once
    if not entities:
        return entities

    has_flag_data = any(
        any(k in ent for k in _LOS_KEYS) for ent in entities
    )

    if not has_flag_data:
        if not _warned_once:
            log.debug(
                "No LOS flag found on nearby_entities — passing through "
                "unfiltered. Add a 'los' boolean per entity on the Java side "
                "for real occlusion filtering (see los_filter.py docstring)."
            )
            _warned_once = True
        return entities

    visible = []
    for ent in entities:
        flag = None
        for k in _LOS_KEYS:
            if k in ent:
                flag = bool(ent[k])
                break
        if flag:
            visible.append(ent)
    return visible


def filter_blocks_by_los(
    blocks: List[Any],
    max_range_without_data: float = 1.8,
) -> List[Any]:
    """
    Return only blocks the agent can see.

    Practically a no-op for the obs_builder's 3x3x3 immediate-neighbourhood
    block grid: every block in that grid is within touching distance, which
    is proprioceptive (you feel the ground under you, the wall you're pressed
    against) rather than visual — LOS doesn't meaningfully apply at that range.

    If individual block dicts carry position data ('pos'/'position'/
    'rel_dx' etc.) AND an explicit LOS flag, this still respects it — for
    forward-compatibility with any future wider block scan. Otherwise it
    passes everything through unchanged.
    """
    if not blocks:
        return blocks

    if not isinstance(blocks[0], dict):
        # Bare type ids / (type, hardness) tuples carry no position info at
        # all — nothing to filter on, pass through.
        return blocks

    has_flag_data = any(
        any(k in b for k in _LOS_KEYS) for b in blocks if isinstance(b, dict)
    )
    if not has_flag_data:
        return blocks

    return [
        b for b in blocks
        if not isinstance(b, dict) or any(
            bool(b[k]) for k in _LOS_KEYS if k in b
        )
    ]