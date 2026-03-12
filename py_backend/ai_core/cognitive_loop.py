# ai_core/cognitive_loop.py
"""
Autonomous Cognitive Loop — Full Integration
============================================

Perceive → Think → Reflect → Decide → Act cycle running at configurable
interval. Integrates with BrainCore's two-speed evaluation:

  Fast path  — evaluate_event() runs every cycle, no world model.
  Slow path  — deliberate() runs only when should_deliberate() returns True.
               Result is a DeliberationResult the loop uses to pick and
               optionally interrupt its current plan.

Mid-task interruption
---------------------
When executing a multi-step plan, the loop checks after every completed
action whether:
  - Urgency has spiked (danger, starvation, etc.)
  - A significantly better option was found by a fresh deliberation
If either condition is met the current plan is abandoned and the full
perceive→decide cycle restarts.
"""

import asyncio
import time
import numpy as np
from typing import Dict, Any, Optional, List
from collections import deque
import logging

log = logging.getLogger("cognitive_loop")


class CognitiveState:
    """Tracks agent's cognitive state across cycles."""

    def __init__(self):
        self.current_focus:           Optional[str]  = None
        self.active_goal:             Optional[str]  = None
        self.attention_level:         float          = 0.5
        self.energy_level:            float          = 1.0
        self.last_significant_event:  Optional[Dict] = None
        self.cycle_count:             int            = 0
        self.last_speech:             Optional[str]  = None
        self.speech_count:            int            = 0

        # Plan execution state — shared between _act and interruption check
        self.current_plan:            Optional[List[Dict]] = None
        self.current_plan_score:      float               = 0.0
        self.plan_step:               int                 = 0


