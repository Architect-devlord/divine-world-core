# ai_core/cognitive_loop.py
"""
Autonomous Cognitive Loop - Think, Reflect, Act
================================================
Gives agents true autonomy by continuously:
1. PERCEIVE - Process visual/audio/state inputs
2. THINK - Evaluate situation, retrieve memories
3. REFLECT - Assess emotions, goals, context
4. DECIDE - Choose whether to act/speak/learn
5. ACT - Execute action or generate speech

No external triggers needed - agent decides when to act.
"""

import asyncio
import time
import numpy as np
from typing import Dict, Any, Optional, List
from collections import deque
import logging

log = logging.getLogger("cognitive_loop")


class CognitiveState:
    """Tracks agent's cognitive state across cycles"""
    
    def __init__(self):
        self.current_focus: Optional[str] = None
        self.active_goal: Optional[str] = None
        self.attention_level: float = 0.5
        self.energy_level: float = 1.0
        self.last_significant_event: Optional[Dict] = None
        self.cycle_count: int = 0


class CognitiveLoop:
    """
    Autonomous cognitive cycle for agents.
    Runs independently, processes continuous inputs, decides when to act/speak.
    """
    
    def __init__(self, agent, loop_interval: float = 0.5):
        self.agent = agent
        self.loop_interval = loop_interval
        
        # Input buffers (thread-safe deques)
        self.visual_buffer = deque(maxlen=10)
        self.audio_buffer = deque(maxlen=5)
        self.state_buffer = deque(maxlen=20)
        self.event_buffer = deque(maxlen=50)
        self.file_buffer = deque(maxlen=20)  # Files to process
        
        # Cognitive state
        self.state = CognitiveState()
        
        # Timing control
        self.last_action_time = 0
        self.last_speech_time = 0
        self.last_learning_time = 0
        
        # Thresholds for autonomous behavior
        self.action_cooldown = 1.0  # seconds between actions
        self.speech_cooldown = 10.0  # seconds between autonomous speech
        self.learning_interval = 30.0  # seconds between learning updates
        self.think_threshold = 0.3  # novelty level to trigger deep thinking
        
        # Behavior weights (personality-influenced)
        self._update_behavior_weights()
        
        # Control
        self.running = False
        self.task = None
        
        log.info(f"CognitiveLoop initialized for {agent.agent_id}")
    
    def _update_behavior_weights(self):
        """Update behavior weights based on personality"""
        personality = self.agent.personality.traits
        
        self.weights = {
            'exploration': personality.get('curiosity', 0.5) * 0.7 + 0.3,
            'social': personality.get('sociability', 0.5) * 0.8 + 0.2,
            'cautious': personality.get('neuroticism', 0.0) * 0.5 + 0.5,
            'reactive': personality.get('boldness', 0.5) * 0.6 + 0.4,
            'learning': personality.get('openness', 0.5) * 0.8 + 0.2
        }
    
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
                
                # === 5. ACT ===
                await self._act(decision, perception)
                
                # === 6. UPDATE STATE ===
                self._update_cognitive_state(perception, thoughts, reflection)
                
                # Cycle complete
                self.state.cycle_count += 1
                
                # Log periodically
                if self.state.cycle_count % 100 == 0:
                    log.info(f"[{self.agent.agent_id}] Cycle {self.state.cycle_count}: "
                            f"Focus={self.state.current_focus}, "
                            f"Energy={self.state.energy_level:.2f}")
                
                # Wait for next cycle
                elapsed = time.time() - cycle_start
                sleep_time = max(0.01, self.loop_interval - elapsed)
                await asyncio.sleep(sleep_time)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"Cognitive loop error for {self.agent.agent_id}: {e}", 
                         exc_info=True)
                await asyncio.sleep(1.0)  # Prevent tight error loop
    
    # ==================== PERCEPTION ====================
    
    def _perceive(self) -> Dict[str, Any]:
        """
        Gather current sensory inputs and compute novelty.
        Returns unified perception dict.
        """
        perception = {
            'timestamp': time.time(),
            'visual': None,
            'audio': None,
            'state': {},
            'events': [],
            'novelty': 0.0,
            'urgency': 0.0
        }
        
        # === Visual Input ===
        if self.visual_buffer:
            latest_visual = self.visual_buffer[-1]
            perception['visual'] = latest_visual.get('frame')
            
            # Compute visual novelty using pattern recognizer
            if perception['visual'] is not None:
                pattern_result = self.agent.brain.pattern_recognizer.observe_pattern(
                    'visual', 
                    perception['visual']
                )
                perception['novelty'] = max(perception['novelty'], 
                                           pattern_result.get('novelty', 0.0))
        
        # === Audio Input ===
        if self.audio_buffer:
            latest_audio = self.audio_buffer[-1]
            perception['audio'] = latest_audio.get('audio')
            
            # Audio novelty
            if perception['audio'] is not None:
                audio_pattern = self.agent.brain.pattern_recognizer.observe_pattern(
                    'audio',
                    perception['audio']
                )
                perception['novelty'] = max(perception['novelty'],
                                           audio_pattern.get('novelty', 0.0))
        
        # === State ===
        perception['state'] = {
            'health': self.agent.health,
            'hunger': self.agent.hunger,
            'emotions': self.agent.emotion.snapshot(),
            'dominant_emotion': self.agent.emotion.dominant_emotion(),
            'memory_size': len(self.agent.memory.events),
            'step_count': self.agent.step_count
        }
        
        # === Events ===
        perception['events'] = list(self.event_buffer)
        
        # Compute urgency (high emotion intensity or low health)
        emotion_intensity = max(abs(v) for v in perception['state']['emotions'].values())
        health_urgency = 1.0 - (perception['state']['health'] / 20.0)
        perception['urgency'] = max(emotion_intensity, health_urgency)
        
        return perception
    
    # ==================== THINKING ====================
    
    async def _think(self, perception: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process perception through brain's cognitive systems.
        Decides what to focus on and retrieves relevant memories.
        """
        thoughts = {
            'focus': None,
            'memories': [],
            'patterns': {},
            'language_activation': 0.0,
            'curiosity': 0.0,
            'analysis': {},
            'should_think_deeply': False
        }
        
        # === Quick Check: Is anything interesting? ===
        if perception['novelty'] < self.think_threshold and perception['urgency'] < 0.5 and not self.file_buffer:
            # Nothing significant, light processing only
            return thoughts
        
        # === Deep Thinking Triggered ===
        thoughts['should_think_deeply'] = True
        
        # === Brain Evaluation ===
        event = {
            'type': 'autonomous_perception',
            'tags': ['autonomous', 'perception', 'cognitive_loop'],
            'payload': {
                'novelty': perception['novelty'],
                'urgency': perception['urgency'],
                'timestamp': perception['timestamp']
            }
        }
        
        # Let brain assess situation
        reward, emotion_delta = self.agent.brain.evaluate_event(
            event, 
            perception['state']
        )
        
        # Update emotions from brain's assessment
        for emotion, value in emotion_delta.items():
            self.agent.emotion.add(emotion, value)
        
        thoughts['analysis'] = {
            'reward': reward,
            'emotion_delta': emotion_delta
        }
        
        # === Memory Retrieval ===
        if perception['novelty'] > 0.5 or perception['urgency'] > 0.6:
            # Retrieve relevant memories
            thoughts['memories'] = self.agent.memory.recall(10)
            
            # Search for similar past experiences
            if perception['events']:
                recent_event = perception['events'][-1]
                event_type = recent_event.get('type', '')
                if event_type:
                    similar = self.agent.memory.search(event_type, limit=5)
                    thoughts['memories'].extend(similar)
        
        # === Pattern Analysis ===
        thoughts['patterns'] = self.agent.brain.get_pattern_summary()
        
        # === File Processing ===
        # If nothing queued explicitly, look for recent uploaded files in memory
        if not self.file_buffer:
            try:
                recent_events = []
                if hasattr(self.agent, 'memory') and hasattr(self.agent.memory, 'recall'):
                    recent_events = self.agent.memory.recall(50)
                for ev in reversed(recent_events):
                    if ev.get('type') == 'file_uploaded':
                        fn = ev.get('filename')
                        # Skip if already processed
                        already = any((e.get('type') == 'file_processed' and e.get('filename') == fn) for e in recent_events)
                        if not already:
                            self.file_buffer.append({
                                'path': ev.get('path'),
                                'filename': fn,
                                'filetype': ev.get('filetype'),
                                'size': ev.get('size'),
                                'timestamp': ev.get('timestamp')
                            })
                            log.info(f"[Thinking] Queued uploaded file from memory: {fn}")
                            break
            except Exception:
                pass

        if self.file_buffer:
            file_info = self.file_buffer[0]  # Peek at oldest file
            thoughts['file_to_process'] = file_info
            log.info(f"[Thinking] File available for processing: {file_info['filename']}")
        
        # === Language Activation ===
        if hasattr(self.agent.brain, 'language') and self.agent.brain.language:
            # Check if agent has enough language ability and reason to speak
            lang_stage = self.agent.brain.language.language_stage
            vocab_size = self.agent.brain.language.vocabulary_size
            
            # Activation increases with:
            # - Language development (stage/vocab)
            # - Emotional intensity
            # - Social personality trait
            lang_progress = min(1.0, (lang_stage / 3.0) * (vocab_size / 50.0))
            emotion_intensity = max(abs(v) for v in perception['state']['emotions'].values())
            social_factor = self.weights['social']
            
            thoughts['language_activation'] = (
                lang_progress * 0.5 +
                emotion_intensity * 0.3 +
                social_factor * 0.2
            )
        
        # === Curiosity Assessment ===
        curiosity_trait = self.agent.personality.traits.get('curiosity', 0.5)
        thoughts['curiosity'] = perception['novelty'] * curiosity_trait * self.weights['exploration']
        
        # === Focus Determination ===
        if perception['urgency'] > 0.7:
            thoughts['focus'] = 'survival'
        elif thoughts['curiosity'] > 0.6:
            thoughts['focus'] = 'exploration'
        elif thoughts['language_activation'] > 0.5:
            thoughts['focus'] = 'communication'
        else:
            thoughts['focus'] = 'observation'
        
        return thoughts
    
    # ==================== REFLECTION ====================
    
    def _reflect(self, thoughts: Dict[str, Any], perception: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reflect on thoughts and internal state.
        Decides emotional response, goals, and priorities.
        """
        reflection = {
            'should_speak': False,
            'should_act': False,
            'should_learn': False,
            'emotional_state': 'neutral',
            'goal': None,
            'urgency': perception['urgency'],
            'confidence': 0.5,
            'reasoning': []
        }
        
        # === Emotional Assessment ===
        emotions = self.agent.emotion.snapshot()
        dominant = self.agent.emotion.dominant_emotion()
        intensity = abs(emotions.get(dominant, 0.0))
        
        reflection['emotional_state'] = dominant
        
        current_time = time.time()
        
        # === Speech Decision ===
        speech_reasoning = []
        
        # High language activation
        if thoughts['language_activation'] > 0.4:
            speech_reasoning.append(f"language_activation={thoughts['language_activation']:.2f}")
        
        # Strong emotion
        if intensity > 0.6:
            speech_reasoning.append(f"strong_{dominant}={intensity:.2f}")
        
        # Social personality + time passed
        if (self.weights['social'] > 0.6 and 
            current_time - self.last_speech_time > self.speech_cooldown * 0.5):
            speech_reasoning.append("social_personality")
        
        # Final speech decision
        if speech_reasoning and current_time - self.last_speech_time > self.speech_cooldown:
            # Ask brain if it actually wants to speak
            if hasattr(self.agent.brain, 'should_speak'):
                reflection['should_speak'] = self.agent.brain.should_speak()
                if reflection['should_speak']:
                    reflection['reasoning'].append(f"speech: {', '.join(speech_reasoning)}")
        
        # === Action Decision ===
        action_reasoning = []
        
        # High curiosity
        if thoughts['curiosity'] > 0.5:
            action_reasoning.append(f"curiosity={thoughts['curiosity']:.2f}")
        
        # High urgency
        if reflection['urgency'] > 0.6:
            action_reasoning.append(f"urgency={reflection['urgency']:.2f}")
        
        # Bold personality
        if self.weights['reactive'] > 0.6:
            action_reasoning.append("bold_personality")
        
        # Time-based action
        if current_time - self.last_action_time > self.action_cooldown:
            if action_reasoning or thoughts['focus'] == 'survival':
                reflection['should_act'] = True
                reflection['reasoning'].append(f"action: {', '.join(action_reasoning)}")
        
        # === Learning Decision ===
        learning_reasoning = []
        
        # High novelty
        if perception['novelty'] > 0.5:
            learning_reasoning.append(f"novelty={perception['novelty']:.2f}")
        
        # Learning interval passed
        if current_time - self.last_learning_time > self.learning_interval:
            if learning_reasoning or len(self.agent.episodic_memory) > 32:
                reflection['should_learn'] = True
                reflection['reasoning'].append(f"learn: {', '.join(learning_reasoning)}")
        
        # === Goal Setting ===
        if thoughts['focus'] == 'survival':
            reflection['goal'] = 'survive'
            reflection['confidence'] = 0.9
        elif thoughts['focus'] == 'exploration':
            reflection['goal'] = 'explore'
            reflection['confidence'] = 0.7
        elif thoughts['focus'] == 'communication':
            reflection['goal'] = 'express'
            reflection['confidence'] = 0.6
        else:
            reflection['goal'] = 'observe'
            reflection['confidence'] = 0.5
        
        return reflection
    
    # ==================== DECISION ====================
    
    def _decide(self, reflection: Dict[str, Any], thoughts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Make final decision on what to do this cycle.
        Returns action specification with priority.
        """
        decision = {
            'type': 'none',
            'content': None,
            'priority': 0.0,
            'reasoning': reflection.get('reasoning', [])
        }
        
        # === Priority System ===
        # 1. Survival actions (highest)
        # 2. Speech (high - social creatures)
        # 3. Goal-directed actions (medium)
        # 4. Learning (low - background)
        # 5. Idle (lowest)
        
        if reflection['urgency'] > 0.8 and reflection['should_act']:
            decision['type'] = 'action'
            decision['content'] = {'goal': 'survive'}
            decision['priority'] = 1.0
            
        elif reflection['should_speak']:
            decision['type'] = 'speak'
            decision['priority'] = 0.8
            
        elif reflection['should_act']:
            decision['type'] = 'action'
            decision['content'] = {'goal': reflection['goal']}
            decision['priority'] = 0.6
            
        elif reflection['should_learn']:
            decision['type'] = 'learn'
            decision['priority'] = 0.3
        
        return decision
    
    # ==================== ACTION EXECUTION ====================
    
    async def _act(self, decision: Dict[str, Any], perception: Dict[str, Any]):
        """Execute the decided action"""
        # If there are files queued, prioritize processing one file now
        if self.file_buffer:
            file_info = self.file_buffer.popleft()
            try:
                # Run potentially blocking file learning in a thread
                if hasattr(self.agent.brain, 'learn_from_file'):
                    summary = await asyncio.to_thread(
                        self.agent.brain.learn_from_file,
                        file_info['path'],
                        file_info.get('filetype')
                    )
                    log.info(f"[CognitiveLoop] Processed file {file_info['filename']}: {str(summary)[:120]}")
                    # Remember the file processing event in memory
                    self.agent.memory.remember({
                        'type': 'file_processed',
                        'filename': file_info['filename'],
                        'path': file_info['path'],
                        'filetype': file_info.get('filetype'),
                        'summary': summary,
                        'timestamp': time.time()
                    })
                    try:
                        from unified_chat_system import chat_system
                        await chat_system.send_message(
                            self.agent.agent_id,
                            f"Processed file: {file_info['filename']}\nSummary: {summary}",
                            target='both',
                            sender='agent'
                        )
                    except Exception:
                        # It's optional to notify frontend
                        pass
            except Exception as e:
                log.error(f"[CognitiveLoop] Error processing file {file_info.get('filename')}: {e}")
                # If processing failed, don't drop it silently — keep a short retry window
                # push back to buffer for a later attempt
                self.file_buffer.append(file_info)
                await asyncio.sleep(0.5)
            # After processing a file, return early to avoid doing other actions this cycle
            return
        
        if decision['type'] == 'speak':
            await self._execute_speech(perception)
            
        elif decision['type'] == 'action':
            await self._execute_action(decision['content'], perception)
            
        elif decision['type'] == 'learn':
            self._execute_learning()
    
    async def _execute_speech(self, perception: Dict[str, Any]):
        """Generate and send autonomous speech"""
        if not hasattr(self.agent.brain, 'generate_speech'):
            return
        
        context = perception['state']
        
        try:
            speech = self.agent.brain.generate_speech(context)
            
            if speech:
                # Import here to avoid circular dependency
                try:
                    from unified_chat_system import chat_system
                    
                    await chat_system.send_message(
                        self.agent.agent_id,
                        speech,
                        target="both",
                        sender="agent"
                    )
                    
                    self.last_speech_time = time.time()
                    log.info(f"[{self.agent.agent_id}] 💬 Autonomous: {speech[:60]}")
                    
                except ImportError:
                    log.warning("unified_chat_system not available")
                    
        except Exception as e:
            log.error(f"Speech execution error: {e}")
    
    async def _execute_action(self, action_content: Dict[str, Any], 
                             perception: Dict[str, Any]):
        """Generate and execute autonomous action"""
        try:
            # Build observation
            obs_dict = {
                'health': perception['state']['health'],
                'hunger': perception['state']['hunger'],
                'position': {'x': 0, 'y': 64, 'z': 0},  # Default if no actual position
                'entities': []
            }
            
            # Perceive
            obs = self.agent.perceive(obs_dict)
            
            # Decide action based on goal
            goal = action_content.get('goal', 'observe')
            
            if goal == 'survive':
                # Survival actions: cautious, defensive
                action_array = self._generate_survival_action(obs)
            elif goal == 'explore':
                # Exploration: movement-focused
                action_array = self._generate_exploration_action(obs)
            else:
                # Normal decision
                action_array = self.agent.decide(obs, deterministic=False)
            
            # Convert to action dict
            action_dict = self.agent.act(action_array)
            
            # Send to actuators if available
            if hasattr(self.agent, 'client_process') and self.agent.client_process:
                # Has Minecraft client - send via IPC
                try:
                    from ai_core.actuators import ForgeIPCClient
                    # Client would be managed elsewhere, just log for now
                    pass
                except ImportError:
                    pass
            
            self.last_action_time = time.time()
            log.debug(f"[{self.agent.agent_id}] ⚡ Action: {goal}")
            
        except Exception as e:
            log.error(f"Action execution error: {e}")
    
    def _generate_survival_action(self, obs: np.ndarray) -> np.ndarray:
        """Generate cautious survival-focused action"""
        # Bias toward defensive actions
        action = self.agent.decide(obs, deterministic=True)  # More predictable
        
        # Reduce aggression, increase caution
        action[4] = min(action[4], 0.0)  # Reduce attack
        action[3] = max(action[3], 0.5)  # Increase sneak
        
        return action
    
    def _generate_exploration_action(self, obs: np.ndarray) -> np.ndarray:
        """Generate movement-focused exploration action"""
        action = self.agent.decide(obs, deterministic=False)
        
        # Bias toward movement
        action[0] = np.clip(action[0] + 0.2, -1.0, 1.0)  # More forward
        action[2] = max(action[2], 0.3)  # Some jumping for terrain
        
        return action
    
    def _execute_learning(self):
        """Trigger continual learning update"""
        try:
            if not hasattr(self.agent, 'episodic_memory'):
                return
            
            if len(self.agent.episodic_memory) < 32:
                return
            
            # Sample batch for learning
            batch = self.agent.episodic_memory.sample(batch_size=32)
            
            # Store in brain's continual buffer
            if hasattr(self.agent.brain, 'continual_buffer'):
                experience = {
                    'observations': batch[0],
                    'actions': batch[1],
                    'rewards': batch[2],
                    'next_observations': batch[3],
                    'dones': batch[4],
                    'task': self.agent.brain.current_task,
                    'timestamp': time.time()
                }
                self.agent.brain.continual_buffer.append(experience)
            
            self.last_learning_time = time.time()
            log.debug(f"[{self.agent.agent_id}] 📚 Learning update with batch_size=32")
            
        except Exception as e:
            log.error(f"Learning execution error: {e}")
    
    # ==================== STATE UPDATE ====================
    
    def _update_cognitive_state(self, perception: Dict[str, Any],
                                thoughts: Dict[str, Any],
                                reflection: Dict[str, Any]):
        """Update internal cognitive state for next cycle"""
        
        # Update focus
        self.state.current_focus = thoughts.get('focus')
        
        # Update goal
        self.state.active_goal = reflection.get('goal')
        
        # Update attention based on novelty and urgency
        novelty_factor = perception['novelty']
        urgency_factor = perception['urgency']
        self.state.attention_level = (novelty_factor + urgency_factor) / 2.0
        
        # Energy decay (simulate fatigue)
        self.state.energy_level *= 0.9995  # Very slow decay
        self.state.energy_level = max(0.3, self.state.energy_level)  # Min 30%
        
        # Store significant events
        if perception['novelty'] > 0.7 or perception['urgency'] > 0.7:
            self.state.last_significant_event = {
                'perception': perception,
                'thoughts': thoughts,
                'reflection': reflection,
                'timestamp': time.time()
            }
        
        # Natural emotion decay
        self.agent.emotion.decay()
    
    # ==================== INPUT RECEPTION ====================
    
    def receive_visual_input(self, frame: np.ndarray, metadata: Optional[Dict] = None):
        """Receive visual input from camera/game"""
        self.visual_buffer.append({
            'frame': frame,
            'timestamp': time.time(),
            'metadata': metadata or {}
        })
    
    def receive_audio_input(self, audio: np.ndarray, sample_rate: int, 
                           metadata: Optional[Dict] = None):
        """Receive audio input from microphone/game"""
        self.audio_buffer.append({
            'audio': audio,
            'sample_rate': sample_rate,
            'timestamp': time.time(),
            'metadata': metadata or {}
        })
    
    def receive_state_update(self, state: Dict[str, Any]):
        """Receive game state update"""
        self.state_buffer.append({
            'state': state,
            'timestamp': time.time()
        })
        
        # Update agent's direct state
        if 'health' in state:
            self.agent.health = state['health']
        if 'hunger' in state:
            self.agent.hunger = state['hunger']
    
    def receive_event(self, event: Dict[str, Any]):
        """Receive custom event"""
        self.event_buffer.append(event)
    
    def receive_file(self, file_info: Dict[str, Any]):
        """Receive file for cognitive processing (from upload endpoint)"""
        self.file_buffer.append(file_info)
        log.info(f"[CognitiveLoop] File queued for processing: {file_info['filename']}")
    
    # ==================== STATUS ====================
    
    def get_status(self) -> Dict[str, Any]:
        """Get current cognitive loop status"""
        return {
            'running': self.running,
            'cycle_count': self.state.cycle_count,
            'focus': self.state.current_focus,
            'goal': self.state.active_goal,
            'attention': self.state.attention_level,
            'energy': self.state.energy_level,
            'buffers': {
                'visual': len(self.visual_buffer),
                'audio': len(self.audio_buffer),
                'events': len(self.event_buffer)
            },
            'last_action': self.last_action_time,
            'last_speech': self.last_speech_time,
            'last_learning': self.last_learning_time
        }