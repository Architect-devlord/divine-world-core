"""
Regression tests for ai_core/actuators.py's TCP wire format
(ForgeIPCClient.send_action).

This is a byte-level protocol shared with DWClientBot's TCPServer.java -
Python has no type system to catch a misalignment here, so these tests
parse the packed frame the same way TCPServer.java does (mirrored in
_java_style_unpack below) and assert the bytes actually round-trip.

Covers: the chat-mapping fix (TCP agents previously had no way to send
chat at all), and guards the historical Bug 1 (flags packed as 7 bytes
instead of 1) / Bug 2 (hotbar_slot and the ability section missing from
the TCP path) from silently coming back.
"""
import struct
import pytest


class FakeSocket:
    """Stands in for a real TCP socket - just records what was sent."""
    def __init__(self):
        self.sent = None

    def sendall(self, data):
        self.sent = data


def _pack(actuators_mod, action_dict, agent_id="test_agent"):
    """Builds a real frame via the actual (unmodified) send_action logic,
    with the network layer swapped for a recording fake."""
    client = actuators_mod.ForgeIPCClient(host="127.0.0.1", port=1)
    client._stop = True
    fake = FakeSocket()
    client.sock = fake
    client._connected = True
    ok = client.send_action(action_dict, agent_id=agent_id)
    assert ok, "send_action returned False - did it fail to reach the (fake) socket?"
    return fake.sent


def _java_style_unpack(frame: bytes) -> dict:
    """Mirrors TCPServer.java's exact read sequence field-for-field. If
    Python's packer and Java's reader ever drift apart, this is where
    that would show up - as leftover/missing bytes below."""
    off = 0
    (agent_len,) = struct.unpack_from("!I", frame, off); off += 4
    agent_id = frame[off:off + agent_len].decode("utf-8"); off += agent_len
    (tick,) = struct.unpack_from("!Q", frame, off); off += 8
    (mf, ms, yd, pd) = struct.unpack_from("!ffff", frame, off); off += 16
    (flags,) = struct.unpack_from("!B", frame, off); off += 1
    (hotbar,) = struct.unpack_from("!B", frame, off); off += 1

    (ability_len,) = struct.unpack_from("!H", frame, off); off += 2
    ability = None
    p1 = p2 = p3 = 0.0
    if ability_len > 0:
        ability = frame[off:off + ability_len].decode("utf-8"); off += ability_len
        (p1, p2, p3) = struct.unpack_from("!fff", frame, off); off += 12

    (chat_len,) = struct.unpack_from("!H", frame, off); off += 2
    chat_msg = None
    if chat_len > 0:
        chat_msg = frame[off:off + chat_len].decode("utf-8"); off += chat_len

    return {
        "agent_id": agent_id, "tick": tick,
        "move_forward": mf, "move_strafe": ms, "yaw_delta": yd, "pitch_delta": pd,
        "flags": flags, "hotbar": hotbar,
        "ability": ability, "ability_params": (p1, p2, p3),
        "chat_msg": chat_msg,
        "bytes_remaining": len(frame) - off,
    }


@pytest.fixture
def actuators():
    import importlib
    return importlib.import_module("ai_core.actuators")


def test_regular_tick_no_chat_no_ability(actuators):
    """The overwhelmingly common case - guards against Bug 1/Bug 2 (flags
    byte width, hotbar_slot/ability section) silently regressing."""
    frame = _pack(actuators, {"move_forward": 1.0, "jump": True})
    parsed = _java_style_unpack(frame)
    assert parsed["ability"] is None
    assert parsed["chat_msg"] is None
    assert parsed["bytes_remaining"] == 0
    assert abs(parsed["move_forward"] - 1.0) < 1e-5


def test_chat_only(actuators):
    frame = _pack(actuators, {"chat_msg": "hello there, over here!"})
    parsed = _java_style_unpack(frame)
    assert parsed["chat_msg"] == "hello there, over here!"
    assert parsed["ability"] is None
    assert parsed["bytes_remaining"] == 0


def test_chat_plus_ability_plus_movement_together(actuators):
    """Chat and a god ability are independent fields - an agent should be
    able to speak on the same tick it uses an ability."""
    frame = _pack(actuators, {
        "move_forward": 0.8, "yaw_delta": 12.5, "jump": True, "sprint": True,
        "god_ability": "summon_vexes",
        "god_params": {"param1": 1.0, "param2": 2.0, "param3": 3.0},
        "chat_msg": "casting a spell",
    })
    parsed = _java_style_unpack(frame)
    assert abs(parsed["move_forward"] - 0.8) < 1e-5
    assert parsed["ability"] == "summon_vexes"
    assert parsed["ability_params"] == (1.0, 2.0, 3.0)
    assert parsed["chat_msg"] == "casting a spell"
    assert parsed["bytes_remaining"] == 0


def test_unicode_chat_message_round_trips(actuators):
    msg = "héllo wörld 你好 🎮"
    frame = _pack(actuators, {"chat_msg": msg})
    parsed = _java_style_unpack(frame)
    assert parsed["chat_msg"] == msg
    assert parsed["bytes_remaining"] == 0


def test_empty_string_chat_msg_treated_as_no_chat(actuators):
    """action.get('chat_msg') or '' means an explicit empty string and a
    missing key behave identically - both should produce chat_len=0."""
    frame = _pack(actuators, {"chat_msg": ""})
    parsed = _java_style_unpack(frame)
    assert parsed["chat_msg"] is None
    assert parsed["bytes_remaining"] == 0


@pytest.mark.parametrize("agent_id", ["a", "agent_with_a_much_longer_name_than_usual", "名前"])
def test_various_agent_id_lengths_and_encodings(actuators, agent_id):
    frame = _pack(actuators, {"move_forward": 0.5}, agent_id=agent_id)
    parsed = _java_style_unpack(frame)
    assert parsed["agent_id"] == agent_id
    assert parsed["bytes_remaining"] == 0