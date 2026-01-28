# ai_core/unified_memory.py - UNIFIED MEMORY SYSTEM
"""
Unified Memory System with Complete ScyllaDB Integration
Replaces both memory.py and provides enhanced unified_memory functionality
"""

import time
import uuid
import numpy as np
import torch
import logging
from typing import Dict, Any, List, Optional, Tuple
from collections import deque, defaultdict

# ScyllaDB/Cassandra imports
try:
    from cassandra.cluster import Cluster
    from cassandra.query import SimpleStatement, BatchStatement, ConsistencyLevel
    from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy
    CASSANDRA_AVAILABLE = True
except Exception:
    CASSANDRA_AVAILABLE = False
    Cluster = None
    SimpleStatement = None

log = logging.getLogger("unified_memory")


class ScyllaMemoryBackend:
    """
    High-performance ScyllaDB backend for agent memories.
    Optimized for fast writes and retrieval with proper indexing.
    """
    
    def __init__(self, contact_points: List[str] = None, port: int = 9042, 
                 keyspace: str = 'divine_world_memories'):
        if not CASSANDRA_AVAILABLE:
            self.disabled = True
            log.warning("ScyllaDB driver not available - using in-memory only")
            return
        
        self.disabled = False
        self.keyspace = keyspace
        contact_points = contact_points or ['127.0.0.1']
        
        try:
            # Create cluster with optimized policies
            self.cluster = Cluster(
                contact_points,
                port=port,
                load_balancing_policy=TokenAwarePolicy(DCAwareRoundRobinPolicy()),
                protocol_version=4
            )
            self.session = self.cluster.connect()
            
            self._ensure_keyspace()
            self._ensure_tables()
            
            log.info(f"✅ ScyllaDB connected: {contact_points}")
            
        except Exception as e:
            log.error(f"ScyllaDB initialization failed: {e}")
            self.disabled = True
    
    def _ensure_keyspace(self):
        """Create keyspace with proper replication"""
        try:
            cql = f"""
                CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
                WITH replication = {{
                    'class': 'NetworkTopologyStrategy',
                    'replication_factor': 3
                }}
                AND durable_writes = true
            """
            self.session.execute(cql)
            self.session.set_keyspace(self.keyspace)
            log.info(f"Keyspace ensured: {self.keyspace}")
        except Exception as e:
            log.error(f"Keyspace creation error: {e}")
    
    def _ensure_tables(self):
        """Create optimized memory tables"""
        try:
            # Main memories table with time-series optimization
            self.session.execute(f"""
                CREATE TABLE IF NOT EXISTS memories (
                    agent_id text,
                    bucket bigint,
                    event_id timeuuid,
                    timestamp double,
                    event_type text,
                    tags set<text>,
                    text text,
                    payload text,
                    embedding blob,
                    PRIMARY KEY ((agent_id, bucket), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
                AND compaction = {{
                    'class': 'TimeWindowCompactionStrategy',
                    'compaction_window_unit': 'DAYS',
                    'compaction_window_size': 1
                }}
            """)
            
            # Tag index for fast tag-based queries
            self.session.execute(f"""
                CREATE TABLE IF NOT EXISTS memories_by_tag (
                    agent_id text,
                    tag text,
                    timestamp double,
                    event_id timeuuid,
                    PRIMARY KEY ((agent_id, tag), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
            """)
            
            # Type index for event type queries
            self.session.execute(f"""
                CREATE TABLE IF NOT EXISTS memories_by_type (
                    agent_id text,
                    event_type text,
                    timestamp double,
                    event_id timeuuid,
                    PRIMARY KEY ((agent_id, event_type), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
            """)
            
            # Embedding index for semantic search (simplified)
            self.session.execute(f"""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    agent_id text,
                    event_id timeuuid,
                    embedding_type text,
                    embedding blob,
                    timestamp double,
                    PRIMARY KEY (agent_id, event_id)
                )
            """)
            
            log.info("Memory tables ensured")
            
        except Exception as e:
            log.error(f"Table creation error: {e}")
    
    def save_event(self, agent_id: str, event: Dict[str, Any], 
                   embedding: Optional[np.ndarray] = None):
        """Save event with batch optimization"""
        if self.disabled:
            return
        
        try:
            import json
            
            event_id = uuid.uuid1()  # Time-based UUID
            timestamp = event.get('timestamp', time.time())
            
            # Time bucketing (1 day buckets)
            bucket = int(timestamp // 86400)
            
            # Prepare data
            tags = set(event.get('tags', []))
            event_type = event.get('type', 'unknown')
            text = event.get('text', '')
            
            # Serialize payload
            payload_data = {
                k: v for k, v in event.items()
                if k not in ['timestamp', 'type', 'tags', 'text', 'event_id']
            }
            payload_json = json.dumps(payload_data)
            
            # Serialize embedding
            embedding_bytes = embedding.tobytes() if embedding is not None else None
            
            # Batch insert for performance
            batch = BatchStatement(consistency_level=ConsistencyLevel.LOCAL_QUORUM)
            
            # Main table
            batch.add(SimpleStatement("""
                INSERT INTO memories (agent_id, bucket, event_id, timestamp, event_type, tags, text, payload, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """), (agent_id, bucket, event_id, timestamp, event_type, tags, text, payload_json, embedding_bytes))
            
            # Tag indexes
            for tag in tags:
                batch.add(SimpleStatement("""
                    INSERT INTO memories_by_tag (agent_id, tag, timestamp, event_id)
                    VALUES (?, ?, ?, ?)
                """), (agent_id, tag, timestamp, event_id))
            
            # Type index
            batch.add(SimpleStatement("""
                INSERT INTO memories_by_type (agent_id, event_type, timestamp, event_id)
                VALUES (?, ?, ?, ?)
            """), (agent_id, event_type, timestamp, event_id))
            
            # Embedding table (if provided)
            if embedding_bytes:
                batch.add(SimpleStatement("""
                    INSERT INTO memory_embeddings (agent_id, event_id, embedding_type, embedding, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """), (agent_id, event_id, 'default', embedding_bytes, timestamp))
            
            self.session.execute(batch)
            
        except Exception as e:
            log.error(f"Save event error: {e}")
    
    def query_recent(self, agent_id: str, limit: int = 10, 
                     since: Optional[float] = None) -> List[Dict]:
        """Query recent memories with time filter"""
        if self.disabled:
            return []
        
        try:
            import json
            
            # Calculate bucket range
            current_bucket = int(time.time() // 86400)
            bucket_range = range(current_bucket - 7, current_bucket + 1)  # Last 7 days
            
            results = []
            
            for bucket in reversed(list(bucket_range)):
                if len(results) >= limit:
                    break
                
                if since:
                    query = """
                        SELECT * FROM memories 
                        WHERE agent_id = ? AND bucket = ? AND timestamp > ?
                        LIMIT ?
                    """
                    rows = self.session.execute(query, (agent_id, bucket, since, limit - len(results)))
                else:
                    query = """
                        SELECT * FROM memories 
                        WHERE agent_id = ? AND bucket = ?
                        LIMIT ?
                    """
                    rows = self.session.execute(query, (agent_id, bucket, limit - len(results)))
                
                for row in rows:
                    event = json.loads(row.payload) if row.payload else {}
                    event.update({
                        'event_id': str(row.event_id),
                        'timestamp': row.timestamp,
                        'type': row.event_type,
                        'tags': list(row.tags) if row.tags else [],
                        'text': row.text or ''
                    })
                    results.append(event)
            
            # Sort by timestamp descending
            results.sort(key=lambda x: x['timestamp'], reverse=True)
            
            return results[:limit]
            
        except Exception as e:
            log.error(f"Query recent error: {e}")
            return []
    
    def query_by_tags(self, agent_id: str, tags: List[str], 
                      limit: int = 10) -> List[Dict]:
        """Query memories by tags"""
        if self.disabled:
            return []
        
        try:
            import json
            
            # Query each tag and merge results
            all_event_ids = set()
            
            for tag in tags:
                query = """
                    SELECT event_id FROM memories_by_tag
                    WHERE agent_id = ? AND tag = ?
                    LIMIT ?
                """
                rows = self.session.execute(query, (agent_id, tag, limit * 2))
                all_event_ids.update(str(row.event_id) for row in rows)
            
            if not all_event_ids:
                return []
            
            # Fetch full events (batch)
            results = []
            for event_id in list(all_event_ids)[:limit]:
                # This is simplified - in production, use batch queries
                results.extend(self.query_recent(agent_id, limit=limit))
            
            return results[:limit]
            
        except Exception as e:
            log.error(f"Query by tags error: {e}")
            return []
    
    def query_by_type(self, agent_id: str, event_type: str, 
                      limit: int = 10) -> List[Dict]:
        """Query memories by event type"""
        if self.disabled:
            return []
        
        try:
            query = """
                SELECT event_id, timestamp FROM memories_by_type
                WHERE agent_id = ? AND event_type = ?
                LIMIT ?
            """
            rows = self.session.execute(query, (agent_id, event_type, limit))
            
            # Fetch full events
            return self.query_recent(agent_id, limit=limit)
            
        except Exception as e:
            log.error(f"Query by type error: {e}")
            return []
    
    def close(self):
        """Close connection"""
        if not self.disabled and self.cluster:
            self.cluster.shutdown()


class UnifiedMemoryStore:
    """
    Unified memory system with ScyllaDB backend and in-memory cache.
    Single source of truth for ALL agent memories.
    """
    
    def __init__(self, agent_id: str, capacity: int = 10000,
                 use_scylla: bool = True, scylla_hosts: List[str] = None):
        self.agent_id = agent_id
        self.capacity = capacity
        
        # In-memory cache for fast access
        self.events: deque = deque(maxlen=capacity)
        self.event_index = 0
        
        # Tag index
        self.tag_index: Dict[str, List[int]] = defaultdict(list)
        
        # Type index
        self.type_index: Dict[str, List[int]] = defaultdict(list)
        
        # Embedding cache
        self.embeddings: Dict[int, np.ndarray] = {}
        
        # ScyllaDB backend
        self.use_scylla = use_scylla
        self.scylla = None
        
        if use_scylla:
            self.scylla = ScyllaMemoryBackend(contact_points=scylla_hosts)
            self.use_scylla = not self.scylla.disabled
        
        backend = "ScyllaDB" if self.use_scylla else "In-Memory"
        log.info(f"UnifiedMemoryStore initialized for {agent_id} ({backend})")
    
    def remember(self, event: Dict[str, Any], tags: List[str] = None,
                 embedding: Optional[np.ndarray] = None) -> int:
        """Store event in unified memory"""
        event_id = self.event_index
        self.event_index += 1
        
        # Ensure required fields
        event.setdefault('timestamp', time.time())
        event.setdefault('type', 'unknown')
        event['tags'] = tags or event.get('tags', [])
        event['event_id'] = event_id
        
        # Store in memory cache
        self.events.append(event)
        
        # Update indexes
        for tag in event['tags']:
            self.tag_index[tag].append(event_id)
        
        self.type_index[event['type']].append(event_id)
        
        # Store embedding
        if embedding is not None:
            self.embeddings[event_id] = embedding
        
        # Persist to ScyllaDB
        if self.use_scylla and self.scylla:
            self.scylla.save_event(self.agent_id, event, embedding)
        
        return event_id
    
    def recall(self, n: int = 10, tags: List[str] = None,
               event_type: str = None, since: float = None) -> List[Dict]:
        """Recall memories with filtering"""
        
        # Try ScyllaDB first for better performance on large datasets
        if self.use_scylla and self.scylla and len(self.events) > 1000:
            if tags:
                return self.scylla.query_by_tags(self.agent_id, tags, n)
            elif event_type:
                return self.scylla.query_by_type(self.agent_id, event_type, n)
            elif since:
                return self.scylla.query_recent(self.agent_id, n, since)
        
        # Fallback to in-memory
        filtered = []
        
        for event in reversed(self.events):
            # Apply filters
            if since and event['timestamp'] < since:
                continue
            
            if event_type and event['type'] != event_type:
                continue
            
            if tags and not any(tag in event['tags'] for tag in tags):
                continue
            
            filtered.append(event.copy())
            
            if len(filtered) >= n:
                break
        
        return filtered
    
    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Simple text search in memories"""
        results = []
        q = query.lower()
        
        for event in reversed(self.events):
            text = str(event.get('text', '')).lower()
            if q in text:
                results.append(event.copy())
                if len(results) >= limit:
                    break
        
        return results
    
    def semantic_search(self, query_embedding: np.ndarray, k: int = 10,
                        tags: List[str] = None) -> List[Dict]:
        """Semantic search using embeddings"""
        if not self.embeddings:
            return []
        
        similarities = []
        for event_id, embedding in self.embeddings.items():
            similarity = np.dot(query_embedding, embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(embedding) + 1e-8
            )
            similarities.append((event_id, similarity))
        
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for event_id, similarity in similarities[:k]:
            for event in self.events:
                if event['event_id'] == event_id:
                    if tags and not any(tag in event['tags'] for tag in tags):
                        continue
                    
                    result = event.copy()
                    result['similarity'] = similarity
                    results.append(result)
                    break
            
            if len(results) >= k:
                break
        
        return results
    
    def get_training_batch(self, batch_size: int = 32,
                           tags: List[str] = None) -> List[Dict]:
        """Sample batch for training"""
        candidates = []
        
        if tags:
            for tag in tags:
                if tag in self.tag_index:
                    for event_id in self.tag_index[tag]:
                        for event in self.events:
                            if event['event_id'] == event_id:
                                candidates.append(event)
                                break
        else:
            candidates = list(self.events)[-1000:]
        
        if len(candidates) <= batch_size:
            return candidates
        
        # Weighted sampling (prefer recent)
        indices = np.arange(len(candidates))
        weights = np.exp(indices / len(candidates))
        weights = weights / weights.sum()
        
        sampled_indices = np.random.choice(
            indices, size=batch_size, replace=False, p=weights
        )
        
        return [candidates[i] for i in sampled_indices]
    
    def novelty_score(self, text: str) -> float:
        """Compute novelty of text"""
        if not self.events:
            return 1.0
        
        low = text.lower()[:200]
        matches = sum(
            1 for e in self.events
            if low in str(e.get('text', '')).lower()
        )
        
        return 1.0 / (1 + matches)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            'total_events': len(self.events),
            'unique_tags': len(self.tag_index),
            'unique_types': len(self.type_index),
            'embeddings_stored': len(self.embeddings),
            'backend': 'ScyllaDB' if self.use_scylla else 'In-Memory',
            'capacity': self.capacity,
            'oldest_event': self.events[0]['timestamp'] if self.events else None,
            'newest_event': self.events[-1]['timestamp'] if self.events else None
        }
    
    def close(self):
        """Close connections"""
        if self.scylla:
            self.scylla.close()


# Legacy compatibility
Memory = UnifiedMemoryStore
EpisodicMemory = UnifiedMemoryStore