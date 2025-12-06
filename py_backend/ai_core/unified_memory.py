# ai_core/unified_memory.py - FIXED ARCHITECTURE
"""
Unified Memory System with ScyllaDB Backend
Solves the memory fragmentation problem between agent and language
"""

import time
import numpy as np
import torch
from typing import Dict, Any, List, Optional
from collections import deque
import logging

# Optional ScyllaDB integration
try:
    from cassandra.cluster import Cluster
    from cassandra.query import SimpleStatement
    SCYLLA_AVAILABLE = True
except ImportError:
    SCYLLA_AVAILABLE = False

log = logging.getLogger("unified_memory")


class UnifiedMemoryStore:
    """
    Single source of truth for ALL agent memories.
    Replaces fragmented memory systems with unified storage.
    
    Features:
    - Tag-based retrieval (existing tag system)
    - Semantic search via embeddings
    - Temporal queries
    - ScyllaDB backend for scale
    """
    
    def __init__(self, agent_id: str, capacity: int = 10000, 
                 use_scylla: bool = False, scylla_hosts: List[str] = None):
        self.agent_id = agent_id
        self.capacity = capacity
        
        # In-memory storage (fast access)
        self.events: deque = deque(maxlen=capacity)
        self.event_index = 0
        
        # Tag index for fast retrieval
        self.tag_index: Dict[str, List[int]] = {}
        
        # Embedding cache for semantic search
        self.embeddings: Dict[int, np.ndarray] = {}
        
        # ScyllaDB backend (optional)
        self.use_scylla = use_scylla and SCYLLA_AVAILABLE
        self.scylla_session = None
        
        if self.use_scylla:
            self._init_scylla(scylla_hosts or ['127.0.0.1'])
        
        log.info(f"UnifiedMemoryStore initialized for {agent_id}")
        log.info(f"  Backend: {'ScyllaDB' if self.use_scylla else 'In-Memory'}")
    
    def _init_scylla(self, hosts: List[str]):
        """Initialize ScyllaDB connection"""
        try:
            cluster = Cluster(hosts)
            self.scylla_session = cluster.connect()
            
            # Create keyspace
            self.scylla_session.execute(f"""
                CREATE KEYSPACE IF NOT EXISTS agent_memories
                WITH replication = {{'class': 'SimpleStrategy', 'replication_factor': 3}}
            """)
            
            self.scylla_session.set_keyspace('agent_memories')
            
            # Create table with proper indexing
            self.scylla_session.execute(f"""
                CREATE TABLE IF NOT EXISTS memories (
                    agent_id text,
                    event_id bigint,
                    timestamp double,
                    event_type text,
                    tags set<text>,
                    payload text,
                    embedding blob,
                    PRIMARY KEY ((agent_id), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
            """)
            
            # Create secondary indexes for common queries
            self.scylla_session.execute("""
                CREATE INDEX IF NOT EXISTS ON memories (event_type)
            """)
            
            log.info("âœ… ScyllaDB initialized")
            
        except Exception as e:
            log.error(f"ScyllaDB init failed: {e}")
            self.use_scylla = False
    
    def remember(self, event: Dict[str, Any], tags: List[str] = None, 
                 embedding: Optional[np.ndarray] = None) -> int:
        """
        Store event in unified memory.
        Returns event_id for later retrieval.
        """
        event_id = self.event_index
        self.event_index += 1
        
        # Ensure required fields
        event.setdefault('timestamp', time.time())
        event.setdefault('type', 'unknown')
        event['tags'] = tags or event.get('tags', [])
        event['event_id'] = event_id
        
        # Store in memory
        self.events.append(event)
        
        # Update tag index
        for tag in event['tags']:
            if tag not in self.tag_index:
                self.tag_index[tag] = []
            self.tag_index[tag].append(event_id)
        
        # Store embedding if provided
        if embedding is not None:
            self.embeddings[event_id] = embedding
        
        # Store in ScyllaDB if enabled
        if self.use_scylla:
            self._store_to_scylla(event, embedding)
        
        return event_id
    
    def _store_to_scylla(self, event: Dict[str, Any], embedding: Optional[np.ndarray]):
        """Store event to ScyllaDB"""
        try:
            import json
            
            query = """
                INSERT INTO memories (agent_id, event_id, timestamp, event_type, tags, payload, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            
            payload_json = json.dumps({
                k: v for k, v in event.items() 
                if k not in ['event_id', 'timestamp', 'type', 'tags']
            })
            
            embedding_bytes = embedding.tobytes() if embedding is not None else None
            
            self.scylla_session.execute(query, (
                self.agent_id,
                event['event_id'],
                event['timestamp'],
                event['type'],
                set(event['tags']),
                payload_json,
                embedding_bytes
            ))
            
        except Exception as e:
            log.error(f"ScyllaDB store failed: {e}")
    
    def recall(self, n: int = 10, tags: List[str] = None, 
               event_type: str = None, since: float = None) -> List[Dict]:
        """
        Recall memories with filtering.
        
        Args:
            n: Number of events to retrieve
            tags: Filter by tags (OR logic)
            event_type: Filter by event type
            since: Only events after this timestamp
        """
        # For simple in-memory queries
        if not self.use_scylla:
            filtered = []
            
            for event in reversed(self.events):
                # Apply filters
                if since and event['timestamp'] < since:
                    continue
                
                if event_type and event['type'] != event_type:
                    continue
                
                if tags and not any(tag in event['tags'] for tag in tags):
                    continue
                
                filtered.append(event)
                
                if len(filtered) >= n:
                    break
            
            return filtered
        
        # ScyllaDB query for large-scale retrieval
        else:
            return self._recall_from_scylla(n, tags, event_type, since)
    
    def _recall_from_scylla(self, n: int, tags: List[str], 
                            event_type: str, since: float) -> List[Dict]:
        """Recall from ScyllaDB"""
        try:
            import json
            
            # Build query
            query_parts = ["SELECT * FROM memories WHERE agent_id = ?"]
            params = [self.agent_id]
            
            if since:
                query_parts.append("AND timestamp > ?")
                params.append(since)
            
            if event_type:
                query_parts.append("AND event_type = ?")
                params.append(event_type)
            
            query_parts.append(f"LIMIT {n}")
            query = " ".join(query_parts)
            
            rows = self.scylla_session.execute(query, params)
            
            # Convert to events
            events = []
            for row in rows:
                event = json.loads(row.payload)
                event['event_id'] = row.event_id
                event['timestamp'] = row.timestamp
                event['type'] = row.event_type
                event['tags'] = list(row.tags)
                
                # Filter by tags if specified (post-query filtering)
                if tags and not any(tag in event['tags'] for tag in tags):
                    continue
                
                events.append(event)
            
            return events[:n]
            
        except Exception as e:
            log.error(f"ScyllaDB recall failed: {e}")
            return []
    
    def semantic_search(self, query_embedding: np.ndarray, k: int = 10,
                        tags: List[str] = None) -> List[Dict]:
        """
        Search by semantic similarity.
        Uses cosine similarity between embeddings.
        """
        if not self.embeddings:
            return []
        
        # Compute similarities
        similarities = []
        for event_id, embedding in self.embeddings.items():
            similarity = np.dot(query_embedding, embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(embedding) + 1e-8
            )
            similarities.append((event_id, similarity))
        
        # Sort by similarity
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        # Retrieve top-k events
        results = []
        for event_id, similarity in similarities[:k]:
            # Find event in memory
            for event in self.events:
                if event['event_id'] == event_id:
                    # Apply tag filter if specified
                    if tags and not any(tag in event['tags'] for tag in tags):
                        continue
                    
                    event_copy = event.copy()
                    event_copy['similarity'] = similarity
                    results.append(event_copy)
                    break
            
            if len(results) >= k:
                break
        
        return results
    
    def get_training_batch(self, batch_size: int = 32, 
                           tags: List[str] = None) -> List[Dict]:
        """
        Sample batch for language training.
        Prioritizes recent and tagged experiences.
        """
        candidates = []
        
        if tags:
            # Get events with specified tags
            for tag in tags:
                if tag in self.tag_index:
                    for event_id in self.tag_index[tag]:
                        for event in self.events:
                            if event['event_id'] == event_id:
                                candidates.append(event)
                                break
        else:
            # Use recent events
            candidates = list(self.events)[-1000:]
        
        # Sample batch
        if len(candidates) <= batch_size:
            return candidates
        
        # Weighted sampling (prefer recent)
        indices = np.arange(len(candidates))
        weights = np.exp(indices / len(candidates))  # Exponential weighting
        weights = weights / weights.sum()
        
        sampled_indices = np.random.choice(
            indices, size=batch_size, replace=False, p=weights
        )
        
        return [candidates[i] for i in sampled_indices]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            'total_events': len(self.events),
            'unique_tags': len(self.tag_index),
            'embeddings_stored': len(self.embeddings),
            'backend': 'ScyllaDB' if self.use_scylla else 'In-Memory',
            'capacity': self.capacity,
            'oldest_event': self.events[0]['timestamp'] if self.events else None,
            'newest_event': self.events[-1]['timestamp'] if self.events else None
        }


# =============================================================================
# ENHANCED LANGUAGE MODULE - USES UNIFIED MEMORY
# =============================================================================

class EnhancedLanguageIntelligence:
    """
    Enhanced language intelligence that:
    1. Uses unified memory (no separate context window)
    2. Trains on ALL agent experiences (not just language)
    3. Generates responses using full personality + context
    """
    
    def __init__(self, agent_ref, memory_store: UnifiedMemoryStore):
        self.agent = agent_ref
        self.memory = memory_store  # UNIFIED MEMORY
        
        # Import existing transformer components
        from ai_core.brain_language import (
            MultimodalGroundingTransformer, 
            Vocabulary
        )
        
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        
        # Vocabulary
        self.vocab = Vocabulary(max_size=5000)
        
        # Transformer (from existing brain_language.py)
        self.model = MultimodalGroundingTransformer(
            concept_dim=256,
            context_dim=64,  # EXPANDED for personality
            n_heads=4,
            n_layers=2,
            vocab_size=5000
        ).to(self.device)
        
        self.optimizer = torch.optim.AdamW(self.model.parameters(), lr=3e-4)
        
        # Language development
        self.language_stage = 0
        self.vocabulary_size = 4  # Start with special tokens
        
        # Speech control
        self.last_speech_time = 0
        self.speech_cooldown = 10.0
        
        log.info("Enhanced Language Intelligence initialized with unified memory")
    
    def process_language_input(self, text: str, context: Dict[str, Any]) -> str:
        """Process language using UNIFIED memory"""
        
        # 1. Store in unified memory
        event = {
            'type': 'language_input',
            'text': text,
            'context_snapshot': context
        }
        
        self.memory.remember(event, tags=['language', 'input', 'human'])
        
        # 2. Add words to vocabulary
        words = text.lower().split()
        for word in words:
            if len(word) > 2:
                self.vocab.add_word(word)
                self.vocabulary_size = self.vocab.next_id
        
        # 3. Train on unified memory (not just this input)
        self._train_from_unified_memory()
        
        # 4. Generate response using FULL context
        response = self._generate_contextual_response(text, context)
        
        # 5. Store response in memory
        if response:
            self.memory.remember({
                'type': 'language_output',
                'text': response,
                'context_snapshot': context
            }, tags=['language', 'output', 'agent'])
        
        return response
    
    def _train_from_unified_memory(self):
        """Train on ALL experiences, not just language"""
        
        # Get diverse training batch from unified memory
        batch_events = self.memory.get_training_batch(
            batch_size=32,
            tags=['language', 'action', 'perception', 'emotion']  # ALL types
        )
        
        if len(batch_events) < 8:
            return
        
        # Convert events to training data
        observations = []
        texts = []
        
        for event in batch_events:
            # Extract text (from language OR describe other events)
            if 'text' in event:
                text = event['text']
            else:
                # Generate text description of non-language events
                text = self._event_to_text(event)
            
            # Build multimodal context
            context_features = self._build_context_features(
                event.get('context_snapshot', {})
            )
            
            observations.append(context_features)
            texts.append(text)
        
        # Train transformer
        self._train_transformer_batch(texts, observations)
    
    def _event_to_text(self, event: Dict[str, Any]) -> str:
        """Convert non-language event to text description"""
        etype = event['type']
        
        if etype == 'action':
            return f"I performed action: {event.get('action_type', 'unknown')}"
        
        elif etype == 'perception':
            return f"I perceived: {event.get('description', 'environment')}"
        
        elif etype == 'emotion':
            emotion = event.get('emotion', 'neutral')
            return f"I felt {emotion}"
        
        elif etype == 'reward':
            reward = event.get('reward', 0)
            if reward > 0:
                return "That was good"
            else:
                return "That was bad"
        
        return "Something happened"
    
    def _build_context_features(self, context: Dict[str, Any]) -> torch.Tensor:
        """Build FULL context vector including personality"""
        features = []
        
        # Basic state
        features.extend([
            context.get('health', 20.0) / 20.0,
            context.get('hunger', 20.0) / 20.0,
            context.get('saturation', 5.0) / 20.0
        ])
        
        # Emotions (8 dimensions)
        if 'emotions' in context:
            emotions = context['emotions']
            for e in ['joy', 'fear', 'surprise', 'anger', 'sadness', 
                      'trust', 'anticipation', 'disgust']:
                features.append(emotions.get(e, 0.0))
        else:
            features.extend([0.0] * 8)
        
        # PERSONALITY (8 dimensions) - CRITICAL FOR AUTHENTIC SPEECH
        if self.agent and hasattr(self.agent, 'personality'):
            persona = self.agent.personality.as_array()
            features.extend(persona.tolist())
        else:
            features.extend([0.0] * 8)
        
        # Recent activity (simplified)
        features.extend([
            context.get('recent_actions', 0) / 10.0,
            context.get('recent_speech', 0) / 10.0,
            len(self.memory.events) / 1000.0
        ])
        
        # Pad to 64
        while len(features) < 64:
            features.append(0.0)
        
        return torch.tensor(features[:64], dtype=torch.float32, device=self.device)
    
    def _train_transformer_batch(self, texts: List[str], 
                                  contexts: List[torch.Tensor]):
        """Train transformer on batch"""
        # Tokenize texts
        max_len = max(len(self.vocab.tokenize(t)) for t in texts)
        max_len = min(max_len, 32)  # Cap sequence length
        
        token_ids_batch = []
        for text in texts:
            tokens = self.vocab.tokenize(text)
            # Pad
            tokens = tokens + [0] * (max_len - len(tokens))
            token_ids_batch.append(tokens[:max_len])
        
        token_ids = torch.tensor(token_ids_batch, dtype=torch.long, device=self.device)
        context_batch = torch.stack(contexts)
        
        # Forward pass
        self.model.train()
        output = self.model(token_ids, context_batch)
        
        # Loss
        targets = token_ids[:, 1:]  # Shifted for next-word prediction
        targets = torch.cat([targets, torch.zeros(targets.shape[0], 1, 
                             dtype=torch.long, device=self.device)], dim=1)
        
        word_logits = output['word_logits']
        loss = torch.nn.functional.cross_entropy(
            word_logits.reshape(-1, self.vocab.max_size),
            targets.reshape(-1),
            ignore_index=0
        )
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
        self.optimizer.step()
    
    def _generate_contextual_response(self, input_text: str, 
                                       context: Dict[str, Any]) -> str:
        """
        Generate response using:
        1. Input text
        2. Full personality
        3. Recent memories
        4. Emotional state
        """
        if self.language_stage == 0:
            return ""  # Pre-linguistic
        
        # Build FULL context vector
        context_vector = self._build_context_features(context)
        
        # Retrieve relevant memories
        relevant_memories = self.memory.recall(
            n=5, 
            tags=['language'],
            since=time.time() - 300  # Last 5 minutes
        )
        
        # Use recent context + personality for generation
        self.model.eval()
        
        with torch.no_grad():
            # Start with input tokens
            input_tokens = self.vocab.tokenize(input_text)
            seed_tokens = input_tokens[-3:] if len(input_tokens) >= 3 else [2]  # START
            
            current_tokens = torch.tensor([seed_tokens], dtype=torch.long, device=self.device)
            
            generated = []
            for _ in range(15):  # Generate up to 15 tokens
                output = self.model(current_tokens, context_vector.unsqueeze(0))
                
                # Sample next token
                logits = output['word_logits'][0, -1, :]
                
                # Temperature based on personality
                if self.agent:
                    openness = self.agent.personality.traits.get('openness', 0.0)
                    temperature = 0.7 + openness * 0.3  # 0.4 to 1.0
                else:
                    temperature = 0.8
                
                probs = torch.softmax(logits / temperature, dim=0)
                next_token = torch.multinomial(probs, 1).item()
                
                if next_token in [0, 3]:  # PAD or END
                    break
                
                generated.append(next_token)
                
                # Update tokens
                current_tokens = torch.cat([
                    current_tokens[:, -2:],
                    torch.tensor([[next_token]], dtype=torch.long, device=self.device)
                ], dim=1)
            
            if generated:
                response = self.vocab.decode(generated)
                return response
        
        return ""
    
    def should_speak(self) -> bool:
        """Decide if agent should speak autonomously"""
        if self.language_stage < 1:
            return False
        
        current_time = time.time()
        if current_time - self.last_speech_time < self.speech_cooldown:
            return False
        
        # Check emotions in unified memory
        recent_events = self.memory.recall(n=5, tags=['emotion'])
        
        for event in recent_events:
            if event.get('intensity', 0) > 0.6:
                return True
        
        # Personality-based
        if self.agent:
            sociability = self.agent.personality.traits.get('sociability', 0.0)
            return np.random.rand() < (sociability + 1.0) / 40.0
        
        return False
    
    def generate_speech(self, context: Dict[str, Any]) -> Optional[str]:
        """Generate autonomous speech"""
        self.last_speech_time = time.time()
        
        if self.language_stage == 0:
            return None
        
        # Use recent memories as context
        recent_memories = self.memory.recall(n=10, tags=['language', 'emotion', 'action'])
        
        # Build prompt from recent experiences
        prompt_words = []
        for mem in recent_memories[-3:]:
            if 'text' in mem:
                prompt_words.extend(mem['text'].split()[-2:])
        
        if not prompt_words:
            prompt_words = ['hello']
        
        prompt = ' '.join(prompt_words)
        
        return self._generate_contextual_response(prompt, context)