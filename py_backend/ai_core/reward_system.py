# ai_core/reward_system.py
"""
Unified Reward System
=====================
Philosophy:
  Any agent experience (perception/action/thought/memory/language)
      -> personality-weighted reward
      -> immediate emotion delta  (applied inside apply_signal)
      -> per-event personality pressure (applied inside apply_signal)
      -> slow personality drift from sustained emotions  (_apply_drift, every DRIFT_EVERY signals)

The same event genuinely feels different to different agents
because every weight is derived from personality traits.

Changes vs original
-------------------
* apply_signal() now also applies signal.personality_pressure to personality —
  this was computed but never used before.
* apply_signal() is the SINGLE place that touches emotion_system and personality
  after a compute_reward() call.  Callers (brain_core, cognitive_loop) must NOT
  apply emotion deltas manually; they should call apply_signal() instead.
"""
import numpy as np
import torch
import torch.nn as nn
from collections import deque, defaultdict
from typing import Dict, Any, Tuple, Optional, List
import logging

log = logging.getLogger("reward_system")


def sycophancy_weight(traits: Dict[str, float]) -> float:
    """
    Personality-derived anti-sycophancy pressure (Chat & Web GRPO plan §3.4).

    Uniform anti-sycophancy pressure across every agent was rejected — it
    would homogenize every NPC into the same "careful, hedges everything"
    voice. A conscientious, low-agreeableness "skeptic" pushes back harder,
    in character; a high-agreeableness agent keeps more warmth, just
    somewhat more grounded warmth.

    Shared between RewardSystem and LanguageIntelligence (brain_language.py
    calls this via its own _sycophancy_weight() wrapper) so both compute the
    exact same trait→weight mapping instead of maintaining two formulas that
    could silently drift apart.
    """
    return 0.1 + 0.3 * max(
        0.0, traits.get('conscientiousness', 0.0) - traits.get('agreeableness', 0.0)
    )


def _extract_domain(url: str) -> str:
    """Minimal domain extraction for the evidence-diversity term (§3.6b).
    Deliberately independent of web_browser.py's own _extract_domain() —
    RewardSystem has no reference to a WebBrowser instance (it's invoked
    generically via evaluate_event(), decoupled from specific subsystems),
    so this reads straight from the event payload's url string instead."""
    try:
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc or urlparse(url).path
        return netloc.replace('www.', '').lower()
    except Exception:
        return ''


