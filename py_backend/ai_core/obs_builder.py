# py_backend/ai_core/obs_builder.py
"""
Phase 6 — Observation Space (128-dim)
=======================================
Replaces the old 50-dim placeholder in agent.perceive() and the old 256-dim
draft of this same file. Read the governing principle before changing
anything here:

    The agent learns what things are by what they lead to. It does not
    receive labels, type tags, hostility flags, or social annotations.
    It receives physics. Reward — via GRPO and the WorldModel's surprise
    signal — is the only teacher.

Concretely, this means the entity block carries distance/relative-position/
speed and NOTHING else (no is_hostile, no type_bucket, no health_norm); the
block-neighbourhood carries only a type id (no hardness — that's felt through
mining outcomes); and there is NO social-context block at all (no
n_agents_nearby, no trust_avg, no oracle_nearby). If you're about to add any
of those back, stop — read the plan doc this file was built from first.

Usage:
    from ai_core.obs_builder import build_observation, OBS_DIM
    obs = build_observation(agent, world_state)   # → np.ndarray shape (128,)

Dimension map (each dimension earns its place — no padding):
    [  0 –   7]  Vitals (8)
                 health/20, hunger/20, oxygen/20, armor/20, exp_level/100,
                 fire_ticks/80, is_child, breeding_cooldown_norm
    [  8 –  14]  Position + orientation (7)
                 x%512/512, y/256, z%512/512, yaw/360, (pitch+90)/180,
                 on_ground, in_water
    [ 15 –  22]  Environment (8)
                 time_of_day/24000, moon_phase/8, is_raining, is_thundering,
                 light_level/15, biome_bucket/30, temperature, humidity
    [ 23 –  49]  Block neighbourhood 3×3×3 (27) — type_bucket/27 only
    [ 50 –  85]  Inventory (36) — 18 slots × (item_id%200/200, count/64)
    [ 86 – 105]  Nearby entities (20) — 4 entities × 5:
                 (distance/32, rel_dx/32, rel_dy/20, rel_dz/32,
                  movement_speed/10) — LOS-filtered before encoding
    [106 – 115]  Emotions (10)
    [116 – 125]  Memory recency (10) — exponential decay, half-life 60s
    [126 – 127]  Language stage (2) — vocabulary_size/5000, language_stage/5

Total: 128 dims.
"""

import time as _time
import numpy as np
from typing import Dict, Any, List

from ai_core.los_filter import filter_entities_by_los, filter_blocks_by_los

OBS_DIM            = 128
BLOCK_TYPE_BUCKETS = 27
N_TRACKED_ENTITIES = 4
N_INVENTORY_SLOTS  = 18

# Ordered emotion keys — must match EmotionSystem.snapshot() keys
EMOTION_KEYS = [
    'joy', 'fear', 'anger', 'sadness', 'curiosity',
    'trust', 'surprise', 'frustration', 'disgust', 'anticipation',
]

# Memory event types to track recency for (10 — fills [116:126])
MEMORY_EVENT_TYPES = [
    'chat_heard', 'entity_seen', 'block_broken', 'item_used',
    'combat', 'death', 'breeding_event', 'trade', 'sleep', 'crafting',
]


