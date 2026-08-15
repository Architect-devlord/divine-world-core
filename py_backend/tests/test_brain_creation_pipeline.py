"""
End-to-end tests for the brain creation pipeline:

    NPCAgent.__init__()
        -> Personality / EmotionSystem / UnifiedMemoryStore
        -> BrainCore(agent_ref=self)
        -> CognitivePlanner(brain=self.brain)
        -> _init_language()          -> brain_language.add_language_to_brain(brain)
        -> initialize_reward_system() -> RewardSystem
        -> _init_world_model()        -> WorldModel / EnsembleWorldModel
        -> _init_vision() / _init_audio_processor()  (best-effort, never fatal)
        -> _init_cognitive_loop()     (only if autonomous=True)
        -> policy auto-init           -> TransformerPolicy / GodTransformerPolicy
    agent.save(path)  -> brain_capsule.BrainCapsule.save()  -> <path>.pcap + .pcap.json
    agent.load(path)  -> brain_capsule.BrainCapsule.load()  -> restores everything above

This mirrors the real production call sequence in
ai_core/agent_spawner.py::AgentSpawner.spawn_npc/spawn_god, which
constructs NPCAgent(...) and immediately calls self._save_brain(agent) --
itself a bare `agent.save(path)` wrapped in a try/except that only logs on
failure (see TestAgentSpawnerSaveWrapperContract below). That means a
regression in construction, save, or load has no other safety net in
production - it degrades silently to an ERROR log line and an agent that
either never persists or never restores state. These tests exercise the
real classes directly (no mocks for BrainCore/BrainCapsule/NPCAgent
itself) specifically so a break here is loud, not a log line nobody reads.

Construction of a full NPCAgent is comparatively heavy (reward system,
world model, vision/audio best-effort init, policy) - marked `slow` per
this suite's existing convention (see tests/README.md / pytest.ini).
Everything not needing a full agent (BrainCore alone, add_language_to_brain
alone, BrainCapsule alone) is fast and unmarked.

Uses use_scylla=False throughout: ScyllaMemoryBackend already falls back to
an in-memory-only mode when it can't connect (see UnifiedMemoryStore),
but forcing it off keeps these tests from depending on - or silently
skipping real checks against - a ScyllaDB instance nobody guarantees is
running.
"""
import importlib
import json

import pytest


# ---------------------------------------------------------------------------
# Module fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def brain_core_mod():
    return importlib.import_module("ai_core.brain_core")


@pytest.fixture
def brain_language_mod():
    return importlib.import_module("ai_core.brain_language")


@pytest.fixture
def brain_capsule_mod():
    return importlib.import_module("ai_core.brain_capsule")


@pytest.fixture
def agent_mod():
    return importlib.import_module("ai_core.agent")


def _make_agent(agent_mod, agent_id="test_agent", god_type=None, autonomous=False,
                 persona_traits=None):
    """Constructs a real NPCAgent the same way agent_spawner.py does
    (agent_id / gender / persona_traits / client_process=None), except
    use_scylla=False (see module docstring) and autonomous=False by
    default so tests don't spin up a CognitiveLoop unless specifically
    testing that path."""
    return agent_mod.NPCAgent(
        agent_id=agent_id,
        gender="male",
        persona_traits=persona_traits,
        client_process=None,
        autonomous=autonomous,
        use_scylla=False,
        god_type=god_type,
    )


# ===========================================================================
# 1. BrainCore in isolation - no NPCAgent required
# ===========================================================================

class TestBrainCoreConstruction:

    def test_constructs_standalone_with_no_agent_ref(self, brain_core_mod):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        assert brain.agent is None

    def test_language_starts_unset(self, brain_core_mod):
        """Regression guard for the fix documented directly in brain_core.py:
        BrainCore.__init__ used to ALSO eagerly construct a LanguageIntelligence,
        contradicting its own comment that add_language_to_brain() is the sole
        construction path - NPCAgent._init_language() unconditionally
        overwrote it moments later, so every agent spawn silently built and
        discarded one full transformer+tokenizer+optimizer. brain.language
        must be None until add_language_to_brain() runs, not before."""
        brain = brain_core_mod.BrainCore(agent_ref=None)
        assert brain.language is None

    def test_reward_system_and_world_model_start_unset(self, brain_core_mod):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        assert brain.reward_system is None
        assert brain.world_model is None

    def test_world_model_property_is_thread_guarded_and_settable(self, brain_core_mod):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        sentinel = object()
        brain.set_world_model(sentinel)
        assert brain.world_model is sentinel

    def test_set_reward_system_attaches_directly(self, brain_core_mod):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        sentinel = object()
        brain.set_reward_system(sentinel)
        assert brain.reward_system is sentinel

    def test_value_table_and_forward_model_start_empty(self, brain_core_mod):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        assert brain.value_table == {}
        assert brain.forward_model == {}


