"""
Regression test for main.py's /api/agents/chat_heard route.

Historical bug: this route called agent_manager.get_chat_queue(), a
method that was never defined anywhere - it 500'd on every single call.
The fix makes it look up the hearer's backend_port and forward the event
to that agent's own /api/perception/chat_heard over real HTTP.

This test runs agent.py's actual FastAPI app on a real port (not just a
function call) so the test exercises the real network hop, not just the
Python-level wiring.
"""
import asyncio
import time
import threading

import pytest


TEST_PORT = 18999  # arbitrary, unlikely to collide with anything real


@pytest.fixture(scope="module")
def agent_mod():
    import importlib
    return importlib.import_module("ai_core.agent")


@pytest.fixture(scope="module")
def main_mod():
    import importlib
    return importlib.import_module("main")


class RecordingMemory:
    def __init__(self):
        self.calls = []

    def remember(self, event, tags=None):
        self.calls.append((event, tags))


class RecordingBrain:
    def __init__(self):
        self.calls = []

    def evaluate_event(self, event):
        self.calls.append(event)


@pytest.fixture(scope="module")
def live_agent_server(agent_mod):
    """Boots agent.py's real FastAPI app on TEST_PORT, with a recording
    mock agent wired in, for the whole module's test session."""
    import uvicorn

    class MockAgent:
        agent_id = "test_agent"
        memory = RecordingMemory()
        brain = RecordingBrain()

    mock_agent = MockAgent()
    agent_mod.global_agent = mock_agent

    config = uvicorn.Config(agent_mod.app, host="127.0.0.1", port=TEST_PORT, log_level="warning")
    server = uvicorn.Server(config)

    def run_server():
        asyncio.run(server.serve())

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    time.sleep(2)  # let it bind

    yield mock_agent

    server.should_exit = True
    time.sleep(0.5)
    agent_mod.global_agent = None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_chat_heard_forwards_over_real_http_to_the_right_agent(
    main_mod, live_agent_server, fake_request
):
    main_mod.agent_manager.agent_info["test_agent"] = {
        "agent_id": "test_agent", "backend_port": TEST_PORT, "status": "running",
    }

    result = await main_mod.agent_chat_heard(fake_request({
        "hearer_id": "test_agent", "speaker_name": "Steve", "message": "hello over there",
    }))

    assert result["status"] == "ok"

    # give the delivery a beat, then check the mock agent actually got it
    await asyncio.sleep(0.2)
    assert len(live_agent_server.memory.calls) == 1
    event, tags = live_agent_server.memory.calls[0]
    assert event["type"] == "chat_heard"
    assert event["speaker"] == "Steve"
    assert event["message"] == "hello over there"
    assert set(tags) == {"chat", "proximity", "heard", "social"}

    assert len(live_agent_server.brain.calls) == 1
    brain_event = live_agent_server.brain.calls[0]
    assert brain_event["type"] == "chat_heard"
    assert brain_event["payload"]["speaker"] == "Steve"
    assert brain_event["payload"]["message"] == "hello over there"


@pytest.mark.asyncio
async def test_chat_heard_unknown_agent_is_ignored_gracefully(main_mod, fake_request):
    result = await main_mod.agent_chat_heard(fake_request({
        "hearer_id": "no_such_agent", "speaker_name": "Steve", "message": "hi",
    }))
    assert result == {"status": "ignored", "reason": "agent not running"}


@pytest.mark.asyncio
async def test_chat_heard_unreachable_port_is_ignored_not_raised(main_mod, fake_request):
    """Known agent, but nothing is actually listening on its port (e.g. it
    crashed) - must degrade gracefully, not raise and take down the
    caller."""
    main_mod.agent_manager.agent_info["dead_agent"] = {
        "backend_port": 1, "status": "running",  # port 1: nothing listens there
    }
    result = await main_mod.agent_chat_heard(fake_request({
        "hearer_id": "dead_agent", "speaker_name": "Steve", "message": "hi",
    }))
    assert result["status"] == "ignored"
    assert result["reason"] == "agent unreachable"


@pytest.mark.asyncio
async def test_chat_heard_missing_required_fields_returns_400(main_mod, fake_request):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await main_mod.agent_chat_heard(fake_request({"hearer_id": "", "message": ""}))
    assert exc_info.value.status_code == 400