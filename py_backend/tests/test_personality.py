"""
Behavioral tests for ai_core/personality.py's Personality class and its
module-level gender/breeding helpers.

Complements test_symbolic_registries.py's TestPersonalityTraits (which
guards the historical 'persistence' bug specifically) - this file tests
the class more broadly on its own terms.
"""
import numpy as np
import pytest


@pytest.fixture
def personality_mod():
    import importlib
    return importlib.import_module("ai_core.personality")


@pytest.fixture
def personality(real_personality):
    return real_personality


def test_starts_at_zero_for_every_declared_trait(personality):
    assert set(personality.traits.keys()) == set(personality.TRAITS)
    assert all(v == 0.0 for v in personality.traits.values())


def test_default_gender_is_male(personality):
    assert personality.gender == "male"


def test_constructor_accepts_partial_traits_dict(personality_mod):
    p = personality_mod.Personality(traits={"openness": 0.7, "boldness": -0.3})
    assert p.traits["openness"] == pytest.approx(0.7)
    assert p.traits["boldness"] == pytest.approx(-0.3)
    # Everything not explicitly given stays at the default
    assert p.traits["extraversion"] == 0.0


def test_constructor_clips_out_of_range_traits(personality_mod):
    p = personality_mod.Personality(traits={"openness": 5.0, "boldness": -5.0})
    assert p.traits["openness"] == pytest.approx(1.0)
    assert p.traits["boldness"] == pytest.approx(-1.0)


def test_constructor_silently_ignores_unknown_trait_names(personality_mod):
    """Same shape as the historical 'persistence' bug: an unknown trait
    name in the input dict must not raise, and must not get added as a
    new key - .traits should only ever contain the declared TRAITS."""
    p = personality_mod.Personality(traits={"persistence": 0.8, "openness": 0.5})
    assert "persistence" not in p.traits
    assert p.traits["openness"] == pytest.approx(0.5)
    assert set(p.traits.keys()) == set(p.TRAITS)


def test_get_returns_default_for_unknown_trait(personality):
    """Directly exercises the exact call shape used at the historical bug
    sites (cognitive_loop.py/skill_tracker.py did
    personality.traits.get('persistence', 0.5))."""
    assert personality.get("persistence", 0.5) == 0.5
    assert personality.get("definitely_not_real") == 0.0  # documented default


def test_get_returns_real_value_for_known_trait(personality):
    personality.traits["conscientiousness"] = 0.6
    assert personality.get("conscientiousness") == pytest.approx(0.6)


def test_to_dict_includes_gender_and_every_trait(personality):
    personality.traits["openness"] = 0.4
    d = personality.to_dict()
    assert d["gender"] == "male"
    assert d["openness"] == pytest.approx(0.4)
    assert set(d.keys()) == {"gender", *personality.TRAITS}


def test_from_dict_round_trips_to_dict(personality_mod):
    original = personality_mod.Personality(
        gender="female", traits={"openness": 0.6, "neuroticism": -0.2}
    )
    restored = personality_mod.Personality.from_dict(original.to_dict())
    assert restored.gender == original.gender
    assert restored.traits == original.traits


def test_from_dict_does_not_mutate_the_caller_supplied_dict(personality_mod):
    """The source has an explicit comment guaranteeing this
    ("never mutate caller's dict") - confirms from_dict's own .pop() on a
    *copy* actually holds, not the original passed in."""
    data = {"gender": "female", "openness": 0.5}
    original_copy = dict(data)
    personality_mod.Personality.from_dict(data)
    assert data == original_copy, "from_dict mutated the caller's dict"


def test_as_array_matches_traits_order_and_length(personality):
    personality.traits["openness"] = 0.3
    personality.traits["boldness"] = -0.5
    arr = personality.as_array()
    assert len(arr) == len(personality.TRAITS)
    assert arr[personality.TRAITS.index("openness")] == pytest.approx(0.3)
    assert arr[personality.TRAITS.index("boldness")] == pytest.approx(-0.5)


def test_apply_update_moves_traits_by_learning_rate_scaled_delta(personality):
    delta = np.zeros(len(personality.TRAITS))
    delta[personality.TRAITS.index("openness")] = 1.0
    personality.apply_update(delta, lr=0.1)
    assert personality.traits["openness"] == pytest.approx(0.1)


def test_apply_update_clips_to_valid_range(personality):
    personality.traits["openness"] = 0.95
    delta = np.zeros(len(personality.TRAITS))
    delta[personality.TRAITS.index("openness")] = 1.0
    personality.apply_update(delta, lr=1.0)
    assert personality.traits["openness"] == pytest.approx(1.0)


def test_similarity_is_one_for_identical_personalities(personality_mod):
    traits = {"openness": 0.5, "boldness": -0.3, "conscientiousness": 0.8}
    a = personality_mod.Personality(traits=traits)
    b = personality_mod.Personality(traits=traits)
    assert a.similarity(b) == pytest.approx(1.0, abs=1e-5)


def test_similarity_of_two_default_zero_personalities_does_not_crash(personality_mod):
    """Cosine similarity divides by the norm of both vectors - two brand
    new agents (all traits at the 0.0 default) both have a zero-norm
    vector. The +1e-8 epsilon must prevent a ZeroDivisionError/NaN here,
    since this is the exact state of every freshly spawned agent."""
    a = personality_mod.Personality()
    b = personality_mod.Personality()
    result = a.similarity(b)
    assert not np.isnan(result)
    assert np.isfinite(result)


def test_similarity_is_lower_for_opposite_personalities(personality_mod):
    a = personality_mod.Personality(traits={"openness": 1.0, "boldness": 1.0})
    b = personality_mod.Personality(traits={"openness": -1.0, "boldness": -1.0})
    assert a.similarity(b) == pytest.approx(-1.0, abs=1e-5)


class TestBreedingHelpers:
    def test_can_breed_male_and_female(self, personality_mod):
        assert personality_mod.can_breed("male", "female") is True
        assert personality_mod.can_breed("female", "male") is True

    def test_cannot_breed_same_binary_gender(self, personality_mod):
        assert personality_mod.can_breed("male", "male") is False
        assert personality_mod.can_breed("female", "female") is False

    def test_dual_can_breed_with_anything(self, personality_mod):
        assert personality_mod.can_breed("dual", "male") is True
        assert personality_mod.can_breed("dual", "female") is True
        assert personality_mod.can_breed("dual", "dual") is True

    def test_assign_god_gender_is_always_dual(self, personality_mod):
        assert personality_mod.assign_god_gender() == "dual"

    def test_assign_npc_gender_returns_a_valid_binary_gender(self, personality_mod):
        for _ in range(20):  # it's random - sample enough to catch a bad value
            assert personality_mod.assign_npc_gender() in ("male", "female")

    def test_determine_child_gender_returns_a_valid_binary_gender(self, personality_mod):
        for _ in range(20):
            assert personality_mod.determine_child_gender("male", "female") in ("male", "female")