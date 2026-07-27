"""
Heavy tests for rl/policy.py's TransformerPolicy and GodTransformerPolicy -
the actual trained policy networks behind every agent's real-time actions.

MOST IMPORTANT TEST IN THIS FILE: test_construction_does_not_crash (both
classes). Until fixed, NEITHER of these classes could be instantiated at
all - SB3's real ActorCriticPolicy._build() unconditionally reads
self.mlp_extractor.latent_dim_pi right after calling the overridden
_build_mlp_extractor(), which set self.features_extractor (a different,
custom attribute) and never touched self.mlp_extractor. Reproduced this
crash against both the installed stable-baselines3 version and the exact
minimum pinned in requirements.txt (>=2.8.0, tested at ==2.8.0 too) - it
wasn't a version-compatibility regression, this construction path had
never worked.
"""
import numpy as np
import pytest
import torch


# ============================================================================
# TransformerPolicy (13-dim, NPC)
# ============================================================================

class TestTransformerPolicyConstruction:
    def test_construction_does_not_crash(self, transformer_policy):
        """The actual regression this whole file exists to prevent."""
        assert transformer_policy is not None

    def test_optimizer_exists_and_covers_every_parameter(self, transformer_policy):
        optimizer_params = {
            id(p) for group in transformer_policy.optimizer.param_groups
            for p in group["params"]
        }
        model_params = {id(p) for p in transformer_policy.parameters()}
        assert optimizer_params == model_params

    def test_custom_action_net_and_value_net_are_not_overwritten_by_sb3(
        self, transformer_policy
    ):
        """SB3's real _build() would otherwise silently replace these with
        its own generic construction after computing latent_dim_pi/vf - a
        much worse failure mode than a crash, since it would run without
        error but not be the architecture this class documents."""
        assert isinstance(transformer_policy.action_net, torch.nn.Sequential)
        assert isinstance(transformer_policy.value_net, torch.nn.Sequential)
        # The custom heads read the transformer's d_model, not whatever
        # SB3's generic MlpExtractor would have chosen independently.
        first_layer = transformer_policy.action_net[0]
        assert first_layer.in_features == transformer_policy.d_model


class TestTransformerPolicyForward:
    @pytest.mark.parametrize("batch_size", [1, 4, 32])
    def test_output_shapes_across_batch_sizes(self, transformer_policy, batch_size):
        obs = torch.randn(batch_size, 128)
        action_mean, values = transformer_policy.forward(obs)
        assert action_mean.shape == (batch_size, 13)
        assert values.shape == (batch_size,)

    def test_action_mean_is_tanh_bounded(self, transformer_policy):
        """action_net's output is wrapped in tanh - must never exceed
        [-1, 1] even for large/adversarial input magnitudes."""
        obs = torch.randn(8, 128) * 100  # deliberately extreme
        action_mean, _ = transformer_policy.forward(obs)
        assert torch.all(action_mean >= -1.0)
        assert torch.all(action_mean <= 1.0)

    def test_outputs_stay_finite_for_extreme_input(self, transformer_policy):
        obs = torch.randn(4, 128) * 1000
        action_mean, values = transformer_policy.forward(obs)
        assert torch.isfinite(action_mean).all()
        assert torch.isfinite(values).all()

    def test_forward_is_deterministic_given_identical_input(self, transformer_policy):
        """No dropout/batchnorm in this architecture - two forward passes
        on the same input in the same mode must match exactly."""
        transformer_policy.eval()
        obs = torch.randn(4, 128)
        with torch.no_grad():
            out1 = transformer_policy.forward(obs)
            out2 = transformer_policy.forward(obs)
        torch.testing.assert_close(out1[0], out2[0])
        torch.testing.assert_close(out1[1], out2[1])

    def test_different_inputs_produce_different_outputs(self, transformer_policy):
        """Sanity check against a degenerate "always outputs the same
        thing regardless of input" architecture bug."""
        transformer_policy.eval()
        with torch.no_grad():
            out_a, _ = transformer_policy.forward(torch.zeros(1, 128))
            out_b, _ = transformer_policy.forward(torch.ones(1, 128) * 5)
        assert not torch.allclose(out_a, out_b)


class TestTransformerPolicyGradientFlow:
    def test_gradient_reaches_features_extractor_and_heads(self, transformer_policy):
        obs = torch.randn(4, 128)
        action_mean, values = transformer_policy.forward(obs)
        (action_mean.sum() + values.sum()).backward()

        # Everything actually used to compute this specific loss.
        for name, p in transformer_policy.named_parameters():
            if name == "log_std":
                continue  # documented exception below
            assert p.grad is not None, f"{name} received no gradient"

    def test_log_std_has_no_gradient_from_a_plain_forward_call(self, transformer_policy):
        """Not a bug: log_std parameterizes the action distribution's
        stddev for stochastic sampling/log-prob computation elsewhere
        (e.g. GRPO's training step) - forward() itself only produces the
        deterministic mean and value estimate, so log_std is legitimately
        untouched by backpropagating through *this* call's output alone."""
        obs = torch.randn(4, 128)
        action_mean, values = transformer_policy.forward(obs)
        (action_mean.sum() + values.sum()).backward()
        assert transformer_policy.log_std.grad is None

    def test_optimizer_step_actually_changes_weights(self, transformer_policy):
        obs = torch.randn(4, 128)
        before = transformer_policy.action_net[0].weight.clone()
        action_mean, values = transformer_policy.forward(obs)
        (action_mean.sum() + values.sum()).backward()
        transformer_policy.optimizer.step()
        after = transformer_policy.action_net[0].weight
        assert not torch.allclose(before, after)


