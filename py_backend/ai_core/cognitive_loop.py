# ai_core/cognitive_loop.py - COMPLETE UNIFIED VERSION
"""
Autonomous Cognitive Loop with Full Integration
================================================
Combines best features from both cognitive_loop.py and coggnitive_loop.py:
- True autonomous thinking and speaking
- File processing integration
- Unified memory usage
- Enhanced language generation
"""

import asyncio
import time
import numpy as np
from typing import Dict, Any, Optional, List
from collections import deque
import logging

log = logging.getLogger("cognitive_loop")


class CognitiveState:
    """Tracks agent's cognitive state"""

    def __init__(self):
        self.current_focus: Optional[str] = None
        self.active_goal: Optional[str] = None
        self.attention_level: float = 0.5
        self.energy_level: float = 1.0
        self.last_significant_event: Optional[Dict] = None
        self.cycle_count: int = 0
        self.last_speech: Optional[str] = None
        self.speech_count: int = 0


class CognitiveLoop:
    """
    FULLY INTEGRATED Autonomous cognitive cycle.

    Features:
    - Uses UnifiedMemoryStore
    - Directly triggers language generation
    - Processes files autonomously
    - Connects to chat_system for output
    - Full personality integration
    """

    def __init__(self, agent, loop_interval: float = 0.5):
        self.agent = agent
        self.loop_interval = loop_interval

        # Input buffers
        self.visual_buffer = deque(maxlen=10)
        self.audio_buffer = deque(maxlen=5)
        self.state_buffer = deque(maxlen=20)
        self.event_buffer = deque(maxlen=50)
        self.file_buffer = deque(maxlen=20)  # CRITICAL: File processing queue

        # Cognitive state
        self.state = CognitiveState()

        # Timing control
        self.last_action_time = 0
        self.last_speech_time = 0
        self.last_learning_time = 0

        # Thresholds (personality-adjusted)
        self._update_thresholds()

        # Control
        self.running = False
        self.task = None

        log.info(f"CognitiveLoop initialized for {agent.agent_id}")

    def _update_thresholds(self):
        """Update thresholds based on personality"""
        personality = self.agent.personality.traits

        # Speech cooldown shorter for extraverts
        extraversion = personality.get('extraversion', 0.0)
        sociability = personality.get('sociability', 0.5)

        base_cooldown = 15.0
        self.speech_cooldown = base_cooldown * (1.0 - (extraversion + sociability) / 4.0)
        self.speech_cooldown = max(5.0, self.speech_cooldown)

        # Action cooldown
        boldness = personality.get('boldness', 0.5)
        self.action_cooldown = 2.0 * (1.0 - boldness * 0.5)

        # Learning interval
        openness = personality.get('openness', 0.5)
        self.learning_interval = 30.0 * (1.0 - openness * 0.3)

        log.debug(f"Thresholds: speech={self.speech_cooldown:.1f}s, "
                 f"action={self.action_cooldown:.1f}s")

    # ==================== CONTROL ====================

    async def start(self):
        """Start autonomous cognitive loop"""
        if self.running:
            log.warning(f"Cognitive loop already running for {self.agent.agent_id}")
            return

        self.running = True
        self.task = asyncio.create_task(self._cognitive_loop())
        log.info(f"✅ Cognitive loop started for {self.agent.agent_id}")

    async def stop(self):
        """Stop autonomous loop gracefully"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        log.info(f"🛑 Cognitive loop stopped for {self.agent.agent_id}")

    # ==================== MAIN LOOP ====================

    async def _cognitive_loop(self):
        """Main autonomous cognitive cycle"""
        log.info(f"🧠 Starting cognitive cycle for {self.agent.agent_id}")

        while self.running:
            try:
                cycle_start = time.time()

                # === 1. PERCEIVE ===
                perception = self._perceive()

                # === 2. THINK ===
                thoughts = await self._think(perception)

                # === 3. REFLECT ===
                reflection = self._reflect(thoughts, perception)

                # === 4. DECIDE ===
                decision = self._decide(reflection, thoughts)

                # === 5. ACT (INCLUDING SPEECH & FILES) ===
                await self._act(decision, perception, thoughts)

                # === 6. UPDATE STATE ===
                self._update_cognitive_state(perception, thoughts, reflection)

                self.state.cycle_count += 1

                # Log periodically
                if self.state.cycle_count % 100 == 0:
                    log.info(f"[{self.agent.agent_id}] Cycle {self.state.cycle_count}: "
                            f"Focus={self.state.current_focus}, "
                            f"Speeches={self.state.speech_count}")

                # Wait for next cycle
                elapsed = time.time() - cycle_start
                sleep_time = max(0.01, self.loop_interval - elapsed)
                await asyncio.sleep(sleep_time)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Cognitive loop error for {self.agent.agent_id}: {e}",
                         exc_info=True)
                await asyncio.sleep(1.0)

    # ==================== PERCEPTION ====================

    def _perceive(self) -> Dict[str, Any]:
        """Gather current state from unified memory"""
        perception = {
            'timestamp': time.time(),
            'state': {
                'health': self.agent.health,
                'hunger': self.agent.hunger,
                'emotions': self.agent.emotion.snapshot(),
                'dominant_emotion': self.agent.emotion.dominant_emotion(),
                'memory_size': len(self.agent.memory.events)
            },
            'recent_events': [],
            'novelty': 0.0,
            'urgency': 0.0
        }

        # Get recent events from unified memory
        recent = self.agent.memory.recall(n=10)
        perception['recent_events'] = recent

        # Calculate novelty
        if recent:
            novelty_scores = []
            for event in recent[-3:]:
                event_type = event.get('type', 'unknown')
                type_count = sum(1 for e in recent if e.get('type') == event_type)
                novelty = 1.0 / (1.0 + type_count)
                novelty_scores.append(novelty)

            perception['novelty'] = np.mean(novelty_scores) if novelty_scores else 0.0

        # Calculate urgency
        emotion_intensity = max(abs(v) for v in perception['state']['emotions'].values())
        health_urgency = 1.0 - (perception['state']['health'] / 20.0)
        perception['urgency'] = max(emotion_intensity, health_urgency)

        return perception

    # ==================== THINKING ====================

    async def _think(self, perception: Dict[str, Any]) -> Dict[str, Any]:
        """Process perception and decide what to focus on"""
        thoughts = {
            'focus': None,
            'language_desire': 0.0,
            'speech_topic': None,
            'curiosity': 0.0,
            'analysis': {},
            'should_think_deeply': False,
            'file_to_process': None,
            'should_browse': False,
            'should_simulate': False,
            'should_think_verbally': False,
            'should_listen': False,
            'audio_data': None,
            'internal_thoughts': [],
            'mental_workspace': None
    }

        # Quick check
        if perception['novelty'] < 0.2 and perception['urgency'] < 0.3 and not self.file_buffer:
            return thoughts

        thoughts['should_think_deeply'] = True

        # === PROCESS AUDIO INPUT (if available) ===
        if hasattr(self.agent, 'audio_processor'):
            audio_result = await asyncio.to_thread(
                lambda: self.agent.audio_processor.process_audio_chunk()
            )

            if audio_result and audio_result.get('transcription'):
                thoughts['audio_data'] = audio_result

                # If speech heard, trigger language processing
                transcription = audio_result['transcription']

                # Process as language input
                context = {
                    'health': perception['state']['health'],
                    'hunger': perception['state']['hunger'],
                    'emotions': perception['state']['emotions']
                }

                response = self.agent.brain.language.process_language_input(
                    transcription,
                    context
                )

                # Broadcast heard speech to frontend
                await self._broadcast_audio_heard(transcription, audio_result.get('emotion'))

                # If agent generates response, speak it
                if response and len(response) > 0:
                    await self._broadcast_speech(response)

        # Evaluate recent events
        event = {
            'type': 'autonomous_perception',
            'tags': ['autonomous', 'perception'],
            'payload': {
                'novelty': perception['novelty'],
                'urgency': perception['urgency']
            }
        }

        reward, emotion_delta = self.agent.brain.evaluate_event(
            event,
            perception['state']
        )

        # Update emotions
        for emotion, value in emotion_delta.items():
            self.agent.emotion.add(emotion, value)

        thoughts['analysis'] = {
            'reward': reward,
            'emotion_delta': emotion_delta
        }

        # === AUTONOMOUS DECISION: Should I listen? ===
        # Agent decides whether to actively listen to audio
        if hasattr(self.agent, 'audio_processor'):
            sociability = self.agent.personality.traits.get('sociability', 0.5)
            openness = self.agent.personality.traits.get('openness', 0.5)
            curiosity = self.agent.personality.traits.get('curiosity', 0.5)

            listening_desire = (
                sociability * 0.4 +  # Social agents listen more
                openness * 0.3 +
                curiosity * 0.2 +
                perception['novelty'] * 0.1
            )

            # Autonomous decision
            if listening_desire > 0.4 and np.random.rand() < listening_desire:
                thoughts['should_listen'] = True

                if not self.agent.audio_processor.is_listening:
                    self.agent.audio_processor.start_listening()
            else:
                # Agent chooses not to listen
                if self.agent.audio_processor.is_listening:
                    self.agent.audio_processor.stop_listening()

        # === AUTONOMOUS DECISION: Should I simulate? ===
        # Agent decides based on:
        # - Novelty (new situations warrant mental simulation)
        # - Urgency (dangerous situations need planning)
        # - Curiosity trait (curious agents simulate more)
        # - Personality (conscientious agents plan more)

        curiosity = self.agent.personality.traits.get('curiosity', 0.5)
        conscientiousness = self.agent.personality.traits.get('conscientiousness', 0.5)

        simulation_desire = (
            perception['novelty'] * 0.4 +
            perception['urgency'] * 0.3 +
            curiosity * 0.2 +
            conscientiousness * 0.1
        )

        # Stochastic decision (not forced)
        if simulation_desire > 0.5 and np.random.rand() < simulation_desire:
            thoughts['should_simulate'] = True

            # Run mental simulation
            if hasattr(self.agent, 'imagine_scenario'):
                scenario_data = self.agent.imagine_scenario(perception['state'])
                thoughts['mental_workspace'] = scenario_data

                # Broadcast to frontend
                await self._broadcast_mental_workspace(scenario_data)

            # === AUTONOMOUS DECISION: Should I think in words? ===
            # Separate from simulation - agent might simulate without verbalizing
            # or verbalize without simulating

            sociability = self.agent.personality.traits.get('sociability', 0.5)
            openness = self.agent.personality.traits.get('openness', 0.5)

            # Introverted agents have more internal monologue
            verbal_thinking_desire = (
                (1.0 - sociability) * 0.4 +  # Introverts think more verbally
                openness * 0.3 +
                perception['novelty'] * 0.2 +
                emotion_delta.get('surprise', 0) * 0.1
            )

            if verbal_thinking_desire > 0.4 and np.random.rand() < verbal_thinking_desire:
                thoughts['should_think_verbally'] = True

                # Generate internal thought
                if hasattr(self.agent, 'generate_internal_thought'):
                    context = {
                        'health': perception['state']['health'],
                        'hunger': perception['state']['hunger'],
                        'emotions': perception['state']['emotions'],
                        'novelty': perception['novelty'],
                            'urgency': perception['urgency']
                    }

                    internal_thought = self.agent.generate_internal_thought(context)

                    if internal_thought:
                        # Broadcast to frontend as internal thought
                        await self._broadcast_internal_thought(internal_thought)

        # === LANGUAGE DESIRE CALCULATION ===
        lang_factors = []

        # 1. Strong emotions trigger expression
        emotion_intensity = max(abs(v) for v in perception['state']['emotions'].values())
        if emotion_intensity > 0.5:
            lang_factors.append(('strong_emotion', emotion_intensity))

        # 2. Novel experiences trigger commentary
        if perception['novelty'] > 0.6:
            lang_factors.append(('novelty', perception['novelty']))

        # 3. Personality traits
        sociability = self.agent.personality.traits.get('sociability', 0.5)
        extraversion = self.agent.personality.traits.get('extraversion', 0.0)
        lang_factors.append(('personality', (sociability + extraversion + 2.0) / 4.0))

        # 4. Time since last speech (builds up desire)
        time_since_speech = time.time() - self.last_speech_time
        time_factor = min(1.0, time_since_speech / self.speech_cooldown)
        if time_factor > 0.5:
            lang_factors.append(('time_pressure', time_factor))

        # 5. Recent conversation context
        recent_speech = [e for e in perception['recent_events']
                        if e.get('type') in ['language_input', 'language_output']]

        if recent_speech and time_since_speech < 30:
            lang_factors.append(('conversation_context', 0.8))
            thoughts['speech_topic'] = 'conversation_response'

        # 6. Internal monologue (urgent thoughts)
        if perception['urgency'] > 0.6:
            lang_factors.append(('urgent_thoughts', perception['urgency']))
            thoughts['speech_topic'] = 'urgent_situation'

        # Combine factors
        if lang_factors:
            weights = [factor[1] for factor in lang_factors]
            thoughts['language_desire'] = np.mean(weights)

            log.debug(f"Language desire: {thoughts['language_desire']:.2f} "
                     f"from {[f[0] for f in lang_factors]}")

        # === FILE PROCESSING CHECK ===
        if self.file_buffer:
            file_info = self.file_buffer[0]
            thoughts['file_to_process'] = file_info
            log.info(f"[Thinking] File queued: {file_info['filename']}")
        else:
            # Check memory for recently uploaded files not yet processed
            try:
                recent_events = self.agent.memory.recall(n=50)
                for ev in reversed(recent_events):
                    if ev.get('type') == 'file_uploaded':
                        fn = ev.get('filename')
                        # Check if already processed
                        already_processed = any(
                            e.get('type') == 'file_processed' and e.get('filename') == fn
                            for e in recent_events
                        )
                        if not already_processed:
                            self.file_buffer.append({
                                'path': ev.get('path'),
                                'filename': fn,
                                'filetype': ev.get('filetype'),
                                'size': ev.get('size'),
                                'timestamp': ev.get('timestamp')
                            })
                            thoughts['file_to_process'] = self.file_buffer[0]
                            log.info(f"[Thinking] Found unprocessed file: {fn}")
                            break
            except Exception as e:
                log.error(f"Error checking for files: {e}")

        # Check if agent wants to browse (when curious and has allowed sites)
        if thoughts['curiosity'] > 0.6 and hasattr(self.agent, 'web_browser'):
            browser = self.agent.web_browser
            if browser.allowed_domains and browser.browse_queue:
                thoughts['should_browse'] = True

        # Determine focus
        if perception['urgency'] > 0.7:
            thoughts['focus'] = 'survival'
        elif thoughts['file_to_process']:
            thoughts['focus'] = 'learning'  # Files are learning opportunities
        elif thoughts['language_desire'] > 0.4:
            thoughts['focus'] = 'expression'
        elif perception['novelty'] > 0.6:
            thoughts['focus'] = 'exploration'
        else:
            thoughts['focus'] = 'observation'

        return thoughts

    # ==================== REFLECTION ====================

    def _reflect(self, thoughts: Dict[str, Any], perception: Dict[str, Any]) -> Dict[str, Any]:
        """Decide what to do"""
        reflection = {
            'should_speak': False,
            'speech_reason': None,
            'should_act': False,
            'should_learn': False,
            'should_process_file': False,
            'confidence': 0.5,
            'should_browse_web': False

        }

        current_time = time.time()

        # === FILE PROCESSING DECISION ===
        # Files are highest priority
        if thoughts.get('file_to_process'):
            reflection['should_process_file'] = True
            reflection['confidence'] = 0.95
            return reflection  # Process file immediately

        # === SPEECH DECISION ===
        if thoughts['language_desire'] > 0.4:
            if current_time - self.last_speech_time > self.speech_cooldown:
                reflection['should_speak'] = True
                reflection['speech_reason'] = thoughts.get('speech_topic', 'general_expression')

                log.info(f"💬 {self.agent.agent_id} deciding to speak: "
                        f"desire={thoughts['language_desire']:.2f}, "
                        f"reason={reflection['speech_reason']}")

        # === ACTION DECISION ===
        if perception['urgency'] > 0.6:
            if current_time - self.last_action_time > self.action_cooldown:
                reflection['should_act'] = True

        # === WEB BROWSING DECISION ===
        if thoughts.get('should_browse'):
            reflection['should_browse_web'] = True
            reflection['confidence'] = 0.6


        # === LEARNING DECISION ===
        if current_time - self.last_learning_time > self.learning_interval:
            if len(self.agent.memory.events) > 50:
                reflection['should_learn'] = True

        return reflection

    # ==================== DECISION ====================

    def _decide(self, reflection: Dict[str, Any], thoughts: Dict[str, Any]) -> Dict[str, Any]:
        """Final decision on what to do"""
        decision = {
            'type': 'none',
            'content': None,
            'priority': 0.0
        }

        # Priority: file > speech > action > learning
        if reflection['should_process_file']:
            decision['type'] = 'process_file'
            decision['content'] = thoughts.get('file_to_process')
            decision['priority'] = 1.0

        elif reflection['should_speak']:
            decision['type'] = 'speak'
            decision['content'] = {
                'reason': reflection['speech_reason'],
                'language_desire': thoughts['language_desire']
            }
            decision['priority'] = 0.9

        elif reflection['should_act']:
            decision['type'] = 'action'
            decision['priority'] = 0.7

        elif reflection['should_learn']:
            decision['type'] = 'learn'
            decision['priority'] = 0.3
        elif reflection.get('should_browse_web'):
            decision['type'] = 'web_browse'
            decision['priority'] = 0.6

        return decision

    # ==================== ACTION EXECUTION ====================

    async def _act(self, decision: Dict[str, Any],
                   perception: Dict[str, Any],
                   thoughts: Dict[str, Any]):
        """Execute decision concurrently - action, learning, and policy updates run in parallel"""

        if decision['type'] == 'process_file':
            await self._execute_file_processing(decision['content'])

        elif decision['type'] == 'speak':
            await self._execute_autonomous_speech(perception, thoughts, decision['content'])

        elif decision['type'] == 'action':
            # RUN CONCURRENTLY: action + learning + policy update in parallel threads
            await asyncio.gather(
                self._execute_action(perception),
                self._execute_learning_async(),
                self._execute_continual_learning_async(),
                return_exceptions=True
            )

        elif decision['type'] == 'learn':
            # RUN CONCURRENTLY: language learning + policy learning in parallel
            await asyncio.gather(
                self._execute_learning_async(),
                self._execute_continual_learning_async(),
                return_exceptions=True
            )

        elif decision['type'] == 'web_browse':
            await self._execute_web_browsing()

    async def _execute_file_processing(self, file_info: Dict[str, Any]):
        """
        Process uploaded file autonomously.
        CRITICAL: This is how agents learn from documents.
        """
        if not file_info:
            return

        try:
            file_path = file_info['path']
            filename = file_info['filename']
            filetype = file_info.get('filetype', 'text/plain')

            log.info(f"[{self.agent.agent_id}] 📄 Processing file: {filename}")

            # Remove from queue
            if self.file_buffer and self.file_buffer[0] == file_info:
                self.file_buffer.popleft()

            # Process using brain's file learning
            if hasattr(self.agent.brain, 'learn_from_file'):
                summary = await asyncio.to_thread(
                    self.agent.brain.learn_from_file,
                    file_path,
                    filetype
                )

                log.info(f"[{self.agent.agent_id}] ✅ File processed: {summary[:120]}")

                # Store processing result in memory
                self.agent.memory.remember({
                    'type': 'file_processed',
                    'filename': filename,
                    'path': file_path,
                    'filetype': filetype,
                    'summary': summary,
                    'timestamp': time.time()
                }, tags=['learning', 'file', 'processed'])

                # Notify via chat system
                try:
                    from unified_chat_system import chat_system
                    await chat_system.send_message(
                        self.agent.agent_id,
                        f"📄 Processed file: {filename}\n\n{summary}",
                        target='both',
                        sender='agent'
                    )
                except Exception as e:
                    log.debug(f"Chat notification failed: {e}")

            else:
                log.warning(f"No file learning capability in brain")

        except Exception as e:
            log.error(f"File processing error: {e}", exc_info=True)
            # Re-queue for retry (max 3 attempts)
            if file_info.get('_retry_count', 0) < 3:
                file_info['_retry_count'] = file_info.get('_retry_count', 0) + 1
                self.file_buffer.append(file_info)
    async def _execute_web_browsing(self):
        """
        Execute autonomous web browsing.
        Just browses queued URLs - brain/memory handle learning naturally.
        """
        if not hasattr(self.agent, 'web_browser'):
            return

        try:
            from ai_core.web_browser import browse_if_curious
            await browse_if_curious(self.agent, max_pages=2)

        except Exception as e:
            log.error(f"Web browsing error: {e}")

    async def _execute_autonomous_speech(self, perception: Dict[str, Any],
                                         thoughts: Dict[str, Any],
                                         content: Dict[str, Any]):
        """
        Generate and broadcast autonomous speech.
        This is where the agent ACTUALLY SPEAKS on its own!
        """
        try:
            # Build context for language generation
            context = perception['state'].copy()
            context['recent_events'] = perception['recent_events']
            context['speech_reason'] = content['reason']
            context['language_desire'] = content['language_desire']

            # Generate speech using language intelligence
            speech = self.agent.brain.language.generate_speech(context)

            if speech and len(speech.strip()) > 0:
                # Store in unified memory
                self.agent.memory.remember({
                    'type': 'autonomous_speech',
                    'text': speech,
                    'reason': content['reason'],
                    'context_snapshot': context
                }, tags=['language', 'output', 'autonomous', 'speech'])

                # Broadcast to chat system
                await self._broadcast_speech(speech)

                # Update state
                self.last_speech_time = time.time()
                self.state.last_speech = speech
                self.state.speech_count += 1

                log.info(f"[{self.agent.agent_id}] 💬 SPOKE: \"{speech[:60]}...\"")

        except Exception as e:
            log.error(f"Autonomous speech error: {e}", exc_info=True)

    async def _broadcast_speech(self, speech: str):
        """Send speech to all connected systems"""
        try:
            await self.agent.broadcast({
                "type": "chat",
                "from": "agent",
                "text": speech,
                "timestamp": time.time()
            })

        except Exception as e:
            log.error(f"Failed to broadcast speech: {e}")

    async def _execute_action(self, perception: Dict[str, Any]):
        """Execute physical action (runs in thread pool to avoid blocking)"""
        try:
            obs_dict = {
                'health': perception['state']['health'],
                'hunger': perception['state']['hunger'],
                'position': {'x': 0, 'y': 64, 'z': 0}
            }

            # Run blocking operations in thread pool
            await asyncio.to_thread(self._action_worker, obs_dict)
            self.last_action_time = time.time()

        except Exception as e:
            log.error(f"Action execution error: {e}")

    def _action_worker(self, obs_dict: Dict[str, Any]):
        """Worker thread for action execution"""
        try:
            obs = self.agent.perceive(obs_dict)
            action_array = self.agent.decide(obs, deterministic=False)
            action_dict = self.agent.act(action_array)
            log.debug(f"[{self.agent.agent_id}] 🎬 Action executed")
        except Exception as e:
            log.error(f"Action worker error: {e}")

    async def _execute_learning_async(self):
        """Trigger language learning update (async, runs in thread pool)"""
        try:
            await asyncio.to_thread(self._learning_worker)
            self.last_learning_time = time.time()
        except Exception as e:
            log.error(f"Learning execution error: {e}")

    def _learning_worker(self):
        """Worker thread for language learning"""
        try:
            # Train language on recent experiences
            if hasattr(self.agent.brain, 'language'):
                # Use unified memory for training
                training_batch = self.agent.memory.get_training_batch(
                    batch_size=32,
                    tags=['language', 'action', 'perception']
                )

                if training_batch:
                    # Process batch through language system
                    for event in training_batch:
                        if 'text' in event:
                            context = event.get('context_snapshot', {})
                            self.agent.brain.language.process_language_input(
                                event['text'],
                                context
                            )

            log.debug(f"[{self.agent.agent_id}] 📚 Language learning update")
        except Exception as e:
            log.error(f"Learning worker error: {e}", exc_info=True)

    async def _execute_continual_learning_async(self):
        """Trigger Avalanche continual learning (async, runs in thread pool)"""
        try:
            await asyncio.to_thread(self._continual_learning_worker)
        except Exception as e:
            log.debug(f"Continual learning trigger failed: {e}")

    def _continual_learning_worker(self):
        """Worker thread for Avalanche continual learning and policy updates"""
        try:
            learner = getattr(self.agent, 'continual_learner', None)
            if learner is None:
                return
            # Perform a single update if enough experiences collected
            res = learner.learn_from_buffer()
            log.info(f"[{self.agent.agent_id}] 🧠 Continual learning (policy updated): {res}")
        except Exception as e:
            log.error(f"Continual learning error: {e}", exc_info=True)

    # ==================== STATE UPDATE ====================

    def _update_cognitive_state(self, perception: Dict[str, Any],
                                thoughts: Dict[str, Any],
                                reflection: Dict[str, Any]):
        """Update internal cognitive state"""
        self.state.current_focus = thoughts.get('focus')
        self.state.attention_level = (perception['novelty'] + perception['urgency']) / 2.0
        self.state.energy_level *= 0.9995
        self.state.energy_level = max(0.3, self.state.energy_level)

        # Store significant events
        if perception['novelty'] > 0.7 or perception['urgency'] > 0.7:
            self.state.last_significant_event = {
                'perception': perception,
                'thoughts': thoughts,
                'timestamp': time.time()
            }

        # Natural emotion decay
        self.agent.emotion.decay()

    # ==================== INPUT RECEPTION ====================

    def receive_visual_input(self, frame: np.ndarray, metadata: Optional[Dict] = None):
        """Receive visual input"""
        self.agent.memory.remember({
            'type': 'visual_input',
            'metadata': metadata or {},
            'frame_shape': frame.shape if frame is not None else None
        }, tags=['perception', 'visual'])

    def receive_audio_input(self, audio: np.ndarray, sample_rate: int,
                           metadata: Optional[Dict] = None):
        """Receive audio input"""
        self.agent.memory.remember({
            'type': 'audio_input',
            'sample_rate': sample_rate,
            'metadata': metadata or {},
            'duration': len(audio) / sample_rate if audio is not None else 0
        }, tags=['perception', 'audio'])

    def receive_state_update(self, state: Dict[str, Any]):
        """Receive state update"""
        if 'health' in state:
            self.agent.health = state['health']
        if 'hunger' in state:
            self.agent.hunger = state['hunger']

    def receive_file(self, file_info: Dict[str, Any]):
        """Receive file for processing"""
        self.file_buffer.append(file_info)
        log.info(f"[CognitiveLoop] File queued: {file_info['filename']}")

    # ==================== BROADCASTING ====================

    async def _broadcast_internal_thought(self, thought: str):
        """Send internal thought to frontend (not spoken aloud)"""
        try:
            await self.agent.broadcast({
                "type": "agent_thought",
                "agent_id": self.agent.agent_id,
                "internal_thought": f"💭 {thought}",
                "timestamp": time.time()
            })
        except Exception as e:
            log.debug(f"Failed to broadcast internal thought: {e}")


    async def _broadcast_mental_workspace(self, workspace_data: Dict[str, Any]):
        """Send world model visualization to frontend"""
        try:
            await self.agent.broadcast({
                "type": "visualization_update",
                "agent_id": self.agent.agent_id,
                "data": workspace_data,
                "timestamp": time.time()
            })
        except Exception as e:
            log.debug(f"Failed to broadcast workspace: {e}")

    async def _broadcast_audio_heard(self, transcription: str, emotion: Optional[str]):
        """Broadcast heard audio to frontend"""
        try:
            emotion_emoji = {
                'excited': '😄',
                'angry': '😠',
                'sad': '😢',
                'calm': '😌',
                'neutral': '😐'
            }.get(emotion, '👂')

            await self.agent.broadcast({
                "type": "chat",
                "from": "system",
                "text": f"{emotion_emoji} Heard: \"{transcription}\"",
                "timestamp": time.time()
            })
        except Exception as e:
            log.debug(f"Failed to broadcast audio: {e}")

    # ==================== STATUS ====================

    def get_status(self) -> Dict[str, Any]:
        """Get cognitive loop status"""
        return {
            'running': self.running,
            'cycle_count': self.state.cycle_count,
            'speech_count': self.state.speech_count,
            'last_speech': self.state.last_speech,
            'focus': self.state.current_focus,
            'attention': self.state.attention_level,
            'energy': self.state.energy_level,
            'last_speech_time': self.last_speech_time,
            'speech_cooldown': self.speech_cooldown,
            'files_queued': len(self.file_buffer)
        }
