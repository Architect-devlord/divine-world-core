# ------------------------------------------------------------------------------
# ai_core/memory.py - Memory systems (no circular deps)
# ------------------------------------------------------------------------------

import time
from typing import List, Dict, Any, Optional
from collections import deque
import numpy as np
import logging
import uuid

log = logging.getLogger("memory")

# Try to import Cassandra driver globally
try:
    from cassandra.cluster import Cluster
    from cassandra.query import SimpleStatement
    CASSANDRA_AVAILABLE = True
except Exception as e:
    log.warning(f"cassandra-driver not available; Scylla backend disabled ({e})")
    Cluster = None
    SimpleStatement = None
    CASSANDRA_AVAILABLE = False


# ------------------------------------------------------------------------------
# Basic Short-Term Memory
# ------------------------------------------------------------------------------
class Memory:
    """Simple short-term memory for events."""

    def __init__(self, capacity: int = 1000, scylla_backend=None):
        self.events = deque(maxlen=capacity)
        self.capacity = capacity
        self.scylla = scylla_backend

    def remember(self, event: Dict[str, Any], tags: Optional[List[str]] = None):
        """Store event"""
        if not isinstance(event, dict):
            event = {'text': str(event), 'type': 'unknown'}

        event.setdefault('timestamp', time.time())
        event.setdefault('tags', tags or [])
        self.events.append(event)

        # Persist to Scylla if backend enabled
        try:
            if getattr(self, 'scylla', None):
                agent_id = (
                    event.get('agent_id')
                    or event.get('source_agent')
                    or 'unknown'
                )
                self.scylla.save_event(agent_id, event)
        except Exception as e:
            log.exception(f"Failed to persist memory to Scylla: {e}")

    def recall(self, n: int = 10) -> List[Dict]:
        return list(self.events)[-n:]

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Simple full-text search."""
        results = []
        q = query.lower()

        for e in reversed(self.events):
            if q in str(e.get("text", "")).lower():
                results.append(e)
                if len(results) >= limit:
                    break

        return results

    def novelty_score(self, text: str) -> float:
        """How new is this message?"""
        if not self.events:
            return 1.0

        low = text.lower()[:200]
        matches = sum(
            1 for e in self.events
            if low in str(e.get("text", "")).lower()
        )

        return 1.0 / (1 + matches)


# ------------------------------------------------------------------------------
# Episodic Memory (RL)
# ------------------------------------------------------------------------------
class EpisodicMemory:
    """Replay buffer with importance sampling."""

    def __init__(self, capacity: int = 10000):
        self.buffer = deque(maxlen=capacity)
        self.importance_weights = deque(maxlen=capacity)

    def store(self, obs, action, reward, next_obs, done, importance: float = 1.0):
        self.buffer.append((obs, action, reward, next_obs, done))
        self.importance_weights.append(importance)

    def sample(self, batch_size: int = 32):
        if len(self.buffer) < batch_size:
            indices = range(len(self.buffer))
        else:
            w = np.array(self.importance_weights, dtype=float)
            w = w / w.sum()
            indices = np.random.choice(
                len(self.buffer),
                batch_size,
                replace=False,
                p=w
            )

        batch = [self.buffer[i] for i in indices]
        obs, actions, rewards, next_obs, dones = zip(*batch)

        return (
            np.array(obs),
            np.array(actions),
            np.array(rewards),
            np.array(next_obs),
            np.array(dones),
        )

    def __len__(self):
        return len(self.buffer)


# ------------------------------------------------------------------------------
# Scylla / Cassandra Memory Backend
# ------------------------------------------------------------------------------
class ScyllaMemoryBackend:
    """Scylla/Cassandra storage for multimodal memory"""

    def __init__(self, contact_points=None, port=9042, keyspace='divine_world'):
        if not CASSANDRA_AVAILABLE:
            self.disabled = True
            return

        self.disabled = False
        contact_points = contact_points or ['127.0.0.1']

        try:
            self.cluster = Cluster(contact_points, port=port)
            self.session = self.cluster.connect()
            self.keyspace = keyspace

            self._ensure_keyspace()
            self._ensure_table()

        except Exception as e:
            log.error(f"Failed to initialize Scylla cluster: {e}")
            self.disabled = True

    # Create keyspace
    def _ensure_keyspace(self):
        cql = (
            f"CREATE KEYSPACE IF NOT EXISTS {self.keyspace} "
            "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': '1'};"
        )
        try:
            self.session.execute(cql)
            self.session.set_keyspace(self.keyspace)
        except Exception as e:
            log.error(f"Error creating keyspace: {e}")

    # Create memories table
    def _ensure_table(self):
        cql = (
            "CREATE TABLE IF NOT EXISTS memories ("
            "id uuid PRIMARY KEY, "
            "agent_id text, "
            "timestamp double, "
            "event_type text, "
            "tags set<text>, "
            "text text, "
            "metadata map<text, text>, "
            "data blob"
            ")"
        )
        try:
            self.session.execute(cql)
        except Exception as e:
            log.error(f"Error creating table: {e}")

    # Save event
    def save_event(self, agent_id: str, event: Dict[str, Any]):
        if self.disabled:
            return

        try:
            insert_cql = (
                "INSERT INTO memories (id, agent_id, timestamp, event_type, tags, text, metadata, data) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
            )

            eid = uuid.uuid4()
            tags = set(event.get("tags", []))
            metadata = {k: str(v) for k, v in (event.get("metadata") or {}).items()}
            blob = event.get("data", None)

            self.session.execute(insert_cql, (
                eid,
                agent_id,
                float(event.get("timestamp", time.time())),
                event.get("type", ""),
                tags,
                event.get("text", ""),
                metadata,
                blob
            ))

        except Exception as e:
            log.error(f"Scylla save_event error: {e}")

    # Query last N events
    def query_recent(self, agent_id: str, limit: int = 10):
        if self.disabled:
            return []

        try:
            stmt = SimpleStatement(
                f"SELECT id, timestamp, event_type, text FROM memories "
                "WHERE agent_id=%s LIMIT %s"
            )
            rows = self.session.execute(stmt, (agent_id, limit))
            return [dict(r._asdict()) for r in rows]

        except Exception as e:
            log.error(f"Scylla query error: {e}")
            return []