# ===========================================================================
# 2. Language attachment in isolation - add_language_to_brain() alone
# ===========================================================================

class TestLanguageAttachment:

    def test_attaches_a_real_language_intelligence_instance(
        self, brain_core_mod, brain_language_mod,
    ):
        brain = brain_core_mod.BrainCore(agent_ref=None)
        brain_language_mod.add_language_to_brain(brain)
        assert brain.language is not None
        assert isinstance(brain.language, brain_language_mod.LanguageIntelligence)

    def test_binds_convenience_methods_onto_the_brain(
        self, brain_core_mod, brain_language_mod,
    ):
        """add_language_to_brain also copies process_input/should_speak/
        generate_speech/learn_from_file/get_language_progress onto the brain
        itself as bound methods - anything calling brain.should_speak(...)
        directly (rather than brain.language.should_speak(...)) depends on
        this, so a rename on either side would otherwise fail silently
        (AttributeError only at first actual use, not at construction)."""
        brain = brain_core_mod.BrainCore(agent_ref=None)
        brain_language_mod.add_language_to_brain(brain)
        for attr in (
            "process_language_input", "should_speak", "generate_speech",
            "learn_from_file", "get_language_progress",
        ):
            assert hasattr(brain, attr), f"brain.{attr} was not attached"
            assert callable(getattr(brain, attr))

    def test_language_intelligence_receives_the_brains_agent_ref(
        self, brain_core_mod, brain_language_mod,
    ):
        sentinel_agent = object()
        brain = brain_core_mod.BrainCore(agent_ref=sentinel_agent)
        brain_language_mod.add_language_to_brain(brain)
        assert brain.language.agent_ref is sentinel_agent

    def test_state_dict_and_load_state_dict_round_trip(
        self, brain_core_mod, brain_language_mod,
    ):
        """LanguageIntelligence.state_dict()/load_state_dict() are exactly
        what BrainCapsule relies on (see TestFullSaveLoadRoundTrip below) -
        tested here on its own terms first, independent of the full agent."""
        brain = brain_core_mod.BrainCore(agent_ref=None)
        brain_language_mod.add_language_to_brain(brain)
        brain.language.vocab.observe("hello")
        brain.language.vocab.observe("hello")
        brain.language.vocab.observe("world")

        state = brain.language.state_dict()
        assert isinstance(state, dict)
        assert "language_stage" in state

        fresh_brain = brain_core_mod.BrainCore(agent_ref=None)
        brain_language_mod.add_language_to_brain(fresh_brain)
        fresh_brain.language.load_state_dict(state)
        assert fresh_brain.language.language_stage == brain.language.language_stage
        assert fresh_brain.language.experience_count == brain.language.experience_count


# ===========================================================================
# 3. Full NPCAgent construction - the real, heavy pipeline
# ===========================================================================

