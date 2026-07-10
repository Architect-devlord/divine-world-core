# ------------------------------------------------------------------------------
# ai_core/actuators.py - Action execution with TCP + WebSocket fallback
#
# TCP frame format (ForgeIPCClient → Java TCPServer):
# ─────────────────────────────────────────────────
#  [4]  agent_id length   (uint32 big-endian)
#  [N]  agent_id          (UTF-8)
#  [8]  tick              (int64  big-endian, ms)
#  [4]  move_forward      (float32)
#  [4]  move_strafe       (float32)
#  [4]  yaw_delta         (float32)
#  [4]  pitch_delta       (float32)
#  [1]  action_flags      (uint8)  bit7=jump bit6=sneak bit5=attack bit4=use
#                                   bit3=drop bit2=open_inv bit1=swap_hand bit0=sprint
#  [1]  hotbar_slot       (uint8, 0xFF = no change)
#  [2]  god_ability len   (uint16 big-endian, 0 = none)
#  [M]  god_ability       (UTF-8, only if len > 0)
#  [4]  param1            (float32, only if len > 0)
#  [4]  param2            (float32, only if len > 0)
#  [4]  param3            (float32, only if len > 0)
#
# FIXES:
#   Bug 1 - ForgeIPCClient.send_action() was packing `!{N}sQffffB` (1 flags byte)
#            but TCPServer.java was reading 7 individual bytes for the booleans,
#            causing complete frame misalignment after the first read.
#            Fix: document the 1-byte contract here; TCPServer.java is fixed to
#            also read exactly 1 byte.
#
#   Bug 2 - TCP path silently dropped hotbar_slot, sprint, and god_ability.
#            These were only present in the WebSocket _build_frame() path.
#            Fix: ForgeIPCClient.send_action() now sends all three fields,
#            making TCP and WebSocket frames byte-equivalent in content.
# ------------------------------------------------------------------------------

import socket
import threading
import time
import json
import struct
import logging
from typing import Any, Dict, Optional, List, Callable
import numpy as np
import asyncio
import websockets

log = logging.getLogger("ai_core.actuators")
log.setLevel(logging.INFO)

MAGIC        = 0x44574149  # 'DWAI'
FRAME_ACTION = 0x02


# ==============================================================================
# Base interface
# ==============================================================================

# ==============================================================================
# Inventory action helpers
# ==============================================================================

def build_inv_action(slot: int, button: int = 0, click_type: int = 0) -> str:
    """
    Build an inventory action string for the TCP special-action field.

    Args:
        slot:       0-based slot index in the currently open container.
                    Player InventoryMenu layout (when no external container open):
                      0       = crafting result
                      1-4     = crafting grid (2x2)
                      5-8     = armour (head=5, chest=6, legs=7, feet=8)
                      9-35    = main inventory (row-major, top row first)
                      36-44   = hotbar (36=slot0 … 44=slot8)
                      45      = offhand
                    For external containers (CraftingTable, Furnace, StoneCutter…):
                      slots are numbered from 0 in the order they appear in that
                      container's AbstractContainerMenu, usually:
                        0..(N-1)  = container-specific slots
                        N..N+26   = player main inventory
                        N+27..N+35= hotbar
        button:     0 = left click / SWAP target hotbar slot (for SWAP type)
                    1 = right click
                    2 = middle click
        click_type: ClickType ordinal (matches net.minecraft.world.inventory.ClickType):
                    0 = PICKUP      — normal left/right click
                    1 = QUICK_MOVE  — shift-click (moves item automatically)
                    2 = SWAP        — swaps slot with hotbar[button]
                    3 = CLONE       — creative middle-click copy
                    4 = THROW       — drop with Q
                    5 = SPREAD      — drag-spread

    Returns:
        String in the format "inv:SLOT,BUTTON,CLICK_TYPE"

    Common usage examples:
        # Move main-inventory slot 9 to hotbar slot 0 (SWAP):
        build_inv_action(slot=9, button=0, click_type=2)  → "inv:9,0,2"

        # Shift-click craft result into inventory (QUICK_MOVE):
        build_inv_action(slot=0, button=0, click_type=1)  → "inv:0,0,1"

        # Pick up item from hotbar slot 3 onto cursor (PICKUP left-click):
        build_inv_action(slot=39, button=0, click_type=0) → "inv:39,0,0"

        # Right-click to split a stack (PICKUP right-click):
        build_inv_action(slot=10, button=1, click_type=0) → "inv:10,1,0"
    """
    return f"inv:{slot},{button},{click_type}"


