"""
Regression test for main.py's global JSONDecodeError exception handler.

Historical bug (reported directly, with a real traceback): POST
/api/genesis/spawn with an empty body crashed with an unhandled 500 -
`json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
- because genesis_spawn() does `data = await request.json()` with no
error handling. The same exact pattern exists at 14 separate route
handlers in main.py; rather than patching each individually, one global
FastAPI exception handler now catches this uniformly.
"""
import pytest


@pytest.fixture(scope="module")
def client():
    import importlib
    main_mod = importlib.import_module("main")
    from fastapi.testclient import TestClient
    return TestClient(main_mod.app)


def test_genesis_spawn_with_no_body_returns_400_not_500(client):
    """The exact reported crash, reproduced against the real app."""
    resp = client.post("/api/genesis/spawn")
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_genesis_spawn_with_a_real_body_still_works_normally(client):
    """Confirms the fix doesn't accidentally break the happy path."""
    resp = client.post("/api/genesis/spawn", json={
        "spawner": "Test", "world": "TestWorld", "spawn_positions": [],
    })
    assert resp.status_code == 200


@pytest.mark.parametrize("path", [
    "/api/agents/chat_heard",
    "/api/gods/ability",
    "/api/gods/transform",
])
def test_other_routes_with_the_same_pattern_are_also_protected(client, path):
    """Same historical bug class, different route - the global handler
    should catch this uniformly rather than needing 14 separate fixes."""
    resp = client.post(path)
    assert resp.status_code == 400
    assert "error" in resp.json()


def test_malformed_json_also_returns_400(client):
    """Not just an empty body - genuinely invalid JSON syntax too."""
    resp = client.post(
        "/api/genesis/spawn",
        content=b"{not valid json!!",
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 400