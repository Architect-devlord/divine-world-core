# ai_core/memory.py - UNIFIED MEMORY SYSTEM
"""
Unified Memory System — merged from memory.py + unified_memory.py.

Exports (all preserved for backward compatibility):
  - ScyllaMemoryBackend   — high-performance ScyllaDB persistence layer
  - Memory                — short-term in-memory store (original interface, now aliases UnifiedMemoryStore)
  - EpisodicMemory        — RL replay buffer (original interface preserved)
  - UnifiedMemoryStore    — primary unified store with ScyllaDB backend + in-memory cache

Integration notes:
  - agent.py uses UnifiedMemoryStore directly; Memory/EpisodicMemory remain as aliases/stubs
    so any file that previously imported them continues to work unchanged.
  - ScyllaMemoryBackend is identical to the one previously in memory.py, now enhanced with
    the optimised table schema from unified_memory.py.
"""

import time
import uuid
import json
import logging
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from collections import deque, defaultdict

# ScyllaDB / Cassandra driver (optional)
try:
    from cassandra.cluster import Cluster
    from cassandra.query import SimpleStatement, BatchStatement, ConsistencyLevel
    from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy
    CASSANDRA_AVAILABLE = True
except Exception:
    CASSANDRA_AVAILABLE = False
    Cluster = None
    SimpleStatement = None
    BatchStatement = None
    ConsistencyLevel = None

log = logging.getLogger("memory")


# =============================================================================
# SCYLLADB BACKEND
# =============================================================================

