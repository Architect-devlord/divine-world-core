"""
Shared pytest configuration for the DivineWorld Python test suite.

WHY THE STUB: ai_core/__init__.py eagerly imports the entire agent stack
(agent.py, memory.py, vision.py, audio, ...) - a real import takes ~65s and
pulls in dependencies (audio hardware checks, etc.) that have nothing to do
with most individual tests. We stub the `ai_core` package in sys.modules so
`import ai_core.whatever` finds the real file on disk via __path__, without
re-running the real __init__.py. Confirmed this drops ~65s to ~1.5s.
This is a deliberate isolation choice, not a workaround for a bug - the same
technique this project has used throughout its own debugging sessions
(see the project's continuation notes: "handle circular imports by stubbing
sys.modules and loading modules in dependency order").

If a test genuinely needs the full, real app wiring (e.g. an actual
end-to-end integration test), import ai_core normally in that specific test
file instead of relying on this stub - it'll just be slower.
"""
import sys
import types
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../py_backend
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT.parent))  # repo root, for `py_backend.X` imports some files use

if "ai_core" not in sys.modules:
    _ai_core_stub = types.ModuleType("ai_core")
    _ai_core_stub.__path__ = [str(REPO_ROOT / "ai_core")]
    sys.modules["ai_core"] = _ai_core_stub

if "py_backend" not in sys.modules:
    _py_backend_stub = types.ModuleType("py_backend")
    _py_backend_stub.__path__ = [str(REPO_ROOT)]
    sys.modules["py_backend"] = _py_backend_stub


# ---------------------------------------------------------------------------
# Fixtures - real components, not mocks, wherever construction is cheap.
# Mocks are still appropriate for external services (HTTP peers, sockets);
# see individual test files for those.
# ---------------------------------------------------------------------------

@pytest.fixture
def world_model_config():
    import importlib
    world_model = importlib.import_module("ai_core.world_model")
    return world_model.WorldModelConfig(device="cpu")


@pytest.fixture
def world_model(world_model_config):
    import importlib
    world_model_mod = importlib.import_module("ai_core.world_model")
    return world_model_mod.WorldModel(world_model_config)


@pytest.fixture
def real_memory():
    import importlib
    memory_mod = importlib.import_module("ai_core.memory")
    return memory_mod.UnifiedMemoryStore(agent_id="test_agent")


@pytest.fixture
def real_brain():
    import importlib
    brain_core_mod = importlib.import_module("ai_core.brain_core")
    return brain_core_mod.BrainCore(agent_ref=None)


@pytest.fixture
def real_emotion():
    import importlib
    emotion_mod = importlib.import_module("ai_core.emotion")
    return emotion_mod.EmotionSystem()


@pytest.fixture
def real_personality():
    import importlib
    personality_mod = importlib.import_module("ai_core.personality")
    return personality_mod.Personality()


class FakeRequest:
    """Stands in for a FastAPI Request when unit-testing a route function
    directly (no real HTTP server needed) - just needs an async .json()."""
    def __init__(self, payload):
        self._payload = payload

    async def json(self):
        return self._payload


@pytest.fixture
def fake_request():
    return FakeRequest


class RecordingMemory:
    """Lightweight memory double that records calls instead of persisting -
    use when a test cares about *what* got recorded, not real persistence
    (real_memory fixture above covers the latter)."""
    def __init__(self):
        self.calls = []

    def remember(self, event, tags=None):
        self.calls.append((event, tags))


class RecordingBrain:
    def __init__(self):
        self.calls = []

    def evaluate_event(self, event):
        self.calls.append(event)
        return (0.0, {})


@pytest.fixture
def recording_memory():
    return RecordingMemory()


@pytest.fixture
def recording_brain():
    return RecordingBrain()