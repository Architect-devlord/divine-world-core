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
pytest                    # everything (~30-90s depending on what's cached)
pytest -m "not slow"      # skip the heaviest tests for fast iteration
pytest tests/test_emotion.py -v   # just one file, while actively editing it
```

## Two critical bugs this suite exists because of

Building the "heavy" tests for the transformer/policy/vocabulary systems
directly found two significant, previously-unknown bugs - not just
regressions in already-known fixes:

1. **`TransformerPolicy`/`GodTransformerPolicy` could never be constructed
   at all.** SB3's real `ActorCriticPolicy._build()` unconditionally reads
   `self.mlp_extractor.latent_dim_pi` immediately after calling the
   overridden `_build_mlp_extractor()` - which sets `self.features_extractor`
   instead, a different, custom attribute. Every single instantiation
   crashed with `AttributeError`, reproduced against both the currently
   installed stable-baselines3 version and the exact minimum pinned in
   requirements.txt (`==2.8.0` specifically, not just `>=2.8.0` generally) -
   this was never a version-compatibility regression, construction had
   never worked. Fixed by overriding `_build()` itself to skip SB3's
   generic path (which would otherwise have gone on to silently overwrite
   the custom action_net/value_net/log_std with its own generic
   construction - a worse failure mode than a crash). See
   `test_policy.py::TestTransformerPolicyConstruction`.

2. **A live, reported crash**: `POST /api/genesis/spawn` with no body
   raised an unhandled 500 (`json.decoder.JSONDecodeError`). The same
   unguarded `await request.json()` pattern exists at 14 separate route
   handlers in `main.py`. Fixed with one global FastAPI exception handler
   rather than patching each site individually. See
   `test_json_error_handling.py`.

## What's here

| File | Covers |
|---|---|
| `test_world_model.py` | action_dim consistency (the single most-repeated bug this session - 4 separate stale hardcodes), the god-agent 18-dim `last_action` truncation, the `next_state` guard fix, `weights_only` save/load |
| `test_policy.py` | `TransformerPolicy`/`GodTransformerPolicy` - the construction-blocking bug above, forward-pass shape/bounds contracts, gradient flow (including which params legitimately don't get gradient and why), `GodAbilityHead`'s deterministic-vs-stochastic decode logic |
| `test_world_model_transformer.py` | The real transformer backbone (`VisionEncoder`/`AudioEncoder`/`ProprioceptionEncoder`/`ActionEncoder`, `TransformerBlock`, `WorldModelTransformer`) - **empirically proves the causal-masking claim** (perturbing only the final timestep must leave every earlier timestep's prediction unchanged), not just that a mask tensor gets constructed |
| `test_online_visual_vocabulary.py` | `OnlineVisualVocabulary` - the actual "no hand-given labels" claim: real discovery/growth dynamics, the precise online k-means update rule, thread safety, persistence |
| `test_feature_extractor.py` | The CNN that feeds the vocabulary - shape contracts, the "trainable, not a frozen ImageNet prior" claim, determinism, persistence |
| `test_actuators_wire_format.py` | The TCP wire format's byte-level protocol with `TCPServer.java` (mirrors Java's exact read sequence) |
| `test_memory.py` | The `query_by_tags`/`query_by_type` dead-join fix, with a fake Scylla session (real ScyllaDB isn't available in most dev/CI environments) |
| `test_emotion.py` | `EmotionSystem` on its own terms - clipping, decay, snapshot immutability, dominant/valence/intensity |
| `test_personality.py` | `Personality` on its own terms - construction, serialization round-trip and non-mutation, `apply_update`, `similarity`'s zero-vector edge case |
| `test_symbolic_registries.py` | The general "symbolic name never actually registered" bug class (found twice: `frustration`/`curiosity` emotions, the `persistence` trait) |
| `test_god_ability_parity.py` | Cross-language: parses `ServerGodAbilityExecutor.java`'s real `case` statements and checks every ability is reachable from both Python registries |
| `test_config_consistency.py` | The two `config.py` files' `agent_spawner` exclude-list entries |
| `test_browser_routes.py` | `/browser/scroll` and `/browser/screenshot`'s real method signatures |
| `test_chat_heard_routing.py` | `main.py`'s chat_heard route, including a real HTTP round trip against agent.py's actual FastAPI app on a real port |
| `test_json_error_handling.py` | The genesis_spawn crash above, plus the other 13 routes sharing the same pattern |

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