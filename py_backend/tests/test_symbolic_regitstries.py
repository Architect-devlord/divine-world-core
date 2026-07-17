"""
Regression tests for the "symbolic name never actually registered in the
real underlying structure" bug class - found and fixed twice this session
(EmotionSystem missing 'frustration'/'curiosity', Personality missing a
real 'persistence' trait).

These tests check the actual invariant (every key obs_builder.py expects
really exists on the real component) rather than hardcoding today's list
of keys - if EMOTION_KEYS or the real EMOTIONS set ever changes, these
tests validate whichever new lists are in place, they don't need editing
just because a key was added or renamed.
"""
import pytest


@pytest.fixture
def obs_builder():
    import importlib
    return importlib.import_module("ai_core.obs_builder")


def test_every_emotion_key_obs_builder_expects_is_real(obs_builder, real_emotion):
    """obs_builder.py's own comment says EMOTION_KEYS 'must match
    EmotionSystem.snapshot() keys' - this is what actually enforces that,
    instead of a comment nobody re-checks. Historically failed for
    'frustration' and 'curiosity' - those two dimensions were permanently
    dead (always 0.0) until fixed."""
    real_snapshot_keys = set(real_emotion.snapshot().keys())
    expected_keys = set(obs_builder.EMOTION_KEYS)

    missing = expected_keys - real_snapshot_keys
    assert not missing, (
        f"obs_builder.EMOTION_KEYS expects {missing}, but EmotionSystem."
        f"snapshot() doesn't produce them - these observation dimensions "
        f"would be permanently stuck at 0.0 (obs_builder.py silently "
        f"defaults via emotions.get(key, 0.0))."
    )


def test_emotion_keys_and_real_emotions_are_exactly_the_same_set(obs_builder, real_emotion):
    """Stronger than the above: also catches the reverse direction (a real
    emotion nothing ever reads into the observation) and exact-length
    drift, in case EMOTION_KEYS's own hardcoded count silently goes stale."""
    assert set(obs_builder.EMOTION_KEYS) == set(real_emotion.EMOTIONS)
    assert len(obs_builder.EMOTION_KEYS) == len(real_emotion.EMOTIONS), (
        "EMOTION_KEYS and EmotionSystem.EMOTIONS have the same set of names "
        "but a different count - likely a duplicate entry in one of them."
    )


def test_add_and_snapshot_round_trip_for_every_declared_emotion(real_emotion):
    """Belt-and-suspenders on top of the key-parity check above: actually
    call .add() for every declared emotion and confirm it moves the
    snapshot value, not just that the key exists."""
    for emotion_name in real_emotion.EMOTIONS:
        before = real_emotion.snapshot().get(emotion_name)
        real_emotion.add(emotion_name, 0.3)
        after = real_emotion.snapshot().get(emotion_name)
        assert after != before, (
            f"add('{emotion_name}', ...) didn't change its own snapshot value"
        )


class TestPersonalityTraits:
    """Guards the 'persistence' bug specifically: every real .traits.get()
    call site should be asking for a trait that actually exists, not
    silently getting a hardcoded fallback default forever."""

    KNOWN_LIVE_CALL_SITES = {
        # (file, trait actually used, what it replaced) - update this list
        # if a new .traits.get(...) call site is added elsewhere; the
        # point of this table is to make that an explicit, reviewed edit.
        "cognitive_loop.py": "conscientiousness",
        "skill_tracker.py": "conscientiousness",
    }

    def test_known_call_sites_use_real_traits(self, real_personality):
        real_traits = set(real_personality.TRAITS)
        for _file, trait in self.KNOWN_LIVE_CALL_SITES.items():
            assert trait in real_traits, (
                f"{_file} reads Personality.traits.get('{trait}', ...) but "
                f"'{trait}' isn't a real trait - it would silently always "
                f"return the hardcoded default."
            )

    def test_persistence_is_not_accidentally_reintroduced_as_a_real_trait(
        self, real_personality
    ):
        """Not a normative claim that 'persistence' must never exist -
        just documents the historical bug (every .traits.get('persistence',
        0.5) call silently returned the default forever) so a future
        change to TRAITS is a deliberate, visible decision either way."""
        assert "persistence" not in real_personality.TRAITS, (
            "If you've deliberately added 'persistence' as a real trait, "
            "update cognitive_loop.py/skill_tracker.py to read it directly "
            "instead of falling back to conscientiousness, then update "
            "KNOWN_LIVE_CALL_SITES above and delete this test."
        )