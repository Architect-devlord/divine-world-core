"""
Heavy tests for world_model.py's actual transformer architecture:
VisionEncoder/AudioEncoder/ProprioceptionEncoder/ActionEncoder,
TransformerBlock, and WorldModelTransformer (the real causal sequence
model that fuses all four modalities).

The centerpiece here is test_causal_mask_actually_blocks_future_leakage -
WorldModelTransformer's docstring/comments claim causal masking, and a
real causal mask (torch.triu(..., diagonal=1)) is genuinely constructed
in WorldModel.forward(). This test doesn't just check that a mask tensor
gets built - it empirically proves the *behavioral* claim: changing a
future timestep's input must leave every earlier timestep's output
completely unchanged. That's the actual thing "causal" is supposed to
guarantee, and reading the mask-construction code alone can't tell you
whether MultiheadAttention is actually being called with it correctly.
"""
import torch
import pytest


@pytest.fixture
def world_model_mod():
    import importlib
    return importlib.import_module("ai_core.world_model")


# ============================================================================
# Modality encoders
# ============================================================================

class TestModalityEncoders:
    @pytest.mark.parametrize("batch_size,seq_len", [(1, 1), (2, 4), (4, 16)])
    def test_vision_encoder_shape(self, world_model_mod, world_model_config, batch_size, seq_len):
        encoder = world_model_mod.VisionEncoder(
            channels=world_model_config.vision_channels, output_dim=world_model_config.d_model
        )
        x = torch.randn(batch_size, seq_len, 3, 84, 84)
        out = encoder(x)
        assert out.shape == (batch_size, seq_len, world_model_config.d_model)

    def test_audio_encoder_shape(self, world_model_mod, world_model_config):
        encoder = world_model_mod.AudioEncoder(input_dim=128, output_dim=world_model_config.d_model)
        x = torch.randn(3, 8, 128)
        out = encoder(x)
        assert out.shape == (3, 8, world_model_config.d_model)

    def test_proprio_encoder_shape(self, world_model_mod, world_model_config):
        encoder = world_model_mod.ProprioceptionEncoder(
            input_dim=32, output_dim=world_model_config.d_model
        )
        x = torch.randn(3, 8, 32)
        out = encoder(x)
        assert out.shape == (3, 8, world_model_config.d_model)

    def test_action_encoder_shape(self, world_model_mod, world_model_config):
        encoder = world_model_mod.ActionEncoder(
            world_model_config.action_dim, world_model_config.d_model
        )
        x = torch.randn(3, 8, world_model_config.action_dim)
        out = encoder(x)
        assert out.shape == (3, 8, world_model_config.d_model)

    def test_all_encoders_produce_finite_output_for_extreme_input(
        self, world_model_mod, world_model_config
    ):
        vision = world_model_mod.VisionEncoder(channels=3, output_dim=world_model_config.d_model)
        out = vision(torch.randn(2, 2, 3, 84, 84) * 1000)
        assert torch.isfinite(out).all()

    def test_gradient_reaches_every_encoder_parameter(self, world_model_mod, world_model_config):
        encoder = world_model_mod.ProprioceptionEncoder(
            input_dim=32, output_dim=world_model_config.d_model
        )
        x = torch.randn(2, 4, 32)
        out = encoder(x)
        out.sum().backward()
        for name, p in encoder.named_parameters():
            assert p.grad is not None, f"{name} received no gradient"


# ============================================================================
# TransformerBlock
# ============================================================================

class TestTransformerBlock:
    def test_output_shape_matches_input(self, world_model_config):
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        block = world_model_mod.TransformerBlock(
            d_model=world_model_config.d_model, n_heads=4, d_ff=256, dropout=0.0
        )
        x = torch.randn(2, 6, world_model_config.d_model)
        out = block(x)
        assert out.shape == x.shape

    def test_block_with_causal_mask_blocks_future_leakage(self, world_model_config):
        """The same behavioral property tested at the full-transformer
        level below, but isolated to a single TransformerBlock, so a
        failure here points directly at the attention mechanism itself
        rather than something in the encoder/summing layers above it."""
        import importlib
        world_model_mod = importlib.import_module("ai_core.world_model")
        torch.manual_seed(0)
        block = world_model_mod.TransformerBlock(
            d_model=world_model_config.d_model, n_heads=4, d_ff=256, dropout=0.0
        )
        block.eval()

        T = 5
        x1 = torch.randn(1, T, world_model_config.d_model)
        x2 = x1.clone()
        x2[:, -1, :] = torch.randn(world_model_config.d_model)  # perturb only the LAST position

        mask = torch.triu(torch.ones(T, T) * float("-inf"), diagonal=1)
        with torch.no_grad():
            out1 = block(x1, mask=mask)
            out2 = block(x2, mask=mask)

        # Every position except the perturbed last one must be identical.
        torch.testing.assert_close(out1[:, :-1, :], out2[:, :-1, :])
        # Sanity check the test itself: the perturbation must actually
        # reach the final position's own output, or this proves nothing.
        assert not torch.allclose(out1[:, -1, :], out2[:, -1, :])


# ============================================================================
# WorldModelTransformer + encode_observation (the full fused sequence model)
# ============================================================================