@pytest.mark.slow
class TestFullAgentBrainConstruction:

    def test_brain_is_wired_to_the_agent_that_owns_it(self, agent_mod):
        agent = _make_agent(agent_mod)
        assert agent.brain is not None
        assert agent.brain.agent is agent

    def test_planner_is_wired_to_the_same_brain(self, agent_mod):
        agent = _make_agent(agent_mod)
        assert agent.planner is not None
        assert agent.planner.brain is agent.brain

    def test_language_is_attached_by_construction_time(self, agent_mod, brain_language_mod):
        agent = _make_agent(agent_mod)
        assert agent.brain.language is not None
        assert isinstance(agent.brain.language, brain_language_mod.LanguageIntelligence)

    def test_obs_dim_is_128_regardless_of_agent_type(self, agent_mod):
        """FIX Step 6: obs_dim/action_dim were never set on the agent at
        all, silently skipping PolicyBridge/SST/SkillTracker attachment
        everywhere agent_runner.py guarded on hasattr(agent, 'obs_dim')."""
        agent = _make_agent(agent_mod)
        assert agent.obs_dim == 128

    def test_action_dim_is_13_for_a_plain_npc(self, agent_mod):
        agent = _make_agent(agent_mod, god_type=None)
        assert agent.action_dim == 13

    def test_action_dim_is_18_for_a_god_agent(self, agent_mod):
        agent = _make_agent(agent_mod, agent_id="test_god", god_type="warden")
        assert agent.action_dim == 18

    def test_reward_system_is_constructed_eagerly_and_dims_match_the_agent(self, agent_mod):
        """FIX (Consolidate Duplicate Implementations, Step 4): a bare
        initialize_reward_system() call used to default to the stale
        obs_dim=50, so RND/ICM's first nn.Linear(50, ...) layer crashed the
        instant a real 128-dim observation reached it. Asserting the
        *actual* dims RewardSystem was built with here, not just that it's
        non-None, is what would have caught that regression."""
        agent = _make_agent(agent_mod)
        assert agent.reward_system is not None
        assert agent.reward_system.obs_dim == agent.obs_dim == 128
        assert agent.reward_system.action_dim == agent.action_dim == 13

    def test_episodic_memory_is_initialized_eagerly(self, agent_mod):
        """FIX #1: EpisodicMemory was never initialized; learn() used a
        hasattr guard that was always False, so the PPO replay buffer
        stayed empty for the entire live session."""
        agent = _make_agent(agent_mod)
        assert agent.episodic_memory is not None
        assert agent.episodic_memory.capacity == 50_000

    def test_policy_is_auto_initialized_not_left_none(self, agent_mod):
        """initialize_policy() used to only be reachable via a manual call
        that nothing ever made - self.policy stayed None forever and
        decide() silently fell back to an 11-dim random action vector."""
        agent = _make_agent(agent_mod)
        assert agent.policy is not None

    def test_world_model_is_constructed(self, agent_mod):
        agent = _make_agent(agent_mod)
        assert agent.world_model is not None

    def test_world_model_is_an_ensemble_when_config_enables_it(self, agent_mod):
        """FIX (report: 'EnsembleWorldModel is built but never
        instantiated'): WorldModelConfig.use_ensemble defaulted to True and
        EnsembleWorldModel existed with 5 real members, but nothing in the
        entire codebase ever called EnsembleWorldModel(...) - every agent
        got a plain WorldModel with no epistemic-uncertainty signal at all,
        which GRPO-style rollout scoring depends on to avoid reward-hacking
        confidently-wrong WorldModel predictions."""
        agent = _make_agent(agent_mod)
        world_model_mod = importlib.import_module("ai_core.world_model")
        if agent.world_model.config.use_ensemble:
            assert isinstance(agent.world_model, world_model_mod.EnsembleWorldModel)

    def test_cognitive_loop_is_none_when_not_autonomous(self, agent_mod):
        agent = _make_agent(agent_mod, autonomous=False)
        assert agent.cognitive_loop is None

    def test_cognitive_loop_is_constructed_when_autonomous(self, agent_mod):
        agent = _make_agent(agent_mod, autonomous=True)
        assert agent.cognitive_loop is not None

    def test_cognitive_loop_construction_does_not_start_a_background_thread(self, agent_mod):
        """CognitiveLoop.__init__ only builds the object - start() is a
        separate async call nothing in NPCAgent.__init__ triggers. Asserted
        explicitly so a future change that makes construction eager
        (e.g. auto-starting the loop) gets caught here rather than as a
        mysterious extra thread/task showing up in an unrelated test run."""
        import threading
        before = {t.ident for t in threading.enumerate()}
        agent = _make_agent(agent_mod, autonomous=True)
        after = {t.ident for t in threading.enumerate()}
        assert after == before, "constructing NPCAgent spawned a new thread"

    def test_vision_and_audio_init_never_raise_out_of_construction(self, agent_mod):
        """_init_vision()/_init_audio_processor() are both wrapped in
        broad try/except in agent.py specifically so missing camera/audio
        hardware in a test or headless-server environment degrades to a
        logged warning, not a crashed agent. This just confirms
        construction completes at all under that path."""
        agent = _make_agent(agent_mod)  # would raise here if either init leaked an exception
        assert agent is not None

    def test_custom_persona_traits_reach_the_personality(self, agent_mod):
        agent = _make_agent(
            agent_mod, persona_traits={"openness": 0.7, "boldness": -0.3},
        )
        assert agent.personality.traits["openness"] == pytest.approx(0.7)
        assert agent.personality.traits["boldness"] == pytest.approx(-0.3)


# ===========================================================================
# 4. Full save -> load round trip (BrainCapsule via NPCAgent.save/load)
# ===========================================================================