class RandomNetworkDistillation(nn.Module):
    def __init__(self, obs_dim: int, hidden_dim: int = 256):
        super().__init__()
        self.target = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2))
        self.predictor = nn.Sequential(
            nn.Linear(obs_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(),
            nn.Linear(hidden_dim, hidden_dim // 2))
        for p in self.target.parameters(): p.requires_grad = False
        self.opt = torch.optim.Adam(self.predictor.parameters(), lr=1e-4)

    def compute_bonus(self, obs: torch.Tensor) -> float:
        with torch.no_grad(): t = self.target(obs)
        return torch.mean((t - self.predictor(obs)) ** 2).item()

    def update(self, obs: torch.Tensor) -> float:
        with torch.no_grad(): t = self.target(obs)
        loss = nn.functional.mse_loss(self.predictor(obs), t)
        self.opt.zero_grad(); loss.backward(); self.opt.step()
        return loss.item()


class ICMModule(nn.Module):
    def __init__(self, obs_dim: int, action_dim: int, hidden_dim: int = 256):
        super().__init__()
        fd = hidden_dim // 2
        self.encoder = nn.Sequential(nn.Linear(obs_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, fd))
        self.fwd     = nn.Sequential(nn.Linear(fd + action_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, fd))
        self.inv     = nn.Sequential(nn.Linear(fd * 2, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, action_dim))
        self.opt = torch.optim.Adam(self.parameters(), lr=1e-4)

    def compute_bonus(self, obs, action, next_obs) -> float:
        f = self.encoder(obs); nf = self.encoder(next_obs)
        pf = self.fwd(torch.cat([f, action], dim=-1))
        return torch.mean((pf - nf.detach()) ** 2).item()

    def update(self, obs, action, next_obs) -> Dict[str, float]:
        f = self.encoder(obs); nf = self.encoder(next_obs).detach()
        fl = nn.functional.mse_loss(self.fwd(torch.cat([f, action], dim=-1)), nf)
        il = nn.functional.mse_loss(self.inv(torch.cat([f, nf], dim=-1)), action)
        loss = fl + 0.2 * il
        self.opt.zero_grad(); loss.backward(); self.opt.step()
        return {'total': loss.item(), 'forward': fl.item(), 'inverse': il.item()}


class ActionEntropyTracker:
    def __init__(self, window: int = 1000):
        self._counts: Dict[tuple, int] = defaultdict(int)
        self._window: deque = deque(maxlen=window)
        self._total = 0

    def update(self, action: np.ndarray):
        key = tuple(np.round(action, 2))
        if len(self._window) == self._window.maxlen:
            old = self._window[0]; self._counts[old] -= 1; self._total -= 1
        self._window.append(key); self._counts[key] += 1; self._total += 1

    def bonus(self, action: np.ndarray) -> float:
        if self._total == 0: return 0.5
        freq = self._counts.get(tuple(np.round(action, 2)), 0) / self._total
        return float(np.clip(-np.log(freq + 1e-8) / 10.0, 0.0, 1.0))


class RewardSignal:
    """Structured output of compute_reward(). Always pass to apply_signal()."""
    __slots__ = ('total','curiosity','exploration','survival',
                 'task','social','familiarity','evidence','aesthetic',
                 'emotion_deltas','personality_pressure')
    def __init__(self, **kw):
        for k in self.__slots__: setattr(self, k, kw.get(k, 0.0))
    def to_dict(self): return {k: getattr(self, k) for k in self.__slots__}
    def __repr__(self):
        return f"RewardSignal(total={self.total:.3f}, curiosity={self.curiosity:.3f}, survival={self.survival:.3f})"


class ChannelNormalizer:
    """
    Per-channel online running-std normalization for reward channels.

    This is the fix for "No cross-channel reward normalization": without it,
    whichever channel happens to have the largest natural magnitude dominates
    the combined signal regardless of which one is actually most important
    right now, and that dominance can shift unpredictably (curiosity spikes
    when something novel appears, silently drowning out social/familiarity).

    Design rationale (comparing to human reward processing):
    Humans don't experience hunger and curiosity on the same intrinsic
    scale — each operates on its own baseline. What makes an episode of
    eating "satisfying" is measured against how hungry you were, not against
    how curious you felt. The normalization here captures exactly that:
    each channel is expressed in "surprise units" relative to its own
    recent history, making its trait-weighted contribution meaningful rather
    than dominated by raw magnitude.

    Why std-only (not mean-subtracted z-score):
    Mean-subtracted normalization would produce NEGATIVE normalized rewards
    for objectively-positive events that are merely below the channel's
    recent mean. An agent shouldn't be penalized for a good social exchange
    just because it recently had an even better one. Dividing by std alone
    preserves the absolute sign while equalizing scale across channels —
    the trait weights then determine relative importance, as intended.

    The warm_up period (default 50 events per channel) prevents early
    noise from incorrect std estimates from distorting the first few dozen
    reward signals. During warm-up a channel's value is passed through
    unchanged (safe passthrough, not zeroed).
    """
    CHANNELS = ('curiosity', 'exploration', 'survival', 'task',
                 'social', 'familiarity', 'evidence', 'aesthetic')

    def __init__(self, window: int = 500, warm_up: int = 50):
        self._window:  int  = window
        self._warm_up: int  = warm_up
        self._history: Dict[str, deque] = {
            ch: deque(maxlen=window) for ch in self.CHANNELS
        }
        # std clamp: below this we consider the channel "stuck" (always the
        # same value) and passthrough unchanged rather than divide near-zero.
        self._eps = 1e-4

    def normalize(self, channel: str, value: float) -> float:
        """Return value normalized by the channel's running std, or value
        unchanged during warm-up / when std is near zero."""
        hist = self._history.get(channel)
        if hist is None:
            return value   # unknown channel — passthrough
        hist.append(value)
        if len(hist) < self._warm_up:
            return value   # warm-up passthrough
        std = float(np.std(hist))
        if std < self._eps:
            return value   # channel not varying — passthrough
        return float(np.clip(value / std, -5.0, 5.0))

    def normalize_all(self, channels: Dict[str, float]) -> Dict[str, float]:
        """Normalize a dict of {channel_name: raw_value} in one call."""
        return {ch: self.normalize(ch, v) for ch, v in channels.items()}

    def get_stds(self) -> Dict[str, float]:
        """Debug helper: return current running std per channel."""
        return {ch: float(np.std(h)) if len(h) >= 2 else 0.0
                for ch, h in self._history.items()}


class RewardSystem:
    """
    Personality-aware reward system — nervous system connecting all subsystems.

    Every agent experience passes through here:
      perception, action, language, memory recall, internal thought, file reading

    Personality traits determine weights:
      curious agent   -> more reward from novelty
      neurotic agent  -> more fear/pain from danger
      social agent    -> more reward from language/interaction
      bold agent      -> survival penalties are dampened
      open agent      -> more reward from creative/exploratory actions, and
                          from the act of checking web evidence
      extraverted agent -> more reward from a familiar, recurring
                          conversation partner (Chat & Web GRPO plan §3.x) —
                          previously a write-only/decay-only trait that never
                          fed back into any reward term

    Emotion -> personality drift (slow, irreversible):
      sustained joy    -> openness, conscientiousness nudge up
      sustained fear   -> neuroticism up, boldness down
      sustained trust  -> agreeableness, sociability up
      sustained surprise -> curiosity, openness up
      sustained sadness  -> neuroticism up, extraversion down

    apply_signal() is the SINGLE authoritative path for updating both
    emotion_system and personality after each compute_reward() call.
    Do NOT apply emotion deltas manually elsewhere.
    """

    DRIFT_EVERY = 200    # signals between sustained-emotion drift steps
    DRIFT_RATE  = 0.002  # max personality change per drift (keeps it slow)

    # Per-event personality pressure learning rate — much faster than drift
    # so individual strong events can nudge personality noticeably but not wildly.
    PRESSURE_LR = 0.0005

    def __init__(self, obs_dim: int, action_dim: int,
                 personality, emotion_system,
                 use_rnd: bool = True, use_icm: bool = True,
                 device: str = None):
        """
        Args:
            obs_dim:        Observation vector dimension.
            action_dim:     Action vector dimension.
            personality:    Personality instance (must have .traits dict and
                            .apply_update(delta_array, lr) method).
            emotion_system: EmotionSystem instance (must have .add(emotion, value)).
            use_rnd:        Enable Random Network Distillation curiosity bonus.
            use_icm:        Enable Intrinsic Curiosity Module bonus.
            device:         Torch device string. Auto-detected if None.
        """
        self.personality    = personality
        self.emotion_system = emotion_system
        self.obs_dim        = obs_dim
        self.action_dim     = action_dim
        self.device = torch.device(device or ('cuda' if torch.cuda.is_available() else 'cpu'))

        self.use_rnd = use_rnd
        self.use_icm = use_icm
        if use_rnd: self.rnd = RandomNetworkDistillation(obs_dim).to(self.device)
        if use_icm: self.icm = ICMModule(obs_dim, action_dim).to(self.device)
        self.entropy_tracker = ActionEntropyTracker()

        self.alive_ticks  = 0
        self.last_health  = 20.0
        self.reward_history: deque = deque(maxlen=500)
        # FIX (Chat & Web GRPO plan §3.6b): rolling window of recently visited
        # distinct domains, for the evidence diversity term. Lives here, not on
        # WebBrowser — RewardSystem has no reference to a live WebBrowser
        # instance, and only needs the URL already present in each web event's
        # own payload.
        self._recent_domains: deque = deque(maxlen=20)
        self._pressure: Dict[str, float] = defaultdict(float)
        self._since_drift = 0
        # FIX (report: "No cross-channel reward normalization"): per-channel
        # running-std normalizer so trait weights are the actual arbiter of
        # channel importance, rather than whichever channel happens to have the
        # largest natural magnitude. See ChannelNormalizer above for full design
        # rationale. 500-event window matches reward_history; 50-event warm-up
        # prevents early noise from distorting the first few dozen signals.
        self._channel_normalizer = ChannelNormalizer(window=500, warm_up=50)
        log.info(f"RewardSystem ready on {self.device}")

    # ------------------------------------------------------------------
    # Primary scoring
    # ------------------------------------------------------------------

    def compute_reward(self,
                       event:    Dict[str, Any],
                       obs:      Optional[torch.Tensor] = None,
                       action:   Optional[torch.Tensor] = None,
                       next_obs: Optional[torch.Tensor] = None,
                       outcome:  Optional[Dict[str, Any]] = None) -> RewardSignal:
        """
        Score any agent experience. Called for EVERY event type:
        perception, action, language, memory recall, internal thought, file processing.

        Does NOT update emotion_system or personality directly —
        call apply_signal(signal) immediately after to apply all side-effects.
        """
        outcome  = outcome or {}
        payload  = event.get('payload', {})
        tags     = event.get('tags', [])
        etype    = event.get('type', 'unknown')
        traits   = self.personality.traits
        emotions = self.emotion_system.snapshot()

        # 1. CURIOSITY (RND + ICM, scaled by curiosity trait)
        raw_curiosity = 0.0
        if obs is not None:
            ob = obs.to(self.device)
            if self.use_rnd:
                raw_curiosity += 0.5 * self.rnd.compute_bonus(ob)
                self.rnd.update(ob)
            if self.use_icm and action is not None and next_obs is not None:
                ac, no = action.to(self.device), next_obs.to(self.device)
                raw_curiosity += 0.5 * self.icm.compute_bonus(ob, ac, no)
                self.icm.update(ob, ac, no)
        c_w = 0.2 + 0.3 * max(0.0, traits.get('curiosity', 0.0))
        curiosity_r = float(np.tanh(c_w * raw_curiosity))

        # 2. EXPLORATION (action entropy, scaled by openness)
        entropy_r = 0.0
        if action is not None:
            anp = action.detach().cpu().numpy().flatten()
            self.entropy_tracker.update(anp)
            e_w = 0.1 + 0.2 * max(0.0, traits.get('openness', 0.0))
            entropy_r = e_w * self.entropy_tracker.bonus(anp)

        # 3. SURVIVAL (health/hunger/death, scaled by neuroticism/boldness)
        health  = float(outcome.get('health',  payload.get('health',  self.last_health)))
        is_dead = bool(outcome.get('is_dead',  payload.get('is_dead', False)))
        survival_r = 0.0
        if is_dead:
            survival_r = -10.0; self.alive_ticks = 0
        else:
            self.alive_ticks += 1
            survival_r += (health - self.last_health) * 0.15
            survival_r += float(payload.get('hunger_delta', 0.0)) * 0.05
            if payload.get('danger_increased'): survival_r -= 0.4
            if self.alive_ticks % 500 == 0:     survival_r += 1.0
        s_scale = 0.3 + 0.15 * traits.get('neuroticism',0.0) - 0.10 * traits.get('boldness',0.0)
        survival_r *= s_scale
        self.last_health = health

        # 4. TASK (conscientiousness scales task reward)
        t_scale = 0.2 + 0.1 * traits.get('conscientiousness', 0.0)
        task_r  = t_scale * float(outcome.get('task_reward', payload.get('task_reward', 0.0)))

        # 5. SOCIAL (language/interaction, scaled by sociability + agreeableness)
        social_r = 0.0
        if 'language' in tags or 'chat' in tags or etype in ('language_input','autonomous_speech'):
            soc = traits.get('sociability',0.0) + traits.get('agreeableness',0.0)
            social_r = soc * 0.15
            if payload.get('success'): social_r += 0.1

        # 5b. FAMILIARITY (repeat-visitor rapport, scaled by extraversion) — NEW.
        # FIX: extraversion was a write-only/decay-only trait — drift could push
        # it down (sustained sadness) but nothing ever read it as an input to any
        # reward term, so it had zero behavioral effect. partner_visit_count is
        # written by LanguageIntelligence.process_input() from its own
        # self-tracked visit history (a partner is "the same visitor returning"
        # once 120s+ has passed since they last talked — the same threshold
        # ConversationBuffer.is_active() already uses for "still mid-conversation"
        # vs "a new exchange") — fully self-referential, no external identity
        # database involved.
        familiarity_r = 0.0
        if 'language' in tags or 'chat' in tags or etype in ('language_input','autonomous_speech'):
            visit_count = float(payload.get('partner_visit_count', 0))
            # FIX: was `extra * 0.15 * ...` with extra=max(0,extraversion) and no
            # baseline — unlike every other trait-weight formula in this file
            # (c_w, e_w, s_scale, t_scale all use baseline + scale*trait), that
            # left a zero-extraversion agent at EXACTLY zero familiarity reward,
            # which meant trust could never cross the 0.05 threshold in
            # _personality_pressure from familiarity alone — extraversion could
            # never bootstrap upward from a cold start. Baseline + scale matches
            # the rest of the file and models "even an introvert appreciates a
            # familiar face, just less than an extravert does."
            extra_w = 0.05 + 0.15 * max(0.0, traits.get('extraversion', 0.0))
            familiarity_r = extra_w * min(1.0, np.log1p(visit_count) / np.log1p(20.0))

        # 6. AESTHETIC/CREATIVE (build/craft/express, scaled by openness)
        aesthetic_r = 0.0
        if etype in ('craft','build','language_output','autonomous_speech','file_processed'):
            op = max(0.0, traits.get('openness', 0.0))
            aesthetic_r = op * 0.1
            if payload.get('success'): aesthetic_r += op * 0.15

        # 6b. EVIDENCE (web-checking behavior, scaled by openness) — Chat & Web
        # GRPO plan §3.6b. The agent is rewarded for the ACT of checking, not
        # for what it finds: claim_support_delta is an absolute shift in
        # memory-search overlap before/after the visit (computed by the
        # caller, cognitive_loop._execute_web_browsing()) — a page that
        # contradicts the user's claim is worth exactly as much as one that
        # confirms it. That's the actual anti-sycophancy lever on the web side.
        evidence_r = 0.0
        if 'web' in tags or etype == 'web_browsed':
            domain = _extract_domain(payload.get('url', ''))
            if domain:
                self._recent_domains.append(domain)
            diversity = min(1.0, len(set(self._recent_domains)) / 5.0)
            grounding = payload.get('claim_support_delta', 0.0)   # |shift|, not direction
            op = max(0.0, traits.get('openness', 0.0))
            evidence_r = (0.1 * diversity + 0.2 * abs(grounding)) * (0.5 + 0.5 * op)

        # 7. PER-CHANNEL NORMALIZATION (new) — normalize each channel by its
        # own running std so trait weights are the actual arbiter of channel
        # importance, not raw magnitude. Applied before emotion modulation so
        # the joy/fear boosts scale already-normalized values uniformly.
        # survival_r is NOT normalized — it has a meaningful absolute scale
        # (negative values = actual damage taken) and normalizing it would
        # make "50% health" look the same as "90% health" after enough events.
        raw_channels = {
            'curiosity':    curiosity_r,
            'exploration':  entropy_r,
            'task':         task_r,
            'social':       social_r,
            'familiarity':  familiarity_r,
            'evidence':     evidence_r,
            'aesthetic':    aesthetic_r,
        }
        norm = self._channel_normalizer.normalize_all(raw_channels)
        curiosity_r_n   = norm['curiosity']
        entropy_r_n     = norm['exploration']
        task_r_n        = norm['task']
        social_r_n      = norm['social']
        familiarity_r_n = norm['familiarity']
        evidence_r_n    = norm['evidence']
        aesthetic_r_n   = norm['aesthetic']

        # 8. EMOTION MODULATION (current feelings bias reward perception)
        joy_boost  = 1.0 + 0.2 * emotions.get('joy',  0.0)
        fear_boost = 1.0 + 0.2 * emotions.get('fear', 0.0)
        pos = (curiosity_r_n + entropy_r_n + task_r_n + social_r_n + familiarity_r_n
               + evidence_r_n + aesthetic_r_n) * joy_boost
        neg = min(0.0, survival_r) * fear_boost
        survival_r = max(0.0, survival_r) + neg
        total = pos + survival_r

        # 9. EMOTION DELTAS — raw values, not normalized: emotion system responds
        # to what physically happened (real damage, real social exchange), not
        # normalized representations of it.
        ed = self._emotion_deltas(total, curiosity_r, survival_r,
                                   social_r, familiarity_r, aesthetic_r,
                                   is_dead, payload, traits)

        # 10. PERSONALITY PRESSURE (per-event nudge — applied in apply_signal)
        pp = self._personality_pressure(total, ed, traits)

        signal = RewardSignal(
            total=float(total), curiosity=float(curiosity_r),
            exploration=float(entropy_r), survival=float(survival_r),
            task=float(task_r), social=float(social_r),
            familiarity=float(familiarity_r), evidence=float(evidence_r),
            aesthetic=float(aesthetic_r),
            emotion_deltas=ed, personality_pressure=pp)

        self.reward_history.append(total)
        self._accumulate(ed)
        self._since_drift += 1
        if self._since_drift >= self.DRIFT_EVERY:
            self._apply_drift(); self._since_drift = 0

        return signal

    # ------------------------------------------------------------------
    # Side-effect application  (SINGLE unified path)
    # ------------------------------------------------------------------

    def apply_signal(self, signal: RewardSignal) -> None:
        """
        Apply ALL side-effects of a RewardSignal to the agent's emotion and
        personality systems.  This is the ONE place these are updated after
        a compute_reward() call.

        1. Emotion deltas  — immediate, every call.
        2. Personality pressure — per-event micro-nudge, every call.

        The sustained-emotion drift (_apply_drift) is handled inside
        compute_reward() on a DRIFT_EVERY cadence and is separate from this.
        """
        # 1. Apply emotion deltas
        if isinstance(signal.emotion_deltas, dict):
            for emotion, delta in signal.emotion_deltas.items():
                if delta != 0.0:
                    self.emotion_system.add(emotion, float(delta))

        # 2. Apply per-event personality pressure
        # personality_pressure is a dict[trait_name -> float delta].
        # We convert it to the array format personality.apply_update() expects.
        if isinstance(signal.personality_pressure, dict) and signal.personality_pressure:
            try:
                traits_list = self.personality.TRAITS  # ordered list of trait names
                delta_array = np.zeros(len(traits_list), dtype=np.float32)
                for i, trait in enumerate(traits_list):
                    delta_array[i] = signal.personality_pressure.get(trait, 0.0)
                # Only nudge if there's meaningful signal — avoids noise on zero-pressure events
                if np.any(delta_array != 0.0):
                    self.personality.apply_update(delta_array, lr=self.PRESSURE_LR)
            except Exception as e:
                log.debug(f"apply_signal: personality pressure update skipped: {e}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _emotion_deltas(self, total, curiosity, survival, social, familiarity,
                         aesthetic, is_dead, payload, traits) -> Dict[str, float]:
        d: Dict[str, float] = {}
        n = traits.get('neuroticism', 0.0)
        a = traits.get('agreeableness', 0.0)
        o = traits.get('openness', 0.0)
        if total > 0:    d['joy']     = min(0.3, total * 0.15)
        else:            d['sadness'] = min(0.3, abs(total) * 0.1 * (1.0 + n))
        if curiosity > 0.05:
            d['anticipation'] = curiosity * 0.2
            d['surprise']     = curiosity * 0.1
        if survival < -0.1:
            d['fear']  = min(0.5, abs(survival) * 0.3 * (1.0 + n))
            d['anger'] = min(0.3, abs(survival) * 0.15)
        if is_dead: d['fear'] = 1.0; d['sadness'] = 1.0
        if social > 0.05:
            d['trust'] = social * 0.3 * (1.0 + a)
            d['joy']   = d.get('joy', 0.0) + social * 0.1
        # FIX: familiarity feeds the same trust/joy channels social does —
        # a recurring conversation partner builds the same kind of warmth a
        # smooth single exchange does, just compounding across visits instead
        # of resetting each time. This is also what gives _personality_pressure
        # below something to read for the new positive-extraversion path.
        if familiarity > 0.02:
            d['trust'] = d.get('trust', 0.0) + familiarity * 0.25
            d['joy']   = d.get('joy',   0.0) + familiarity * 0.1
        if aesthetic > 0.02:
            amp = 1.0 + max(0.0, o)
            d['joy']          = d.get('joy', 0.0) + aesthetic * 0.15 * amp
            d['anticipation'] = d.get('anticipation', 0.0) + aesthetic * 0.05
        if payload.get('danger_increased'):
            d['disgust'] = 0.1 + 0.1 * n
        return d

    def _personality_pressure(self, total, ed, traits) -> Dict[str, float]:
        p: Dict[str, float] = {}
        joy   = ed.get('joy',         0.0)
        fear  = ed.get('fear',        0.0)
        trust = ed.get('trust',       0.0)
        surp  = ed.get('surprise',    0.0)
        anti  = ed.get('anticipation',0.0)
        if total > 0.1:
            p['openness'] = total * 0.01; p['conscientiousness'] = total * 0.005
        if fear > 0.05:
            p['neuroticism'] = fear * 0.02; p['boldness'] = -fear * 0.01
        if trust > 0.05:
            p['agreeableness'] = trust * 0.015; p['sociability'] = trust * 0.01
            # FIX: extraversion previously had ONLY a negative path (sustained
            # sadness pushes it down, below) — nothing ever pushed it back up,
            # making it a one-way ratchet toward introversion regardless of how
            # sociable the agent's actual experience was. Sustained trust (which
            # now includes the familiarity bonus above) is the natural positive
            # counterpart: an agent that keeps having warm, recurring
            # conversations should drift toward more extraverted over time, the
            # same way sustained fear already drifts boldness down.
            p['extraversion'] = p.get('extraversion', 0.0) + trust * 0.01
        if surp + anti > 0.05:
            p['curiosity'] = (surp + anti) * 0.01
            p['openness']  = p.get('openness', 0.0) + (surp + anti) * 0.005
        if total < -0.2:
            p['neuroticism']  = p.get('neuroticism', 0.0) + abs(total) * 0.01
            p['extraversion'] = p.get('extraversion', 0.0) - abs(total) * 0.005
        if total > 0 and self.alive_ticks > 100:
            p['boldness'] = p.get('boldness', 0.0) + 0.001
        return p

    def _accumulate(self, ed: Dict[str, float]):
        for k in ('joy','fear','trust','surprise','anticipation','sadness'):
            self._pressure[k] += ed.get(k, 0.0)

    def _apply_drift(self):
        """
        Nudge personality based on sustained emotional state.
        Intentionally slow — personality should not change overnight.
        This runs every DRIFT_EVERY signals (i.e. roughly every few hundred events).
        """
        n  = max(1, self._since_drift)
        p  = {k: self._pressure[k] / n for k in self._pressure}
        ti = {t: i for i, t in enumerate(self.personality.TRAITS)}
        drift = np.zeros(len(self.personality.TRAITS), dtype=np.float32)
        drift[ti['openness']]          += p.get('joy',         0) * 0.3
        drift[ti['conscientiousness']] += p.get('joy',         0) * 0.2
        drift[ti['neuroticism']]       += p.get('fear',        0) * 0.4
        drift[ti['boldness']]          -= p.get('fear',        0) * 0.2
        drift[ti['agreeableness']]     += p.get('trust',       0) * 0.3
        drift[ti['sociability']]       += p.get('trust',       0) * 0.2
        drift[ti['curiosity']]         += p.get('surprise',    0) * 0.3
        drift[ti['openness']]          += p.get('surprise',    0) * 0.2
        drift[ti['openness']]          += p.get('anticipation',0) * 0.15
        drift[ti['neuroticism']]       += p.get('sadness',     0) * 0.2
        drift[ti['extraversion']]      -= p.get('sadness',     0) * 0.1
        self.personality.apply_update(drift, lr=self.DRIFT_RATE)
        self._pressure = defaultdict(float)
        log.debug(f"Personality drift applied: {self.personality.traits}")

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def recent_average(self, n: int = 50) -> float:
        recent = list(self.reward_history)[-n:]
        return float(np.mean(recent)) if recent else 0.0

    def emotional_state_label(self) -> str:
        avg = self.recent_average(20)
        if avg >  0.5: return "satisfied"
        if avg >  0.0: return "content"
        if avg > -0.5: return "struggling"
        return "distressed"

    def save(self, path: str):
        s = {}
        if self.use_rnd: s['rnd'] = self.rnd.state_dict()
        if self.use_icm: s['icm'] = self.icm.state_dict()
        torch.save(s, path)

    def load(self, path: str):
        s = torch.load(path, map_location='cpu')
        if self.use_rnd and 'rnd' in s: self.rnd.load_state_dict(s['rnd'])
        if self.use_icm and 'icm' in s: self.icm.load_state_dict(s['icm'])