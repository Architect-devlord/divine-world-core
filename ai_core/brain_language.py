# ai_core/brain_language.py - COMPLETE IMPLEMENTATION
"""
Brain Language Extension - Language Intelligence for BrainCore
--------------------------------------------------------------
Extends BrainCore with:
- Symbol grounding (multimodal concept-to-word mapping)
- Language processing (understanding and generation)
- Speech generation (autonomous and reactive)
- Emergent language creation (symbol invention)
- Developmental language stages (pre-linguistic → proto → linguistic)

This module provides methods that should be added to BrainCore class.
Integrates with existing: memory, emotion, personality, reward systems.
"""

import time
import numpy as np
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict, deque
from pathlib import Path
import logging

log = logging.getLogger("brain.language")


# ============================================================================
# CORE LANGUAGE METHODS - Add these to BrainCore class in brain_core.py
# ============================================================================

class LanguageIntelligence:
    """
    Language intelligence mixin for BrainCore.
    Can be used standalone or integrated into BrainCore.
    """
    
    def __init__(self, agent_ref=None):
        """Initialize language capabilities"""
        self.agent = agent_ref
        
        # Symbol grounding: word ↔ multimodal concept vectors
        self.word_to_concept: Dict[str, List[np.ndarray]] = defaultdict(list)
        self.concept_to_word: Dict[str, str] = {}  # concept_hash -> word
        self.word_frequencies: Dict[str, int] = defaultdict(int)
        self.word_co_occurrence: Dict[Tuple[str, str], int] = defaultdict(int)
        
        # Sentence patterns (learned from experience)
        self.sentence_patterns: List[List[str]] = []
        self.sentence_templates: List[str] = []
        
        # Developmental stage tracking
        self.language_stage = 0  # 0=none, 1=proto, 2=linguistic, 3=advanced
        self.language_experience_count = 0
        self.vocabulary_size = 0
        
        # Speech control
        self.last_speech_time = 0
        self.speech_cooldown = 10.0  # seconds between autonomous speech
        self.speech_queue: deque = deque(maxlen=10)
        
        # Symbol invention system
        self.invented_symbols: Dict[str, np.ndarray] = {}
        self.symbol_counter = 0
        self.symbol_prefix = "sym"
        
        # Semantic network (word relationships)
        self.semantic_links: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        
        # Context memory (recent conversation)
        self.context_window: deque = deque(maxlen=20)
        
        log.info("Language intelligence initialized")
    
    
    # ==================== CORE LANGUAGE PROCESSING ====================
    
    def process_language_input(self, text: str, context: Dict[str, Any]) -> str:
        """
        Main entry point: process incoming language and generate response.
        
        Args:
            text: Input text (from user, game chat, file)
            context: Multimodal context (vision, state, emotions, memory)
        
        Returns:
            Generated response text (or empty string if pre-linguistic)
        """
        if not text or not text.strip():
            return ""
        
        text = text.strip()
        
        # Extract concept vector from multimodal context
        concept_vector = self._extract_concept_vector(context)
        
        # Tokenize and ground words to concepts
        words = self._tokenize(text)
        
        for word in words:
            if len(word) > 2:  # Skip very short words
                self.word_to_concept[word].append(concept_vector)
                self.word_frequencies[word] += 1
        
        # Update co-occurrence statistics
        self._update_co_occurrence(words)
        
        # Store sentence pattern
        if len(words) > 1:
            self.sentence_patterns.append(words)
        
        # Track experience and update stage
        self.language_experience_count += 1
        self.vocabulary_size = len(self.word_to_concept)
        self._update_language_stage()
        
        # Store in context window
        self.context_window.append({
            'text': text,
            'words': words,
            'concept': concept_vector,
            'timestamp': time.time()
        })
        
        # Generate response based on developmental stage
        response = self._generate_response(text, words, concept_vector, context)
        
        # Evaluate as learning event (integrate with brain's reward system)
        if self.agent and hasattr(self.agent, 'brain'):
            event = {
                'type': 'language_input',
                'tags': ['language', 'learning'],
                'payload': {
                    'text': text,
                    'words': len(words),
                    'stage': self.language_stage,
                    'novelty': self._compute_text_novelty(text)
                }
            }
            reward, emotion_delta = self.agent.brain.evaluate_event(event, context)
            
            # Update emotions
            for emotion, value in emotion_delta.items():
                self.agent.emotion.add(emotion, value)
        
        return response
    
    
    def _extract_concept_vector(self, context: Dict[str, Any]) -> np.ndarray:
        """
        Extract fixed-size concept vector from multimodal context.
        Combines vision, action, state, and emotion features.
        """
        features = []
        
        # Visual features (if available)
        if 'visual' in context and context['visual'] is not None:
            visual = context['visual']
            if isinstance(visual, np.ndarray):
                if len(visual.shape) == 3:  # Image
                    # Extract simple statistics
                    features.extend([
                        float(np.mean(visual)),
                        float(np.std(visual)),
                        float(np.max(visual)),
                        float(np.min(visual))
                    ])
                else:
                    features.extend(visual.flatten()[:10].tolist())
        
        # Action features (if available)
        if 'last_action' in context and context['last_action'] is not None:
            action = context['last_action']
            if isinstance(action, np.ndarray):
                features.extend(action.flatten()[:5].tolist())
            elif isinstance(action, dict):
                # Convert dict to array
                features.extend([
                    float(action.get('move_forward', 0.0)),
                    float(action.get('move_strafe', 0.0)),
                    1.0 if action.get('jump', False) else 0.0,
                    1.0 if action.get('attack', False) else 0.0,
                    float(action.get('yaw_delta', 0.0) / 2.0)
                ])
        
        # State features
        features.extend([
            context.get('health', 20.0) / 20.0,
            context.get('hunger', 20.0) / 20.0,
            context.get('saturation', 5.0) / 20.0
        ])
        
        # Position features (if available)
        if 'position' in context:
            pos = context['position']
            features.extend([
                pos.get('x', 0.0) / 100.0,
                pos.get('y', 64.0) / 100.0,
                pos.get('z', 0.0) / 100.0
            ])
        
        # Emotion features
        if 'emotions' in context:
            emotions = context['emotions']
            for e in ['joy', 'fear', 'surprise', 'anger']:
                features.append(emotions.get(e, 0.0))
        
        # Personality features (if agent available)
        if self.agent and hasattr(self.agent, 'personality'):
            persona = self.agent.personality.as_array()
            features.extend(persona[:4].tolist())
        
        # Pad or truncate to fixed size (32 dimensions)
        target_size = 32
        while len(features) < target_size:
            features.append(0.0)
        
        return np.array(features[:target_size], dtype=np.float32)
    
    
    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization (word-level)"""
        # Remove punctuation, lowercase, split
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        words = text.split()
        return [w for w in words if len(w) > 0]
    
    
    def _update_co_occurrence(self, words: List[str]):
        """Update word co-occurrence statistics (for semantic relationships)"""
        for i, word1 in enumerate(words):
            for j in range(i + 1, min(i + 5, len(words))):  # 5-word window
                word2 = words[j]
                self.word_co_occurrence[(word1, word2)] += 1
                self.word_co_occurrence[(word2, word1)] += 1
    
    
    def _update_language_stage(self):
        """Update developmental language stage based on experience"""
        old_stage = self.language_stage
        
        # Stage progression thresholds
        if self.language_experience_count >= 5 and self.vocabulary_size >= 10:
            self.language_stage = max(self.language_stage, 1)  # Proto-language
        
        if self.vocabulary_size >= 30 and len(self.sentence_patterns) >= 20:
            self.language_stage = max(self.language_stage, 2)  # Linguistic
        
        if self.vocabulary_size >= 100 and len(self.sentence_patterns) >= 100:
            self.language_stage = max(self.language_stage, 3)  # Advanced
        
        if self.language_stage != old_stage:
            log.info(f"Language stage advanced: {old_stage} → {self.language_stage}")
            
            # Update personality (increase openness, sociability)
            if self.agent and hasattr(self.agent, 'personality'):
                delta = np.zeros(8)
                delta[0] = 0.05  # openness
                delta[7] = 0.05  # sociability
                self.agent.personality.apply_update(delta, lr=0.1)
    
    
    # ==================== RESPONSE GENERATION ====================
    
    def _generate_response(self, text: str, words: List[str], 
                           concept_vector: np.ndarray, 
                           context: Dict[str, Any]) -> str:
        """Generate response based on current language stage"""
        
        if self.language_stage == 0:
            # Pre-linguistic: no speech
            return ""
        
        elif self.language_stage == 1:
            # Proto-language: single-word responses
            return self._generate_proto_response(concept_vector, context)
        
        elif self.language_stage == 2:
            # Linguistic: simple sentences
            return self._generate_linguistic_response(words, concept_vector, context)
        
        else:  # stage >= 3
            # Advanced: complex sentences with context
            return self._generate_advanced_response(text, words, concept_vector, context)
    
    
    def _generate_proto_response(self, concept_vector: np.ndarray, 
                                 context: Dict[str, Any]) -> str:
        """Generate single-word response (proto-language stage)"""
        
        # Find word with highest similarity to current concept
        best_word = None
        best_similarity = 0.0
        
        for word, concepts in self.word_to_concept.items():
            if not concepts:
                continue
            
            # Average concept vector for this word
            avg_concept = np.mean(concepts, axis=0)
            
            # Cosine similarity
            similarity = self._cosine_similarity(concept_vector, avg_concept)
            
            # Bias by frequency (more common words more likely)
            freq_bias = min(1.0, self.word_frequencies[word] / 10.0)
            adjusted_similarity = similarity * (0.7 + 0.3 * freq_bias)
            
            if adjusted_similarity > best_similarity and adjusted_similarity > 0.5:
                best_similarity = adjusted_similarity
                best_word = word
        
        # Fallback: invent symbol if no good match
        if not best_word and self.agent:
            best_word = self._invent_symbol(concept_vector)
        
        return best_word if best_word else ""
    
    
    def _generate_linguistic_response(self, input_words: List[str],
                                      concept_vector: np.ndarray,
                                      context: Dict[str, Any]) -> str:
        """Generate simple sentence (linguistic stage)"""
        
        # Find relevant words based on concept similarity
        relevant_words = self._find_relevant_words(concept_vector, limit=5)
        
        if not relevant_words:
            # Fallback to proto-language
            return self._generate_proto_response(concept_vector, context)
        
        # Try to use learned sentence patterns
        if self.sentence_patterns:
            # Find pattern of similar length
            target_len = min(len(relevant_words), 4)
            matching_patterns = [
                p for p in self.sentence_patterns 
                if target_len <= len(p) <= target_len + 2
            ]
            
            if matching_patterns:
                # Use most recent pattern as template
                template = matching_patterns[-1]
                
                # Simple word substitution
                output_words = []
                for i, template_word in enumerate(template[:target_len]):
                    if i < len(relevant_words):
                        output_words.append(relevant_words[i])
                    else:
                        output_words.append(template_word)
                
                return ' '.join(output_words)
        
        # Fallback: just concatenate relevant words
        return ' '.join(relevant_words[:3])
    
    
    def _generate_advanced_response(self, input_text: str, input_words: List[str],
                                    concept_vector: np.ndarray,
                                    context: Dict[str, Any]) -> str:
        """Generate complex response with context awareness (advanced stage)"""
        
        # Analyze input intent
        intent = self._analyze_intent(input_words)
        
        # Get relevant words
        relevant_words = self._find_relevant_words(concept_vector, limit=8)
        
        # Consider conversation context
        context_words = []
        for entry in list(self.context_window)[-3:]:
            context_words.extend(entry['words'][:3])
        
        # Get emotional state
        emotion = context.get('dominant_emotion', 'neutral')
        
        # Generate response based on intent and emotion
        if intent == 'question':
            return self._generate_answer(relevant_words, context_words, emotion)
        elif intent == 'greeting':
            return self._generate_greeting(emotion)
        elif intent == 'statement':
            return self._generate_statement(relevant_words, emotion)
        else:
            # Fallback to linguistic response
            return self._generate_linguistic_response(input_words, concept_vector, context)
    
    
    def _analyze_intent(self, words: List[str]) -> str:
        """Analyze input intent (question, greeting, statement, etc.)"""
        if not words:
            return 'unknown'
        
        # Question indicators
        question_words = {'what', 'why', 'how', 'when', 'where', 'who', 'which'}
        if any(w in question_words for w in words[:3]):
            return 'question'
        
        # Greeting indicators
        greeting_words = {'hello', 'hi', 'hey', 'greetings'}
        if any(w in greeting_words for w in words[:2]):
            return 'greeting'
        
        return 'statement'
    
    
    def _generate_answer(self, relevant_words: List[str], 
                        context_words: List[str], emotion: str) -> str:
        """Generate answer to question"""
        # Combine relevant and context words
        all_words = relevant_words[:3] + context_words[:2]
        
        # Emotion-based prefix
        prefix = {
            'joy': "I think",
            'fear': "Maybe",
            'surprise': "Interesting,",
            'anger': "Well,"
        }.get(emotion, "I believe")
        
        if len(all_words) >= 2:
            return f"{prefix} {all_words[0]} {all_words[1]}"
        elif all_words:
            return f"{prefix} {all_words[0]}"
        else:
            return prefix
    
    
    def _generate_greeting(self, emotion: str) -> str:
        """Generate greeting based on emotion"""
        greetings = {
            'joy': "Hello! Nice to see you!",
            'fear': "Um, hello...",
            'surprise': "Oh! Hello there!",
            'sadness': "Hello...",
            'anger': "What do you want?",
            'neutral': "Hello"
        }
        return greetings.get(emotion, "Hello")
    
    
    def _generate_statement(self, relevant_words: List[str], emotion: str) -> str:
        """Generate statement"""
        if not relevant_words:
            return "I understand"
        
        # Emotion-based response style
        if emotion == 'joy' and len(relevant_words) >= 2:
            return f"Yes! {relevant_words[0]} {relevant_words[1]}!"
        elif emotion == 'fear' and relevant_words:
            return f"I'm not sure about {relevant_words[0]}"
        elif len(relevant_words) >= 3:
            return f"{relevant_words[0]} {relevant_words[1]} {relevant_words[2]}"
        elif len(relevant_words) >= 2:
            return f"{relevant_words[0]} {relevant_words[1]}"
        else:
            return relevant_words[0] if relevant_words else "Yes"
    
    
    # ==================== HELPER FUNCTIONS ====================
    
    def _find_relevant_words(self, concept_vector: np.ndarray, 
                             limit: int = 5) -> List[str]:
        """Find words most relevant to given concept vector"""
        scored_words = []
        
        for word, concepts in self.word_to_concept.items():
            if not concepts:
                continue
            
            avg_concept = np.mean(concepts, axis=0)
            similarity = self._cosine_similarity(concept_vector, avg_concept)
            
            if similarity > 0.3:  # Threshold
                scored_words.append((word, similarity))
        
        # Sort by similarity and return top words
        scored_words.sort(key=lambda x: x[1], reverse=True)
        return [word for word, _ in scored_words[:limit]]
    
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors"""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    
    def _compute_text_novelty(self, text: str) -> float:
        """Compute novelty score for text based on vocabulary"""
        if not self.agent or not hasattr(self.agent, 'memory'):
            return 0.5
        
        return self.agent.memory.novelty_score(text[:512])
    
    
    # ==================== SYMBOL INVENTION ====================
    
    def _invent_symbol(self, concept_vector: np.ndarray) -> str:
        """
        Invent new symbol for novel concept.
        Creates grounded symbol that can be used in communication.
        """
        # Generate unique symbol name
        symbol_name = f"{self.symbol_prefix}{self.symbol_counter}"
        self.symbol_counter += 1
        
        # Store concept mapping
        self.invented_symbols[symbol_name] = concept_vector
        self.word_to_concept[symbol_name].append(concept_vector)
        self.word_frequencies[symbol_name] = 1
        
        # Create concept hash for reverse lookup
        concept_hash = self._hash_concept(concept_vector)
        self.concept_to_word[concept_hash] = symbol_name
        
        log.info(f"Invented symbol: {symbol_name}")
        
        return symbol_name
    
    
    def _hash_concept(self, concept: np.ndarray) -> str:
        """Create hash string from concept vector"""
        # Round to 2 decimals and create string
        rounded = np.round(concept, 2)
        return '_'.join(str(x) for x in rounded[:8])
    
    
    # ==================== AUTONOMOUS SPEECH ====================
    
    def should_speak(self) -> bool:
        """
        Decide if agent should speak autonomously.
        Based on emotions, personality, memory state, cooldown.
        """
        if self.language_stage < 1:
            return False  # Pre-linguistic stage
        
        current_time = time.time()
        
        # Check cooldown
        if current_time - self.last_speech_time < self.speech_cooldown:
            return False
        
        if not self.agent:
            return False
        
        # Strong emotions trigger speech
        emotions = self.agent.emotion.snapshot()
        for emotion, value in emotions.items():
            if abs(value) > 0.6:
                return True
        
        # Significant learning events
        if self.language_experience_count % 50 == 0 and self.language_experience_count > 0:
            return True
        
        # Personality-based random chance
        sociability = self.agent.personality.traits.get('sociability', 0.0)
        openness = self.agent.personality.traits.get('openness', 0.0)
        
        # Higher sociability = more likely to speak
        speak_probability = (sociability + openness + 2.0) / 60.0  # ~0.05-0.1 per check
        
        if np.random.rand() < speak_probability:
            return True
        
        return False
    
    
    def generate_speech(self, context: Dict[str, Any]) -> Optional[str]:
        """
        Generate autonomous speech (not in response to input).
        Used for self-expression, thoughts, observations.
        """
        self.last_speech_time = time.time()
        
        if self.language_stage == 0:
            return None
        
        # Extract current concept
        concept_vector = self._extract_concept_vector(context)
        
        # Generate based on stage
        if self.language_stage == 1:
            # Proto: single word expressing current state
            return self._generate_proto_response(concept_vector, context)
        
        elif self.language_stage >= 2:
            # Linguistic: express emotion or observation
            emotion = context.get('dominant_emotion', 'neutral')
            
            # Get words related to current state
            relevant_words = self._find_relevant_words(concept_vector, limit=4)
            
            if not relevant_words:
                return None
            
            # Generate emotive statement
            if emotion == 'joy' and len(relevant_words) >= 2:
                return f"*{relevant_words[0]} {relevant_words[1]}!*"
            elif emotion == 'fear' and relevant_words:
                return f"*worried about {relevant_words[0]}*"
            elif emotion == 'surprise' and relevant_words:
                return f"*notices {relevant_words[0]}*"
            elif len(relevant_words) >= 2:
                return f"{relevant_words[0]} {relevant_words[1]}"
            else:
                return relevant_words[0]
        
        return None
    
    
    # ==================== FILE LEARNING ====================
    
    def learn_from_file(self, file_path: str, filetype: str) -> str:
        """
        Learn from uploaded file (text, image, etc.)
        Returns summary of learning.
        """
        path = Path(file_path)
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        try:
            if filetype.startswith('text/') or path.suffix in ['.txt', '.md', '.json', '.py']:
                return self._learn_from_text_file(path)
            
            elif filetype.startswith('image/') or path.suffix in ['.jpg', '.png', '.bmp']:
                return self._learn_from_image_file(path)
            
            else:
                # Generic file storage
                if self.agent:
                    self.agent.memory.remember({
                        'type': 'file_input',
                        'tags': ['file'],
                        'payload': {
                            'filename': path.name,
                            'type': filetype,
                            'size': path.stat().st_size
                        }
                    })
                return f"File stored: {path.name}"
        
        except Exception as e:
            log.error(f"Failed to learn from file: {e}")
            return f"Error processing file: {str(e)}"
    
    
    def _learn_from_text_file(self, path: Path) -> str:
        """Learn from text file content"""
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return f"Failed to read file: {path.name}"
        
        # Build context
        context = {}
        if self.agent:
            context = {
                'health': self.agent.health,
                'hunger': self.agent.hunger,
                'emotions': self.agent.emotion.snapshot()
            }
        
        concept_vector = self._extract_concept_vector(context)
        
        # Process sentences
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        learned_words = 0
        new_patterns = 0
        
        for sentence in sentences[:50]:  # Process up to 50 sentences
            words = self._tokenize(sentence)
            
            # Ground words to concepts
            for word in words:
                if len(word) > 2:
                    self.word_to_concept[word].append(concept_vector)
                    self.word_frequencies[word] += 1
                    learned_words += 1
            
            # Store pattern
            if len(words) > 1:
                self.sentence_patterns.append(words)
                new_patterns += 1
            
            # Update co-occurrence
            self._update_co_occurrence(words)
        
        self.language_experience_count += len(sentences)
        self._update_language_stage()
        
        # Compute novelty
        novelty = self._compute_text_novelty(text)
        
        # Store in memory
        if self.agent:
            self.agent.memory.remember({
                'type': 'text_learning',
                'tags': ['text', 'learning', 'file'],
                'payload': {
                    'filename': path.name,
                    'sentences': len(sentences),
                    'words': learned_words,
                    'patterns': new_patterns,
                    'novelty': novelty
                }
            })
            
            # Update emotions based on novelty
            if novelty > 0.5:
                self.agent.emotion.add('surprise', min(0.15, novelty * 0.2))
                self.agent.emotion.add('joy', min(0.1, novelty * 0.15))
        
        return (f"Learned from text: {learned_words} words, "
                f"{new_patterns} patterns. "
                f"Stage: {self.language_stage}, "
                f"Vocab: {self.vocabulary_size}")
    
    
    def _learn_from_image_file(self, path: Path) -> str:
        """Learn from image file"""
        try:
            import cv2
            img = cv2.imread(str(path))
            
            if img is None:
                return f"Failed to load image: {path.name}"
            
            h, w = img.shape[:2]
            brightness = float(np.mean(img))
            
            # Create visual concept
            visual_features = np.array([
                w / 100.0,
                h / 100.0,
                brightness / 255.0,
                float(np.std(img)) / 255.0
            ], dtype=np.float32)
            
            # Pad to concept size
            concept = np.zeros(32, dtype=np.float32)
            concept[:len(visual_features)] = visual_features
            
            # Invent symbol for this visual concept
            concept_hash = self._hash_concept(concept)
            
            if concept_hash not in self.concept_to_word:
                symbol = self._invent_symbol(concept)
                log.info(f"Created visual symbol: {symbol} for {path.name}")
            
            # Store in memory
            if self.agent:
                self.agent.memory.remember({
                    'type': 'image_learning',
                    'tags': ['vision', 'learning', 'file'],
                    'payload': {
                        'filename': path.name,
                        'size': (w, h),
                        'brightness': brightness
                    }
                })
            
            return f"Image learned: {w}x{h}, brightness: {brightness:.1f}"
        
        except Exception as e:
            return f"Image processing error: {str(e)}"
    
    
    # ==================== LANGUAGE PROGRESS ====================
    
    def get_language_progress(self) -> Dict[str, Any]:
        """Get detailed language learning progress"""
        return {
            'stage': self.language_stage,
            'stage_name': ['pre-linguistic', 'proto-language', 'linguistic', 'advanced'][self.language_stage],
            'vocabulary_size': self.vocabulary_size,
            'experience_count': self.language_experience_count,
            'sentence_patterns': len(self.sentence_patterns),
            'invented_symbols': len(self.invented_symbols),
            'context_window_size': len(self.context_window),
            'most_frequent_words': sorted(
                self.word_frequencies.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:10]
        }