def build_screen_action(command: str) -> str:
    """
    Build a screen control action string.

    Args:
        command: "close" — close any open GUI screen
                 "inv"   — open player inventory

    Returns:
        String in the format "screen:COMMAND"
    """
    return f"screen:{command}"


# ClickType ordinal constants (mirrors net.minecraft.world.inventory.ClickType)
INV_CLICK_PICKUP     = 0   # normal left / right click
INV_CLICK_QUICK_MOVE = 1   # shift-click → automatic move
INV_CLICK_SWAP       = 2   # swap slot ↔ hotbar[button]
INV_CLICK_CLONE      = 3   # creative middle-click copy
INV_CLICK_THROW      = 4   # Q / drop
INV_CLICK_SPREAD     = 5   # drag-spread


class BaseActuatorBackend:
    def apply_action(self, action: Dict[str, Any]) -> bool:
        raise NotImplementedError

    def get_observation(self) -> Optional[Dict[str, Any]]:
        return None

    def close(self):
        pass


# ==============================================================================
# Shared infrastructure
# ==============================================================================

class _WebSocketEventLoop:
    _instance: Optional['_WebSocketEventLoop'] = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> '_WebSocketEventLoop':
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self.loop.run_forever, daemon=True, name="ws-event-loop"
        )
        self._thread.start()

    def submit(self, coro) -> asyncio.Future:
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def submit_and_wait(self, coro, timeout: float = 5.0):
        return self.submit(coro).result(timeout=timeout)


class _TCPConnectionPool:
    _instances: Dict[tuple, '_TCPConnectionPool'] = {}
    _class_lock = threading.Lock()

    @classmethod
    def get(cls, host: str, port: int) -> '_TCPConnectionPool':
        key = (host, port)
        with cls._class_lock:
            if key not in cls._instances:
                cls._instances[key] = cls(host, port)
            return cls._instances[key]

    def __init__(self, host: str, port: int):
        self._client = ForgeIPCClient(host, port)

    def send(self, action: Dict[str, Any], agent_id: str) -> bool:
        return self._client.send_action(action, agent_id)

    def is_connected(self) -> bool:
        return self._client.is_connected()


# ==============================================================================
# Minecraft backend
# ==============================================================================

class MinecraftClient(BaseActuatorBackend):
    """
    Action channel from Python to the Minecraft Java client.

    Architecture
    ------------
    Actions travel ONLY via TCP (ForgeIPCClient → Java TCPServer).
    The WebSocket action path that previously existed here was a self-loop:
    MinecraftWebSocketClient was connecting to Python's own FastAPI server
    (ws_port == _backend_port) instead of to Java.  It is removed (B-05).

    The correct WebSocket action path — Python → Java — is handled by
    AgentConnectionHandler.send_action() inside handle_agent_websocket(),
    which sends back over the SAME WebSocket connection the Java mod opened.
    That path is triggered by perception frames arriving from Java and does
    not require an outbound client here.

    connect_websocket() is kept as a no-op for call-site compatibility.
    """

    def __init__(self, agent_id='agent', tcp_host='127.0.0.1', tcp_port=8765,
                 ws_host='127.0.0.1', ws_port=11400, prefer_tcp=True):
        self.agent_id   = agent_id
        self.prefer_tcp = prefer_tcp
        self._tcp_pool  = _TCPConnectionPool.get(tcp_host, tcp_port)
        # ws_host / ws_port accepted for API compatibility but NOT used —
        # see class docstring above.

    def connect_websocket(self):
        """No-op: outbound WS to Java is not used (see class docstring)."""
        pass

    async def wait_for_connection(self, timeout=60.0, poll_interval=1.0):
        import asyncio as _asyncio, time as _time
        deadline = _time.monotonic() + timeout
        last_log = _time.monotonic()
        elapsed  = 0.0
        log.info("[%s] Waiting for Minecraft connection (timeout=%ss)...", self.agent_id, timeout)
        while _time.monotonic() < deadline:
            if self._tcp_pool and self._tcp_pool.is_connected():
                log.info("[%s] ✅ Minecraft connected via TCP (%.1fs)", self.agent_id, elapsed)
                return True
            await _asyncio.sleep(poll_interval)
            elapsed = _time.monotonic() - (deadline - timeout)
            if _time.monotonic() - last_log >= 10.0:
                log.info("[%s] Still waiting... (%.0fs elapsed)", self.agent_id, elapsed)
                last_log = _time.monotonic()
        log.warning("[%s] ⚠️  Connection timed out after %.0fs.", self.agent_id, timeout)
        return False

    def apply_action(self, action: Dict[str, Any]) -> bool:
        # TCP is the sole outbound action channel.  WS actions from Python to
        # Java travel through AgentConnectionHandler.send_action() inside
        # handle_agent_websocket() — not from here (see class docstring).
        if self._tcp_pool and self._tcp_pool.is_connected():
            if self._tcp_pool.send(action, self.agent_id):
                return True
            log.debug("[%s] TCP send failed", self.agent_id)
        return False

    def get_observation(self):
        return None

    def get_active_mode(self):
        if self._tcp_pool and self._tcp_pool.is_connected():
            return 'tcp'
        return None

    def close(self):
        pass  # TCP pool is a singleton — don't close here


