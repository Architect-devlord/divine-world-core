# ai_core/brain_core.py
"""
BrainCore — Central Intelligence for DW Agents
===============================================

The brain sits between raw perception and action. It is responsible for:

  1. Fast evaluation  — routine intuitive response via RewardSystem +
                        PatternRecognizer + learned value table. This runs
                        every cognitive cycle. No world model involved.

  2. Selective deliberation — expensive imagination via the WorldModel.
                        The brain decides WHEN deliberation is worth it
                        (novelty, urgency, stakes) and exposes the result
                        to the cognitive loop, which decides WHAT to do
                        with it. The world model is a tool the agent
                        reaches for, not a mandatory pipeline stage.

  3. Language          — routes to LanguageIntelligence for input processing
                        and speech generation.

  4. Continual memory  — stores experiences for Avalanche-style replay.

Design rules
------------
- BrainCore owns its world model connection via set_world_model().
  Nobody patches brain.evaluate_event from outside.
- evaluate_event() is always fast. Never blocks on torch.
- deliberate() is always explicit. The cognitive loop calls it only when
  it has decided the situation warrants deep thought.
- GodBrainExtension is removed. Gods use the same brain — their
  personality weights and reward system configuration make them different.
- PatternRecognizer.observe_pattern uses time() correctly (not time.time()).
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict, deque
from time import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

log = logging.getLogger("brain_core")


def _action_to_vector(action: Dict[str, Any], action_dim: int) -> np.ndarray:
    """
    Encode a candidate action dict as a vector for the world model / GRPO.

    Discovered skills (from EmergentSkillPool) carry their own centroid
    in 'action_vector' — a real point in action space, not restricted to
    a one-hot basis direction. Hand-authored templates (DEFAULT_TEMPLATES,
    god abilities) have no 'action_vector' and fall back to the original
    ACTION_TYPE_INDEX one-hot encoding, unchanged from before this fix.
    """
    raw = action.get('action_vector')
    if raw is not None:
        vec = np.asarray(raw, dtype=np.float32).reshape(-1)[:action_dim]
        if vec.shape[0] < action_dim:
            vec = np.pad(vec, (0, action_dim - vec.shape[0]))
        return vec

    from ai_core.planner import ACTION_TYPE_INDEX
    vec = np.zeros(action_dim, dtype=np.float32)
    idx = ACTION_TYPE_INDEX.get(action.get('type', ''), 0) % action_dim
    vec[idx] = 1.0
    return vec


# ============================================================================
# PatternRecognizer
# ============================================================================

class PatternRecognizer:
    """
    Lightweight online pattern tracker.

    Records observations by type, tracks transition frequencies, and
    computes novelty (inverse frequency). Thread-safe via a single lock.

    Pattern types: behavior | visual | audio | language | state
    """

    def __init__(self, pattern_types: Optional[List[str]] = None):
        if pattern_types is None:
            pattern_types = ['behavior', 'visual', 'audio', 'language', 'state']

        self.pattern_types   = pattern_types
        # {type: {hash: [count, last_seen_ts, context]}}
        self.patterns        = {pt: {} for pt in pattern_types}
        # {type: {(prev_hash, next_hash): count}}
        self.transitions     = {pt: defaultdict(int) for pt in pattern_types}
        # {type: deque of recent hashes}
        self.recent_patterns = {pt: deque(maxlen=10) for pt in pattern_types}

        self._lock = threading.Lock()

    # ── public ──────────────────────────────────────────────────────────────

    def observe_pattern(self, pattern_type: str,
                        pattern_data: Any,
                        context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Record an observation and return analysis.

        Returns:
            novelty         — 1.0 = never seen before, approaches 0 as freq grows
            frequency       — how many times this exact pattern has been seen
            related_patterns — list of hashes that commonly co-occur
            pattern_hash    — the hash used internally
        """
        if pattern_type not in self.pattern_types:
            return {'novelty': 0.0, 'frequency': 0,
                    'related_patterns': [], 'pattern_hash': ''}

        h = self._hash_pattern(pattern_data)

        with self._lock:
            store = self.patterns[pattern_type]

            if h not in store:
                # [count, last_seen, context]
                store[h] = [0, time(), context or {}]
                novelty = 1.0
            else:
                novelty = 1.0 / (1.0 + store[h][0])

            store[h][0] += 1
            store[h][1]  = time()       # ← correct: time() not time.time()
            freq         = store[h][0]

            recent = self.recent_patterns[pattern_type]
            if len(recent) >= 2:
                prev = list(recent)[-1]
                self.transitions[pattern_type][(prev, h)] += 1
            recent.append(h)

            related = self._related(pattern_type, h)

        return {
            'novelty':          novelty,
            'frequency':        freq,
            'related_patterns': related,
            'pattern_hash':     h,
        }

    def get_novelty(self, pattern_type: str, pattern_data: Any) -> float:
        """
        Read-only novelty check — does NOT record an observation.
        Safe to call from evaluate_event without double-counting.
        """
        if pattern_type not in self.pattern_types:
            return 0.0
        h = self._hash_pattern(pattern_data)
        with self._lock:
            entry = self.patterns[pattern_type].get(h)
        if entry is None:
            return 1.0
        return 1.0 / (1.0 + entry[0])

    def predict_next_pattern(self, pattern_type: str) -> Optional[str]:
        """Return the most likely next pattern hash given the current one."""
        with self._lock:
            recent = self.recent_patterns.get(pattern_type)
            if not recent:
                return None
            cur   = list(recent)[-1]
            cands = {
                n: c
                for (p, n), c in self.transitions[pattern_type].items()
                if p == cur
            }
        return max(cands, key=cands.get) if cands else None

    def get_pattern_stats(self, pattern_type: str) -> Dict[str, Any]:
        if pattern_type not in self.pattern_types:
            return {}
        with self._lock:
            store      = self.patterns[pattern_type]
            total_obs  = sum(p[0] for p in store.values())
            frequent   = sorted(store.items(),
                                key=lambda x: x[1][0], reverse=True)[:10]
        return {
            'total_unique_patterns': len(store),
            'total_observations':    total_obs,
            'most_frequent': [
                {'hash': h[:50], 'count': d[0]} for h, d in frequent
            ],
        }

    # ── private ─────────────────────────────────────────────────────────────

    def _hash_pattern(self, data: Any) -> str:
        # FIX Step 2a: old impl joined rounded-float strings / sorted key:value
        # pairs — distinct arrays/dicts with similar shapes routinely collided,
        # corrupting the novelty signal that gates all deliberation.
        import hashlib, json
        return hashlib.md5(
            json.dumps(data, sort_keys=True, default=str).encode()
        ).hexdigest()

    def _related(self, pt: str, h: str, limit: int = 5) -> List[str]:
        rel = []
        for (p, n), c in self.transitions[pt].items():
            if p == h or n == h:
                other = n if p == h else p
                if other != h:
                    rel.append((other, c))
        rel.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in rel[:limit]]


