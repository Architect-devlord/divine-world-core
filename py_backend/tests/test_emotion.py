"""
Behavioral tests for ai_core/emotion.py's EmotionSystem.

Complements test_symbolic_registries.py, which checks EmotionSystem stays
consistent with obs_builder.py's expectations - this file tests the class
on its own terms: does add/set/decay/snapshot/dominant_emotion/valence
actually do what they claim to.
"""
import pytest


@pytest.fixture
def emotion(real_emotion):
    return real_emotion


def test_starts_at_zero_for_every_declared_emotion(emotion):
    snap = emotion.snapshot()
    assert set(snap.keys()) == set(emotion.EMOTIONS)
    assert all(v == 0.0 for v in snap.values())


def test_add_accumulates(emotion):
    emotion.add("joy", 0.3)
    emotion.add("joy", 0.2)
    assert emotion.snapshot()["joy"] == pytest.approx(0.5)


def test_add_clips_to_positive_one(emotion):
    emotion.add("joy", 0.9)
    emotion.add("joy", 0.9)
    assert emotion.snapshot()["joy"] == pytest.approx(1.0)


def test_add_clips_to_negative_one(emotion):
    emotion.add("fear", -0.9)
    emotion.add("fear", -0.9)
    assert emotion.snapshot()["fear"] == pytest.approx(-1.0)


def test_add_unknown_emotion_name_is_a_silent_no_op_not_a_crash(emotion):
    """This is exactly the shape of bug this file's own EMOTIONS list has
    already had (frustration/curiosity used to be 'unknown' to this dict)
    - confirms the *current*, correct failure mode is silent-ignore, not
    an exception, so a typo'd emotion name degrades gracefully rather than
    crashing whatever called it."""
    before = emotion.snapshot()
    emotion.add("definitely_not_a_real_emotion", 0.5)
    after = emotion.snapshot()
    assert before == after
    assert "definitely_not_a_real_emotion" not in after


def test_set_overwrites_rather_than_accumulates(emotion):
    emotion.add("anger", 0.9)
    emotion.set("anger", 0.2)
    assert emotion.snapshot()["anger"] == pytest.approx(0.2)


def test_set_also_clips(emotion):
    emotion.set("anger", 5.0)
    assert emotion.snapshot()["anger"] == pytest.approx(1.0)
    emotion.set("anger", -5.0)
    assert emotion.snapshot()["anger"] == pytest.approx(-1.0)


def test_decay_moves_every_emotion_toward_zero(emotion):
    for e in emotion.EMOTIONS:
        emotion.set(e, 1.0)
    emotion.decay_rate = 0.5
    emotion.decay()
    snap = emotion.snapshot()
    assert all(v == pytest.approx(0.5) for v in snap.values())


def test_decay_never_flips_sign(emotion):
    emotion.set("fear", -0.8)
    emotion.decay()
    assert emotion.snapshot()["fear"] < 0


def test_reset_zeroes_everything(emotion):
    for e in emotion.EMOTIONS:
        emotion.set(e, 0.7)
    emotion.reset()
    assert all(v == 0.0 for v in emotion.snapshot().values())


def test_snapshot_returns_a_copy_not_a_live_reference(emotion):
    """If this were the internal dict itself, code that does
    `snap = agent.emotion.snapshot(); snap['joy'] = 99` would silently
    corrupt the agent's real emotional state - snapshot() must return an
    independent copy."""
    snap = emotion.snapshot()
    snap["joy"] = 99.0
    assert emotion.snapshot()["joy"] == 0.0


def test_as_array_matches_emotions_order_and_length(emotion):
    emotion.set("joy", 0.4)
    emotion.set("fear", -0.6)
    arr = emotion.as_array()
    assert len(arr) == len(emotion.EMOTIONS)
    joy_idx = emotion.EMOTIONS.index("joy")
    fear_idx = emotion.EMOTIONS.index("fear")
    assert arr[joy_idx] == pytest.approx(0.4)
    assert arr[fear_idx] == pytest.approx(-0.6)


def test_dominant_emotion_picks_largest_magnitude_even_if_negative(emotion):
    """max(..., key=lambda x: abs(x[1])) - a strong negative emotion
    should win over a weak positive one, not be ignored for being
    negative."""
    emotion.set("joy", 0.2)
    emotion.set("fear", -0.9)
    assert emotion.dominant_emotion() == "fear"


def test_intensity_is_max_absolute_value(emotion):
    emotion.set("joy", 0.3)
    emotion.set("fear", -0.7)
    assert emotion.intensity() == pytest.approx(0.7)


def test_is_calm_reflects_intensity_threshold(emotion):
    assert emotion.is_calm() is True  # everything starts at 0.0
    emotion.set("fear", 0.9)
    assert emotion.is_calm() is False
    assert emotion.is_calm(threshold=0.95) is True  # explicit looser threshold


def test_valence_positive_when_positive_emotions_dominate(emotion):
    emotion.set("joy", 1.0)
    emotion.set("trust", 1.0)
    emotion.set("anticipation", 1.0)
    assert emotion.valence() == pytest.approx(1.0)


def test_valence_negative_when_negative_emotions_dominate(emotion):
    emotion.set("sadness", 1.0)
    emotion.set("anger", 1.0)
    emotion.set("fear", 1.0)
    emotion.set("disgust", 1.0)
    # (4 negatives summed then /3.0, then clipped) - just confirm sign and clip
    assert emotion.valence() == pytest.approx(-1.0)


def test_valence_neutral_at_rest(emotion):
    assert emotion.valence() == pytest.approx(0.0)