class ForgeIPCClient:
    """Raw TCP client — one instance per server endpoint, managed by pool."""

    def __init__(self, host='127.0.0.1', port=8765, reconnect=True, timeout=3.0):
        self.host       = host
        self.port       = port
        self.sock: Optional[socket.socket] = None
        self.lock       = threading.Lock()
        self.reconnect  = reconnect
        self.timeout    = timeout
        self._stop      = False
        self._connected = False
        threading.Thread(target=self._maintain, daemon=True,
                         name=f"tcp-maintain-{port}").start()

    def _maintain(self):
        while not self._stop:
            if self.sock is None:
                try:
                    s = socket.create_connection((self.host, self.port), timeout=self.timeout)
                    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    with self.lock:
                        self.sock       = s
                        self._connected = True
                    log.info("TCP connected to %s:%d", self.host, self.port)
                except Exception:
                    self._connected = False
                    time.sleep(1.0)
            else:
                time.sleep(1.0)

    def is_connected(self) -> bool:
        return self._connected and self.sock is not None

    def send_action(self, action: Dict[str, Any], agent_id: str = "agent") -> bool:
        """
        Pack and send one action frame to Java TCPServer.

        FIX Bug 1: Old code packed a single flags byte but TCPServer read 7 bytes,
        causing misalignment. Now both sides agree on 1 packed byte.

        FIX Bug 2: hotbar_slot, sprint (in flags bit 0), and god_ability section
        were all missing from the TCP path. All are now included, making this
        frame byte-compatible with MinecraftWebSocketClient._build_frame().
        """
        tick = int(time.time() * 1000)

        # Single packed flags byte — must match ActionExecutor FLAG_* bit layout
        flags = 0
        if action.get('jump',      False): flags |= 0b10000000
        if action.get('sneak',     False): flags |= 0b01000000
        if action.get('attack',    False): flags |= 0b00100000
        if action.get('use',       False): flags |= 0b00010000
        if action.get('drop',      False): flags |= 0b00001000
        if action.get('open_inv',  False): flags |= 0b00000100
        if action.get('swap_hand', False): flags |= 0b00000010
        if action.get('sprint',    False): flags |= 0b00000001  # FIX Bug 2

        hotbar = action.get('hotbar_slot')
        hotbar_byte = 0xFF if hotbar is None else int(max(0, min(8, hotbar)))  # FIX Bug 2

        # Special action section (FIX Bug 2 + inventory actions):
        # Priority: inv_action > screen_action > god_ability > (none)
        #
        # inv_action — inventory slot click for ALL agents:
        #   Format built by build_inv_action():
        #     "inv:SLOT,BUTTON,CLICK_TYPE"  e.g. "inv:9,0,2" = SWAP slot 9 → hotbar 0
        #   ClickType ordinals: 0=PICKUP 1=QUICK_MOVE 2=SWAP 3=CLONE 4=THROW 5=SPREAD
        #
        # screen_action — GUI screen control:
        #   "screen:close"  close any open screen
        #   "screen:inv"    open player inventory
        #
        # god_ability — god-agent abilities (existing behaviour unchanged)
        inv_action    = action.get('inv_action')    # e.g. "inv:9,0,2"
        screen_action = action.get('screen_action') # e.g. "screen:close"
        god_ability   = action.get('god_ability')

        special = inv_action or screen_action or god_ability
        if special:
            ab     = special.encode('utf-8')
            params = action.get('god_params') or {}
            ability_section = (
                struct.pack('!H', len(ab)) + ab +
                struct.pack('!fff',
                    params.get('param1', 0.0),
                    params.get('param2', 0.0),
                    params.get('param3', 0.0),
                )
            )
        else:
            ability_section = struct.pack('!H', 0)

        agent_bytes = agent_id.encode('utf-8')
        try:
            frame = (
                struct.pack('!I', len(agent_bytes)) +
                agent_bytes +
                struct.pack('!Q', tick) +
                struct.pack('!ffff',
                    float(action.get('move_forward', 0.0)),
                    float(action.get('move_strafe',  0.0)),
                    float(action.get('yaw_delta',    0.0)),
                    float(action.get('pitch_delta',  0.0)),
                ) +
                struct.pack('!B', flags) +        # FIX Bug 1: 1 byte not 7
                struct.pack('!B', hotbar_byte) +  # FIX Bug 2
                ability_section                   # FIX Bug 2
            )
        except Exception as e:
            log.error("Failed to pack TCP payload: %s", e)
            return False

        with self.lock:
            if self.sock:
                try:
                    self.sock.sendall(frame)
                    return True
                except Exception as e:
                    log.debug("TCP send error: %s", e)
                    try:
                        self.sock.close()
                    except Exception:
                        pass
                    self.sock       = None
                    self._connected = False
        return False

    def close(self):
        self._stop = True
        with self.lock:
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
                self.sock       = None
                self._connected = False