class ScyllaMemoryBackend:
    """
    High-performance ScyllaDB backend for agent memories.
    Optimised for fast writes and retrieval with proper indexing.
    Unchanged public API from original memory.py; schema enhanced from unified_memory.py.
    """

    def __init__(self, contact_points: List[str] = None, port: int = 9042,
                 keyspace: str = 'divine_world_memories'):
        if not CASSANDRA_AVAILABLE:
            self.disabled = True
            log.warning("ScyllaDB driver not available — using in-memory only")
            return

        self.disabled = False
        self.keyspace = keyspace
        contact_points = contact_points or ['127.0.0.1']

        try:
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
            log.error(f"ScyllaDB initialisation failed: {e}")
            self.disabled = True

    # ------------------------------------------------------------------
    # Schema helpers
    # ------------------------------------------------------------------

    def _ensure_keyspace(self):
        try:
            self.session.execute(f"""
                CREATE KEYSPACE IF NOT EXISTS {self.keyspace}
                WITH replication = {{
                    'class': 'NetworkTopologyStrategy',
                    'replication_factor': 3
                }}
                AND durable_writes = true
            """)
            self.session.set_keyspace(self.keyspace)
        except Exception as e:
            log.error(f"Keyspace creation error: {e}")

    def _ensure_tables(self):
        try:
            # Main memories table — time-series optimised
            self.session.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    agent_id  text,
                    bucket    bigint,
                    event_id  timeuuid,
                    timestamp double,
                    event_type text,
                    tags      set<text>,
                    text      text,
                    payload   text,
                    embedding blob,
                    PRIMARY KEY ((agent_id, bucket), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
                AND compaction = {
                    'class': 'TimeWindowCompactionStrategy',
                    'compaction_window_unit': 'DAYS',
                    'compaction_window_size': 1
                }
            """)

            # Tag index
            self.session.execute("""
                CREATE TABLE IF NOT EXISTS memories_by_tag (
                    agent_id  text,
                    tag       text,
                    timestamp double,
                    event_id  timeuuid,
                    PRIMARY KEY ((agent_id, tag), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
            """)

            # Type index
            self.session.execute("""
                CREATE TABLE IF NOT EXISTS memories_by_type (
                    agent_id   text,
                    event_type text,
                    timestamp  double,
                    event_id   timeuuid,
                    PRIMARY KEY ((agent_id, event_type), timestamp, event_id)
                ) WITH CLUSTERING ORDER BY (timestamp DESC)
            """)

            # Embedding index
            self.session.execute("""
                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    agent_id       text,
                    event_id       timeuuid,
                    embedding_type text,
                    embedding      blob,
                    timestamp      double,
                    PRIMARY KEY (agent_id, event_id)
                )
            """)

            log.info("Memory tables ensured")
        except Exception as e:
            log.error(f"Table creation error: {e}")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def save_event(self, agent_id: str, event: Dict[str, Any],
                   embedding: Optional[np.ndarray] = None):
        """Persist a single event via batched CQL."""
        if self.disabled:
            return

        try:
            event_id = uuid.uuid1()
            timestamp = event.get('timestamp', time())
            bucket = int(timestamp // 86400)

            tags = set(event.get('tags', []))
            event_type = event.get('type', 'unknown')
            text = event.get('text', '')

            payload_data = {
                k: v for k, v in event.items()
                if k not in ('timestamp', 'type', 'tags', 'text', 'event_id')
            }
            payload_json = json.dumps(payload_data, default=str)
            embedding_bytes = embedding.tobytes() if embedding is not None else None

            batch = BatchStatement(consistency_level=ConsistencyLevel.LOCAL_QUORUM)

            batch.add(SimpleStatement("""
                INSERT INTO memories
                    (agent_id, bucket, event_id, timestamp, event_type, tags, text, payload, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """), (agent_id, bucket, event_id, timestamp, event_type,
                   tags, text, payload_json, embedding_bytes))

            for tag in tags:
                batch.add(SimpleStatement("""
                    INSERT INTO memories_by_tag (agent_id, tag, timestamp, event_id)
                    VALUES (?, ?, ?, ?)
                """), (agent_id, tag, timestamp, event_id))

            batch.add(SimpleStatement("""
                INSERT INTO memories_by_type (agent_id, event_type, timestamp, event_id)
                VALUES (?, ?, ?, ?)
            """), (agent_id, event_type, timestamp, event_id))

            if embedding_bytes:
                batch.add(SimpleStatement("""
                    INSERT INTO memory_embeddings
                        (agent_id, event_id, embedding_type, embedding, timestamp)
                    VALUES (?, ?, ?, ?, ?)
                """), (agent_id, event_id, 'default', embedding_bytes, timestamp))

            self.session.execute(batch)

        except Exception as e:
            log.error(f"save_event error: {e}")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def query_recent(self, agent_id: str, limit: int = 10,
                     since: Optional[float] = None) -> List[Dict]:
        """Return most-recent memories, optionally filtered by `since` timestamp."""
        if self.disabled:
            return []
        try:
            current_bucket = int(time() // 86400)
            bucket_range = range(current_bucket - 7, current_bucket + 1)
            results = []

            for bucket in reversed(list(bucket_range)):
                if len(results) >= limit:
                    break

                if since:
                    rows = self.session.execute(
                        "SELECT * FROM memories WHERE agent_id=? AND bucket=? AND timestamp>? LIMIT ?",
                        (agent_id, bucket, since, limit - len(results))
                    )
                else:
                    rows = self.session.execute(
                        "SELECT * FROM memories WHERE agent_id=? AND bucket=? LIMIT ?",
                        (agent_id, bucket, limit - len(results))
                    )

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

            results.sort(key=lambda x: x['timestamp'], reverse=True)
            return results[:limit]

        except Exception as e:
            log.error(f"query_recent error: {e}")
            return []

    def query_by_tags(self, agent_id: str, tags: List[str],
                      limit: int = 10) -> List[Dict]:
        """Return memories matching any of the given tags.

        FIX: Old code collected event_ids from memories_by_tag but then called
        query_recent() which ignored those ids entirely — the tag filter was a
        dead join.  Now we use the ids to fetch matching timestamps and return
        only those events via a bounded IN-style fetch.
        """
        if self.disabled:
            return []
        try:
            # Gather (timestamp, event_id) pairs for matched tags
            matched: list = []
            for tag in tags:
                rows = self.session.execute(
                    "SELECT timestamp, event_id FROM memories_by_tag "
                    "WHERE agent_id=? AND tag=? LIMIT ?",
                    (agent_id, tag, limit * 4)
                )
                for r in rows:
                    matched.append((r.timestamp, str(r.event_id)))

            if not matched:
                return []

            # Sort by timestamp descending, deduplicate, take top `limit`
            matched.sort(key=lambda x: x[0], reverse=True)
            seen_ids: set = set()
            top_ts: list  = []
            for ts, eid in matched:
                if eid not in seen_ids:
                    seen_ids.add(eid)
                    top_ts.append(ts)
                if len(top_ts) >= limit:
                    break

            # Fetch full events whose timestamps we now know
            if not top_ts:
                return []
            oldest_ts = min(top_ts)
            results = self.query_recent(agent_id, limit=limit * 2, since=oldest_ts - 1)
            # Filter to only the matched event_ids
            results = [r for r in results if str(r.get('event_id', '')) in seen_ids]
            return results[:limit]

        except Exception as e:
            log.error(f"query_by_tags error: {e}")
            return []

    def query_by_type(self, agent_id: str, event_type: str,
                      limit: int = 10) -> List[Dict]:
        """Return memories of a specific event type.

        FIX: Old code fetched event_ids/timestamps but returned query_recent()
        which ignored the type filter entirely.  Now we use the fetched
        timestamps to bound a since-filtered recent query.
        """
        if self.disabled:
            return []
        try:
            rows = list(self.session.execute(
                "SELECT timestamp FROM memories_by_type "
                "WHERE agent_id=? AND event_type=? LIMIT ?",
                (agent_id, event_type, limit * 2)
            ))
            if not rows:
                return []
            oldest_ts = min(r.timestamp for r in rows)
            results = self.query_recent(agent_id, limit=limit * 2, since=oldest_ts - 1)
            return [r for r in results if r.get('type') == event_type][:limit]
        except Exception as e:
            log.error(f"query_by_type error: {e}")
            return []

    def close(self):
        if not self.disabled and self.cluster:
            self.cluster.shutdown()


# =============================================================================
# UNIFIED MEMORY STORE  (primary store — used by agent.py directly)
# =============================================================================

class UnifiedMemoryStore:
    """
    Single source of truth for ALL agent memories.

    Provides:
      - In-memory deque cache for fast, low-latency access
      - Tag and type indexes for O(1) filtered recall
      - Embedding cache for semantic search
      - Optional ScyllaDB backend for persistence and large-scale queries
      - Full backward-compatible surface: remember / recall / search / novelty_score /
        get_training_batch / semantic_search / get_stats / close
    """

    def __init__(self, agent_id: str = 'default', capacity: int = 10000,
                 use_scylla: bool = True, scylla_hosts: List[str] = None):
        self.agent_id = agent_id
        self.capacity = capacity

        # In-memory cache
        self.events: deque = deque(maxlen=capacity)
        self.event_index = 0

        # Indexes
        self.tag_index: Dict[str, List[int]] = defaultdict(list)
        self.type_index: Dict[str, List[int]] = defaultdict(list)

        # Embedding cache  {event_id -> np.ndarray}
        self.embeddings: Dict[int, np.ndarray] = {}

        # ScyllaDB backend
        self.scylla: Optional[ScyllaMemoryBackend] = None
        self.use_scylla = False

        if use_scylla:
            self.scylla = ScyllaMemoryBackend(contact_points=scylla_hosts)
            self.use_scylla = not self.scylla.disabled

        backend = "ScyllaDB" if self.use_scylla else "In-Memory"
        log.info(f"UnifiedMemoryStore initialised for '{agent_id}' ({backend})")

    # ------------------------------------------------------------------
    # Core write
    # ------------------------------------------------------------------

    def remember(self, event: Dict[str, Any], tags: List[str] = None,
                 embedding: Optional[np.ndarray] = None) -> int:
        """
        Store an event.

        Args:
            event:     Arbitrary dict — must be JSON-serialisable for ScyllaDB persistence.
            tags:      Optional list of string tags (merged with event['tags'] if present).
            embedding: Optional numpy embedding for semantic search.

        Returns:
            Integer event_id assigned to this event.
        """
        event_id = self.event_index
        self.event_index += 1

        event.setdefault('timestamp', time())
        event.setdefault('type', 'unknown')

        # Merge tags
        existing = event.get('tags', [])
        merged_tags = list(dict.fromkeys((tags or []) + (existing if isinstance(existing, list) else list(existing))))
        event['tags'] = merged_tags
        event['event_id'] = event_id

        # Cache
        self.events.append(event)

        # Indexes
        for tag in merged_tags:
            self.tag_index[tag].append(event_id)
        self.type_index[event['type']].append(event_id)

        # Embedding
        if embedding is not None:
            self.embeddings[event_id] = embedding

        # Persist
        if self.use_scylla and self.scylla:
            self.scylla.save_event(self.agent_id, event, embedding)

        return event_id

    # ------------------------------------------------------------------
    # Core read
    # ------------------------------------------------------------------

    def recall(self, n: int = 10, tags: List[str] = None,
               event_type: str = None, since: float = None) -> List[Dict]:
        """
        Return up to `n` recent memories, with optional filters.

        Delegates to ScyllaDB when the in-memory cache is large (>1000 events)
        and a specific filter is provided; otherwise uses the fast in-memory path.
        """
        # Prefer ScyllaDB for large datasets with specific filters
        if self.use_scylla and self.scylla and len(self.events) > 1000:
            if tags:
                return self.scylla.query_by_tags(self.agent_id, tags, n)
            if event_type:
                return self.scylla.query_by_type(self.agent_id, event_type, n)
            if since:
                return self.scylla.query_recent(self.agent_id, n, since)

        # In-memory path
        filtered = []
        for event in reversed(self.events):
            if since and event.get('timestamp', 0) < since:
                continue
            if event_type and event.get('type') != event_type:
                continue
            if tags and not any(t in event.get('tags', []) for t in tags):
                continue
            filtered.append(event.copy())
            if len(filtered) >= n:
                break

        return filtered

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Simple substring search across the `text` field of cached events."""
        q = query.lower()
        results = []
        for event in reversed(self.events):
            if q in str(event.get('text', '')).lower():
                results.append(event.copy())
                if len(results) >= limit:
                    break
        return results

    def semantic_search(self, query_embedding: np.ndarray, k: int = 10,
                        tags: List[str] = None) -> List[Dict]:
        """
        Cosine-similarity search over the stored embedding cache.

        Args:
            query_embedding: 1-D numpy array.
            k:               Max results to return.
            tags:            Optional tag filter applied after similarity ranking.

        Returns:
            List of event dicts with an added 'similarity' key.
        """
        if not self.embeddings:
            return []

        similarities: List[Tuple[int, float]] = []
        for eid, emb in self.embeddings.items():
            sim = float(np.dot(query_embedding, emb) /
                        (np.linalg.norm(query_embedding) * np.linalg.norm(emb) + 1e-8))
            similarities.append((eid, sim))

        similarities.sort(key=lambda x: x[1], reverse=True)

        # Build a lookup dict for O(1) event access
        event_by_id = {e['event_id']: e for e in self.events if 'event_id' in e}

        results = []
        for eid, sim in similarities[:k * 2]:  # over-fetch to allow for tag filtering
            event = event_by_id.get(eid)
            if event is None:
                continue
            if tags and not any(t in event.get('tags', []) for t in tags):
                continue
            result = event.copy()
            result['similarity'] = sim
            results.append(result)
            if len(results) >= k:
                break

        return results

    def get_training_batch(self, batch_size: int = 32,
                           tags: List[str] = None) -> List[Dict]:
        """
        Sample a batch of events for training, weighted towards recent events.

        Args:
            batch_size: Number of events to return.
            tags:       If provided, only sample from events with these tags.

        Returns:
            List of event dicts.
        """
        if tags:
            # Collect candidates from tag index
            seen = set()
            candidates = []
            event_by_id = {e['event_id']: e for e in self.events if 'event_id' in e}
            for tag in tags:
                for eid in self.tag_index.get(tag, []):
                    if eid not in seen:
                        seen.add(eid)
                        ev = event_by_id.get(eid)
                        if ev is not None:
                            candidates.append(ev)
        else:
            candidates = list(self.events)[-1000:]

        if not candidates:
            return []

        if len(candidates) <= batch_size:
            return list(candidates)

        # Exponentially weighted sampling — prefer recent
        indices = np.arange(len(candidates))
        weights = np.exp(indices / len(candidates))
        weights /= weights.sum()

        sampled = np.random.choice(indices, size=batch_size, replace=False, p=weights)
        return [candidates[i] for i in sampled]

    def novelty_score(self, text: str) -> float:
        """
        Returns a score in (0, 1] reflecting how novel `text` is relative to
        stored memories.  Score of 1.0 means completely unseen; lower means
        the text (or a prefix) has been encountered many times before.
        """
        if not self.events:
            return 1.0

        probe = text.lower()[:200]
        matches = sum(
            1 for e in self.events
            if probe in str(e.get('text', '')).lower()
        )
        return 1.0 / (1 + matches)

    # ------------------------------------------------------------------
    # Stats & lifecycle
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            'total_events':     len(self.events),
            'unique_tags':      len(self.tag_index),
            'unique_types':     len(self.type_index),
            'embeddings_stored': len(self.embeddings),
            'backend':          'ScyllaDB' if self.use_scylla else 'In-Memory',
            'capacity':         self.capacity,
            'oldest_event':     self.events[0]['timestamp'] if self.events else None,
            'newest_event':     self.events[-1]['timestamp'] if self.events else None,
        }

    def close(self):
        """Shut down the ScyllaDB connection if active."""
        if self.scylla:
            self.scylla.close()


# =============================================================================
# EPISODIC MEMORY  (original RL replay buffer — interface preserved)
# =============================================================================

class EpisodicMemory:
    """
    Prioritised RL replay buffer.

    Kept as a distinct class because its access pattern (sample by TD-error priority,
    store (obs, action, reward, next_obs, done) tuples) differs fundamentally from the
    event-store semantics of UnifiedMemoryStore.

    Original public API is fully preserved.
    """

    def __init__(self, capacity: int = 50000):
        self.capacity = capacity
        self.buffer: deque = deque(maxlen=capacity)
        self.priorities: deque = deque(maxlen=capacity)
        self._max_priority: float = 1.0

    def add(self, obs: np.ndarray, action: np.ndarray, reward: float,
            next_obs: np.ndarray, done: bool,
            priority: Optional[float] = None):
        """Add a transition to the replay buffer."""
        transition = (obs, action, reward, next_obs, done)
        self.buffer.append(transition)
        self.priorities.append(priority if priority is not None else self._max_priority)

    def sample(self, batch_size: int,
               alpha: float = 0.6) -> Optional[Tuple]:
        """
        Importance-sampled batch.

        Returns:
            Tuple of (obs, actions, rewards, next_obs, dones, indices, weights)
            or None if buffer is too small.
        """
        if len(self.buffer) < batch_size:
            return None

        priorities = np.array(self.priorities, dtype=np.float32) ** alpha
        probs = priorities / priorities.sum()

        indices = np.random.choice(len(self.buffer), size=batch_size,
                                   replace=False, p=probs)

        weights = (len(self.buffer) * probs[indices]) ** (-1.0)
        weights /= weights.max()

        batch = [self.buffer[i] for i in indices]
        obs, actions, rewards, next_obs, dones = zip(*batch)

        return (
            np.array(obs),
            np.array(actions),
            np.array(rewards, dtype=np.float32),
            np.array(next_obs),
            np.array(dones, dtype=bool),
            indices,
            weights.astype(np.float32)
        )

    def update_priorities(self, indices: np.ndarray, priorities: np.ndarray):
        """Update TD-error priorities after a learning step."""
        for idx, prio in zip(indices, priorities):
            self.priorities[idx] = float(prio)
            if prio > self._max_priority:
                self._max_priority = float(prio)

    def __len__(self) -> int:
        return len(self.buffer)

    def is_ready(self, min_size: int = 1000) -> bool:
        return len(self.buffer) >= min_size


# =============================================================================
# LEGACY ALIASES  (backward compatibility)
# =============================================================================

# Any file that previously did `from ai_core.memory import Memory` continues to work.
# Memory now delegates entirely to UnifiedMemoryStore.
Memory = UnifiedMemoryStore
