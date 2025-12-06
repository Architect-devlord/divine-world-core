# ai_core/brain_language.pY TRANSFORMER-BASED LANGUAGE LEARNING
"""
Brain Language Extension - Transformer-based Language Intelligence
------------------------------------------------------------------------
Uses transformer architecture for:
- Multimodal understanding (vision + language grounding)
- Developmental language learning (like humans learn)
- Symbol grounding through experience
- Emergent language creation

NOT a chatbot wrapper - this is the agent LEARNING language.
"""

import time
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, Any, Optional, List, Tuple
from collections import defaultdict, deque
from pathlib import Path
import logging

log = logging.getLogger("brain.language")


# ============================================================================
# TRANSFORMER ENCODER FOR MULTIMODAL GROUNDING
# ============================================================================

class MultimodalGroundingTransformer(nn.Module):
    """
    Transformer that learns to ground concepts to multimodal observations.
    This is how the agent LEARNS what words mean.
    """
    
    def __init__(self, 
                 concept_dim: int = 256,
                 context_dim: int = 32,  # vision, audio, state features
                 n_heads: int = 4,
                 n_layers: int = 2,
                 vocab_size: int = 5000):
        super().__init__()
        
        self.concept_dim = concept_dim
        self.vocab_size = vocab_size
        
        # Word embeddings (learned)
        self.word_embeddings = nn.Embedding(vocab_size, concept_dim)
        
        # Context encoder (multimodal → concept space)
        self.context_encoder = nn.Sequential(
            nn.Linear(context_dim, 128),
            nn.ReLU(),
            nn.Linear(128, concept_dim)
        )
        
        # Transformer for reasoning over concepts
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=concept_dim,
            nhead=n_heads,
            dim_feedforward=concept_dim * 2,
            dropout=0.1,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        # Output heads
        self.word_predictor = nn.Linear(concept_dim, vocab_size)  # Predict next word
        self.context_predictor = nn.Linear(concept_dim, context_dim)  # Predict context from words
        
    def forward(self, word_ids: torch.Tensor, context: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Forward pass for learning word-context associations.
        
        Args:
            word_ids: (batch, seq_len) token IDs
            context: (batch, context_dim) multimodal context features
        
        Returns:
            dict with predictions
        """
        batch_size = word_ids.shape[0]
        
        # Embed words
        word_embeds = self.word_embeddings(word_ids)  # (batch, seq_len, concept_dim)
        
        # Encode context
        context_embed = self.context_encoder(context).unsqueeze(1)  # (batch, 1, concept_dim)
        
        # Combine: [context, word1, word2, ...]
        combined = torch.cat([context_embed, word_embeds], dim=1)
        
        # Transform
        transformed = self.transformer(combined)
        
        # Predictions
        word_logits = self.word_predictor(transformed[:, 1:, :])  # Skip context token
        predicted_context = self.context_predictor(transformed[:, 0, :])  # Use context token
        
        return {
            'word_logits': word_logits,
            'predicted_context': predicted_context,
            'concept_embeddings': transformed
        }
    
    def ground_word(self, word_id: int, context: torch.Tensor) -> torch.Tensor:
        """
        Get grounded concept vector for a word in given context.
        This is the agent understanding what the word means.
        """
        word_ids = torch.tensor([[word_id]], dtype=torch.long, device=context.device)
        
        with torch.no_grad():
            output = self.forward(word_ids, context.unsqueeze(0))
            concept = output['concept_embeddings'][0, 1, :]  # First word's concept
        
        return concept


# ============================================================================
# VOCABULARY MANAGER
# ============================================================================

class Vocabulary:
    """Manages word-to-ID mappings and learns new words"""
    
    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self.word_to_id: Dict[str, int] = {
            '<PAD>': 0,
            '<UNK>': 1,
            '<START>': 2,
            '<END>': 3
        }
        self.id_to_word: Dict[int, str] = {v: k for k, v in self.word_to_id.items()}
        self.word_counts: Dict[str, int] = defaultdict(int)
        self.next_id = 4
    
    def add_word(self, word: str) -> int:
        """Add word to vocabulary, return ID"""
        word = word.lower().strip()
        
        if not word or len(word) < 2:
            return self.word_to_id['<UNK>']
        
        if word in self.word_to_id:
            self.word_counts[word] += 1
            return self.word_to_id[word]
        
        if self.next_id >= self.max_size:
            # Vocabulary full, use UNK
            return self.word_to_id['<UNK>']
        
        # Add new word
        word_id = self.next_id
        self.word_to_id[word] = word_id
        self.id_to_word[word_id] = word
        self.word_counts[word] = 1
        self.next_id += 1
        
        log.info(f"Learned new word: '{word}' (ID: {word_id})")
        return word_id
    
    def get_id(self, word: str) -> int:
        """Get ID for word (or UNK)"""
        return self.word_to_id.get(word.lower(), self.word_to_id['<UNK>'])
    
    def get_word(self, word_id: int) -> str:
        """Get word for ID"""
        return self.id_to_word.get(word_id, '<UNK>')
    
    def tokenize(self, text: str) -> List[int]:
        """Convert text to token IDs"""
        import re
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        words = text.split()
        return [self.get_id(w) for w in words if w]
    
    def decode(self, token_ids: List[int]) -> str:
        """Convert token IDs to text"""
        words = [self.get_word(tid) for tid in token_ids]
        return ' '.join(w for w in words if w not in ['<PAD>', '<UNK>', '<START>', '<END>'])


# ============================================================================
# MAIN LANGUAGE INTELLIGENCE
# ============================================================================

class LanguageIntelligence:
    """
    Transformer-based language learning for agents.
    Learns through experience, not pre-training.
    """
    
    def __init__(self, agent_ref=None, device: str = None):
        self.agent = agent_ref
        
        if device is None:
            self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        else:
            self.device = torch.device(device)
        
        # Vocabulary
        self.vocab = Vocabulary(max_size=5000)
        
        # Transformer model
        self.model = MultimodalGroundingTransformer(
            concept_dim=256,
            context_dim=32,
            n_heads=4,
            n_layers=2,
            vocab_size=self.vocab.max_size
        ).to(self.device)
        
        # Optimizer
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=3e-4)
        
        # Training state
        self.training_buffer: deque = deque(maxlen=1000)
        self.updates_done = 0
        
        # Developmental stage
        self.language_stage = 0  # 0=pre-linguistic, 1=proto, 2=linguistic, 3=advanced
        self.experience_count = 0
        
        # Speech control
        self.last_speech_time = 0
        self.speech_cooldown = 10.0
        
        # Context memory
        self.context_window: deque = deque(maxlen=20)
        
        log.info(f"Language Intelligence initialized on {self.device}")
    
    # ==================== CORE LEARNING ====================
    
    def process_language_input(self, text: str, context: Dict[str, Any]) -> str:
        """
        Process incoming language and learn from it.
        Returns generated response (or empty if pre-linguistic).
        """
        if not text or not text.strip():
            return ""
        
        text = text.strip()
        
        # Extract multimodal context features
        context_vector = self._extract_context_vector(context)
        
        # Tokenize
        token_ids = self.vocab.tokenize(text)
        
        # Store for learning
        self.training_buffer.append({
            'tokens': token_ids,
            'context': context_vector.cpu().numpy(),
            'text': text,
            'timestamp': time.time()
        })
        
        # Learn from this input
        if len(self.training_buffer) >= 8:  # Batch of 8
            self._train_step()
        
        # Update vocabulary with new words
        for word in text.lower().split():
            if len(word) > 2:
                self.vocab.add_word(word)
        
        # Update developmental stage
        self.experience_count += 1
        self._update_language_stage()
        
        # Store in context window
        self.context_window.append({
            'text': text,
            'tokens': token_ids,
            'context': context_vector.cpu().numpy(),
            'timestamp': time.time()
        })
        
        # Generate response based on stage
        response = self._generate_response(token_ids, context_vector, context)
        
        # Evaluate as learning event
        if self.agent and hasattr(self.agent, 'brain'):
            event = {
                'type': 'language_input',
                'tags': ['language', 'learning'],
                'payload': {
                    'text': text,
                    'words': len(token_ids),
                    'stage': self.language_stage,
                    'vocab_size': self.vocab.next_id
                }
            }
            reward, emotion_delta = self.agent.brain.evaluate_event(event, context)
            
            # Update emotions
            if hasattr(self.agent, 'emotion'):
                for emotion, value in emotion_delta.items():
                    self.agent.emotion.add(emotion, value)
        
        return response
    
    def _train_step(self):
        """Single training step on buffered experiences"""
        if len(self.training_buffer) < 4:
            return
        
        # Sample batch
        batch = list(self.training_buffer)[-8:]  # Last 8 experiences
        
        # Prepare tensors
        max_len = max(len(exp['tokens']) for exp in batch)
        
        token_ids = []
        contexts = []
        targets = []
        
        for exp in batch:
            # Pad tokens
            tokens = exp['tokens'] + [0] * (max_len - len(exp['tokens']))
            token_ids.append(tokens[:max_len])
            
            contexts.append(exp['context'])
            
            # Target: predict next word (shifted)
            target = tokens[1:] + [0]
            targets.append(target[:max_len])
        
        token_ids = torch.tensor(token_ids, dtype=torch.long, device=self.device)
        contexts = torch.tensor(np.array(contexts), dtype=torch.float32, device=self.device)
        targets = torch.tensor(targets, dtype=torch.long, device=self.device)
        
        # Forward pass
        self.model.train()
        output = self.model(token_ids, contexts)
        
        # Loss: predict next word + predict context from words
        word_loss = nn.functional.cross_entropy(
            output['word_logits'].reshape(-1, self.vocab.max_size),
            targets.reshape(-1),
            ignore_index=0  # Ignore padding
        )
        
        context_loss = nn.functional.mse_loss(
            output['predicted_context'],
            contexts
        )
        
        total_loss = word_loss + 0.5 * context_loss
        
        # Backward pass
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()
        
        self.updates_done += 1
        
        if self.updates_done % 10 == 0:
            log.info(f"Language update {self.updates_done}: "
                    f"word_loss={word_loss.item():.4f}, "
                    f"context_loss={context_loss.item():.4f}")
    
    def _extract_context_vector(self, context: Dict[str, Any]) -> torch.Tensor:
        """Extract fixed-size context vector from multimodal context"""
        features = []
        
        # Visual features (simple stats if available)
        if 'visual' in context and context['visual'] is not None:
            visual = context['visual']
            if isinstance(visual, np.ndarray):
                if len(visual.shape) == 3:
                    features.extend([
                        float(np.mean(visual)),
                        float(np.std(visual)),
                        float(np.max(visual)),
                        float(np.min(visual))
                    ])
                else:
                    features.extend(visual.flatten()[:4].tolist())
        
        # State features
        features.extend([
            context.get('health', 20.0) / 20.0,
            context.get('hunger', 20.0) / 20.0,
            context.get('saturation', 5.0) / 20.0
        ])
        
        # Position
        if 'position' in context:
            pos = context['position']
            features.extend([
                pos.get('x', 0.0) / 100.0,
                pos.get('y', 64.0) / 100.0,
                pos.get('z', 0.0) / 100.0
            ])
        
        # Emotions
        if 'emotions' in context:
            emotions = context['emotions']
            for e in ['joy', 'fear', 'surprise', 'anger']:
                features.append(emotions.get(e, 0.0))
        
        # Personality
        if self.agent and hasattr(self.agent, 'personality'):
            persona = self.agent.personality.as_array()
            features.extend(persona[:4].tolist())
        
        # Pad to fixed size (32)
        while len(features) < 32:
            features.append(0.0)
        
        return torch.tensor(features[:32], dtype=torch.float32, device=self.device)
    
    def _update_language_stage(self):
        """Update developmental language stage"""
        old_stage = self.language_stage
        vocab_size = self.vocab.next_id
        
        # Stage progression
        if self.experience_count >= 5 and vocab_size >= 15:
            self.language_stage = max(self.language_stage, 1)  # Proto-language
        
        if vocab_size >= 50 and self.experience_count >= 50:
            self.language_stage = max(self.language_stage, 2)  # Linguistic
        
        if vocab_size >= 200 and self.experience_count >= 200:
            self.language_stage = max(self.language_stage, 3)  # Advanced
        
        if self.language_stage != old_stage:
            log.info(f"Language stage: {old_stage} → {self.language_stage}")
    
    # ==================== RESPONSE GENERATION ====================
    
    def _generate_response(self, input_tokens: List[int], 
                          context_vector: torch.Tensor,
                          context: Dict[str, Any]) -> str:
        """Generate response using transformer"""
        
        if self.language_stage == 0:
            return ""  # Pre-linguistic
        
        self.model.eval()
        
        with torch.no_grad():
            # Start with input tokens
            current_tokens = torch.tensor([input_tokens[-3:]], dtype=torch.long, device=self.device)
            
            # Generate up to 10 tokens
            generated = []
            for _ in range(10):
                output = self.model(current_tokens, context_vector.unsqueeze(0))
                
                # Get next token prediction
                logits = output['word_logits'][0, -1, :]  # Last position
                
                # Sample (with temperature for creativity)
                temperature = 0.8 if self.language_stage >= 2 else 1.2
                probs = torch.softmax(logits / temperature, dim=0)
                next_token = torch.multinomial(probs, 1).item()
                
                # Stop if end token or padding
                if next_token in [0, 3]:  # PAD or END
                    break
                
                generated.append(next_token)
                
                # Update current tokens
                current_tokens = torch.cat([
                    current_tokens[:, -2:],  # Keep last 2 tokens
                    torch.tensor([[next_token]], dtype=torch.long, device=self.device)
                ], dim=1)
            
            # Decode
            if generated:
                response = self.vocab.decode(generated)
                return response
            
        return ""
    
    # ==================== AUTONOMOUS SPEECH ====================
    
    def should_speak(self) -> bool:
        """Decide if agent should speak autonomously"""
        if self.language_stage < 1:
            return False
        
        current_time = time.time()
        if current_time - self.last_speech_time < self.speech_cooldown:
            return False
        
        if not self.agent:
            return False
        
        # Strong emotions trigger speech
        emotions = self.agent.emotion.snapshot()
        for emotion, value in emotions.items():
            if abs(value) > 0.6:
                return True
        
        # Personality-based random chance
        sociability = self.agent.personality.traits.get('sociability', 0.0)
        speak_probability = (sociability + 1.0) / 40.0
        
        return np.random.rand() < speak_probability
    
    def generate_speech(self, context: Dict[str, Any]) -> Optional[str]:
        """Generate autonomous speech"""
        self.last_speech_time = time.time()
        
        if self.language_stage == 0:
            return None
        
        context_vector = self._extract_context_vector(context)
        
        # Use recent context as seed
        if self.context_window:
            recent = list(self.context_window)[-1]
            seed_tokens = recent['tokens'][-3:]
        else:
            seed_tokens = [2]  # START token
        
        response = self._generate_response(seed_tokens, context_vector, context)
        
        if response and len(response) > 2:
            return response
        
        return None
    
    # ==================== FILE LEARNING ====================
    
    def learn_from_file(self, file_path: str, filetype: str) -> str:
        """Learn from uploaded file"""
        path = Path(file_path)
        
        if not path.exists():
            return f"File not found: {file_path}"
        
        try:
            if filetype.startswith('text/') or path.suffix in ['.txt', '.md']:
                return self._learn_from_text_file(path)
            else:
                return f"Unsupported file type: {filetype}"
        except Exception as e:
            log.error(f"Failed to learn from file: {e}")
            return f"Error: {str(e)}"
    
    def _learn_from_text_file(self, path: Path) -> str:
        """Learn from text file"""
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return f"Failed to read: {path.name}"
        
        # Build context
        context = {}
        if self.agent:
            context = {
                'health': self.agent.health,
                'hunger': self.agent.hunger,
                'emotions': self.agent.emotion.snapshot()
            }
        
        context_vector = self._extract_context_vector(context)
        
        # Process sentences
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        learned_words = 0
        
        for sentence in sentences[:100]:  # Max 100 sentences
            tokens = self.vocab.tokenize(sentence)
            
            # Add to training buffer
            self.training_buffer.append({
                'tokens': tokens,
                'context': context_vector.cpu().numpy(),
                'text': sentence,
                'timestamp': time.time()
            })
            
            # Learn new words
            for word in sentence.lower().split():
                if len(word) > 2:
                    self.vocab.add_word(word)
                    learned_words += 1
            
            self.experience_count += 1
        
        # Train on buffered data
        for _ in range(10):  # Multiple passes
            if len(self.training_buffer) >= 8:
                self._train_step()
        
        self._update_language_stage()
        
        return (f"Learned from text: {learned_words} words, "
                f"{len(sentences)} sentences. "
                f"Stage: {self.language_stage}, "
                f"Vocab: {self.vocab.next_id}")
    
    # ==================== PERSISTENCE ====================
    
    def get_language_progress(self) -> Dict[str, Any]:
        """Get language learning progress"""
        return {
            'stage': self.language_stage,
            'stage_name': ['pre-linguistic', 'proto-language', 'linguistic', 'advanced'][self.language_stage],
            'vocabulary_size': self.vocab.next_id,
            'experience_count': self.experience_count,
            'updates_done': self.updates_done,
            'most_frequent_words': sorted(
                self.vocab.word_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:20]
        }
    
    def state_dict(self) -> Dict[str, Any]:
        """Get state for saving"""
        return {
            'model': self.model.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'vocab_word_to_id': dict(self.vocab.word_to_id),
            'vocab_counts': dict(self.vocab.word_counts),
            'vocab_next_id': self.vocab.next_id,
            'language_stage': self.language_stage,
            'experience_count': self.experience_count,
            'updates_done': self.updates_done
        }
    
    def load_state_dict(self, state: Dict[str, Any]):
        """Load state from save"""
        self.model.load_state_dict(state['model'])
        self.optimizer.load_state_dict(state['optimizer'])
        
        self.vocab.word_to_id = state['vocab_word_to_id']
        self.vocab.id_to_word = {v: k for k, v in self.vocab.word_to_id.items()}
        self.vocab.word_counts = defaultdict(int, state['vocab_counts'])
        self.vocab.next_id = state['vocab_next_id']
        
        self.language_stage = state['language_stage']
        self.experience_count = state['experience_count']
        self.updates_done = state['updates_done']
        
        log.info("Language state loaded successfully")


# ============================================================================
# INTEGRATION
# ============================================================================

def add_language_to_brain(brain_instance):
    """Add language capabilities to BrainCore"""
    lang = LanguageIntelligence(agent_ref=brain_instance.agent)
    
    brain_instance.language = lang
    brain_instance.process_language_input = lang.process_language_input
    brain_instance.should_speak = lang.should_speak
    brain_instance.generate_speech = lang.generate_speech
    brain_instance.learn_from_file = lang.learn_from_file
    brain_instance.get_language_progress = lang.get_language_progress
    
    log.info("Language capabilities added to BrainCore")

# This file (brain_language.py) is the transformer-based learning system