class MinecraftWebSocketClient:
    def __init__(self, agent_id, host='127.0.0.1', port=11400):
        self.agent_id      = agent_id
        self.uri           = f"ws://{host}:{port}"
        self.ws            = None
        self._connected    = False
        self._reconnecting = False

    async def connect(self):
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            self.ws = await websockets.connect(self.uri)
            await self.ws.send(json.dumps({
                "agent_id": self.agent_id, "protocol": "binary", "version": "2.1.0",
            }))
            self._connected = True
            log.info("[%s] ✅ WebSocket connected", self.agent_id)
        except Exception as e:
            log.error("[%s] WebSocket connection failed: %s", self.agent_id, e)
            self._connected = False
        finally:
            self._reconnecting = False

    def is_connected(self):
        return self._connected and self.ws is not None and self.ws.open

    def is_reconnecting(self):
        return self._reconnecting

    async def send_action(self, action: Dict[str, Any]):
        if not self.is_connected():
            if not self._reconnecting:
                asyncio.ensure_future(self.connect())
            return
        try:
            await self.ws.send(self._build_frame(action))
        except Exception as e:
            log.error("[%s] WebSocket send error: %s", self.agent_id, e)
            self._connected = False

    async def send_chat(self, message: str):
        if not self.is_connected():
            if not self._reconnecting:
                asyncio.ensure_future(self.connect())
            return
        try:
            agent_bytes = self.agent_id.encode('utf-8')
            msg_bytes   = message.encode('utf-8')
            frame = struct.pack(
                f'!II I{len(agent_bytes)}s d I{len(msg_bytes)}s',
                MAGIC, 0x03, len(agent_bytes), agent_bytes,
                time.time(), len(msg_bytes), msg_bytes,
            )
            await self.ws.send(frame)
        except Exception as e:
            log.error("[%s] WebSocket chat send error: %s", self.agent_id, e)
            self._connected = False

    def _build_frame(self, action: Dict[str, Any]) -> bytes:
        agent_bytes  = self.agent_id.encode('utf-8')
        move_forward = float(np.clip(action.get('move_forward', 0.0), -1.0,   1.0))
        move_strafe  = float(np.clip(action.get('move_strafe',  0.0), -1.0,   1.0))
        yaw_delta    = float(np.clip(action.get('yaw_delta',    0.0) * 2.0, -180.0, 180.0))
        pitch_delta  = float(np.clip(action.get('pitch_delta',  0.0) * 1.2,  -90.0,  90.0))

        flags = 0
        if action.get('jump',      False): flags |= 0b10000000
        if action.get('sneak',     False): flags |= 0b01000000
        if action.get('attack',    False): flags |= 0b00100000
        if action.get('use',       False): flags |= 0b00010000
        if action.get('drop',      False): flags |= 0b00001000
        if action.get('open_inv',  False): flags |= 0b00000100
        if action.get('swap_hand', False): flags |= 0b00000010
        if action.get('sprint',    False): flags |= 0b00000001

        hotbar      = action.get('hotbar_slot')
        hotbar_byte = 0xFF if hotbar is None else int(hotbar)

        god_ability = action.get('god_ability')
        if god_ability:
            ab     = god_ability.encode('utf-8')
            params = action.get('god_params') or {}
            ability_section = struct.pack('!H', len(ab)) + ab + struct.pack(
                '!fff', params.get('param1', 0.0), params.get('param2', 0.0),
                params.get('param3', 0.0))
        else:
            ability_section = struct.pack('!H', 0)

        return struct.pack(
            f'!II I{len(agent_bytes)}s d ffff BB',
            MAGIC, FRAME_ACTION,
            len(agent_bytes), agent_bytes,
            time.time(),
            move_forward, move_strafe, yaw_delta, pitch_delta,
            flags, hotbar_byte,
        ) + ability_section

    async def close(self):
        if self.ws:
            await self.ws.close()
            self._connected = False


