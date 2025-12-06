# ai_core/cognitive_loop.py - ENHANCED WITH AUTONOMOUS SPEECH
"""
Autonomous Cognitive Loop - FULLY INTEGRATED
The agent thinks continuously and speaks when it feels appropriate
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
    
    Changes from original:
    - Uses UnifiedMemoryStore (not separate buffers)
    - Directly triggers language generation
    - Connects to chat_system for output
    - Considers full personality for speech decisions
    """
    
    def __init__(self, agent, loop_interval: float = 0.5):
        self.agent = agent
        self.loop_interval = loop_interval
        
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
        self.speech_cooldown = max(5.0, self.speech_cooldown)  # Minimum 5s
        
        # Action cooldown
        boldness = personality.get('boldness', 0.5)
        self.action_cooldown = 2.0 * (1.0 - boldness * 0.5)
        
        # Learning interval
        openness = personality.get('openness', 0.5)
        self.learning_interval = 30.0 * (1.0 - openness * 0.3)
        
        log.debug(f"Thresholds: speech={self.speech_cooldown:.1f}s, action={self.action_cooldown:.1f}s")

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
                
                # === 5. ACT (INCLUDING SPEECH) ===
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
        
        # Calculate novelty (how surprising recent events are)
        if recent:
            novelty_scores = []
            for event in recent[-3:]:
                # Higher novelty for rare event types
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
            'language_desire': 0.0,  # NEW: How much agent wants to speak
            'speech_topic': None,     # NEW: What to talk about
            'curiosity': 0.0,
            'analysis': {},
            'should_think_deeply': False
        }
        
        # Quick check
        if perception['novelty'] < 0.2 and perception['urgency'] < 0.3:
            return thoughts
        
        thoughts['should_think_deeply'] = True
        
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
        
        # === LANGUAGE DESIRE CALCULATION ===
        # This is KEY for autonomous speech!
        
        lang_factors = []
        
        # 1. Strong emotions make agent want to express
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
        
        # 5. Recent events suggest conversation topic
        recent_speech = [e for e in perception['recent_events'] 
                        if e.get('type') in ['language_input', 'language_output']]
        
        if recent_speech and time_since_speech < 30:
            # Recently in conversation - higher desire to continue
            lang_factors.append(('conversation_context', 0.8))
            thoughts['speech_topic'] = 'conversation_response'
        
        # 6. Internal monologue (thinking out loud)
        if perception['urgency'] > 0.6:
            lang_factors.append(('urgent_thoughts', perception['urgency']))
            thoughts['speech_topic'] = 'urgent_situation'
        
        # Combine factors
        if lang_factors:
            weights = [factor[1] for factor in lang_factors]
            thoughts['language_desire'] = np.mean(weights)
            
            log.debug(f"Language desire: {thoughts['language_desire']:.2f} from {[f[0] for f in lang_factors]}")
        
        # Determine focus
        if perception['urgency'] > 0.7:
            thoughts['focus'] = 'survival'
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
            'confidence': 0.5
        }
        
        current_time = time.time()
        
        # === SPEECH DECISION ===
        # Agent speaks when language_desire is high AND cooldown expired
        
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
        
        # Prioritize speech highly for social agents
        if reflection['should_speak']:
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
        
        return decision

    # ==================== ACTION EXECUTION ====================
    
    async def _act(self, decision: Dict[str, Any], 
                   perception: Dict[str, Any],
                   thoughts: Dict[str, Any]):
        """Execute decision - INCLUDING AUTONOMOUS SPEECH"""
        
        if decision['type'] == 'speak':
            await self._execute_autonomous_speech(perception, thoughts, decision['content'])
        
        elif decision['type'] == 'action':
            await self._execute_action(perception)
        
        elif decision['type'] == 'learn':
            self._execute_learning()
    
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
            
            # Generate speech using enhanced language intelligence
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
            # Import here to avoid circular dependency
            from unified_chat_system import chat_system
            
            await chat_system.send_message(
                agent_id=self.agent.agent_id,
                message=speech,
                target="both",  # Both game and GUI
                sender="agent",
                is_emote=False
            )
            
        except ImportError:
            # Fallback: just log if chat system not available
            log.warning("Chat system not available - speech logged only")
        except Exception as e:
            log.error(f"Failed to broadcast speech: {e}")
    
    async def _execute_action(self, perception: Dict[str, Any]):
        """Execute physical action"""
        try:
            obs_dict = {
                'health': perception['state']['health'],
                'hunger': perception['state']['hunger'],
                'position': {'x': 0, 'y': 64, 'z': 0}
            }
            
            obs = self.agent.perceive(obs_dict)
            action_array = self.agent.decide(obs, deterministic=False)
            action_dict = self.agent.act(action_array)
            
            self.last_action_time = time.time()
            
        except Exception as e:
            log.error(f"Action execution error: {e}")
    
    def _execute_learning(self):
        """Trigger learning update"""
        try:
            # Train language on recent experiences
            self.agent.brain.language._train_from_unified_memory()
            
            self.last_learning_time = time.time()
            log.debug(f"[{self.agent.agent_id}] 📚 Learning update")
            
        except Exception as e:
            log.error(f"Learning execution error: {e}")

    # ==================== STATE UPDATE ====================
    
    def _update_cognitive_state(self, perception: Dict[str, Any],
                                thoughts: Dict[str, Any],
                                reflection: Dict[str, Any]):
        """Update internal cognitive state"""
        self.state.current_focus = thoughts.get('focus')
        self.state.attention_level = (perception['novelty'] + perception['urgency']) / 2.0
        self.state.energy_level *= 0.9995  # Slow decay
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
            'speech_cooldown': self.speech_cooldown
        }