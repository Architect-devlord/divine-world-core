"""
Regression tests for ai_core/memory.py's ScyllaMemoryBackend.

query_by_tags/query_by_type had a "dead join" bug: they fetched matching
event_ids from the tag/type index tables, then called query_recent() -
which ignored those ids entirely and just returned whatever was most
recent, regardless of tag or type. These tests build a fake Scylla
session (real ScyllaDB isn't available in this environment) so the
actual filtering logic runs for real, rather than re-confirming the fix
by reading the source.
"""
import json
import pytest


class FakeRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeSession:
    """Mocks just enough of a Cassandra/Scylla session.execute() to
    exercise query_by_tags/query_by_type/query_recent's real logic."""

    def __init__(self, tag_index_rows=None, type_index_rows=None, memory_rows=None):
        self.tag_index_rows = tag_index_rows or []
        self.type_index_rows = type_index_rows or []
        self.memory_rows = memory_rows or []
        self._memories_table_calls = 0

    def execute(self, query, params):
        if "memories_by_tag" in query:
            tag = params[1]
            return [r for r in self.tag_index_rows if r.tag == tag]
        if "memories_by_type" in query:
            event_type = params[1]
            return [r for r in self.type_index_rows if r.event_type == event_type]
        if "FROM memories " in query:
            # query_recent's own table - only "populate" on the first
            # (most-recent) bucket call, matching how a real event would
            # only live in the one bucket it was actually written to.
            self._memories_table_calls += 1
            if self._memories_table_calls > 1:
                return []
            rows = self.memory_rows
            if "timestamp>?" in query:
                since = params[2]
                rows = [r for r in rows if r.timestamp > since]
            return rows
        return []


def _memory_row(event_id, timestamp, event_type, tags, text):
    return FakeRow(
        event_id=event_id, timestamp=timestamp, event_type=event_type,
        tags=tags, text=text, payload=json.dumps({}),
    )


@pytest.fixture
def backend():
    import importlib
    memory_mod = importlib.import_module("ai_core.memory")
    # Bypass __init__ entirely - it tries a real Scylla connection, which
    # isn't available here and isn't what these tests are about.
    b = object.__new__(memory_mod.ScyllaMemoryBackend)
    b.disabled = False
    return b


def test_query_by_tags_actually_filters_not_just_returns_everything(backend):
    """The exact historical bug: without the fix, this would return ALL
    three events (whatever query_recent's default ordering produced),
    not just the one actually tagged 'social'."""
    combat_event = _memory_row("id-1", 100.0, "combat", ["combat", "danger"], "a fight")
    social_event = _memory_row("id-2", 200.0, "chat_heard", ["social", "chat"], "a greeting")
    craft_event  = _memory_row("id-3", 300.0, "crafting", ["crafting"], "made a pickaxe")

    backend.session = FakeSession(
        tag_index_rows=[FakeRow(tag="social", timestamp=200.0, event_id="id-2")],
        memory_rows=[combat_event, social_event, craft_event],
    )

    results = backend.query_by_tags("test_agent", ["social"], limit=10)

    assert len(results) == 1
    assert results[0]["event_id"] == "id-2"
    assert results[0]["text"] == "a greeting"


def test_query_by_tags_no_match_returns_empty(backend):
    backend.session = FakeSession(tag_index_rows=[], memory_rows=[
        _memory_row("id-1", 100.0, "combat", ["combat"], "a fight"),
    ])
    assert backend.query_by_tags("test_agent", ["nonexistent_tag"]) == []


def test_query_by_tags_respects_limit_after_dedup(backend):
    rows = [_memory_row(f"id-{i}", float(i), "chat_heard", ["social"], f"msg {i}")
            for i in range(5)]
    backend.session = FakeSession(
        tag_index_rows=[FakeRow(tag="social", timestamp=float(i), event_id=f"id-{i}")
                        for i in range(5)],
        memory_rows=rows,
    )
    results = backend.query_by_tags("test_agent", ["social"], limit=2)
    assert len(results) == 2
    # Most recent (highest timestamp) first
    assert results[0]["event_id"] == "id-4"
    assert results[1]["event_id"] == "id-3"


def test_query_by_type_actually_filters_not_just_returns_everything(backend):
    """Same historical bug, the event_type variant."""
    combat_event = _memory_row("id-1", 100.0, "combat", ["combat"], "a fight")
    craft_event  = _memory_row("id-2", 200.0, "crafting", ["crafting"], "made a pickaxe")

    backend.session = FakeSession(
        type_index_rows=[FakeRow(event_type="crafting", timestamp=200.0)],
        memory_rows=[combat_event, craft_event],
    )

    results = backend.query_by_type("test_agent", "crafting", limit=10)

    assert len(results) == 1
    assert results[0]["type"] == "crafting"
    assert results[0]["text"] == "made a pickaxe"


def test_query_by_type_no_match_returns_empty(backend):
    backend.session = FakeSession(type_index_rows=[], memory_rows=[
        _memory_row("id-1", 100.0, "combat", ["combat"], "a fight"),
    ])
    assert backend.query_by_type("test_agent", "nonexistent_type") == []


def test_disabled_backend_returns_empty_without_touching_session(backend):
    """When there's no real Scylla connection, every query method should
    short-circuit cleanly rather than trying (and failing) to use a
    session that doesn't exist."""
    backend.disabled = True
    backend.session = None  # would crash if any query method tried to touch it
    assert backend.query_by_tags("test_agent", ["social"]) == []
    assert backend.query_by_type("test_agent", "combat") == []
    assert backend.query_recent("test_agent") == []