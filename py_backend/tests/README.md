# DivineWorld Python test suite

Real `pytest` tests, converted from (and extending) the ad-hoc verification
scripts written while auditing this codebase in July 2026. Every test here
either directly guards a bug that was found and fixed, or checks an
invariant (like "every symbolic name obs_builder.py expects actually
exists") that's the kind of thing most likely to silently break again.

## Running

```bash
pip install -r requirements-test.txt -r requirements.txt --break-system-packages
cd py_backend
pytest                    # everything (~35s)
pytest -m "not slow"      # skip the heaviest tests for fast iteration
pytest tests/test_emotion.py -v   # just one file, while actively editing it
```

## Why `conftest.py` stubs the `ai_core` package

`ai_core/__init__.py` eagerly imports the entire agent stack - a real
`import ai_core.anything` takes ~65 seconds and pulls in things like audio
hardware checks that have nothing to do with most individual tests.
`conftest.py` stubs `ai_core` in `sys.modules` so `import ai_core.world_model`
(for example) finds the real file on disk directly, without re-running
`__init__.py`. This is the same technique this project's own debugging
sessions have used throughout (see the project's continuation notes on
"handle circular imports by stubbing sys.modules"), just made permanent
instead of copy-pasted into every throwaway script.

If you're writing a genuine end-to-end integration test that specifically
needs the real, full app wiring, that's a legitimate reason to import
`ai_core` normally instead in that one test file - it'll just be slower.

## What's here

| File | Covers |
|---|---|
| `test_world_model.py` | action_dim consistency (the single most-repeated bug this session - 4 separate stale hardcodes), the god-agent 18-dim `last_action` truncation, the `next_state` guard fix, `weights_only` save/load |
| `test_actuators_wire_format.py` | The TCP wire format's byte-level protocol with `TCPServer.java` (mirrors Java's exact read sequence) |
| `test_memory.py` | The `query_by_tags`/`query_by_type` dead-join fix, with a fake Scylla session (real ScyllaDB isn't available in most dev/CI environments) |
| `test_emotion.py` | `EmotionSystem` on its own terms - clipping, decay, snapshot immutability, dominant/valence/intensity |
| `test_personality.py` | `Personality` on its own terms - construction, serialization round-trip and non-mutation, `apply_update`, `similarity`'s zero-vector edge case |
| `test_symbolic_registries.py` | The general "symbolic name never actually registered" bug class (found twice: `frustration`/`curiosity` emotions, the `persistence` trait) |
| `test_god_ability_parity.py` | Cross-language: parses `ServerGodAbilityExecutor.java`'s real `case` statements and checks every ability is reachable from both Python registries |
| `test_config_consistency.py` | The two `config.py` files' `agent_spawner` exclude-list entries |
| `test_browser_routes.py` | `/browser/scroll` and `/browser/screenshot`'s real method signatures |
| `test_chat_heard_routing.py` | `main.py`'s chat_heard route, including a real HTTP round trip against agent.py's actual FastAPI app on a real port |

## Adding a new test

1. Put it in a new or existing `test_*.py` file under `tests/`.
2. Need a real component (memory, brain, emotion, personality, a world model)?
   Check `conftest.py` first - there's probably already a fixture for it.
3. Prefer testing the *invariant* over today's specific value, where the two
   differ. `test_action_encoder_matches_config_action_dim` checks against
   `world_model_config.action_dim` dynamically, not a hardcoded `13` - if
   that number is ever deliberately changed, the test keeps working instead
   of needing an edit just because a number moved. (`test_fresh_config_
   default_action_dim` is the one deliberate exception: it pins that
   default *on purpose*, so a change to it is a visible, reviewed diff
   rather than a silent one.)
4. If a test mutates something process-wide (see
   `test_world_model.py`'s note on `torch.serialization.add_safe_globals`),
   make sure it doesn't depend on running before/after any particular
   other test - pytest doesn't guarantee file order.
5. Real execution beats reading the source and asserting it "looks right" -
   every fixture in `conftest.py` exists so that's the easy path, not the
   hard one.

## Known gaps

- **Java has no real test runner wired up yet** - the actual verification
  technique used this session was compiling the touched `.java` files for
  real against hand-built stub classes matching the real Forge 1.20.1 API
  (`Minecraft`, `LocalPlayer`, etc.), rather than syntax-only review. That
  stub approach is a reasonable starting point for a permanent Java check,
  but wiring it into ForgeGradle's test source set (or just running it as
  a plain script in CI) hasn't been done yet.
- **The Electron frontend has no tests** - lowest bug density found this
  session, and JS/React testing has a different toolchain (Vitest +
  Testing Library, most likely) than anything above. Worth adding if the
  frontend grows, not urgent today.
- **This isn't exhaustive.** It covers what this session's audit actually
  found broken, plus the two modules (`emotion.py`, `personality.py`)
  tested more broadly on request. Plenty of other files in `ai_core/`
  don't have dedicated test files yet.