# ============================================================================
# GodTransformerPolicy (18-dim: 13 base + 5 ability extension)
# ============================================================================

class TestGodTransformerPolicyConstruction:
    def test_construction_does_not_crash(self, god_transformer_policy):
        assert god_transformer_policy is not None

    def test_optimizer_covers_every_parameter(self, god_transformer_policy):
        optimizer_params = {
            id(p) for group in god_transformer_policy.optimizer.param_groups
            for p in group["params"]
        }
        model_params = {id(p) for p in god_transformer_policy.parameters()}
        assert optimizer_params == model_params


class TestGodTransformerPolicyForward:
    @pytest.mark.parametrize("batch_size", [1, 4, 16])
    def test_output_shape_is_18dim(self, god_transformer_policy, batch_size):
        obs = torch.randn(batch_size, 128)
        action, values = god_transformer_policy.forward(obs)
        assert action.shape == (batch_size, 18)
        assert values.shape == (batch_size,)

    def test_base_movement_dims_are_tanh_bounded(self, god_transformer_policy):
        obs = torch.randn(8, 128) * 100
        action, _ = god_transformer_policy.forward(obs)
        base = action[:, :13]
        assert torch.all(base >= -1.0) and torch.all(base <= 1.0)

    def test_ability_index_dim_is_a_valid_index_into_n_abilities(
        self, god_transformer_policy
    ):
        """dims[14] must always land in [0, n_abilities), since agent.py's
        act_god() uses round(action[14]) directly as a list index into
        god_controls.ability_names()."""
        obs = torch.randn(16, 128)
        action, _ = god_transformer_policy.forward(obs)
        ability_idx = action[:, 14]
        assert torch.all(ability_idx >= 0)
        assert torch.all(ability_idx <= god_transformer_policy.n_abilities - 1)

    def test_deterministic_mode_is_reproducible(self, god_transformer_policy):
        """deterministic=True must not involve any sampling - two calls on
        the same input must match exactly (unlike deterministic=False,
        which samples the ability trigger/index and should NOT match)."""
        god_transformer_policy.eval()
        obs = torch.randn(4, 128)
        with torch.no_grad():
            action1, _ = god_transformer_policy.forward(obs, deterministic=True)
            action2, _ = god_transformer_policy.forward(obs, deterministic=True)
        torch.testing.assert_close(action1, action2)

    def test_stochastic_mode_actually_samples(self, god_transformer_policy):
        """The flip side of the above - deterministic=False uses
        torch.bernoulli/Categorical.sample(), so repeated calls on
        identical input should differ at least some of the time. Runs
        several trials since sampling could coincidentally match once."""
        god_transformer_policy.eval()
        obs = torch.randn(1, 128)
        with torch.no_grad():
            outputs = [
                god_transformer_policy.forward(obs, deterministic=False)[0]
                for _ in range(20)
            ]
        distinct = {tuple(o.flatten().tolist()) for o in outputs}
        assert len(distinct) > 1, "20 stochastic samples were all identical - sampling isn't happening"


class TestGodAbilityHeadDecodeLogic:
    """Directly exercises GodAbilityHead.decode()'s deterministic-vs-
    stochastic branching, since act_god() (agent.py) trusts dims[13]/[14]
    completely - a bug here means the wrong ability fires, or one fires
    when it shouldn't."""

    @pytest.fixture
    def ability_head(self):
        import importlib
        policy_mod = importlib.import_module("rl.policy")
        return policy_mod.GodAbilityHead(d_model=128, n_abilities=6)

    def test_deterministic_trigger_is_a_hard_threshold_not_a_coin_flip(self, ability_head):
        """decode()'s first parameter is a raw logit - sigmoid is applied
        internally (trigger_prob = torch.sigmoid(trigger_logit)) before
        the threshold comparison, so the logit values here need to
        actually straddle the threshold *after* that transform: sigmoid(0)
        == 0.5 exactly, so a clearly negative logit sigmoids below 0.5
        and a clearly positive one sigmoids above it."""
        high_logit = torch.tensor([[2.0]])   # sigmoid(2.0) ≈ 0.88
        low_logit = torch.tensor([[-2.0]])   # sigmoid(-2.0) ≈ 0.12
        logits = torch.zeros(1, 6)
        p = torch.zeros(1, 3)
        high_flag = ability_head.decode(high_logit, logits, p, deterministic=True, threshold=0.5)[:, 0]
        low_flag = ability_head.decode(low_logit, logits, p, deterministic=True, threshold=0.5)[:, 0]
        assert high_flag.item() == 1.0
        assert low_flag.item() == 0.0

    def test_deterministic_ability_choice_is_argmax_not_sampled(self, ability_head):
        trigger_logit = torch.tensor([[2.0]])  # sigmoid(2.0) ≈ 0.88 - clearly "trigger"
        logits = torch.tensor([[0.0, 0.0, 5.0, 0.0, 0.0, 0.0]])  # index 2 clearly dominant
        p = torch.zeros(1, 3)
        result = ability_head.decode(trigger_logit, logits, p, deterministic=True)
        assert result[:, 1].item() == 2.0

    def test_ability_params_pass_through_unmodified(self, ability_head):
        trigger_logit = torch.tensor([[2.0]])  # sigmoid(2.0) ≈ 0.88 - clearly "trigger"
        logits = torch.zeros(1, 6)
        p = torch.tensor([[0.3, -0.5, 0.8]])
        result = ability_head.decode(trigger_logit, logits, p, deterministic=True)
        torch.testing.assert_close(result[:, 2:5], p)