# ============================================================================
# INTEGRATION WITH BrainCore
# ============================================================================

def add_language_to_brain(brain_instance):
    """
    Add language capabilities to existing BrainCore instance.
    Usage: add_language_to_brain(agent.brain)
    """
    lang = LanguageIntelligence(agent_ref=brain_instance.agent)
    
    # Bind methods to brain instance
    brain_instance.language = lang
    brain_instance.process_language_input = lang.process_language_input
    brain_instance.should_speak = lang.should_speak
    brain_instance.generate_speech = lang.generate_speech
    brain_instance.learn_from_file = lang.learn_from_file
    brain_instance.get_language_progress = lang.get_language_progress
    
    log.info("Language capabilities added to BrainCore")


# ============================================================================
# STANDALONE USAGE
# ============================================================================

if __name__ == "__main__":
    # Test language intelligence standalone
    from ai_core.agent import NPCAgent
    
    logging.basicConfig(level=logging.INFO)
    
    print("\n=== Language Intelligence Test ===\n")
    
    # Create agent
    agent = NPCAgent("language_test")
    
    # Add language capabilities
   # In UnifiedChatSystem.__init__ or register_agent:
def register_agent(self, agent_id: str, agent):
    """Register agent - brain will handle all intelligence"""
    
    # Ensure brain has language capabilities
    if not hasattr(agent.brain, 'language'):
        from ai_core.brain_language import add_language_to_brain
        add_language_to_brain(agent.brain)
    
    self.registered_agents[agent_id] = agent
    log.info(f"Agent registered: {agent_id} with language capabilities")