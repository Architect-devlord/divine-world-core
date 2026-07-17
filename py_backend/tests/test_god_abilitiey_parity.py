"""
Cross-language regression test for the "ability implemented in Java but
unreachable from Python" bug class - this made Oracle's summon_vexes/
summon_fangs and Creaking's retract_tentacles/emerge unreachable until
fixed, because they were missing from both action_format_sync.py's
GOD_ABILITY_NAMES and god_controls.py's _ABILITY_DEFS.

Parses ServerGodAbilityExecutor.java's actual `case "ability_name" -> ...`
statements per god type (the real Java source, not a hand-maintained
mirror of it that could itself drift) and asserts every alias group is
reachable from both Python registries (at least one name per group must
appear in each - a case like `case "toggle_underground", "burrow" -> ...`
is one ability with two accepted names, not two abilities that both need
independent Python registration).

NOTE ON FRAGILITY: this is regex-based Java parsing, not a real parser -
it's deliberately simple (capture from one `execute<X>Ability` method's
start to the next) so it tolerates routine edits (a case added, a body
changed), but a large refactor of ServerGodAbilityExecutor.java's method
structure could require updating METHOD_TO_GOD_TYPE below. If this test
ever fails to find any abilities at all for a known god type, that's the
parser needing an update, not a real gap.
"""
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]  # .../divine-world-core
JAVA_FILE = (REPO_ROOT / "DivineWorld" / "src" / "main" / "java" / "com" /
             "divineworld" / "commands" / "ServerGodAbilityExecutor.java")

METHOD_TO_GOD_TYPE = {
    "executeWardenAbility": "warden",
    "executeWitherAbility": "wither",
    "executeDragonAbility": "ender_dragon",
    "executeElderGuardianAbility": "elder_guardian",
    "executeOracleAbility": "oracle",
    "executeCreakingAbility": "creaking",
}


def _parse_java_abilities() -> dict:
    """Returns {god_type: [alias_groups]} from the real Java source, where
    each alias_group is a frozenset of names that all trigger the SAME
    underlying ability (e.g. case "wither_skull", "blue_skull" -> ... means
    those two names are aliases for one ability, not two abilities that
    both need independent Python registration - the Java side accepts
    multiple names sometimes for backward-compat, but the policy should
    only ever see one canonical name per real ability)."""
    source = JAVA_FILE.read_text()
    method_starts = list(re.finditer(r"private static void (execute\w+Ability)\(", source))
    result = {}
    for i, m in enumerate(method_starts):
        method_name = m.group(1)
        if method_name not in METHOD_TO_GOD_TYPE:
            continue
        start = m.start()
        end = method_starts[i + 1].start() if i + 1 < len(method_starts) else len(source)
        body = source[start:end]
        alias_groups = []
        for case_group in re.findall(r'case\s+((?:"[^"]+"\s*,?\s*)+)->', body):
            names = frozenset(re.findall(r'"([^"]+)"', case_group))
            if names:
                alias_groups.append(names)
        result[METHOD_TO_GOD_TYPE[method_name]] = alias_groups
    return result


@pytest.fixture(scope="module")
def java_abilities():
    parsed = _parse_java_abilities()
    assert parsed, (
        f"Parsed zero abilities from {JAVA_FILE} - either the file moved, "
        f"or ServerGodAbilityExecutor.java's method structure changed "
        f"enough that this test's parser needs updating (see module "
        f"docstring). This is very unlikely to mean there are truly no "
        f"abilities left."
    )
    return parsed


@pytest.fixture
def action_format_sync():
    import importlib
    return importlib.import_module("utils.action_format_sync")


@pytest.fixture
def god_controls_ability_defs():
    import importlib
    god_controls = importlib.import_module("ai_core.god_controls")
    # _ABILITY_DEFS lives on whichever class defines it - find it directly
    # rather than assuming a specific class name.
    for name in dir(god_controls):
        obj = getattr(god_controls, name)
        if hasattr(obj, "_ABILITY_DEFS"):
            return obj._ABILITY_DEFS
    pytest.fail("Could not find _ABILITY_DEFS anywhere in god_controls.py")


@pytest.mark.parametrize("god_type", list(METHOD_TO_GOD_TYPE.values()))
def test_every_java_ability_reachable_from_action_format_sync(
    god_type, java_abilities, action_format_sync
):
    python_names = set(action_format_sync.GOD_ABILITY_NAMES.get(god_type, []))
    unreachable_groups = [
        group for group in java_abilities.get(god_type, [])
        if not (group & python_names)
    ]
    assert not unreachable_groups, (
        f"{god_type}: {unreachable_groups} implemented in "
        f"ServerGodAbilityExecutor.java, but none of each alias group's "
        f"names appear in action_format_sync.py's GOD_ABILITY_NAMES"
        f"['{god_type}'] - the policy can never select these abilities."
    )


@pytest.mark.parametrize("god_type", list(METHOD_TO_GOD_TYPE.values()))
def test_every_java_ability_reachable_from_god_controls(
    god_type, java_abilities, god_controls_ability_defs
):
    python_names = set(god_controls_ability_defs.get(god_type, {}).keys())
    unreachable_groups = [
        group for group in java_abilities.get(god_type, [])
        if not (group & python_names)
    ]
    assert not unreachable_groups, (
        f"{god_type}: {unreachable_groups} implemented in "
        f"ServerGodAbilityExecutor.java, but none of each alias group's "
        f"names appear in god_controls.py's _ABILITY_DEFS['{god_type}']."
    )


def test_parser_found_all_six_known_god_types(java_abilities):
    """Sanity check on the parser itself: confirms it found something for
    every god type this project currently has, not just a subset."""
    assert set(java_abilities.keys()) == set(METHOD_TO_GOD_TYPE.values())
    for god_type, groups in java_abilities.items():
        assert groups, f"Parsed zero abilities for '{god_type}' - parser likely needs updating"