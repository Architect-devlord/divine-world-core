"""
Regression test for the config.py / ai_core/config.py duality fix.

These two files are deliberately separate (not a stale duplicate) - see
the wiki's config-two-copies.md - but their AGENT_EXCLUDE_MODULES lists
had drifted out of sync with their own shared comment's stated intent
(both bare 'ai_core.agent_spawner' and qualified
'py_backend.ai_core.agent_spawner' forms should be excluded).
"""
import importlib
import pytest


@pytest.fixture
def outer_config():
    from py_backend.config import Config
    return Config


@pytest.fixture
def inner_config():
    import importlib.util
    from pathlib import Path
    config_path = Path(__file__).resolve().parents[1] / "ai_core" / "config.py"
    spec = importlib.util.spec_from_file_location("ai_core_config_standalone", config_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Config


@pytest.mark.parametrize("agent_spawner_form", [
    "ai_core.agent_spawner",
    "py_backend.ai_core.agent_spawner",
])
def test_both_agent_spawner_forms_excluded_in_outer_config(outer_config, agent_spawner_form):
    assert agent_spawner_form in outer_config.AGENT_EXCLUDE_MODULES


@pytest.mark.parametrize("agent_spawner_form", [
    "ai_core.agent_spawner",
    "py_backend.ai_core.agent_spawner",
])
def test_both_agent_spawner_forms_excluded_in_inner_config(inner_config, agent_spawner_form):
    assert agent_spawner_form in inner_config.AGENT_EXCLUDE_MODULES


def test_no_bogus_nonexistent_agent_spawner_path(outer_config):
    """The original bug: 'py_backend.agent_spawner' names a file that has
    never existed - agent_spawner.py has always lived inside ai_core/."""
    assert "py_backend.agent_spawner" not in outer_config.AGENT_EXCLUDE_MODULES