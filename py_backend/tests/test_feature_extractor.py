"""
Tests for vision.py's FeatureExtractor/_SimpleCNNExtractor - the CNN that
produces the feature vectors OnlineVisualVocabulary clusters on.

Complements test_online_visual_vocabulary.py: that file assumes it's
being handed reasonable feature vectors and tests what the vocabulary
does with them; this file tests where those vectors actually come from.
"""
import numpy as np
import pytest
import torch


@pytest.fixture
def vision_mod():
    import importlib
    return importlib.import_module("ai_core.vision")


@pytest.fixture
def extractor(vision_mod):
    return vision_mod.FeatureExtractor(feature_dim=64, device="cpu")


def _random_frame() -> np.ndarray:
    return np.random.rand(3, 84, 84).astype(np.float32)


class TestShapeContract:
    def test_extract_produces_the_declared_feature_dim(self, extractor):
        out = extractor.extract(_random_frame())
        assert out.shape == (64,)
        assert out.dtype == np.float32

    @pytest.mark.parametrize("feature_dim", [8, 32, 128])
    def test_respects_a_custom_feature_dim(self, vision_mod, feature_dim):
        extractor = vision_mod.FeatureExtractor(feature_dim=feature_dim, device="cpu")
        out = extractor.extract(_random_frame())
        assert out.shape == (feature_dim,)


class TestDeterminism:
    def test_identical_frame_produces_identical_features(self, extractor):
        """No dropout/batchnorm in this architecture, and extract() runs
        under eval()+no_grad() - two calls on the same frame must match
        exactly, not just approximately."""
        frame = _random_frame()
        out1 = extractor.extract(frame)
        out2 = extractor.extract(frame)
        np.testing.assert_array_equal(out1, out2)

    def test_different_frames_produce_different_features(self, extractor):
        out_a = extractor.extract(np.zeros((3, 84, 84), dtype=np.float32))
        out_b = extractor.extract(np.ones((3, 84, 84), dtype=np.float32))
        assert not np.allclose(out_a, out_b)

    def test_output_stays_finite_for_extreme_input(self, extractor):
        extreme = (np.random.randn(3, 84, 84) * 1000).astype(np.float32)
        out = extractor.extract(extreme)
        assert np.isfinite(out).all()


class TestWeightsAreTrainableNotFrozen:
    """The docstring's actual claim: 'weights start random and are updated
    by the agent's world-model trainer over time - so the features
    genuinely belong to the agent's learned experience, not an ImageNet
    prior.' Confirms the structural precondition for that: every
    parameter must be trainable (requires_grad=True), not frozen."""

    def test_every_cnn_parameter_requires_grad(self, extractor):
        assert extractor._net is not None, "torch should be available in this environment"
        for name, p in extractor._net.named_parameters():
            assert p.requires_grad, f"{name} is frozen (requires_grad=False)"

    def test_weights_are_not_all_zero_or_identical_at_init(self, extractor):
        """Confirms 'randomly initialised' isn't accidentally 'zero
        initialised' or 'constant initialised' - either would produce
        identical features for every input regardless of content."""
        conv1_weight = dict(extractor._net.named_parameters())["conv.0.weight"]
        assert conv1_weight.std().item() > 0.001

    def test_gradient_can_actually_flow_through_the_network(self, vision_mod):
        """extract() itself uses no_grad() (it's an inference helper), but
        the underlying network must still support being trained directly
        elsewhere - confirms a real backward pass reaches every parameter."""
        net = vision_mod._SimpleCNNExtractor(feature_dim=64)
        net.train()
        x = torch.randn(2, 3, 84, 84, requires_grad=False)
        out = net(x)
        out.sum().backward()
        for name, p in net.named_parameters():
            assert p.grad is not None, f"{name} received no gradient"


class TestPersistence:
    def test_state_dict_round_trips_to_identical_features(self, vision_mod, extractor):
        frame = _random_frame()
        original_output = extractor.extract(frame)

        state = extractor.state_dict()
        restored = vision_mod.FeatureExtractor(feature_dim=64, device="cpu")
        restored.load_state_dict(state)

        restored_output = restored.extract(frame)
        np.testing.assert_array_equal(original_output, restored_output)

    def test_two_fresh_extractors_differ_before_loading_shared_state(self, vision_mod):
        """Sanity check for the test above: two independently random-
        initialised extractors should NOT already agree by default -
        otherwise the round-trip test wouldn't actually be proving
        anything about persistence."""
        a = vision_mod.FeatureExtractor(feature_dim=64, device="cpu")
        b = vision_mod.FeatureExtractor(feature_dim=64, device="cpu")
        frame = _random_frame()
        assert not np.allclose(a.extract(frame), b.extract(frame))