# ============================================================================
# DeliberationResult
# ============================================================================

class DeliberationResult:
    """
    Output of BrainCore.deliberate().

    Contains ranked action candidates with their imagined values, plus
    metadata the cognitive loop can use to decide whether to interrupt
    a running plan.
    """

    def __init__(self,
                 ranked_actions: List[Tuple[float, Dict[str, Any]]],
                 imagination_summaries: List[Dict[str, Any]],
                 context_novelty: float,
                 context_urgency: float,
                 used_world_model: bool,
                 all_scored_actions: Optional[List[Tuple[float, np.ndarray]]] = None):
        # [(score, action_dict), ...] — highest score first
        self.ranked_actions        = ranked_actions
        # One summary dict per imagined trajectory (from ImagineResult.summary())
        self.imagination_summaries = imagination_summaries
        self.context_novelty       = context_novelty
        self.context_urgency       = context_urgency
        self.used_world_model      = used_world_model
        # FIX Step 2c: GRPO needs [(score, action_ndarray), ...] — ranked_actions
        # holds dicts, not arrays, so a dedicated field is required. Populated
        # by _deliberate_with_world_model() / _deliberate_with_table() using the
        # same one-hot ACTION_TYPE_INDEX encoding already used for imagination.
        self.all_scored_actions: List[Tuple[float, np.ndarray]] = (
            all_scored_actions if all_scored_actions is not None else []
        )

    @property
    def best_action(self) -> Optional[Dict[str, Any]]:
        """The highest-scored action candidate (dict form) — used by the
        planner/cognitive-loop plan-splicing flow (_execute_action)."""
        if self.ranked_actions:
            return self.ranked_actions[0][1]
        return None

    @property
    def best_action_vector(self) -> Optional[np.ndarray]:
        """
        The highest-scored action as a raw numpy vector — used by SkillTracker
        to compute MSE against the agent's own attempt (fully self-referential,
        no external teacher). all_scored_actions is sorted in the same order
        as ranked_actions, so index 0 is always the top trial.
        """
        if self.all_scored_actions:
            return self.all_scored_actions[0][1]
        return None

    @property
    def best_score(self) -> float:
        if self.ranked_actions:
            return self.ranked_actions[0][0]
        return 0.0

    def should_abort_current_plan(self,
                                  running_plan_score: float,
                                  urgency_threshold: float = 0.75) -> bool:
        """
        Returns True if the cognitive loop should abandon its current plan
        and switch to the best action found here.

        Conditions:
          - Urgency spiked above threshold (danger, starvation, etc.)
          - A significantly better option was found (>20% improvement)
        """
        if self.context_urgency >= urgency_threshold:
            return True
        if self.best_score > running_plan_score * 1.2:
            return True
        return False

    def summary(self) -> Dict[str, Any]:
        return {
            'best_action':       self.best_action,
            'best_score':        self.best_score,
            'n_candidates':      len(self.ranked_actions),
            'used_world_model':  self.used_world_model,
            'context_novelty':   self.context_novelty,
            'context_urgency':   self.context_urgency,
            'top_3': [
                {'score': s, 'action': a.get('type')}
                for s, a in self.ranked_actions[:3]
            ],
        }