# ==============================================================================
# Isaac Sim — soft imports with 5.x (isaacsim) first, omni.* fallback for 4.x
# ==============================================================================

# ArticulationAction availability
ArticulationAction = None
_ISAAC_AVAILABLE = False
try:
    from isaacsim.core.utils.types import ArticulationAction
    _ISAAC_AVAILABLE = True
except ImportError:
    try:
        from omni.isaac.core.utils.types import ArticulationAction  # type: ignore
        _ISAAC_AVAILABLE = True
    except Exception:
        ArticulationAction = None
        _ISAAC_AVAILABLE = False

# DifferentialController (wheeled robots) availability
DifferentialController = None
_DIFF_CTRL_AVAILABLE = False
try:
    from isaacsim.robot.wheeled_robots.controllers.differential_controller import DifferentialController
    _DIFF_CTRL_AVAILABLE = True
except ImportError:
    try:
        from omni.isaac.robot.wheeled_robots.controllers.differential_controller import DifferentialController  # type: ignore
        _DIFF_CTRL_AVAILABLE = True
    except Exception:
        DifferentialController = None
        _DIFF_CTRL_AVAILABLE = False

# Rotation utilities
rot_utils = None
_ROT_UTILS_AVAILABLE = False
try:
    import isaacsim.core.utils.numpy.rotations as rot_utils
    _ROT_UTILS_AVAILABLE = True
except ImportError:
    try:
        import omni.isaac.core.utils.numpy.rotations as rot_utils  # type: ignore
        _ROT_UTILS_AVAILABLE = True
    except Exception:
        rot_utils = None
        _ROT_UTILS_AVAILABLE = False

_MODE_VELOCITY = "velocity"
_MODE_POSITION = "position"
_MODE_EFFORT   = "effort"

def _infer_drive_mode(kp, kd):
    if kp < 1e-6 and kd < 1e-6: return _MODE_EFFORT
    if kp < 1e-6:                return _MODE_VELOCITY
    return _MODE_POSITION

_ACTION_PATTERNS = [
    ("move_forward", 1, "linear",   ["left_wheel","wheel_left","front_wheel","drive","base_x","linear_x"]),
    ("move_strafe",  2, "linear",   ["strafe","lateral","base_y","linear_y","slide"]),
    ("yaw_delta",    3, "angular",  ["yaw","base_rot","rotate","turn","steer","angular_z","right_wheel","wheel_right"]),
    ("pitch_delta",  4, "angular",  ["pitch","tilt","elevation","angular_y"]),
    ("arm_position", 5, "position", ["joint","arm","finger","elbow","wrist","panda"]),
]

