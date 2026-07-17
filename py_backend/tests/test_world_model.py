"""
Regression tests for ai_core/world_model.py.

Covers bugs found and fixed in this project's July 2026 audit session:
- action_dim=11 stale hardcodes (test_world_model's dummy batch, and the
  cold-start fallback in _build_observation_from_context)
- god agents' 18-dim last_action not truncated before hitting the
  fixed-width action_encoder
- compute_loss's next_state guard checking key-presence instead of
  value-presence
- torch>=2.6 weights_only breaking WorldModel.load()

Each test checks the *invariant* (does the real action tensor's last
dimension match model.config.action_dim) rather than hardcoding today's
value (13), so these stay meaningful if that number is ever deliberately
changed later - only the tests that pin an intentional design default
(e.g. the fresh-config default itself) hardcode a number on purpose.
"""
import numpy as np
import torch
import pytest


def test_fresh_config_default_action_dim():
    """Pins the intentional default - if this ever changes, it should be
    a deliberate, reviewed decision, not a silent drift."""
    import importlib
    world_model = importlib.import_module("ai_core.world_model")
    assert world_model.WorldModelConfig().action_dim == 13


def test_action_encoder_matches_config_action_dim(world_model, world_model_config):
    """The actual invariant that caused every action_dim bug this session:
    action_encoder must accept exactly config.action_dim, whatever that is."""
    dummy = torch.randn(2, 4, world_model_config.action_dim)
    encoded = world_model.transformer.action_encoder(dummy)
    assert encoded.shape[0] == 2 and encoded.shape[1] == 4


@pytest.mark.slow
def test_built_in_self_test_runs_clean(world_model_config):
    """Runs the module's own test_world_model() end to end: forward pass,
    train_step, imagine, and save/load. This is the single broadest
    regression guard in this file - if any of the four historical bugs
    (or a new one in the same family) comes back, this fails."""
    import importlib
    world_model = importlib.import_module("ai_core.world_model")
    world_model.test_world_model()  # raises on any internal failure


class TestActionFallbackDimensions:
    """_build_observation_from_context's action tensor must always end up
    at config.action_dim, regardless of what agent.last_action looks like."""

    def _build_agent(self, world_model, real_emotion, real_personality,
                      last_action=None, god_type=None):
        class _Agent:
            agent_id = "test_agent"
            health = 20.0
            hunger = 20.0
            emotion = real_emotion
            personality = real_personality
        a = _Agent()
        a.world_model = world_model
        a.last_action = last_action
        a.god_type = god_type
        return a

    def test_cold_start_fallback_matches_config_dim(
        self, world_model, world_model_config, real_emotion, real_personality
    ):
        """No last_action set at all (a fresh agent's very first tick)."""
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        agent = self._build_agent(world_model, real_emotion, real_personality,
                                   last_action=None)
        obs = world_model_mod._build_observation_from_context(agent, {})
        assert obs["action"].shape[-1] == world_model_config.action_dim

    def test_npc_last_action_passes_through_at_config_dim(
        self, world_model, world_model_config, real_emotion, real_personality
    ):
        """An NPC's last_action is already exactly config.action_dim - must
        pass through unchanged (not accidentally truncated further)."""
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        npc_action = np.random.randn(world_model_config.action_dim).astype(np.float32)
        agent = self._build_agent(world_model, real_emotion, real_personality,
                                   last_action=npc_action)
        obs = world_model_mod._build_observation_from_context(agent, {})
        assert obs["action"].shape[-1] == world_model_config.action_dim
        np.testing.assert_allclose(
            obs["action"].squeeze().numpy(), npc_action, rtol=1e-5
        )

    def test_god_18dim_last_action_gets_truncated(
        self, world_model, world_model_config, real_emotion, real_personality
    ):
        """The actual bug: act_god() stores the full (wider-than-NPC)
        policy output in last_action. Whatever that width is, the world
        model must only ever see the first config.action_dim entries."""
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        wider_action = np.random.randn(world_model_config.action_dim + 5).astype(np.float32)
        agent = self._build_agent(world_model, real_emotion, real_personality,
                                   last_action=wider_action, god_type="wither")
        obs = world_model_mod._build_observation_from_context(agent, {})
        assert obs["action"].shape[-1] == world_model_config.action_dim
        np.testing.assert_allclose(
            obs["action"].squeeze().numpy(),
            wider_action[:world_model_config.action_dim],
            rtol=1e-5,
        )

    def test_fallback_and_god_action_both_feed_forward_pass_without_crashing(
        self, world_model, world_model_config, real_emotion, real_personality
    ):
        """End-to-end: whatever _build_observation_from_context produces
        must actually be consumable by the real model, not just the right
        shape in isolation."""
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        for last_action, god_type in [
            (None, None),
            (np.random.randn(world_model_config.action_dim).astype(np.float32), None),
            (np.random.randn(world_model_config.action_dim + 5).astype(np.float32), "wither"),
        ]:
            agent = self._build_agent(world_model, real_emotion, real_personality,
                                       last_action=last_action, god_type=god_type)
            obs = world_model_mod._build_observation_from_context(agent, {})
            with torch.no_grad():
                pred = world_model(obs)
            assert pred["reward"].shape == (1, 1, 1)


def test_train_step_handles_missing_next_state_key(world_model, world_model_config):
    """compute_loss's guard must check whether a real next_state value is
    present, not just whether the dict happens to have the key (train_step
    always inserts the key via batch.get(), even when there's no real
    target) - this is what "crashed on the model's own self-test" meant."""
    B, T = 2, 8
    batch = {
        "vision": torch.randn(B, T, 3, 84, 84),
        "audio": torch.randn(B, T, 128),
        "proprio": torch.randn(B, T, 32),
        "action": torch.randn(B, T, world_model_config.action_dim),
        "reward": torch.randn(B, T, 1),
        "termination": torch.randint(0, 2, (B, T, 1)).float(),
        # deliberately no 'next_state' key at all
    }
    losses = world_model.train_step(batch)
    assert "total" in losses  # must return normally, not raise


def test_save_load_round_trip_survives_torch_weights_only_default(world_model, tmp_path):
    """torch>=2.6 defaults torch.load() to weights_only=True, which rejects
    custom classes like WorldModelConfig unless explicitly allowlisted.
    WorldModel.load() must handle this itself - the caller shouldn't need
    to know or care which torch version is installed.

    NOTE: deliberately does NOT also assert that a raw, unfixed
    torch.load(..., weights_only=True) call fails - add_safe_globals()
    mutates a process-wide registry, so once *any* test in this session
    has exercised the real WorldModel.load() (see
    test_built_in_self_test_runs_clean above), that registration leaks
    forward and a raw call would misleadingly succeed too, regardless of
    test order. The real regression protection is the round-trip below.
    """
    import importlib
    world_model_mod = importlib.import_module("ai_core.world_model")
    ckpt_path = str(tmp_path / "test_checkpoint.pt")
    world_model.save(ckpt_path)

    loaded = world_model_mod.WorldModel.load(ckpt_path)
    assert loaded.config.action_dim == world_model.config.action_dim