# ============================================================================
# BrainCore
# ============================================================================

class BrainCore:
    """
    Central intelligence hub.

    Wiring
    ------
    After construction, call:
        brain.set_world_model(wm)     — attach WorldModel (optional)
        brain.set_reward_system(rs)   — attach RewardSystem (optional,
                                         also done by agent.initialize_reward_system)

    Both can be swapped at runtime without restarting the agent.
    """

    def __init__(self, agent_ref=None):
        self.agent  = agent_ref

        # ── Sub-systems (wired after construction) ───────────────────────
        self.reward_system: Any   = None   # RewardSystem
        self._world_model:  Any   = None   # WorldModel (private — use property)
        self._wm_lock               = threading.Lock()

        # ── Fast evaluation systems ──────────────────────────────────────
        # value_table: {(event_type, first_tag): [cumulative_reward, count]}
        self.value_table: Dict[Tuple, List] = {}
        # forward_model: {action_type: {outcome_tag: probability}}
        self.forward_model: Dict[str, Dict[str, float]] = {}

        self.curiosity_weight      = 0.5
        self.predictability_weight = 0.2

        self.pattern_recognizer = PatternRecognizer()

        # ── Language ────────────────────────────────────────────────────
        # Initialised by add_language_to_brain() in NPCAgent._init_language(),
        # called right after BrainCore() is constructed.
        # FIX: this used to ALSO eagerly construct a LanguageIntelligence
        # here, contradicting its own comment — every agent spawn built two
        # full instances (duplicate transformer, tokenizer, AdamW optimizer)
        # since add_language_to_brain() unconditionally overwrites
        # self.language with a second one moments later in __init__ and the
        # first was simply discarded, wasted construction cost on every
        # single agent. Left as None here; add_language_to_brain() is the
        # sole, authoritative construction path, matching what the comment
        # already said it should be.
        self.language: Any = None

        # ── Continual learning buffer ────────────────────────────────────
        self.continual_buffer: deque = deque(maxlen=10_000)
        self.task_labels: Dict[int, float] = {}
        self.current_task: int = 0

        # ── Deliberation settings ────────────────────────────────────────
        self.deliberation_novelty_threshold: float = 0.55
        self.deliberation_urgency_threshold: float = 0.60
        self.deliberation_cooldown: float          = 2.0
        self._last_deliberation_ts: float          = 0.0

        # ── Browsing settings ─────────────────────────────────────────────
        # Minimum browse_desire score before the agent considers browsing
        self.browsing_desire_threshold: float = 0.40
        # Minimum seconds between autonomous browsing sessions
        self.browsing_cooldown: float         = 60.0

        log.info("BrainCore initialised.")

    # ── World model property (thread-safe swap) ──────────────────────────

    @property
    def world_model(self):
        with self._wm_lock:
            return self._world_model

    @world_model.setter
    def world_model(self, wm):
        with self._wm_lock:
            self._world_model = wm

    def set_world_model(self, wm) -> None:
        """
        Attach a WorldModel to the brain.

        This is the ONLY sanctioned way to wire in the world model.
        No external monkey-patching of evaluate_event is needed or allowed.
        """
        self.world_model = wm
        log.info(f"BrainCore: WorldModel attached "
                 f"({'with VAE' if getattr(wm, 'config', None) and wm.config.use_vae else 'no VAE'}).")

    def set_reward_system(self, rs) -> None:
        """Attach a RewardSystem. Also called by agent.initialize_reward_system()."""
        self.reward_system = rs
        log.info("BrainCore: RewardSystem attached.")

    # =========================================================================
    # FAST PATH — evaluate_event
    # =========================================================================

    def evaluate_event(self,
                       event: Dict[str, Any],
                       context: Optional[Dict] = None
                       ) -> Tuple[float, Dict[str, float]]:
        """
        Fast intuitive evaluation of an event.

        Routes through RewardSystem when available (full personality-weighted
        scoring, emotion updates, curiosity signals). Falls back to the
        table-based scorer otherwise.

        This method NEVER touches the world model. Keep it fast.

        Returns:
            (reward: float, emotion_delta: dict)

        When RewardSystem is attached:
            emotion_delta is {} — apply_signal() already updated emotion_system
            and personality. Callers must NOT apply emotion_delta again.

        When RewardSystem is NOT attached (table fallback):
            emotion_delta contains raw deltas for the caller to apply.
        """
        # ── RewardSystem path ─────────────────────────────────────────────
        if self.reward_system is not None:
            try:
                # FIX: pass obs/action tensors so RND and ICM curiosity modules
                # actually compute intrinsic rewards.  Without them, raw_curiosity
                # is always 0.0 — the agent has no intrinsic motivation from
                # brain-level events (chat, sound, vision observations).
                # We pull the agent's last cached obs when available.
                obs_t    = None
                action_t = None
                if self.agent is not None:
                    last_obs = getattr(self.agent, 'last_obs', None)
                    if last_obs is not None:
                        try:
                            import torch as _torch
                            obs_t = _torch.tensor(
                                last_obs, dtype=_torch.float32
                            ).unsqueeze(0)
                        except Exception:
                            pass
                    last_act = getattr(self.agent, 'last_action', None)
                    if last_act is not None and obs_t is not None:
                        try:
                            import torch as _torch
                            action_t = _torch.tensor(
                                last_act, dtype=_torch.float32
                            ).unsqueeze(0)
                        except Exception:
                            pass

                signal = self.reward_system.compute_reward(
                    event=event,
                    obs=obs_t,
                    action=action_t,
                    outcome=context or {},
                )
                self.reward_system.apply_signal(signal)
                self._update_learning(event, event.get('payload', {}), signal.total)
                self._store_continual_experience(event, signal.total, context)
                return signal.total, {}
            except Exception as e:
                log.warning(f"RewardSystem failed, falling back to table: {e}")

        # ── Table fallback ────────────────────────────────────────────────
        try:
            payload      = event.get('payload', {})
            pattern_type = self._classify_event_pattern_type(event)
            analysis     = self.pattern_recognizer.observe_pattern(
                pattern_type, event, context
            )
            novelty = analysis['novelty']
            reward  = (
                self._drive_reward(payload)
                + self.curiosity_weight * novelty
                + self._lookup_learned_value(event)
                - self.predictability_weight * self._prediction_error(event)
                + (0.1 if novelty > 0.7 else 0.0)
            )
        except Exception:
            return 0.0, {'surprise': 0.1}

        emo_delta = {
            'joy':      max(0.0,  reward) * 0.2,
            'fear':     max(0.0, -reward) * 0.3,
            'surprise': novelty * 0.2,
        }
        self._update_learning(event, event.get('payload', {}), reward)
        self._store_continual_experience(event, reward, context)
        return reward, emo_delta

    # =========================================================================
    # DELIBERATION GATE — should the agent think deeply right now?
    # =========================================================================

    def should_deliberate(self,
                          novelty: float,
                          urgency: float,
                          force: bool = False) -> bool:
        """
        Decide whether a full world-model deliberation is worth running.

        Called by the cognitive loop before invoking deliberate().
        Returns False quickly when the world model is absent, on cooldown,
        or the situation is routine.

        Args:
            novelty  — 0–1, from cognitive loop perception
            urgency  — 0–1, from cognitive loop perception
            force    — skip cooldown check (e.g. explicit planning request)
        """
        if self.world_model is None:
            return False

        # Rate limit — don't deliberate on every cycle
        if not force:
            since_last = time() - self._last_deliberation_ts
            if since_last < self.deliberation_cooldown:
                return False

        # Situation must be interesting enough
        if (novelty >= self.deliberation_novelty_threshold or
                urgency >= self.deliberation_urgency_threshold):
            return True

        return False

    # =========================================================================
    # BROWSING GATE — should the agent look something up on the web?
    # =========================================================================

    def should_browse(self,
                      novelty:  float,
                      urgency:  float,
                      context:  Optional[Dict] = None) -> bool:
        """
        Decide whether the agent wants to browse the web right now.

        This is the agent's own decision — not the user's. The brain weighs
        personality (curiosity, openness), situation (novelty, urgency), and
        how recently it last browsed. It does NOT check whether there are URLs
        in the queue — that is the cognitive loop's job after this returns True.

        Args:
            novelty  — 0–1 from perception (new situations spark curiosity)
            urgency  — 0–1, high urgency suppresses idle browsing
            context  — optional dict with 'recent_events' for memory check

        Returns True only when:
            - The agent has web browsing attached
            - Curiosity + situation cross a threshold
            - Browsing cooldown has elapsed
            - The situation is not urgent enough to demand action instead
        """
        # No browser attached
        if self.agent is None or not hasattr(self.agent, 'web_browser'):
            return False

        browser = self.agent.web_browser
        # No allowed domains — browsing is not permitted
        if not browser.allowed_domains:
            return False

        # Urgent situations demand action, not browsing
        if urgency > 0.70:
            return False

        # Browsing cooldown (don't browse more than once per 60s autonomously)
        since_last = time() - browser.stats.get('last_browse_time', 0.0)
        if since_last < self.browsing_cooldown:
            return False

        # Personality-weighted curiosity score
        traits    = {}
        if self.agent is not None and hasattr(self.agent, 'personality'):
            traits = self.agent.personality.traits

        curiosity     = traits.get('curiosity',     0.5)
        openness      = traits.get('openness',      0.5)
        conscientiousness = traits.get('conscientiousness', 0.5)

        # Curious + open agents browse more; conscientious agents only browse
        # when there's a clear knowledge gap (novelty)
        browse_desire = (
            curiosity     * 0.45 +
            openness      * 0.25 +
            novelty       * 0.20 +
            (1.0 - conscientiousness) * 0.10   # less focused → more wandering
        )

        # Boost if recent memory mentions a URL or an unanswered question
        if context is not None:
            recent = context.get('recent_events', [])
            for ev in recent[-5:]:
                text = str(ev.get('text', '') or ev.get('message', ''))
                if 'http' in text or '?' in text:
                    browse_desire = min(1.0, browse_desire + 0.15)
                    break

        # Stochastic gate — prevents mechanical periodicity
        import random
        threshold = self.browsing_desire_threshold
        if browse_desire >= threshold and random.random() < browse_desire:
            log.debug(
                f"BrainCore.should_browse → True "
                f"(desire={browse_desire:.2f}, novelty={novelty:.2f})"
            )
            return True

        return False

    # =========================================================================
    # SLOW PATH — deliberate (world-model imagination)
    # =========================================================================

    def deliberate(self,
                   perception: Dict[str, Any],
                   candidate_actions: Optional[List[Dict]] = None,
                   horizon: int = 12,       # FIX Step 2b: was 3 — too myopic
                   n_trials: int = 40) -> DeliberationResult:  # FIX Step 2b: was 15
        """
        Full imagination-based deliberation via the WorldModel.

        The cognitive loop calls this ONLY when should_deliberate() returns
        True. The result is handed back to the cognitive loop, which decides
        what to do with it — brain and planner stay decoupled.

        Args:
            perception        — current perception dict from _perceive()
            candidate_actions — action dicts to evaluate. If None, the
                                planner's DEFAULT_TEMPLATES are used.
            horizon           — imagination rollout depth
            n_trials          — random sequences to sample per candidate

        Returns:
            DeliberationResult with ranked actions and imagination summaries
        """
        novelty = float(perception.get('novelty', 0.0))
        urgency = float(perception.get('urgency', 0.0))

        # Build context for world model observations
        context = self._perception_to_context(perception)

        # Resolve candidate actions
        if candidate_actions is None:
            try:
                # FIX (template-ceiling): read the agent's *live* planner
                # template list — the same list add_template() already
                # grows for god abilities, and that EmergentSkillPool now
                # also grows from lived experience — instead of
                # re-importing the frozen DEFAULT_TEMPLATES constant.
                # Previously any template added at runtime never reached
                # deliberate(), so it never reached GRPO: this was the
                # actual ceiling on what the training signal could learn.
                planner = getattr(self.agent, 'planner', None) if self.agent else None
                if planner is not None and getattr(planner, 'templates', None):
                    candidate_actions = planner.templates
                else:
                    from ai_core.planner import DEFAULT_TEMPLATES
                    candidate_actions = DEFAULT_TEMPLATES
            except Exception:
                candidate_actions = [
                    {'type': 'explore'}, {'type': 'flee'},
                    {'type': 'attack'}, {'type': 'eat'},
                ]

        ranked:     List[Tuple[float, Dict]]      = []
        summaries:  List[Dict]                    = []
        all_scored: List[Tuple[float, np.ndarray]] = []
        used_wm                                    = False

        wm = self.world_model  # snapshot — safe even if swapped mid-call
        if wm is not None and context:
            used_wm = True
            try:
                ranked, summaries, all_scored = self._deliberate_with_world_model(
                    wm, candidate_actions, context, horizon, n_trials
                )
            except Exception as e:
                log.warning(f"World-model deliberation failed, falling back: {e}")
                used_wm = False

        # Fallback to value-table scoring if WM unavailable or failed
        if not ranked:
            ranked, all_scored = self._deliberate_with_table(candidate_actions, context)

        # Sort descending by score — keep ranked_actions and all_scored_actions
        # in the same relative order so best_action_vector[0] matches best_action.
        order = sorted(range(len(ranked)), key=lambda i: ranked[i][0], reverse=True)
        ranked     = [ranked[i]     for i in order]
        all_scored = [all_scored[i] for i in order] if len(all_scored) == len(order) else all_scored

        self._last_deliberation_ts = time()

        result = DeliberationResult(
            ranked_actions        = ranked,
            imagination_summaries = summaries,
            context_novelty       = novelty,
            context_urgency       = urgency,
            used_world_model      = used_wm,
            all_scored_actions    = all_scored,   # FIX Step 2c
        )

        log.debug(
            f"BrainCore.deliberate: best={result.best_action}, "
            f"score={result.best_score:.3f}, wm={used_wm}, "
            f"novelty={novelty:.2f}, urgency={urgency:.2f}"
        )

        return result

    # ── Deliberation internals ────────────────────────────────────────────

    def _deliberate_with_world_model(
            self,
            wm,
            candidates: List[Dict],
            context: Dict,
            horizon: int,
            n_trials: int
    ) -> Tuple[List[Tuple[float, Dict]], List[Dict], List[Tuple[float, np.ndarray]]]:
        """
        Score each candidate action by imagining short rollouts and applying
        the planner's scoring function (if available) or pure reward.
        """
        import random

        # Get scoring_fn from planner if available
        scoring_fn = None
        if (self.agent is not None and
                hasattr(self.agent, 'planner') and
                self.agent.planner is not None):
            scoring_fn = getattr(self.agent.planner, 'scoring_fn', None)
        if scoring_fn is None:
            scoring_fn = lambda r: r.total_reward  # noqa: E731

        try:
            from ai_core.planner import ImagineResult
            from ai_core.world_model import _build_observation_from_context
            import torch
        except ImportError as e:
            raise RuntimeError(f"Cannot import planner/world_model: {e}")

        initial_obs = _build_observation_from_context(self.agent, context)
        action_dim  = wm.config.action_dim
        device      = wm.device

        # FIX: read the ensemble attached by NPCAgent._init_world_model().
        # None = no ensemble (use_ensemble=False or construction failed) —
        # deliberation proceeds without uncertainty penalty in that case.
        ensemble = getattr(self, 'world_model_ensemble', None)

        # Personality-derived uncertainty aversion (λ in score - λ*std).
        # Bold agents take uncertain bets (low λ); neurotic ones penalize
        # uncertainty heavily (high λ). Range ≈ 0.05 – 0.45.
        # Using the difference because boldness and neuroticism genuinely
        # pull opposite directions — an agent can be both; net disposition
        # toward risk is what matters.
        traits = {}
        if (self.agent is not None and
                hasattr(self.agent, 'personality') and
                self.agent.personality is not None):
            traits = self.agent.personality.traits
        boldness    = float(traits.get('boldness',    0.0))
        neuroticism = float(traits.get('neuroticism', 0.0))
        uncertainty_lambda = max(0.05, 0.25 - 0.2 * boldness + 0.2 * neuroticism)

        ranked:     List[Tuple[float, Dict]]       = []
        summaries:  List[Dict]                     = []
        all_scored: List[Tuple[float, np.ndarray]] = []   # FIX Step 2c

        # Pre-compute the ensemble's uncertainty for the CURRENT state once,
        # shared across all candidates — the query is about "how well does
        # the model know this state", not about the specific action taken,
        # so per-action queries would return essentially the same value while
        # costing 5x more compute. Each candidate's uncertainty penalty is
        # then scaled by the candidate's own novelty (novel actions in
        # uncertain states = highest penalty).
        ens_uncertainty = 0.0
        if ensemble is not None:
            try:
                with torch.no_grad():
                    ens_pred = ensemble.forward(
                        {k: v[:, :1, ...] for k, v in initial_obs.items()}
                    )
                if 'next_state_std' in ens_pred:
                    ens_uncertainty = float(ens_pred['next_state_std'].mean().cpu())
            except Exception as _ue:
                log.debug(f"Ensemble uncertainty query failed: {_ue}")

        for candidate in candidates:
            best_trial_score = -1e9
            best_summary     = None

            # FIX Step 2c: the candidate is always seq[0], so its vector
            # is identical across every trial — compute it once here
            # rather than re-deriving it from inside the trial loop.
            # FIX (template-ceiling): _action_to_vector uses the candidate's
            # own 'action_vector' when present (discovered skills), so a
            # discovered skill is imagined as the real direction it was
            # executed in, not collapsed onto a one-hot template basis.
            cand_vec = _action_to_vector(candidate, action_dim)

            for _ in range(n_trials):
                # Build a short sequence starting with this candidate
                seq = [candidate] + [
                    random.choice(candidates) for _ in range(horizon - 1)
                ]

                action_matrix = np.zeros((1, horizon, action_dim), dtype=np.float32)
                for t, act in enumerate(seq):
                    action_matrix[0, t, :] = _action_to_vector(act, action_dim)

                actions_t = torch.tensor(action_matrix,
                                         dtype=torch.float32, device=device)

                try:
                    with torch.no_grad():
                        imagined = wm.imagine(initial_obs, actions_t, steps=horizon)

                    ir = ImagineResult(
                        sequence          = seq,
                        rewards           = imagined['rewards'][0, :, 0].cpu().numpy(),
                        termination_probs = imagined['terminations'][0, :, 0].cpu().numpy(),
                        states            = imagined['states'][0].cpu().numpy(),
                    )
                    score = scoring_fn(ir)

                    # Novelty bonus for rarely-tried actions
                    score += self._action_novelty_bonus(candidate) * 0.15

                    # FIX: uncertainty penalty — penalize candidates where the
                    # model's epistemic uncertainty is high. Without this the
                    # policy learns to find states where the model makes
                    # confident-sounding but wrong predictions (model-gaming).
                    # Scaled by candidate novelty so familiar actions in uncertain
                    # states are penalized less than novel ones — mirrors how
                    # humans use known-good strategies as a hedge when their
                    # mental model is least reliable. Personality scaling via
                    # uncertainty_lambda handles bold/neurotic character differences.
                    if ens_uncertainty > 0.0:
                        candidate_novelty = self._action_novelty_bonus(candidate)
                        # 1 + novelty so familiar actions (novelty≈0) still get
                        # some penalty, not zero — the model might be wrong about
                        # familiar territory too, just slightly less so on average.
                        score -= uncertainty_lambda * ens_uncertainty * (1.0 + candidate_novelty)

                    if score > best_trial_score:
                        best_trial_score = score
                        best_summary     = ir.summary()

                except Exception as e:
                    log.debug(f"Imagination trial failed for {candidate}: {e}")
                    continue

            if best_summary is not None:
                ranked.append((best_trial_score, candidate))
                summaries.append(best_summary)
                all_scored.append((best_trial_score, cand_vec))   # FIX Step 2c

        return ranked, summaries, all_scored

    def _deliberate_with_table(
            self,
            candidates: List[Dict],
            context: Optional[Dict]
    ) -> Tuple[List[Tuple[float, Dict]], List[Tuple[float, np.ndarray]]]:
        """
        Score candidates using the learned value table only.

        FIX Step 2c: also returns all_scored_actions (vectors) so
        GRPO/SkillTracker still get correctly-typed data even when the
        WorldModel is unavailable and deliberation falls back to this path.
        """

        # No WorldModel here by definition, so action_dim can't come from
        # wm.config — use the agent's own action space (set in NPCAgent.__init__,
        # Step 6), falling back to the NPC baseline of 13 if unavailable.
        action_dim = getattr(self.agent, 'action_dim', 13) if self.agent else 13

        ranked:     List[Tuple[float, Dict]]       = []
        all_scored: List[Tuple[float, np.ndarray]] = []
        for c in candidates:
            score = self.predict_value_of_action(c, context)
            ranked.append((score, c))
            all_scored.append((score, _action_to_vector(c, action_dim)))

        return ranked, all_scored

    # =========================================================================
    # Value prediction (used by both deliberation and planner)
    # =========================================================================

    def predict_value_of_action(self,
                                action: Dict[str, Any],
                                context: Optional[Dict] = None) -> float:
        """
        Estimate the value of a single action.

        Uses the world model when available and context is provided,
        otherwise uses the learned value table. This is the fast single-step
        version — deliberate() is the multi-step version.
        """
        if self.world_model is not None and context is not None:
            try:
                return self._world_model_action_value(action, context)
            except Exception as e:
                log.debug(f"WM single-step value failed, using table: {e}")
        return self._table_action_value(action)

    def _table_action_value(self, action: Dict) -> float:
        atype = action.get('type')
        if atype not in self.forward_model:
            return 0.0
        total = 0.0
        for outcome, prob in self.forward_model[atype].items():
            v = self.value_table.get((atype, outcome))
            if v and v[1] > 0:
                total += prob * (v[0] / v[1])
        return total

    def _world_model_action_value(self,
                                  action: Dict,
                                  context: Dict) -> float:
        import torch
        from ai_core.world_model import _build_observation_from_context

        wm  = self.world_model
        obs = _build_observation_from_context(self.agent, context)

        vec = _action_to_vector(action, wm.config.action_dim)

        obs['action'] = torch.tensor(
            vec, dtype=torch.float32, device=wm.device
        ).unsqueeze(0).unsqueeze(0)

        with torch.no_grad():
            pred = wm(obs)
        return float(pred['reward'][0, -1, 0].item())

    # =========================================================================
    # Language
    # =========================================================================

    def process_language_input(self,
                               text: str,
                               context: Optional[Dict] = None,
                               speaker_id: str = 'unknown') -> str:
        """Route text through LanguageIntelligence."""
        if self.language is None:
            log.warning("BrainCore: no LanguageIntelligence attached.")
            return ""
        try:
            # FIX: was missing speaker_id entirely — any caller passing it
            # through this wrapper (e.g. chat_loop()'s console path) would
            # have hit a TypeError, since process_input() on the underlying
            # LanguageIntelligence now requires it for familiarity/visit
            # tracking (Chat & Web GRPO plan — extraversion reward fix).
            return self.language.process_input(text, context or {}, speaker_id=speaker_id)
        except Exception as e:
            log.error(f"BrainCore.process_language_input: {e}")
            return ""

    def get_language_progress(self) -> Dict[str, Any]:
        """Return language system stats for agent status reporting."""
        if self.language is None:
            return {}
        try:
            return {
                'stage':      self.language.language_stage,
                'vocab_size': self.language.vocab.next_id,
            }
        except Exception:
            return {}

    # =========================================================================
    # Continual learning buffer
    # =========================================================================

    def get_continual_buffer(self,
                             task: Optional[int] = None,
                             limit: Optional[int] = None) -> List[Dict]:
        exps = [
            e for e in self.continual_buffer
            if task is None or e['task'] == task
        ]
        return exps[-limit:] if limit else exps

    def switch_task(self, new_task: int) -> None:
        self.current_task = new_task
        self.task_labels[new_task] = time()

    def get_pattern_summary(self) -> Dict[str, Any]:
        return {
            pt: self.pattern_recognizer.get_pattern_stats(pt)
            for pt in self.pattern_recognizer.pattern_types
        }

    # =========================================================================
    # Internal helpers
    # =========================================================================

    def _classify_event_pattern_type(self, event: Dict) -> str:
        etype = event.get('type', '')
        tags  = event.get('tags', [])
        if 'vision'  in tags or 'visual'   in etype: return 'visual'
        if 'audio'   in tags or 'sound'    in etype: return 'audio'
        if 'chat'    in tags or 'language' in tags:  return 'language'
        if 'action'  in tags or 'movement' in etype: return 'behavior'
        return 'state'

    def _drive_reward(self, payload: Dict) -> float:
        r = 0.0
        if 'health_delta' in payload: r += float(payload['health_delta'])
        if 'hunger_delta' in payload: r += float(payload['hunger_delta']) * 0.25
        if payload.get('danger_increased'): r -= 0.5
        if payload.get('success'):          r += 0.5
        return r

    def _lookup_learned_value(self, event: Dict) -> float:
        key = (event.get('type'), (event.get('tags') or [None])[0])
        v   = self.value_table.get(key)
        return (v[0] / max(1, v[1])) if v else 0.0

    def _prediction_error(self, event: Dict) -> float:
        a = event.get('type')
        if a in self.forward_model:
            actual = event.get('tags', [])
            if actual:
                return 1.0 - self.forward_model[a].get(actual[0], 0.0)
        return 0.0

    def _update_learning(self,
                         event: Dict,
                         payload: Dict,
                         reward: float) -> None:
        # Value table update
        key = (event.get('type'), (event.get('tags') or [None])[0])
        if key not in self.value_table:
            self.value_table[key] = [0.0, 0]
        self.value_table[key][0] += reward
        self.value_table[key][1] += 1

        # Forward model update (transition frequency → probability)
        action = event.get('type')
        tag    = (event.get('tags') or ['none'])[0]
        if action not in self.forward_model:
            self.forward_model[action] = {}
        self.forward_model[action][tag] = \
            self.forward_model[action].get(tag, 0) + 1
        total = sum(self.forward_model[action].values())
        for k in self.forward_model[action]:
            self.forward_model[action][k] /= total

    def _store_continual_experience(self,
                                    event: Dict,
                                    reward: float,
                                    context: Optional[Dict]) -> None:
        self.continual_buffer.append({
            'event':     event,
            'reward':    reward,
            'context':   context,
            'task':      self.current_task,
            'timestamp': time(),
        })

    def _perception_to_context(self,
                               perception: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert a cognitive-loop perception dict to the context format
        expected by _build_observation_from_context in world_model.py.
        """
        state = perception.get('state', {})
        return {
            'health':   state.get('health',  20.0),
            'hunger':   state.get('hunger',  20.0),
            'emotions': state.get('emotions', {}),
            'novelty':  perception.get('novelty', 0.0),
            'urgency':  perception.get('urgency', 0.0),
        }

    def _action_novelty_bonus(self, action: Dict) -> float:
        """
        Small bonus for actions the agent hasn't tried much.
        Uses the forward model as a proxy for action frequency.
        """
        atype = action.get('type', '')
        if atype not in self.forward_model:
            return 1.0   # never tried → maximum novelty bonus
        total_uses = sum(self.forward_model[atype].values())
        return 1.0 / (1.0 + total_uses)

    def _reward_to_emotion_delta(self,
                                  reward: float,
                                  event: Dict) -> Dict[str, float]:
        """
        Convert a scalar reward + event into an emotion delta dict.
        Used by integrate_world_model_with_agent in world_model.py as a
        fallback when the RewardSystem path is not taken.
        """
        novelty = self.pattern_recognizer.get_novelty(
            self._classify_event_pattern_type(event), event
        )
        return {
            'joy':      max(0.0,  reward) * 0.2,
            'fear':     max(0.0, -reward) * 0.3,
            'surprise': novelty * 0.2,
        }