def _match_dofs(dof_names):
    claimed, mapping = set(), {}
    for action_key, priority, kind, patterns in sorted(_ACTION_PATTERNS, key=lambda x: x[1]):
        matched = [i for i, n in enumerate(dof_names)
                   if i not in claimed and any(p in n.lower() for p in patterns)]
        if matched:
            mapping[action_key] = matched
            for i in matched: claimed.add(i)
    return mapping

class _DOFProfile:
    __slots__ = ("name","index","drive_mode","lower","upper","is_revolute")
    def __init__(self, name, index, drive_mode, lower, upper, is_revolute):
        self.name=name; self.index=index; self.drive_mode=drive_mode
        self.lower=lower; self.upper=upper; self.is_revolute=is_revolute

class ActuatorAdapterIsaacSim(BaseActuatorBackend):
    def __init__(self, articulation=None, camera=None, send_joint_positions=None,
                 set_camera_ori=None, joint_overrides=None, linear_scale=1.0, angular_scale=1.0):
        if not _ISAAC_AVAILABLE: log.warning("isaacsim not found — using legacy callbacks only.")
        self._articulation=articulation; self._camera=camera
        self._linear_scale=linear_scale; self._angular_scale=angular_scale
        self._send_joint_positions=send_joint_positions; self._set_camera_ori=set_camera_ori
        self._joint_overrides=joint_overrides or {}
        self._profiles=[]; self._mapping={}; self._drive_modes={}
        self._diff_ctrl=None; self._is_wheeled=False; self._inspected=False
        self._cam_yaw=0.0; self._cam_pitch=0.0

    def inspect_robot(self):
        if self._articulation is None or not _ISAAC_AVAILABLE: return {}
        try: return self._do_inspect()
        except Exception as e: return {"error": str(e)}

    def _do_inspect(self):
        art = self._articulation
        dof_names = list(art.dof_names); n = len(dof_names)
        # Isaac Sim 5.0: get_gains() replaces get_dof_gains()
        try:
            kps, kds = art.get_gains()
        except AttributeError:
            try:
                kps, kds = art.get_dof_gains()
            except AttributeError:
                kps = [1000.0] * n; kds = [100.0] * n
        drive_modes = [_infer_drive_mode(float(kps[i]), float(kds[i])) for i in range(n)]
        # Isaac Sim 5.0: get_dof_position_limits() replaces get_joint_limits()
        try:
            limits = art.get_dof_position_limits()
            lower_limits = limits[:, 0]; upper_limits = limits[:, 1]
        except AttributeError:
            try:
                lower_limits, upper_limits = art.get_joint_limits()
            except AttributeError:
                lower_limits = [-1e4] * n; upper_limits = [1e4] * n
        # Isaac Sim 5.0: dof_types may not exist; default to revolute
        try:
            dof_types = art.get_dof_types() or []
        except AttributeError:
            dof_types = []
        self._profiles = [
            _DOFProfile(dof_names[i], i, drive_modes[i], float(lower_limits[i]),
                        float(upper_limits[i]), "rot" in str(dof_types[i]).lower() if dof_types else True)
            for i in range(n)
        ]
        self._drive_modes = {p.index: p.drive_mode for p in self._profiles}
        self._mapping = _match_dofs(dof_names)
        self._mapping.update(self._joint_overrides)
        fwd_idxs = self._mapping.get("move_forward", [])
        if len(fwd_idxs) == 2 and _DIFF_CTRL_AVAILABLE:
            names = [dof_names[i].lower() for i in fwd_idxs]
            if any("left" in nm or "right" in nm for nm in names):
                self._is_wheeled = True
                self._diff_ctrl = DifferentialController(name=f"diff_ctrl_{id(art)}",
                                                          wheel_radius=0.05, wheel_base=0.15)
        self._inspected = True
        return {"n_dofs": n, "dof_names": dof_names,
                "drive_modes": {dof_names[i]: drive_modes[i] for i in range(n)},
                "mapping": {k: [dof_names[i] for i in v] for k,v in self._mapping.items()},
                "is_wheeled": self._is_wheeled}

    def apply_action(self, action):
        mf=float(np.clip(action.get("move_forward",0.),-1.,1.))
        ms=float(np.clip(action.get("move_strafe", 0.),-1.,1.))
        yd=float(action.get("yaw_delta",0.)); pd=float(action.get("pitch_delta",0.))
        self._apply_robot(mf,ms,yd,pd); self._apply_camera(yd,pd); return True

    def get_observation(self):
        if self._articulation is None or not _ISAAC_AVAILABLE: return None
        return {"joint_positions": self._articulation.get_joint_positions().tolist(),
                "joint_velocities": self._articulation.get_joint_velocities().tolist()}

    @property
    def diff_ctrl(self): return self._diff_ctrl
    @property
    def mapping(self): return dict(self._mapping)
    @property
    def profiles(self): return list(self._profiles)

    def _apply_robot(self, mf, ms, yd, pd):
        if self._articulation is None:
            if self._send_joint_positions:
                self._send_joint_positions([mf*self._linear_scale, ms*self._linear_scale,
                    float(np.deg2rad(yd))*self._angular_scale, float(np.deg2rad(pd))*self._angular_scale])
            return
        if not _ISAAC_AVAILABLE or not self._inspected: return
        if self._is_wheeled and self._diff_ctrl:
            # Isaac Sim 5.0: apply_wheel_actions() removed from generic Articulation.
            # Use apply_action(ArticulationAction(joint_velocities=...)) instead.
            wheel_action = self._diff_ctrl.forward(
                command=np.array([mf * self._linear_scale,
                                  float(np.deg2rad(yd)) * self._angular_scale])
            )
            if _ISAAC_AVAILABLE and ArticulationAction is not None:
                self._articulation.apply_action(wheel_action)
            return
        av = {"move_forward": mf*self._linear_scale, "move_strafe": ms*self._linear_scale,
              "yaw_delta": float(np.deg2rad(yd))*self._angular_scale,
              "pitch_delta": float(np.deg2rad(pd))*self._angular_scale,
              "arm_position": mf*self._linear_scale}
        vel_cmds, pos_cmds, eff_cmds = {}, {}, {}
        for key, val in av.items():
            for idx in self._mapping.get(key, []):
                p = self._profiles[idx]
                c = float(np.clip(val, p.lower, p.upper)) if p.lower < p.upper else float(val)
                mode = self._drive_modes.get(idx, _MODE_VELOCITY)
                if mode == _MODE_POSITION: pos_cmds[idx] = c
                elif mode == _MODE_EFFORT: eff_cmds[idx] = c
                else: vel_cmds[idx] = c
        for cmds, field in [(vel_cmds,"joint_velocities"),(pos_cmds,"joint_positions"),(eff_cmds,"joint_efforts")]:
            if cmds:
                self._articulation.apply_action(ArticulationAction(**{
                    field: np.array(list(cmds.values()), dtype=np.float32),
                    "joint_indices": np.array(list(cmds.keys()), dtype=np.int32)}))

    def _apply_camera(self, yd, pd):
        self._cam_yaw  += float(np.deg2rad(yd))
        self._cam_pitch = float(np.clip(self._cam_pitch + float(np.deg2rad(pd)), -np.pi/2, np.pi/2))
        if self._camera is not None and _ROT_UTILS_AVAILABLE:
            quat = rot_utils.euler_angles_to_quats(
                np.array([[0., self._cam_pitch, self._cam_yaw]]), degrees=False)[0]
            self._camera.set_local_pose(orientation=quat)
        elif self._set_camera_ori:
            self._set_camera_ori(float(np.rad2deg(self._cam_yaw)), float(np.rad2deg(self._cam_pitch)))


class ActuatorManager:
    _BACKENDS = {"minecraft": MinecraftClient, "isaac": ActuatorAdapterIsaacSim}

    def __init__(self, backend: str, **kwargs):
        cls = self._BACKENDS.get(backend)
        if cls is None:
            raise ValueError(f"Unknown backend '{backend}'. Valid: {list(self._BACKENDS)}")
        self._backend_name = backend
        self.backend: BaseActuatorBackend = cls(**kwargs)
        log.info("ActuatorManager: backend='%s'", backend)

    def apply_action(self, action): return self.backend.apply_action(action)
    def get_observation(self): return self.backend.get_observation()
    def inspect_robot(self):
        if hasattr(self.backend, 'inspect_robot'): return self.backend.inspect_robot()
        return {}
    def close(self): self.backend.close()