def build_observation(agent, world_state: Dict[str, Any]) -> np.ndarray:
    """
    Build the canonical 128-dim observation vector for this agent.

    All values normalised to [0,1] (a few signed/centred terms reach
    [-1,1]). Missing data falls back to neutral defaults rather than raising
    — the Java/perception side populating every field is a separate,
    ongoing effort; this function must degrade gracefully in the meantime.
    """
    obs = np.zeros(OBS_DIM, dtype=np.float32)
    idx = 0

    # ── [0–7] Vitals ────────────────────────────────────────────────────
    obs[0] = _clip01(agent.health / 20.0)
    obs[1] = _clip01(agent.hunger / 20.0)
    obs[2] = _clip01(world_state.get('oxygen',    20) / 20.0)
    obs[3] = _clip01(world_state.get('armor',      0) / 20.0)
    obs[4] = _clip01(world_state.get('exp_level',  0) / 100.0)
    obs[5] = _clip01(world_state.get('fire_ticks', 0) / 80.0)
    # is_child / breeding_cooldown_norm: biological intrinsic state, not a
    # social signal — lives in vitals, not in any (removed) social block.
    obs[6] = float(bool(world_state.get('is_child', False)))
    obs[7] = _clip01(world_state.get('breeding_cooldown_norm', 0.0))
    idx = 8

    # ── [8–14] Position + orientation ──────────────────────────────────
    pos = world_state.get('position', {})
    obs[idx]   = _clip01((pos.get('x', 0) % 512) / 512.0)
    obs[idx+1] = _clip01(pos.get('y', 64) / 256.0)
    obs[idx+2] = _clip01((pos.get('z', 0) % 512) / 512.0)
    obs[idx+3] = _clip01(pos.get('yaw',    0) / 360.0)
    obs[idx+4] = _clip01((pos.get('pitch', 0) + 90) / 180.0)
    obs[idx+5] = float(bool(world_state.get('on_ground', True)))
    obs[idx+6] = float(bool(world_state.get('in_water',  False)))
    idx += 7

    # ── [15–22] Environment ────────────────────────────────────────────
    obs[idx]   = _clip01(world_state.get('time_of_day',  0) / 24000.0)
    obs[idx+1] = _clip01(world_state.get('moon_phase',   0) / 8.0)
    obs[idx+2] = float(bool(world_state.get('is_raining',    False)))
    obs[idx+3] = float(bool(world_state.get('is_thundering', False)))
    obs[idx+4] = _clip01(world_state.get('light_level',  15) / 15.0)
    obs[idx+5] = _clip01(world_state.get('biome_bucket',  0) / 30.0)
    obs[idx+6] = _clip01(world_state.get('temperature', 0.5))
    obs[idx+7] = _clip01(world_state.get('humidity',    0.5))
    idx += 8

    # ── [23–49] Block neighbourhood 3×3×3 (27 blocks × 1 dim) ───────────
    # type_bucket only — no hardness. Hardness is felt through mining
    # outcomes (reward), not pre-given in perception.
    blocks = filter_blocks_by_los(world_state.get('nearby_blocks', []))
    for i in range(27):
        if i < len(blocks):
            obs[idx] = _block_type_bucket(blocks[i]) / BLOCK_TYPE_BUCKETS
        idx += 1

    # ── [50–85] Inventory (18 slots × 2 dims) ───────────────────────────
    inventory: List = world_state.get('inventory', [])
    for i in range(N_INVENTORY_SLOTS):
        if i < len(inventory):
            item_id, count = _unpack_inventory_slot(inventory[i])
            obs[idx]   = (item_id % 200) / 200.0
            obs[idx+1] = _clip01(count / 64.0)
        idx += 2

    # ── [86–105] Nearby entities (4 × 5 physical dims) ──────────────────
    # Physics only: distance + relative offset + speed. No is_hostile, no
    # type_bucket, no health_norm — the agent infers meaning from reward,
    # it is not told what anything "is". LOS-filtered before encoding so an
    # entity behind a wall contributes nothing (see los_filter.py).
    entities = filter_entities_by_los(world_state.get('nearby_entities', []))
    # Closest first so the 4 observed slots are stable across ticks.
    entities = sorted(entities, key=lambda e: e.get('distance', 999.0))[:N_TRACKED_ENTITIES]
    for i in range(N_TRACKED_ENTITIES):
        if i < len(entities):
            ent = entities[i]
            obs[idx]   = _clip01(ent.get('distance', 32.0) / 32.0)
            obs[idx+1] = _centered(ent.get('rel_dx', 0.0), 32.0)
            obs[idx+2] = _centered(ent.get('rel_dy', 0.0), 20.0)
            obs[idx+3] = _centered(ent.get('rel_dz', 0.0), 32.0)
            obs[idx+4] = _clip01(ent.get('movement_speed', 0.0) / 10.0)
        idx += 5

    # ── [106–115] Emotions ───────────────────────────────────────────────
    emotions = _safe_emotions(agent)
    for key in EMOTION_KEYS:
        obs[idx] = float(np.clip(emotions.get(key, 0.0), -1.0, 1.0))
        idx += 1

    # ── [116–125] Memory recency ─────────────────────────────────────────
    now         = _time.time()
    recency_map = _compute_recency(agent, now)
    for etype in MEMORY_EVENT_TYPES:
        obs[idx] = recency_map.get(etype, 0.0)
        idx += 1

    # ── [126–127] Language stage ─────────────────────────────────────────
    lang = getattr(getattr(agent, 'brain', None), 'language', None)
    if lang is not None:
        obs[idx]   = _clip01(getattr(lang, 'vocabulary_size', 0) / 5000.0)
        obs[idx+1] = _clip01(getattr(lang, 'language_stage',  0) / 5.0)
    idx += 2

    assert idx == OBS_DIM, f"obs_builder index drift: ended at {idx}, expected {OBS_DIM}"

    return obs


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _clip01(v: float) -> float:
    return float(np.clip(v, 0.0, 1.0))


def _centered(v: float, scale: float) -> float:
    """Map a signed relative offset to [-1, 1] by dividing by scale and clipping."""
    return float(np.clip(v / scale, -1.0, 1.0))


def _block_type_bucket(block: Any) -> float:
    """
    Accept any of: bare int type id, (type, hardness) tuple (legacy Java
    wire format — hardness discarded), or {'type': ...} dict.
    """
    if isinstance(block, dict):
        return float(block.get('type', block.get('type_bucket', 0)))
    if isinstance(block, (tuple, list)):
        return float(block[0]) if block else 0.0
    try:
        return float(block)
    except (TypeError, ValueError):
        return 0.0


def _unpack_inventory_slot(slot: Any):
    """Accept (item_id, count) tuple or {'item_id':..,'count':..} dict."""
    if isinstance(slot, dict):
        return slot.get('item_id', 0), slot.get('count', 0)
    if isinstance(slot, (tuple, list)) and len(slot) >= 2:
        return slot[0], slot[1]
    return 0, 0


def _safe_emotions(agent) -> dict:
    try:
        return agent.emotion.snapshot()
    except Exception:
        return {}


def _compute_recency(agent, now: float) -> dict:
    """
    For each tracked event type, compute a recency score in [0, 1].
    1.0 = happened very recently, 0.0 = never / very long ago.
    Decays exponentially with a 60-second half-life.

    'chat_heard' is kept here deliberately: this is internal bookkeeping of
    a detectable audio-pattern event, not a social annotation. The agent
    does not "know" it's chat — it only knows a vocalisation-like pattern
    occurred recently. Meaning arrives later, through reward correlation.
    """
    result = {etype: 0.0 for etype in MEMORY_EVENT_TYPES}
    try:
        events = getattr(agent.memory, 'events', [])
        for event in reversed(list(events)[-200:]):
            etype = event.get('type', '')
            if etype in result and result[etype] == 0.0:
                ts  = event.get('timestamp', now - 999)
                age = max(0.0, now - ts)
                result[etype] = float(np.exp(-age / 60.0))
    except Exception:
        pass
    return result