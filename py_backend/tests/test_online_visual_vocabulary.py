"""
Heavy tests for vision.py's OnlineVisualVocabulary - the system behind
this project's central claim: the agent discovers visual categories from
what it actually encounters, with no hand-given labels (no COCO, no
ImageNet, no fixed class list anywhere).

These tests exercise the actual discovery/clustering/growth dynamics, not
just "does it construct and not crash": does a genuinely novel feature
get a new token, does a repeated/similar feature get recognized as the
same token, does the vocabulary actually grow over time, does the online
k-means update move cluster centres by the exact claimed amount, and does
state genuinely round-trip through save/load.
"""
import threading

import numpy as np
import pytest


@pytest.fixture
def vision_mod():
    import importlib
    return importlib.import_module("ai_core.vision")


@pytest.fixture
def vocab(vision_mod):
    return vision_mod.OnlineVisualVocabulary(
        max_clusters=16, feature_dim=8, lr=0.1, min_obs_to_split=5
    )


def _feature(seed: int, dim: int = 8) -> np.ndarray:
    """A deterministic pseudo-random feature vector, for reproducible tests."""
    rng = np.random.RandomState(seed)
    return rng.randn(dim).astype(np.float32)


class TestBootstrap:
    def test_first_observation_creates_cluster_zero(self, vocab):
        assert vocab.n_clusters == 0
        token = vocab.observe(_feature(1))
        assert token == 0
        assert vocab.n_clusters == 1

    def test_vocabulary_starts_completely_empty(self, vocab):
        """The literal 'blank slate' claim - no pre-seeded clusters, no
        hand-given categories, before anything has been observed."""
        assert vocab.n_clusters == 0
        assert vocab.get_stats()["total_obs"] == 0


class TestRecognitionVsDiscovery:
    def test_repeated_identical_feature_returns_same_token(self, vocab):
        f = _feature(1)
        token1 = vocab.observe(f)
        token2 = vocab.observe(f)
        token3 = vocab.observe(f)
        assert token1 == token2 == token3

    def test_slightly_varied_but_close_features_are_recognized_as_the_same_token(self, vocab):
        """Not just exact duplicates - genuinely similar (small-noise)
        observations of "the same kind of thing" should still map to one
        token, the way recognizing "another oak tree" shouldn't require
        pixel-identical input."""
        base = _feature(1)
        vocab.observe(base)
        for _ in range(5):
            noisy = base + np.random.randn(8).astype(np.float32) * 0.01
            token = vocab.observe(noisy)
            assert token == 0

    def test_a_wildly_different_feature_does_not_silently_merge_into_an_existing_token(
        self, vocab
    ):
        """The flip side: something genuinely different from what's been
        seen so far shouldn't just get absorbed into the nearest existing
        cluster with no trace - it should at minimum be recognized as the
        *farthest* possible match, not the nearest. (Whether it actually
        splits into a brand new cluster is covered by the growth tests
        below - min_obs_to_split gates that separately.)"""
        vocab.observe(np.zeros(8, dtype=np.float32))
        far_feature = np.ones(8, dtype=np.float32) * 1000
        nearest = vocab.most_similar(far_feature, k=1)
        # With only one cluster so far, it necessarily "is" the nearest -
        # the real assertion is that the reported distance reflects how
        # far away it actually is, not a falsely-small number.
        assert nearest[0][1] > 100


class TestVocabularyGrowth:
    def test_repeated_novel_observations_eventually_grow_the_vocabulary(self, vocab):
        """THE core discovery claim: something genuinely new and
        recurring gets its own token over time, with no one telling the
        system what category it is or that it should split."""
        # Establish an initial cluster.
        for _ in range(10):
            vocab.observe(_feature(1) + np.random.randn(8).astype(np.float32) * 0.01)
        assert vocab.n_clusters == 1

        # Repeatedly show something far away and different enough that,
        # once it's been seen min_obs_to_split times, it should split off.
        far = np.ones(8, dtype=np.float32) * 50
        for _ in range(10):
            vocab.observe(far + np.random.randn(8).astype(np.float32) * 0.01)

        assert vocab.n_clusters > 1, (
            "vocabulary never grew past its first cluster despite repeated, "
            "clearly-distinct observations - discovery isn't happening"
        )

    def test_vocabulary_never_exceeds_max_clusters(self, vision_mod):
        """No hand-given labels doesn't mean unbounded memory - max_clusters
        is a real, enforced ceiling."""
        vocab = vision_mod.OnlineVisualVocabulary(
            max_clusters=4, feature_dim=8, lr=0.1, min_obs_to_split=2
        )
        # Throw a lot of wildly different features at it - if the cap
        # weren't enforced, this would grow far past 4.
        for i in range(200):
            vocab.observe(_feature(i) * (i + 1))  # each one further apart
        assert vocab.n_clusters <= 4

    def test_n_clusters_never_decreases(self, vocab):
        """Growth is monotonic - clusters split, they're never merged or
        dropped by observe() alone."""
        seen_counts = []
        for i in range(30):
            vocab.observe(_feature(i) * (i % 5))
            seen_counts.append(vocab.n_clusters)
        assert seen_counts == sorted(seen_counts)