@pytest.mark.slow
class TestFullSaveLoadRoundTrip:

    def test_save_produces_pcap_and_json_sidecar(self, agent_mod, tmp_path):
        agent = _make_agent(agent_mod)
        path = str(tmp_path / "brain")
        agent.save(path)
        assert (tmp_path / "brain.pcap").exists()
        assert (tmp_path / "brain.pcap.json").exists()

    def test_json_sidecar_is_valid_json_with_no_raw_tensors(self, agent_mod, tmp_path):
        """brain_capsule.py's own docstring promises the sidecar is
        'human-readable ... no tensors or large blobs'; if a future change
        stuffs a tensor object straight into the summary dict, json.dump
        itself would fail first - this asserts the promise holds, not just
        that *a* file got written."""
        agent = _make_agent(agent_mod)
        path = str(tmp_path / "brain")
        agent.save(path)
        with open(tmp_path / "brain.pcap.json") as f:
            data = json.load(f)
        assert "metadata" in data
        assert "saved_components" in data

    def test_personality_round_trips(self, agent_mod, tmp_path):
        agent = _make_agent(
            agent_mod, persona_traits={"openness": 0.6, "neuroticism": -0.2},
        )
        path = str(tmp_path / "brain")
        agent.save(path)

        fresh = _make_agent(agent_mod, agent_id="test_agent_reloaded")
        fresh.load(path)
        assert fresh.personality.traits["openness"] == pytest.approx(0.6)
        assert fresh.personality.traits["neuroticism"] == pytest.approx(-0.2)

    def test_emotion_snapshot_round_trips(self, agent_mod, tmp_path):
        agent = _make_agent(agent_mod)
        agent.emotion.emotions["joy"] = 0.42
        path = str(tmp_path / "brain")
        agent.save(path)

        fresh = _make_agent(agent_mod, agent_id="test_agent_reloaded")
        fresh.load(path)
        assert fresh.emotion.emotions.get("joy") == pytest.approx(0.42)

    def test_memory_events_round_trip(self, agent_mod, tmp_path):
        agent = _make_agent(agent_mod)
        agent.memory.remember({"type": "test_event", "text": "hello world"}, tags=["greeting"])
        path = str(tmp_path / "brain")
        agent.save(path)

        fresh = _make_agent(agent_mod, agent_id="test_agent_reloaded")
        fresh.load(path)
        recalled = fresh.memory.recall(10)
        assert any(e.get("text") == "hello world" for e in recalled)

    def test_language_state_round_trips(self, agent_mod, tmp_path):
        agent = _make_agent(agent_mod)
        agent.brain.language.vocab.observe("greetings")
        path = str(tmp_path / "brain")
        agent.save(path)

        fresh = _make_agent(agent_mod, agent_id="test_agent_reloaded")
        fresh.load(path)
        assert fresh.brain.language.experience_count == agent.brain.language.experience_count

    def test_god_type_persists_and_god_controls_reintegrate_on_load(self, agent_mod):
        """FIX: god_type was never persisted - a restarted god agent had
        god_type=None, so god_controls / the 18-dim ability space / the
        god-tier policy never re-initialised after load(), and every god
        ability was silently lost on restart. Uses two real agent_ids and
        real files on disk (not tmp_path's default temp dir - the fixture
        already gives an isolated per-test dir) since load() needs a
        second, fresh, god_type=None agent to prove the type was actually
        *restored* rather than just passed through from construction."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "brain")
            agent = _make_agent(agent_mod, agent_id="test_god", god_type="warden")
            agent.save(path)

            fresh = _make_agent(agent_mod, agent_id="test_god_reloaded", god_type=None)
            assert fresh.god_type is None  # sanity: genuinely unset before load
            fresh.load(path)
            assert fresh.god_type == "warden"

    def test_step_count_and_metadata_round_trip(self, agent_mod, tmp_path):
        agent = _make_agent(agent_mod)
        agent.step_count = 4321
        path = str(tmp_path / "brain")
        agent.save(path)

        fresh = _make_agent(agent_mod, agent_id="test_agent_reloaded")
        fresh.load(path)
        assert fresh.step_count == 4321


# ===========================================================================
# 5. BrainCapsule edge cases - failure modes worth being deliberate about
# ===========================================================================

class TestBrainCapsuleEdgeCases:

    def test_load_missing_path_raises_file_not_found(self, brain_capsule_mod, tmp_path):
        with pytest.raises(FileNotFoundError):
            brain_capsule_mod.BrainCapsule.load(str(tmp_path / "does_not_exist"))

    def test_save_creates_parent_directories(self, brain_capsule_mod, tmp_path):
        capsule = brain_capsule_mod.BrainCapsule(metadata={"agent_id": "x"})
        nested_path = tmp_path / "nested" / "dirs" / "brain"
        capsule.save(str(nested_path))
        assert (tmp_path / "nested" / "dirs" / "brain.pcap").exists()

    def test_save_load_round_trip_on_the_capsule_alone(self, brain_capsule_mod, tmp_path):
        capsule = brain_capsule_mod.BrainCapsule(
            metadata={"agent_id": "x", "step_count": 7},
            personality={"gender": "male", "traits": {"openness": 0.1}},
            gender="male",
        )
        path = str(tmp_path / "brain")
        capsule.save(path)

        loaded = brain_capsule_mod.BrainCapsule.load(path)
        assert loaded.metadata["step_count"] == 7
        assert loaded.gender == "male"
        assert loaded.personality["traits"]["openness"] == pytest.approx(0.1)

    def test_legacy_json_plus_torch_pair_still_loads(self, brain_capsule_mod, tmp_path):
        """BrainCapsule.load() documents a legacy fallback path: an old
        <base>.pcap.json + <base>.pcap.torch pair (pre-dating the unified
        .pcap format) should still load correctly, read-only. Constructs
        that legacy layout by hand rather than via .save() (which always
        writes the current format) to actually exercise the fallback
        branch, not just re-confirm the current-format path again."""
        import torch
        base = tmp_path / "legacy_brain"
        json_payload = {
            "metadata": {"agent_id": "legacy", "step_count": 3},
            "personality": {"gender": "female"},
            "gender": "female",
        }
        with open(str(base) + ".pcap.json", "w") as f:
            json.dump(json_payload, f)
        torch.save({"policy": {"dummy": 1}}, str(base) + ".pcap.torch")

        loaded = brain_capsule_mod.BrainCapsule.load(str(base))
        assert loaded.metadata["step_count"] == 3
        assert loaded.gender == "female"
        assert loaded.model_state == {"policy": {"dummy": 1}}

    def test_corrupted_pcap_with_no_legacy_fallback_raises_file_not_found(
        self, brain_capsule_mod, tmp_path,
    ):
        """Documents actual, current behaviour rather than assuming it: a
        present-but-corrupt .pcap with no .pcap.json fallback available
        does NOT surface the underlying torch.load error to the caller -
        load() logs it, falls through to the legacy-format check, finds
        nothing there either, and raises a plain FileNotFoundError instead.
        Worth knowing if 'brain failed to load' ever gets debugged from the
        exception type alone - the real cause is masked by this fallback."""
        base = tmp_path / "corrupt_brain"
        with open(str(base) + ".pcap", "wb") as f:
            f.write(b"not a valid torch checkpoint")

        with pytest.raises(FileNotFoundError):
            brain_capsule_mod.BrainCapsule.load(str(base))

    def test_save_is_atomic_no_tmp_file_left_behind_on_success(
        self, brain_capsule_mod, tmp_path,
    ):
        capsule = brain_capsule_mod.BrainCapsule(metadata={"agent_id": "x"})
        path = str(tmp_path / "brain")
        capsule.save(path)
        assert not (tmp_path / "brain.pcap.tmp").exists()


# ===========================================================================
# 6. The production wrapper's contract (agent_spawner.py::_save_brain)
# ===========================================================================

class TestAgentSpawnerSaveWrapperContract:
    """agent_spawner.py::AgentSpawner._save_brain() wraps agent.save() in a
    bare try/except that only logs.error() on failure - meaning production
    never raises on a broken brain save, it just silently continues with an
    agent whose brain never made it to disk. That makes the tests above the
    *only* thing that will ever fail loudly if save() regresses; this test
    just documents/pins that production contract itself so a future change
    to _save_brain() that removes the swallow (making it raise, or degrade
    differently) is a deliberate decision, not an accidental behavour change
    caught only by a customer-facing symptom."""

    def test_save_brain_swallows_a_failing_save_and_only_logs(self, agent_mod, tmp_path, caplog):
        agent_spawner_mod = importlib.import_module("ai_core.agent_spawner")
        agent = _make_agent(agent_mod)

        def _boom(path):
            raise RuntimeError("simulated disk failure")
        agent.save = _boom

        spawner = object.__new__(agent_spawner_mod.AgentSpawner)
        with caplog.at_level("ERROR"):
            spawner._save_brain(agent)  # must not raise
        assert any("Brain save failed" in rec.message for rec in caplog.records)