class CognitiveLoop:
    """
    Fully integrated autonomous cognitive cycle.

    Key additions over the original:
    - Calls brain.should_deliberate() before running world-model imagination
    - Passes DeliberationResult to _execute_action for plan selection
    - Checks interruption condition between every plan step
    - Vision tokens from VisionAdapter injected into perception dict
    """

    def __init__(self, agent, loop_interval: float = 0.5):
        self.agent         = agent
        self.loop_interval = loop_interval

        # Input buffers
        self.visual_buffer = deque(maxlen=10)
        self.audio_buffer  = deque(maxlen=5)
        self.state_buffer  = deque(maxlen=20)
        self.event_buffer  = deque(maxlen=50)
        self.file_buffer   = deque(maxlen=20)

        # Cognitive state
        self.state = CognitiveState()

        # Timing control
        self.last_action_time   = 0.0
        self.last_speech_time   = 0.0
        self.last_learning_time = 0.0

        # Thresholds (personality-adjusted)
        self._update_thresholds()

        # Control
        self.running = False
        self.task    = None

        log.info(f"CognitiveLoop initialised for {agent.agent_id}")

    def _update_thresholds(self):
        """Derive timing thresholds from personality traits."""
        traits = self.agent.personality.traits

        extraversion = traits.get('extraversion', 0.0)
        sociability  = traits.get('sociability',  0.5)
        boldness     = traits.get('boldness',      0.5)
        openness     = traits.get('openness',      0.5)

        base_cooldown       = 15.0
        self.speech_cooldown = max(
            5.0,
            base_cooldown * (1.0 - (extraversion + sociability) / 4.0)
        )
        self.action_cooldown   = 2.0 * (1.0 - boldness * 0.5)
        self.learning_interval = 30.0 * (1.0 - openness * 0.3)

        log.debug(
            f"Thresholds: speech={self.speech_cooldown:.1f}s "
            f"action={self.action_cooldown:.1f}s"
        )

    # =========================================================================
    # Control
    # =========================================================================

    async def start(self):
        if self.running:
            log.warning(f"Cognitive loop already running for {self.agent.agent_id}")
            return
        self.running = True
        self.task    = asyncio.create_task(self._cognitive_loop())
        log.info(f"✅ Cognitive loop started for {self.agent.agent_id}")

    async def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        log.info(f"🛑 Cognitive loop stopped for {self.agent.agent_id}")

    # =========================================================================
    # Main loop
    # =========================================================================

    async def _cognitive_loop(self):
        log.info(f"🧠 Cognitive cycle started for {self.agent.agent_id}")

        while self.running:
            try:
                cycle_start = time.time()

                # 1. PERCEIVE
                perception = self._perceive()

                # 2. THINK  (may trigger deliberation)
                thoughts = await self._think(perception)

                # 3. REFLECT
                reflection = self._reflect(thoughts, perception)

                # 4. DECIDE
                decision = self._decide(reflection, thoughts)

                # 5. ACT
                await self._act(decision, perception, thoughts)

                # 6. UPDATE STATE
                self._update_cognitive_state(perception, thoughts, reflection)

                self.state.cycle_count += 1
                if self.state.cycle_count % 100 == 0:
                    log.info(
                        f"[{self.agent.agent_id}] Cycle {self.state.cycle_count}: "
                        f"focus={self.state.current_focus} "
                        f"speeches={self.state.speech_count}"
                    )

                elapsed    = time.time() - cycle_start
                sleep_time = max(0.01, self.loop_interval - elapsed)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(
                    f"Cognitive loop error for {self.agent.agent_id}: {e}",
                    exc_info=True
                )
                await asyncio.sleep(1.0)

    # =========================================================================
    # Perception
    # =========================================================================

    def _perceive(self) -> Dict[str, Any]:
        """
        Gather current state. Augments the base dict with:
          - visual_token / visual_token_name from VisionAdapter (if attached)
          - novelty contribution from vision
        """
        perception = {
            'timestamp': time.time(),
            'state': {
                'health':           self.agent.health,
                'hunger':           self.agent.hunger,
                'emotions':         self.agent.emotion.snapshot(),
                'dominant_emotion': self.agent.emotion.dominant_emotion(),
                'memory_size':      len(self.agent.memory.events),
            },
            'recent_events': [],
            'novelty':  0.0,
            'urgency':  0.0,
            # vision fields (populated below if VisionAdapter is attached)
            'visual_token':      -1,
            'visual_token_name': 'nothing',
            'has_depth':         False,
        }

        # Recent events from unified memory
        recent = self.agent.memory.recall(n=10)
        perception['recent_events'] = recent

        # Novelty from event frequency
        if recent:
            scores = []
            for event in recent[-3:]:
                etype      = event.get('type', 'unknown')
                type_count = sum(1 for e in recent if e.get('type') == etype)
                scores.append(1.0 / (1.0 + type_count))
            perception['novelty'] = float(np.mean(scores)) if scores else 0.0

        # Urgency from emotions + health
        emotions         = perception['state']['emotions']
        emotion_intensity = max(abs(v) for v in emotions.values()) if emotions else 0.0
        health_urgency    = 1.0 - (perception['state']['health'] / 20.0)
        perception['urgency'] = float(max(emotion_intensity, health_urgency))

        # ── Vision augmentation ──────────────────────────────────────────
        vision = getattr(self.agent, 'vision', None)
        if vision is not None:
            try:
                frames = vision.drain_frames()
                if not frames:
                    lf = vision.latest_frame
                    if lf:
                        frames = [lf]

                if frames:
                    latest     = frames[-1]
                    token_name = vision.vocab.name_of(latest.visual_token)

                    # Visual novelty: inverse of how often this token appears
                    counts = vision.vocab._counts
                    token_count = (
                        counts[latest.visual_token]
                        if latest.visual_token < len(counts) else 1
                    )
                    visual_novelty = 1.0 / (1.0 + float(token_count) / 10.0)

                    perception['visual_token']      = latest.visual_token
                    perception['visual_token_name'] = token_name
                    perception['has_depth']         = latest.depth is not None
                    # Blend visual novelty into overall novelty
                    perception['novelty'] = float(max(
                        perception['novelty'], visual_novelty
                    ))
            except Exception as e:
                log.debug(f"Vision perception augmentation failed: {e}")

        return perception

    # =========================================================================
    # Thinking — may trigger deliberation
    # =========================================================================

    async def _think(self, perception: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process perception. Runs fast evaluation every cycle.
        Triggers world-model deliberation only when the brain decides it's
        worth it (should_deliberate() gate).
        """
        thoughts = {
            'focus':                 None,
            'language_desire':       0.0,
            'speech_topic':          None,
            'curiosity':             0.0,
            'analysis':              {},
            'file_to_process':       None,
            'should_browse':         False,
            'should_simulate':       False,
            'should_think_verbally': False,
            'should_listen':         False,
            'audio_data':            None,
            'internal_thoughts':     [],
            'mental_workspace':      None,
            # Deliberation result — populated below if deliberation ran
            'deliberation':          None,
        }

        # ── Fast evaluation (runs every cycle) ───────────────────────────
        event = {
            'type':    'autonomous_perception',
            'tags':    ['autonomous', 'perception'],
            'payload': {
                'novelty': perception['novelty'],
                'urgency': perception['urgency'],
            },
        }
        reward, emotion_delta = self.agent.brain.evaluate_event(
            event, perception['state']
        )
        for emotion, value in emotion_delta.items():
            self.agent.emotion.add(emotion, value)

        thoughts['analysis'] = {'reward': reward, 'emotion_delta': emotion_delta}

        # Quick-exit for routine cycles
        if (perception['novelty'] < 0.2 and
                perception['urgency'] < 0.3 and
                not self.file_buffer):
            return thoughts

        # ── Audio processing ─────────────────────────────────────────────
        if hasattr(self.agent, 'audio_processor'):
            try:
                audio_result = await asyncio.to_thread(
                    lambda: self.agent.audio_processor.process_audio_chunk()
                )
                if audio_result and audio_result.get('transcription'):
                    thoughts['audio_data'] = audio_result
                    transcription = audio_result['transcription']
                    context = {
                        'health':   perception['state']['health'],
                        'hunger':   perception['state']['hunger'],
                        'emotions': perception['state']['emotions'],
                    }
                    response = self.agent.brain.process_language_input(
                        transcription, context
                    )
                    await self._broadcast_audio_heard(
                        transcription, audio_result.get('emotion_label')
                    )
                    if response:
                        await self._broadcast_speech(response)
            except Exception as e:
                log.debug(f"Audio processing error: {e}")

        # ── Deliberation gate ────────────────────────────────────────────
        # Ask the brain whether this situation warrants world-model thinking.
        # This is the ONLY place deliberate() is called — the brain controls
        # the when, the cognitive loop controls the what.
        if self.agent.brain.should_deliberate(
            novelty=perception['novelty'],
            urgency=perception['urgency'],
        ):
            try:
                delib = self.agent.brain.deliberate(perception)
                thoughts['deliberation'] = delib
                thoughts['should_simulate'] = True

                log.debug(
                    f"[{self.agent.agent_id}] Deliberated: "
                    f"best={delib.best_action}, "
                    f"wm={delib.used_world_model}"
                )

                # Optionally run mental workspace visualization
                if (hasattr(self.agent, 'imagine_scenario') and
                        delib.used_world_model):
                    scenario_data = self.agent.imagine_scenario(
                        perception['state']
                    )
                    thoughts['mental_workspace'] = scenario_data
                    await self._broadcast_mental_workspace(scenario_data)

            except Exception as e:
                log.warning(f"Deliberation error: {e}")

        # ── Autonomous listening decision ────────────────────────────────
        if hasattr(self.agent, 'audio_processor'):
            traits           = self.agent.personality.traits
            listening_desire = (
                traits.get('sociability', 0.5) * 0.4 +
                traits.get('openness',    0.5) * 0.3 +
                traits.get('curiosity',   0.5) * 0.2 +
                perception['novelty']           * 0.1
            )
            if listening_desire > 0.4 and np.random.rand() < listening_desire:
                thoughts['should_listen'] = True
                if not self.agent.audio_processor.is_listening:
                    self.agent.audio_processor.start_listening()
            else:
                if self.agent.audio_processor.is_listening:
                    self.agent.audio_processor.stop_listening()

        # ── Verbal thinking decision ─────────────────────────────────────
        if thoughts['should_simulate']:
            traits  = self.agent.personality.traits
            vt_desire = (
                (1.0 - traits.get('sociability', 0.5)) * 0.4 +
                traits.get('openness', 0.5)             * 0.3 +
                perception['novelty']                   * 0.2 +
                thoughts['analysis'].get(
                    'emotion_delta', {}
                ).get('surprise', 0)                    * 0.1
            )
            if vt_desire > 0.4 and np.random.rand() < vt_desire:
                thoughts['should_think_verbally'] = True
                if hasattr(self.agent, 'generate_internal_thought'):
                    ctx = {
                        'health':   perception['state']['health'],
                        'hunger':   perception['state']['hunger'],
                        'emotions': perception['state']['emotions'],
                        'novelty':  perception['novelty'],
                        'urgency':  perception['urgency'],
                    }
                    internal = self.agent.generate_internal_thought(ctx)
                    if internal:
                        await self._broadcast_internal_thought(internal)

        # ── Language desire ──────────────────────────────────────────────
        lang_factors = []
        emotions     = perception['state']['emotions']
        em_intensity = max(abs(v) for v in emotions.values()) if emotions else 0.0
        if em_intensity > 0.5:
            lang_factors.append(('strong_emotion', em_intensity))
        if perception['novelty'] > 0.6:
            lang_factors.append(('novelty', perception['novelty']))

        traits      = self.agent.personality.traits
        sociability = traits.get('sociability', 0.5)
        extraversion = traits.get('extraversion', 0.0)
        lang_factors.append(('personality', (sociability + extraversion + 2.0) / 4.0))

        time_since_speech = time.time() - self.last_speech_time
        time_factor       = min(1.0, time_since_speech / self.speech_cooldown)
        if time_factor > 0.5:
            lang_factors.append(('time_pressure', time_factor))

        recent_speech = [
            e for e in perception['recent_events']
            if e.get('type') in ('language_input', 'language_output')
        ]
        if recent_speech and time_since_speech < 30:
            lang_factors.append(('conversation_context', 0.8))
            thoughts['speech_topic'] = 'conversation_response'

        if perception['urgency'] > 0.6:
            lang_factors.append(('urgent_thoughts', perception['urgency']))
            thoughts['speech_topic'] = 'urgent_situation'

        if lang_factors:
            thoughts['language_desire'] = float(
                np.mean([f[1] for f in lang_factors])
            )

        # ── File processing check ────────────────────────────────────────
        if self.file_buffer:
            thoughts['file_to_process'] = self.file_buffer[0]
        else:
            try:
                for ev in reversed(self.agent.memory.recall(n=50)):
                    if ev.get('type') == 'file_uploaded':
                        fn = ev.get('filename')
                        already = any(
                            e.get('type') == 'file_processed' and
                            e.get('filename') == fn
                            for e in self.agent.memory.recall(n=50)
                        )
                        if not already:
                            self.file_buffer.append({
                                'path':      ev.get('path'),
                                'filename':  fn,
                                'filetype':  ev.get('filetype'),
                                'size':      ev.get('size'),
                                'timestamp': ev.get('timestamp'),
                            })
                            thoughts['file_to_process'] = self.file_buffer[0]
                            break
            except Exception as e:
                log.error(f"File check error: {e}")

        # ── Curiosity score (used by web browsing + focus) ───────────────
        # Derived from personality traits so it's always a real value
        traits = self.agent.personality.traits
        thoughts['curiosity'] = float(
            traits.get('curiosity', 0.5) * 0.5 +
            traits.get('openness',  0.5) * 0.3 +
            perception['novelty']        * 0.2
        )

        # ── Web browsing — agent decides, brain owns the decision ─────────
        # brain.should_browse() checks personality, cooldown, urgency, and
        # whether there are actually allowed domains configured.
        # The cognitive loop then checks if there's anything queued to browse.
        if self.agent.brain.should_browse(
            novelty=perception['novelty'],
            urgency=perception['urgency'],
            context={'recent_events': perception['recent_events']},
        ):
            browser = getattr(self.agent, 'web_browser', None)
            if browser is not None and browser.browse_queue:
                thoughts['should_browse'] = True
            elif browser is not None and not browser.browse_queue:
                # Agent wants to browse but queue is empty — nothing to do yet.
                # URLs enter the queue when the user mentions them in chat,
                # or when the agent discovers links while browsing other pages.
                log.debug(
                    f"[{self.agent.agent_id}] Wants to browse but queue empty"
                )

        # ── Focus determination ──────────────────────────────────────────
        if perception['urgency'] > 0.7:
            thoughts['focus'] = 'survival'
        elif thoughts['file_to_process']:
            thoughts['focus'] = 'learning'
        elif thoughts['deliberation'] is not None:
            thoughts['focus'] = 'planning'
        elif thoughts['language_desire'] > 0.4:
            thoughts['focus'] = 'expression'
        elif perception['novelty'] > 0.6:
            thoughts['focus'] = 'exploration'
        else:
            thoughts['focus'] = 'observation'

        return thoughts

    # =========================================================================
    # Reflection
    # =========================================================================

    def _reflect(self,
                 thoughts: Dict[str, Any],
                 perception: Dict[str, Any]) -> Dict[str, Any]:
        reflection = {
            'should_speak':        False,
            'speech_reason':       None,
            'should_act':          False,
            'should_learn':        False,
            'should_process_file': False,
            'should_browse_web':   False,
            'confidence':          0.5,
        }

        now = time.time()

        # File processing is highest priority
        if thoughts.get('file_to_process'):
            reflection['should_process_file'] = True
            reflection['confidence']          = 0.95
            return reflection

        # Speech
        if thoughts['language_desire'] > 0.4:
            if now - self.last_speech_time > self.speech_cooldown:
                reflection['should_speak']   = True
                reflection['speech_reason']  = thoughts.get(
                    'speech_topic', 'general_expression'
                )

        # Action (normal urgency or deliberation found something worth doing)
        if perception['urgency'] > 0.6:
            if now - self.last_action_time > self.action_cooldown:
                reflection['should_act'] = True
        elif thoughts.get('deliberation') is not None:
            if (thoughts['deliberation'].best_action is not None and
                    now - self.last_action_time > self.action_cooldown):
                reflection['should_act'] = True

        # Web browsing
        if thoughts.get('should_browse'):
            reflection['should_browse_web'] = True
            reflection['confidence']        = 0.6

        # Learning
        if now - self.last_learning_time > self.learning_interval:
            if len(self.agent.memory.events) > 50:
                reflection['should_learn'] = True

        return reflection

    # =========================================================================
    # Decision
    # =========================================================================

    def _decide(self,
                reflection: Dict[str, Any],
                thoughts:   Dict[str, Any]) -> Dict[str, Any]:
        decision = {'type': 'none', 'content': None, 'priority': 0.0}

        if reflection['should_process_file']:
            decision.update(type='process_file',
                            content=thoughts.get('file_to_process'),
                            priority=1.0)

        elif reflection['should_speak']:
            decision.update(type='speak',
                            content={
                                'reason':           reflection['speech_reason'],
                                'language_desire':  thoughts['language_desire'],
                            },
                            priority=0.9)

        elif reflection['should_act']:
            # Pass deliberation result through so _execute_action can use it
            decision.update(type='action',
                            content={
                                'deliberation': thoughts.get('deliberation'),
                            },
                            priority=0.7)

        elif reflection['should_learn']:
            decision.update(type='learn', priority=0.3)

        elif reflection.get('should_browse_web'):
            decision.update(type='web_browse', priority=0.6)

        return decision

    # =========================================================================
    # Action execution
    # =========================================================================

    async def _act(self,
                   decision:   Dict[str, Any],
                   perception: Dict[str, Any],
                   thoughts:   Dict[str, Any]):
        dtype = decision['type']

        if dtype == 'process_file':
            await self._execute_file_processing(decision['content'])

        elif dtype == 'speak':
            await self._execute_autonomous_speech(
                perception, thoughts, decision['content']
            )

        elif dtype == 'action':
            delib = (decision.get('content') or {}).get('deliberation')
            await asyncio.gather(
                self._execute_action(perception, delib),
                self._execute_learning_async(),
                self._execute_continual_learning_async(),
                return_exceptions=True,
            )

        elif dtype == 'learn':
            await asyncio.gather(
                self._execute_learning_async(),
                self._execute_continual_learning_async(),
                return_exceptions=True,
            )

        elif dtype == 'web_browse':
            await self._execute_web_browsing()

    # =========================================================================
    # Interruptible action execution
    # =========================================================================

    async def _execute_action(self,
                               perception: Dict[str, Any],
                               deliberation=None):
        """
        Execute a plan step-by-step with interruption checks between steps.

        If a DeliberationResult is available, use its best_action as the
        starting point for the planner. After each step, re-evaluate whether
        the plan should be abandoned:
          - Urgency spike above 0.75
          - A fresh deliberation finds a >20% better option
        """
        try:
            context = {
                'health':   perception['state']['health'],
                'hunger':   perception['state']['hunger'],
                'emotions': perception['state']['emotions'],
                'position': {'x': 0, 'y': 64, 'z': 0},
                'novelty':  perception['novelty'],
                'urgency':  perception['urgency'],
            }

            # ── Select plan ──────────────────────────────────────────────
            # Prefer deliberation result; fall back to planner or single action
            plan: List[Dict] = []

            if deliberation is not None and deliberation.best_action is not None:
                # Deliberation already ranked candidates — build a plan
                # starting with the best action
                if (hasattr(self.agent, 'planner') and
                        self.agent.planner is not None):
                    plan = self.agent.planner.generate_plan(
                        obs=context,
                        memory=self.agent.memory,
                        horizon=3,
                        context=context,
                    )
                    # Replace first step with deliberation's best choice
                    if plan:
                        plan[0] = deliberation.best_action
                else:
                    plan = [deliberation.best_action]

                self.state.current_plan_score = deliberation.best_score

            elif hasattr(self.agent, 'planner') and self.agent.planner is not None:
                plan = self.agent.planner.generate_plan(
                    obs=context,
                    memory=self.agent.memory,
                    horizon=3,
                    context=context,
                )
                self.state.current_plan_score = 0.0

            if not plan:
                await asyncio.to_thread(self._action_worker, context)
                self.last_action_time = time.time()
                return

            # ── Execute plan with interruption checks ────────────────────
            self.state.current_plan  = plan
            self.state.plan_step     = 0

            for i, step in enumerate(plan):
                if not self.running:
                    break

                self.state.plan_step = i

                # Execute single step
                await asyncio.to_thread(
                    self._execute_planned_action, step, context
                )
                self.last_action_time = time.time()

                # ── Interruption check ────────────────────────────────
                # Re-perceive cheaply (just health/hunger/urgency)
                current_urgency = max(
                    1.0 - self.agent.health / 20.0,
                    max(
                        abs(v)
                        for v in self.agent.emotion.snapshot().values()
                    ) if self.agent.emotion.snapshot() else 0.0,
                )

                # Hard interrupt: urgent situation
                if current_urgency >= 0.75:
                    log.info(
                        f"[{self.agent.agent_id}] ⚠️  Plan interrupted: "
                        f"urgency={current_urgency:.2f}"
                    )
                    self.state.current_plan = None
                    break

                # Soft interrupt: deliberation found something much better
                if (i < len(plan) - 1 and          # not the last step
                        self.agent.brain.should_deliberate(
                            novelty=0.0,            # don't re-check novelty
                            urgency=current_urgency,
                            force=False,
                        )):
                    fresh_delib = self.agent.brain.deliberate(
                        perception={
                            'novelty':  0.0,
                            'urgency':  current_urgency,
                            'state':    perception['state'],
                        }
                    )
                    if fresh_delib.should_abort_current_plan(
                        self.state.current_plan_score
                    ):
                        log.info(
                            f"[{self.agent.agent_id}] 🔄 Plan superseded: "
                            f"new_score={fresh_delib.best_score:.3f} > "
                            f"current={self.state.current_plan_score:.3f}"
                        )
                        self.state.current_plan = None
                        break

            # Route completed action through reward system
            if hasattr(self.agent, 'reward_system') and self.agent.reward_system:
                event  = {'type': 'action', 'tags': ['action'], 'payload': context}
                signal = self.agent.reward_system.compute_reward(event=event)
                self.agent.reward_system.apply_signal(signal)

            self.state.current_plan = None

        except Exception as e:
            log.error(f"Action execution error: {e}", exc_info=True)

    def _execute_planned_action(self,
                                 action: Dict[str, Any],
                                 context: Dict[str, Any]):
        """
        Execute a single planned action in a worker thread.

        FIX Bug 1a — act() result was discarded, actions never reached Minecraft:
          The old code called agent.act() and threw away the returned controls dict.
          agent.act() / act_god() only CONVERT the action array — they do not send
          anything to Minecraft by themselves.  Sending requires calling
          minecraft_client.apply_action(controls).

          Additionally, god agents must use act_god() (18-dim) so that ability
          trigger dims 13-17 are decoded and included in the controls dict.

        FIX Bug 1b — god agents always used act() instead of act_god():
          act() clips to 13 dims, silently dropping the ability dims for gods.
          Now we check self.agent.god_type and route to act_god() when appropriate.
        """
        try:
            obs        = self.agent.perceive(context)
            action_arr = self.agent.decide(obs, deterministic=False)

            # Route: god agents use act_god (18-dim) to include ability dims;
            # NPC agents use act (13-dim).
            is_god = bool(getattr(self.agent, 'god_type', None))
            if is_god and len(action_arr) >= 18:
                controls = self.agent.act_god(action_arr)
            else:
                controls = self.agent.act(action_arr)

            # Send to Minecraft via the actuator — minecraft_client handles
            # TCP/WebSocket transport selection automatically.
            mc = getattr(self.agent, 'minecraft_client', None)
            if mc is not None:
                mc.apply_action(controls)
            else:
                log.debug(
                    f"[{self.agent.agent_id}] No minecraft_client — "
                    "action computed but not sent (autonomous-only mode)"
                )

            log.debug(
                f"[{self.agent.agent_id}] 🎬 Step: {action.get('type')}"
            )
        except Exception as e:
            log.error(f"Planned action error: {e}")

    def _action_worker(self, context: Dict[str, Any]):
        """
        Fallback: single unplanned action in worker thread.

        FIX Bug 1a/1b: same as _execute_planned_action — use act_god for gods,
        and send via minecraft_client.apply_action() so actions reach Minecraft.
        """
        try:
            obs        = self.agent.perceive(context)
            action_arr = self.agent.decide(obs, deterministic=False)

            is_god = bool(getattr(self.agent, 'god_type', None))
            if is_god and len(action_arr) >= 18:
                controls = self.agent.act_god(action_arr)
            else:
                controls = self.agent.act(action_arr)

            mc = getattr(self.agent, 'minecraft_client', None)
            if mc is not None:
                mc.apply_action(controls)
        except Exception as e:
            log.error(f"Action worker error: {e}")

    # =========================================================================
    # Speech
    # =========================================================================

    async def _execute_autonomous_speech(self,
                                          perception: Dict[str, Any],
                                          thoughts:   Dict[str, Any],
                                          content:    Dict[str, Any]):
        try:
            ctx = perception['state'].copy()
            ctx['recent_events']  = perception['recent_events']
            ctx['speech_reason']  = content['reason']
            ctx['language_desire'] = content['language_desire']

            speech = self.agent.brain.language.generate_speech(ctx)

            if speech and speech.strip():
                self.agent.memory.remember(
                    {
                        'type':             'autonomous_speech',
                        'text':             speech,
                        'reason':           content['reason'],
                        'context_snapshot': ctx,
                    },
                    tags=['language', 'output', 'autonomous', 'speech'],
                )
                await self._broadcast_speech(speech)
                self.last_speech_time       = time.time()
                self.state.last_speech      = speech
                self.state.speech_count    += 1
                log.info(f"[{self.agent.agent_id}] 💬 \"{speech[:60]}...\"")

        except Exception as e:
            log.error(f"Autonomous speech error: {e}", exc_info=True)

    # =========================================================================
    # File processing
    # =========================================================================

    async def _execute_file_processing(self, file_info: Dict[str, Any]):
        if not file_info:
            return
        try:
            file_path = file_info['path']
            filename  = file_info['filename']
            filetype  = file_info.get('filetype', 'text/plain')

            log.info(f"[{self.agent.agent_id}] 📄 Processing: {filename}")

            if self.file_buffer and self.file_buffer[0] == file_info:
                self.file_buffer.popleft()

            if hasattr(self.agent.brain, 'learn_from_file'):
                summary = await asyncio.to_thread(
                    self.agent.brain.learn_from_file, file_path, filetype
                )
                self.agent.memory.remember(
                    {
                        'type':      'file_processed',
                        'filename':  filename,
                        'path':      file_path,
                        'filetype':  filetype,
                        'summary':   summary,
                        'timestamp': time.time(),
                    },
                    tags=['learning', 'file', 'processed'],
                )
                try:
                    from chat_system import chat_system
                    await chat_system.send_message(
                        self.agent.agent_id,
                        f"📄 Processed: {filename}\n\n{summary}",
                        target='both',
                        sender='agent',
                    )
                except Exception:
                    pass
        except Exception as e:
            log.error(f"File processing error: {e}", exc_info=True)
            if file_info.get('_retry_count', 0) < 3:
                file_info['_retry_count'] = file_info.get('_retry_count', 0) + 1
                self.file_buffer.append(file_info)

    # =========================================================================
    # Web browsing
    # =========================================================================

    async def _execute_web_browsing(self):
        """
        Browse queued URLs. The browser handles the actual page visit;
        this method decides how many pages to visit and optionally
        broadcasts a summary of what the agent found.
        """
        if not hasattr(self.agent, 'web_browser'):
            return
        browser = self.agent.web_browser
        if not browser.browse_queue:
            return

        try:
            # Visit up to 2 pages per cognitive decision — keeps loop responsive
            pages_visited = 0
            while browser.browse_queue and pages_visited < 2:
                url      = browser.browse_queue[0]   # peek, don't pop yet
                snapshot = await browser.browse(url)
                pages_visited += 1

                if snapshot and snapshot.visible_text:
                    # Store in memory (browser already did this, but add a
                    # browsing-event tag so language learning picks it up)
                    self.agent.memory.remember(
                        {
                            'type':    'web_browsed',
                            'url':     snapshot.url,
                            'title':   snapshot.title,
                            'text':    snapshot.visible_text[:2000],
                            'summary': snapshot.get_summary(300),
                        },
                        tags=['web', 'learning', 'language'],
                    )

                    # If the agent is verbal, let it comment on what it found
                    if (hasattr(self.agent.brain, 'language') and
                            self.agent.brain.language.language_stage >= 1):
                        ctx = {
                            'web_page_title':   snapshot.title,
                            'web_page_summary': snapshot.get_summary(200),
                            'emotions':         self.agent.emotion.snapshot(),
                        }
                        comment = self.agent.brain.language.generate_speech(ctx)
                        if comment and comment.strip():
                            await self._broadcast_speech(comment)

                await asyncio.sleep(1.0)   # polite delay between pages

            log.info(
                f"[{self.agent.agent_id}] 🌐 Browsed {pages_visited} page(s)"
            )

        except Exception as e:
            log.error(f"Web browsing error: {e}", exc_info=True)

    # =========================================================================
    # Learning
    # =========================================================================

    async def _execute_learning_async(self):
        try:
            await asyncio.to_thread(self._learning_worker)
            self.last_learning_time = time.time()
        except Exception as e:
            log.error(f"Learning execution error: {e}")

    def _learning_worker(self):
        try:
            if hasattr(self.agent.brain, 'language'):
                batch = self.agent.memory.get_training_batch(
                    batch_size=32,
                    tags=['language', 'action', 'perception'],
                )
                if batch:
                    for event in batch:
                        if 'text' in event:
                            self.agent.brain.process_language_input(
                                event['text'],
                                event.get('context_snapshot', {}),
                            )
        except Exception as e:
            log.error(f"Learning worker error: {e}", exc_info=True)

    async def _execute_continual_learning_async(self):
        try:
            await asyncio.to_thread(self._continual_learning_worker)
        except Exception as e:
            log.debug(f"Continual learning trigger failed: {e}")

    def _continual_learning_worker(self):
        try:
            learner = getattr(self.agent, 'continual_learner', None)
            if learner is None:
                return
            res = learner.learn_from_buffer()
            log.info(
                f"[{self.agent.agent_id}] 🧠 Continual learning: {res}"
            )
        except Exception as e:
            log.error(f"Continual learning error: {e}", exc_info=True)

    # =========================================================================
    # State update
    # =========================================================================

    def _update_cognitive_state(self,
                                 perception: Dict[str, Any],
                                 thoughts:   Dict[str, Any],
                                 reflection: Dict[str, Any]):
        self.state.current_focus   = thoughts.get('focus')
        self.state.attention_level = (
            perception['novelty'] + perception['urgency']
        ) / 2.0
        self.state.energy_level   *= 0.9995
        self.state.energy_level    = max(0.3, self.state.energy_level)

        if perception['novelty'] > 0.7 or perception['urgency'] > 0.7:
            self.state.last_significant_event = {
                'perception': perception,
                'thoughts':   thoughts,
                'timestamp':  time.time(),
            }

        self.agent.emotion.decay()

    # =========================================================================
    # Input reception
    # =========================================================================

    def receive_visual_input(self,
                              frame: np.ndarray,
                              metadata: Optional[Dict] = None):
        self.agent.memory.remember(
            {
                'type':        'visual_input',
                'metadata':    metadata or {},
                'frame_shape': frame.shape if frame is not None else None,
            },
            tags=['perception', 'visual'],
        )

    def receive_audio_input(self,
                             audio:       np.ndarray,
                             sample_rate: int,
                             metadata:    Optional[Dict] = None):
        self.agent.memory.remember(
            {
                'type':        'audio_input',
                'sample_rate': sample_rate,
                'metadata':    metadata or {},
                'duration':    len(audio) / sample_rate if audio is not None else 0,
            },
            tags=['perception', 'audio'],
        )

    def receive_state_update(self, state: Dict[str, Any]):
        if 'health' in state:
            self.agent.health = state['health']
        if 'hunger' in state:
            self.agent.hunger = state['hunger']

    def receive_file(self, file_info: Dict[str, Any]):
        self.file_buffer.append(file_info)
        log.info(f"[CognitiveLoop] File queued: {file_info['filename']}")

    # =========================================================================
    # Broadcasting
    # =========================================================================

    async def _broadcast_speech(self, speech: str):
        try:
            if hasattr(self.agent, 'broadcast'):
                await self.agent.broadcast({
                    "type":      "chat",
                    "from":      "agent",
                    "text":      speech,
                    "timestamp": time.time(),
                })
        except Exception as e:
            log.error(f"Failed to broadcast speech: {e}")

        # Also push to Minecraft in-world chat when connected
        try:
            send_mc = getattr(self.agent, '_minecraft_send_chat', None)
            if send_mc is not None:
                await send_mc(speech)
        except Exception as e:
            log.debug(f"Minecraft chat push failed: {e}")

    async def _broadcast_internal_thought(self, thought: str):
        try:
            if hasattr(self.agent, 'broadcast'):
                await self.agent.broadcast({
                    "type":             "agent_thought",
                    "agent_id":         self.agent.agent_id,
                    "internal_thought": f"💭 {thought}",
                    "timestamp":        time.time(),
                })
        except Exception as e:
            log.debug(f"Failed to broadcast internal thought: {e}")

    async def _broadcast_mental_workspace(self, workspace_data: Dict[str, Any]):
        try:
            if hasattr(self.agent, 'broadcast'):
                await self.agent.broadcast({
                    "type":      "visualization_update",
                    "agent_id":  self.agent.agent_id,
                    "data":      workspace_data,
                    "timestamp": time.time(),
                })
        except Exception as e:
            log.debug(f"Failed to broadcast workspace: {e}")

    async def _broadcast_audio_heard(self,
                                      transcription: str,
                                      emotion:       Optional[str]):
        try:
            emoji = {
                'excited': '😄', 'angry': '😠', 'sad': '😢',
                'calm': '😌',   'neutral': '😐',
            }.get(emotion, '👂')
            if hasattr(self.agent, 'broadcast'):
                await self.agent.broadcast({
                    "type":      "chat",
                    "from":      "system",
                    "text":      f"{emoji} Heard: \"{transcription}\"",
                    "timestamp": time.time(),
                })
        except Exception as e:
            log.debug(f"Failed to broadcast audio: {e}")

    # =========================================================================
    # Status
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        return {
            'running':          self.running,
            'cycle_count':      self.state.cycle_count,
            'speech_count':     self.state.speech_count,
            'last_speech':      self.state.last_speech,
            'focus':            self.state.current_focus,
            'attention':        self.state.attention_level,
            'energy':           self.state.energy_level,
            'last_speech_time': self.last_speech_time,
            'speech_cooldown':  self.speech_cooldown,
            'files_queued':     len(self.file_buffer),
            'plan_active':      self.state.current_plan is not None,
            'plan_step':        self.state.plan_step,
        }