class TestOnlineKMeansUpdateRule:
    def test_nearest_centre_moves_toward_observation_by_exactly_lr_fraction(
        self, vision_mod
    ):
        """Precise, checkable version of "online k-means" - not just that
        the centre moves *some* amount, but the documented formula:
        centre += lr * (feature - centre)."""
        vocab = vision_mod.OnlineVisualVocabulary(
            max_clusters=16, feature_dim=8, lr=0.2, min_obs_to_split=1000  # prevent splitting
        )
        first = np.zeros(8, dtype=np.float32)
        vocab.observe(first)
        centre_before = vocab._centres[0].copy()

        second = np.ones(8, dtype=np.float32)
        vocab.observe(second)
        centre_after = vocab._centres[0]

        expected = centre_before + 0.2 * (second - centre_before)
        np.testing.assert_allclose(centre_after, expected, rtol=1e-5)

    def test_cluster_count_increments_on_each_assignment(self, vocab):
        f = _feature(1)
        vocab.observe(f)
        vocab.observe(f)
        vocab.observe(f)
        assert vocab._counts[0] == 3


class TestNaming:
    def test_unnamed_token_gets_a_generic_placeholder_not_a_hand_given_label(self, vocab):
        """This is the "no hand-given labels" claim made concrete: the
        DEFAULT name is a generic index-based placeholder, never a
        semantic guess like "tree" or "grass" - meaning is only ever
        attached later, explicitly, via assign_name()."""
        vocab.observe(_feature(1))
        assert vocab.name_of(0) == "visual_0"

    def test_assigned_name_is_retrieved_correctly(self, vocab):
        vocab.observe(_feature(1))
        vocab.assign_name(0, "oak_tree")
        assert vocab.name_of(0) == "oak_tree"

    def test_assigning_a_name_does_not_affect_clustering(self, vocab):
        """Naming is purely a label attached after the fact - it must not
        change which token future observations resolve to."""
        f = _feature(1)
        token_before = vocab.observe(f)
        vocab.assign_name(token_before, "oak_tree")
        token_after = vocab.observe(f)
        assert token_before == token_after


class TestMostSimilar:
    def test_returns_k_results_sorted_nearest_first(self, vocab):
        for i in range(6):
            vocab.observe(_feature(i) * (i + 1) * 10)  # spread them out
        results = vocab.most_similar(_feature(0), k=3)
        assert len(results) == 3
        distances = [dist for _, dist in results]
        assert distances == sorted(distances)

    def test_empty_vocabulary_returns_empty_list(self, vocab):
        assert vocab.most_similar(_feature(1)) == []


class TestPersistence:
    def test_state_dict_round_trips_through_load_state_dict(self, vision_mod, vocab):
        vocab.observe(_feature(1))
        vocab.observe(_feature(2) * 10)
        vocab.assign_name(0, "oak_tree")

        state = vocab.state_dict()
        restored = vision_mod.OnlineVisualVocabulary(feature_dim=8)
        restored.load_state_dict(state)

        assert restored.n_clusters == vocab.n_clusters
        assert restored.get_stats()["total_obs"] == vocab.get_stats()["total_obs"]
        assert restored.name_of(0) == "oak_tree"
        np.testing.assert_allclose(restored._centres, vocab._centres)

    def test_restored_vocabulary_still_recognizes_the_same_token_for_the_same_feature(
        self, vision_mod, vocab
    ):
        f = _feature(1)
        token_before = vocab.observe(f)
        state = vocab.state_dict()

        restored = vision_mod.OnlineVisualVocabulary(feature_dim=8)
        restored.load_state_dict(state)
        # A near-identical observation post-restore should resolve to the
        # same token, proving the restored centres are actually usable,
        # not just structurally present.
        token_after = restored.observe(f + np.random.randn(8).astype(np.float32) * 0.001)
        assert token_after == token_before


class TestThreadSafety:
    def test_concurrent_observations_do_not_corrupt_internal_state(self, vocab):
        """observe() holds self._lock - concurrent callers (e.g. multiple
        perception pipelines feeding the same agent's vocabulary) must not
        corrupt _centres/_counts into an inconsistent state."""
        n_threads = 8
        calls_per_thread = 25

        def worker(seed_offset):
            for i in range(calls_per_thread):
                vocab.observe(_feature(seed_offset + i))

        threads = [threading.Thread(target=worker, args=(t * 1000,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert vocab.get_stats()["total_obs"] == n_threads * calls_per_thread
        # Centres and counts arrays must stay the same length as each
        # other no matter how many threads raced to grow the vocabulary.
        assert len(vocab._centres) == len(vocab._counts)