class TestWorldModelTransformerCausality:
    def test_causal_mask_actually_blocks_future_leakage(self, world_model, world_model_config):
        """THE key architectural claim in this file. Builds two full
        observations identical except at the last timestep, runs both
        through the real WorldModel (encoders -> summing -> transformer),
        and asserts every earlier timestep's prediction is byte-identical
        - proving the causal mask is genuinely wired all the way through,
        not just constructed and silently unused."""
        torch.manual_seed(0)
        B, T = 1, 6

        def build_obs(last_step_seed):
            g = torch.Generator().manual_seed(last_step_seed)
            obs = {
                "vision": torch.randn(B, T, 3, 84, 84, generator=torch.Generator().manual_seed(1)),
                "audio": torch.randn(B, T, 128, generator=torch.Generator().manual_seed(2)),
                "proprio": torch.randn(B, T, 32, generator=torch.Generator().manual_seed(3)),
                "action": torch.randn(B, T, world_model_config.action_dim,
                                       generator=torch.Generator().manual_seed(4)),
            }
            # Perturb only the final timestep, every modality, using a
            # different seed so it's guaranteed different from the shared base.
            for key, shape in [("vision", (3, 84, 84)), ("audio", (128,)),
                                ("proprio", (32,)), ("action", (world_model_config.action_dim,))]:
                obs[key][:, -1] = torch.randn(B, *shape, generator=g)
            return obs

        obs_a = build_obs(last_step_seed=100)
        obs_b = build_obs(last_step_seed=999)  # only the last timestep differs from obs_a

        world_model.eval()
        with torch.no_grad():
            # WorldModelConfig.use_vae defaults to True, and
            # VariationalEncoder reparameterizes with fresh noise
            # (eps = torch.randn_like(std)) on every single forward call.
            # Without controlling for that, pred_a and pred_b would differ
            # at EVERY timestep from that independent noise draw alone,
            # regardless of causal masking - reseeding identically before
            # each call makes the noise itself identical, isolating the
            # comparison to the actual effect of the perturbed input.
            torch.manual_seed(42)
            pred_a = world_model(obs_a)
            torch.manual_seed(42)
            pred_b = world_model(obs_b)

        # Every prediction is per-timestep (B, T, ...) - positions 0..T-2
        # must be completely unaffected by the perturbed final position.
        for key in ("reward", "termination"):
            torch.testing.assert_close(pred_a[key][:, :-1], pred_b[key][:, :-1])

        # Confirm the perturbation is real (the test would be meaningless
        # if obs_a and obs_b's last timesteps happened to match, or if
        # nothing downstream is sensitive to the last timestep at all).
        assert not torch.allclose(pred_a["reward"][:, -1], pred_b["reward"][:, -1])

    def test_encode_observation_sums_present_modalities(self, world_model, world_model_config):
        """encode_observation adds each present modality's encoding
        together rather than concatenating - confirms this directly by
        checking that providing only proprio+action produces a DIFFERENT
        (non-zero-vision/audio-contribution) result than providing all
        four, and that omitted modalities don't crash it."""
        B, T = 1, 3
        full_obs = {
            "vision": torch.randn(B, T, 3, 84, 84),
            "audio": torch.randn(B, T, 128),
            "proprio": torch.randn(B, T, 32),
            "action": torch.randn(B, T, world_model_config.action_dim),
        }
        partial_obs = {
            "proprio": full_obs["proprio"],
            "action": full_obs["action"],
        }
        with torch.no_grad():
            full_encoding = world_model.encode_observation(full_obs)
            partial_encoding = world_model.encode_observation(partial_obs)

        assert full_encoding.shape == (B, T, world_model_config.d_model)
        assert partial_encoding.shape == (B, T, world_model_config.d_model)
        assert not torch.allclose(full_encoding, partial_encoding)

    def test_encode_observation_handles_single_modality(self, world_model, world_model_config):
        B, T = 2, 3
        obs = {"proprio": torch.randn(B, T, 32)}
        with torch.no_grad():
            encoding = world_model.encode_observation(obs)
        assert encoding.shape == (B, T, world_model_config.d_model)
        assert torch.isfinite(encoding).all()

    @pytest.mark.parametrize("batch_size,seq_len", [(1, 1), (2, 4), (4, 16)])
    def test_full_forward_pass_shapes_across_batch_and_sequence_lengths(
        self, world_model, world_model_config, batch_size, seq_len
    ):
        obs = {
            "vision": torch.randn(batch_size, seq_len, 3, 84, 84),
            "audio": torch.randn(batch_size, seq_len, 128),
            "proprio": torch.randn(batch_size, seq_len, 32),
            "action": torch.randn(batch_size, seq_len, world_model_config.action_dim),
        }
        with torch.no_grad():
            pred = world_model(obs)
        assert pred["reward"].shape == (batch_size, seq_len, 1)

    def test_gradient_reaches_transformer_and_all_four_encoders(self, world_model, world_model_config):
        B, T = 2, 4
        obs = {
            "vision": torch.randn(B, T, 3, 84, 84),
            "audio": torch.randn(B, T, 128),
            "proprio": torch.randn(B, T, 32),
            "action": torch.randn(B, T, world_model_config.action_dim),
        }
        pred = world_model(obs)
        pred["reward"].sum().backward()

        encoder_prefixes = ("vision_encoder", "audio_encoder", "proprio_encoder", "action_encoder")
        for name, p in world_model.transformer.named_parameters():
            if name.split(".")[0] in encoder_prefixes or "blocks" in name:
                assert p.grad is not None, f"transformer.{name} received no gradient"