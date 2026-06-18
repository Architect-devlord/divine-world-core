# py_backend/main.py
"""
Divine World Management Server
================================
Central control for all Divine World agents.

Launch modes
------------
  python main.py            — asks: GUI or CLI?
  python main.py --cli      — skip prompt, start CLI server
  python main.py --gui      — skip prompt, open GUI
  python main.py --port N   — override port (CLI mode)

GUI features (in addition to everything available in CLI)
---------------------------------------------------------
  • Full live log stream (scrolling, colour-coded by level)
  • Agent list with real-time status
  • Personality editor (trait sliders, −1 → +1)
  • Memory viewer / editor (add, remove, edit individual events)
  • Drag-and-drop memory transfer between agents
  • Agent type toggle (NPC ↔ God) with god-type selector
  • Gender picker (male / female / dual)
  • Per-agent host:port override
  • One-click spawn NPC / spawn God / Genesis / Divine Reset
  • Package, stop, restart controls per agent
"""

# ── stdlib ────────────────────────────────────────────────────────────────────
import asyncio
import json
import logging
import threading
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── third-party ───────────────────────────────────────────────────────────────
import psutil
import uvicorn
import argparse
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

# ── project ───────────────────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from py_backend.config import Config
from ai_core.agent_spawner import AgentSpawner
from ai_core.personality import assign_npc_gender, assign_god_gender
from py_backend.auto_packager import EnhancedAgentSpawner
from py_backend.auto_connect_system import integrate_with_backend
from py_backend.utils.mc_uuid import get_minecraft_uuid, AgentNameManager
from py_backend.utils.agents_json_manager import get_manager as get_agents_manager
from py_backend.minecraft_launcher import UltimMCLauncher, MultiAgentLauncher

# ── logging ───────────────────────────────────────────────────────────────────
try:
    from ai_core.logger_setup import initialize_logging
    initialize_logging()
except ImportError:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

log = logging.getLogger("agent_manager")

# ── config ────────────────────────────────────────────────────────────────────
Config.ensure_dirs()
if not Config.validate():
    log.warning("Config validation failed — some features may not work")

name_manager = AgentNameManager()



def _extract_spawn_pos(args: list) -> dict:
    """Pull --spawn-x/y/z values out of an additional_args list."""
    pos = {}
    try:
        for flag, key in [("--spawn-x", "x"), ("--spawn-y", "y"), ("--spawn-z", "z")]:
            if flag in args:
                pos[key] = float(args[args.index(flag) + 1])
    except (ValueError, IndexError):
        pass
    return pos if len(pos) == 3 else {}

def sanitize_agent_id(name: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", name.lower().replace(" ", "_"))


# =============================================================================
# In-memory log handler — feeds the GUI log panel via WebSocket
# =============================================================================

class _GuiLogHandler(logging.Handler):
    """
    Captures log records and forwards them to all connected GUI WebSockets.

    emit() is called from any thread (logging is thread-safe by default).
    We buffer the entry and schedule delivery on the running asyncio event
    loop using the loop stored at subscription time — no deprecated
    get_event_loop() call, no risk of targeting a closed or wrong loop.
    """

    MAX_BUFFER = 500

    def __init__(self):
        super().__init__()
        self._buffer:  List[Dict]                    = []
        self._sockets: List[tuple]                   = []  # (WebSocket, asyncio.AbstractEventLoop)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord):
        entry = {
            "ts":      record.created,
            "level":   record.levelname,
            "name":    record.name,
            "message": self.format(record),
        }
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self.MAX_BUFFER:
                self._buffer.pop(0)
            targets = list(self._sockets)

        for ws, loop in targets:
            try:
                # Schedule on the loop that owns the WebSocket connection.
                # call_soon_threadsafe is safe to call from any thread and
                # does not require the loop to be the current thread's loop.
                loop.call_soon_threadsafe(
                    loop.create_task,
                    ws.send_json({"type": "log", **entry}),
                )
            except Exception:
                pass

    def subscribe(self, ws: WebSocket, loop: asyncio.AbstractEventLoop):
        with self._lock:
            self._sockets.append((ws, loop))

    def unsubscribe(self, ws: WebSocket):
        with self._lock:
            self._sockets = [(w, l) for w, l in self._sockets if w is not ws]

    def get_buffer(self) -> List[Dict]:
        with self._lock:
            return list(self._buffer)


_gui_log_handler = _GuiLogHandler()
_gui_log_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
)
logging.getLogger().addHandler(_gui_log_handler)



# =============================================================================
# Minecraft server integration
# =============================================================================

# =============================================================================
# FIX 1: MinecraftServerIntegration collapsed — was vestigial after usercache
# removal. server_folder is now read directly from Config.SERVER_FOLDER.
# FIX 2: Gender detection replaced — was a hardcoded 10-name set that would
# misclassify any female agent not in the list. Now uses agents.json as the
# single source of truth: if the name is already registered its gender is
# preserved; for new names the caller must supply gender explicitly.
# =============================================================================

def list_registered_agents() -> List[Dict[str, Any]]:
    """Return all agents registered in agents.json."""
    try:
        mgr = get_agents_manager()
        result: List[Dict[str, Any]] = []
        for name in mgr.get_all_male_npcs():
            result.append({"agent_id": name, "type": "npc_male"})
        for name in mgr.get_all_female_npcs():
            result.append({"agent_id": name, "type": "npc_female"})
        for name in mgr.get_all_gods():
            result.append({"agent_id": name, "type": "god"})
        return result
    except Exception as e:
        log.warning(f"list_registered_agents error: {e}")
        return []


def register_agent(agent_id: str, agent_uuid: str,
                   agent_type: str = "npc",
                   custom_name: Optional[str] = None,
                   gender: Optional[str] = None) -> None:
    """
    Register agent in agents.json only.
    usercache.json / usernamecache.json are managed by the MC server.

    FIX 2: gender parameter is now explicit (passed from the spawn request).
    Fallback order when gender is None:
      1. agents.json lookup — if the name is already registered, its existing
         gender is preserved automatically (no action needed).
      2. Default to "male" with a warning so callers know to pass gender.
    """
    display = (custom_name if custom_name and custom_name not in ("", "Unnamed")
               else agent_id)
    mgr = get_agents_manager()

    if agent_type.startswith("god_"):
        god_type = agent_type[len("god_"):]
        mgr.register_god(display, god_type)
        log.info(f"Registered god agent: {display} ({god_type})")
        return

    # NPC path — resolve gender
    resolved_gender = gender  # caller-supplied (most reliable)
    if not resolved_gender:
        # Check if already in agents.json — preserve existing registration
        if display in mgr.get_all_male_npcs():
            resolved_gender = "male"
        elif display in mgr.get_all_female_npcs():
            resolved_gender = "female"
        else:
            resolved_gender = "male"
            log.warning(
                f"register_agent: no gender supplied for new NPC '{display}' "
                f"— defaulting to 'male'. Pass gender= from the spawn request."
            )

    mgr.register_npc(display, resolved_gender)
    log.info(f"Registered NPC: {display} ({resolved_gender})")


# Thin compatibility shim so existing code that imports server_integration
# still works without changes to call sites.
class _ServerIntegrationShim:
    """Backward-compat wrapper — delegates to module-level functions."""
    @property
    def server_folder(self) -> Path:
        return Config.SERVER_FOLDER if Config.SERVER_FOLDER.exists() else None

    def list_registered_agents(self): return list_registered_agents()

    def register_agent(self, *args, **kwargs): return register_agent(*args, **kwargs)


server_integration = _ServerIntegrationShim()
log.info(f"Server folder: {Config.SERVER_FOLDER}")


# =============================================================================
# Agent Process Manager
# =============================================================================

class AgentProcessManager:
    def __init__(self):
        self.agent_processes:   Dict[str, subprocess.Popen] = {}
        self.agent_info:        Dict[str, Dict[str, Any]]   = {}
        self.minecraft_processes: Dict[str, subprocess.Popen] = {}

        self.ultimmc_launcher = MultiAgentLauncher()
        self.source_launcher = UltimMCLauncher(
            client_jar_path=str(Config.CLIENT_JAR) if Config.CLIENT_JAR else None,
            mod_jar_path=str(Config.MOD_JAR)       if Config.MOD_JAR    else None,
        )
        self.spawner = EnhancedAgentSpawner(
            client_jar_path=str(Config.CLIENT_JAR) if Config.CLIENT_JAR else None,
            auto_package=True,
            package_output_dir=str(Config.NPC_APPLICATIONS_DIR),
        )
        log.info("AgentProcessManager initialised")

    # ------------------------------------------------------------------
    # UUID helpers
    # ------------------------------------------------------------------

    def _generate_agent_uuid(self, agent_id: str, agent_type: str = "npc",
                              custom_name: Optional[str] = None) -> str:
        username = name_manager.resolve_display_name(agent_id, custom_name)
        return get_minecraft_uuid(username)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start_agent_process(
        self, agent_id: str,
        mode:            str                   = "minecraft",
        server_addr:     str                   = Config.DEFAULT_SERVER,
        load_brain:      Optional[str]         = None,
        additional_args: Optional[List[str]]   = None,
        agent_type:      str                   = "npc",
        custom_name:     Optional[str]         = None,
        memory_mb:       int                   = 2048,
    ) -> bool:
        if agent_id in self.agent_processes:
            log.warning(f"Agent {agent_id} already running")
            return False
        try:
            brain_dir = Config.BRAINS_DIR / agent_id
            brain_dir.mkdir(parents=True, exist_ok=True)

            exe_path = (
                Path(Config.NPC_APPLICATIONS_DIR)
                / agent_id
                / agent_id   # no DW_ prefix — matches packager.py exe_name
            )

            if exe_path.exists():
                cmd = [str(exe_path)]
            else:
                # Resolve display name → username → UUID
                username = name_manager.resolve_display_name(agent_id, custom_name)

                agent_uuid = self._generate_agent_uuid(
                    agent_id, agent_type, custom_name
                )
                server_integration.register_agent(
                    username, agent_uuid, agent_type, custom_name,
                    gender=locals().get("gender")   # FIX 2: pass caller-supplied gender
                )

                # UltimMC setup is intentionally NOT called here.
                # setup_agent() and launch_agent() need the packaged UltimMC
                # copy at npc_applications/<id>/bin/UltimMC to exist first.
                # That copy is created by _auto_package_agent (below), which
                # runs after the brain file appears.  The whole MC flow is:
                #   brain.pcap written → package → setup_agent → launch_agent
                # All of that happens inside _auto_package_agent.

                # ── Port resolution ───────────────────────────────────────
                # TCP port  : agents.json lookup by display name (starts 11401).
                #             Injected into Java as -Ddw.tcp.port by launcher.
                # WS port   : tcp_port + WS_BACKEND_PORT_OFFSET (default 10000).
                #             Gives WebSocket ports starting at 21401, well clear
                #             of the TCP range and of Config.BASE_BACKEND_PORT.
                # Both ports are stable across restarts and guaranteed unique as
                # long as agents.json assigns each name a unique TCP port.
                WS_BACKEND_PORT_OFFSET = 10000
                _display_name = custom_name or username
                tcp_port = name_manager.get_port_for_name(_display_name)
                if tcp_port:
                    backend_port = tcp_port + WS_BACKEND_PORT_OFFSET
                    log.info(
                        f"[PortAlloc] {_display_name!r} -> "
                        f"TCP {tcp_port} / WS {backend_port} (from agents.json)"
                    )
                else:
                    # Name not yet in agents.json (freshly spawned agent).
                    # Register it now so it gets a stable port every restart.
                    _gender = (
                        agent_type[len("god_"):] if agent_type.startswith("god_")
                        else ("female" if _display_name.lower() in {
                            "eve", "alice", "diana", "emily", "fiona",
                            "grace", "hannah", "iris", "julia", "kate",
                        } else "male")
                    )
                    _cat = "GODs" if agent_type.startswith("god_") else "NPCs"
                    tcp_port = name_manager.add_name(_cat, _gender, _display_name) or Config.BASE_BACKEND_PORT
                    backend_port = tcp_port + WS_BACKEND_PORT_OFFSET
                    log.warning(
                        f"[PortAlloc] {_display_name!r} was not in agents.json -- "
                        f"registered now -> TCP {tcp_port} / WS {backend_port}"
                    )

                brain_save   = str(Config.get_agent_brain_path(agent_id))
                agent_script = Path(__file__).parent / "ai_core" / "agent.py"

                cmd = [
                    sys.executable, str(agent_script),
                    "--agent-id",        agent_id,
                    "--mode",            mode,
                    "--port",            str(backend_port),
                    "--tcp-port",        str(tcp_port),
                    "--log-level",       "INFO",
                    "--brain-save-path", brain_save,
                ]
                if custom_name:
                    cmd += ["--custom-name", custom_name]
                if load_brain:
                    cmd += ["--load-brain", load_brain]
                if additional_args:
                    cmd += additional_args

            env = os.environ.copy()
            env["PYTHONPATH"] = (
                f"{env.get('PYTHONPATH', '')}{os.pathsep}"
                f"{str(Path(__file__).parent)}"
            )
            process = subprocess.Popen(
                cmd, env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # merge stderr→stdout; prevents 64KB pipe blockage
                text=True, bufsize=1,
            )

            self.agent_processes[agent_id] = process
            self.agent_info[agent_id] = {
                "agent_id":    agent_id,
                "mode":        mode,
                "pid":         process.pid,
                "backend_port": locals().get("backend_port", 0),
                "tcp_port":     locals().get("tcp_port", 0),
                "started_at":  time.monotonic(),
                "brain_path":  load_brain,
                "status":      "running",
                "agent_type":  agent_type,
                "custom_name": custom_name or "Unnamed",
                "uuid":        locals().get("agent_uuid", ""),
                "server_addr": server_addr,
                # Spawn coordinates — extracted from --spawn-x/y/z additional_args
                # so /api/player_event can return them to Java for teleport on join.
                "spawn_pos":   _extract_spawn_pos(additional_args or []),
            }

            asyncio.create_task(self._monitor_logs(agent_id, process))
            asyncio.create_task(
                self._auto_package_agent(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    custom_name=custom_name,
                    server_addr=server_addr,
                    memory_mb=memory_mb,
                )
            )

            log.info(f"✅ Agent {agent_id} started (PID {process.pid})")
            return True

        except Exception as e:
            import traceback
            log.error(f"start_agent_process failed for {agent_id}: {e}\n"
                      f"{traceback.format_exc()}")
            return False

    # ------------------------------------------------------------------
    # Auto-package
    # ------------------------------------------------------------------

    async def _auto_package_agent(self, agent_id: str, agent_type: str,
                                   custom_name: Optional[str],
                                   server_addr: str = Config.DEFAULT_SERVER,
                                   memory_mb:   int = 2048):
        """
        Wait for the brain capsule to be written, then package the agent.

        This is also the trigger point for UltimMC setup + launch when mode
        is "minecraft" — because create_launcher_for_agent() prioritises the
        packaged copy at npc_applications/<id>/bin/UltimMC, that copy must
        exist before setup/launch is called.  So the order is:

          1. Wait for brain.pcap  (agent process writes this on first save)
          2. Run AgentPackager    → copies UltimMC into npc_applications/<id>/
          3. setup_agent()        → now finds the packaged UltimMC ✓
          4. launch_agent()       → launches from the correct per-agent copy ✓

        main.py's start_agent_process() no longer calls setup_agent or
        launch_agent directly — it defers entirely to this coroutine.
        """
        brain_path = Config.get_agent_brain_path(agent_id)
        for i in range(1500):        # up to 3000 seconds
            if brain_path.exists():
                break
            if i % 15 == 0 and i:
                log.info(
                    f"[Auto-Package] waiting for brain ({i*2}s)…"
                )
            await asyncio.sleep(2)
        else:
            log.error(f"[Auto-Package] Brain never created: {agent_id}")
            return

        await asyncio.sleep(2)   # let the brain file finish flushing
        pkg = self.spawner.package_agent(
            agent_id=agent_id,
            brain_path=str(brain_path),
            agent_type=agent_type,
            custom_name=custom_name or "Unnamed",
            # gender is resolved from brain capsule inside package_agent()
        )
        if pkg:
            log.info(f"✅ [Auto-Package] {agent_id} → {pkg}")
            if agent_id in self.agent_info:
                self.agent_info[agent_id]["package_path"] = str(pkg)
                self.agent_info[agent_id]["packaged"]     = True
        else:
            log.warning(f"⚠️  [Auto-Package] packaging failed for {agent_id}")

        # ── Now that the packaged UltimMC copy exists, do MC setup + launch ──
        info = self.agent_info.get(agent_id, {})
        if info.get("mode") != "minecraft":
            return
        if agent_id in self.minecraft_processes:
            return  # already launched (shouldn't happen, but be safe)

        log.info(f"[MC] Setting up UltimMC for {agent_id} (post-package)…")
        agent_uuid = info.get("uuid", "")
        ok = await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self.ultimmc_launcher.setup_agent(
                agent_id=agent_id,
                server_addr=server_addr,
                custom_uuid=agent_uuid,
                custom_name=custom_name,
                agent_type=agent_type,
                source_launcher=self.source_launcher,
            ),
        )
        if not ok:
            log.error(f"[MC] UltimMC setup failed for {agent_id} (post-package)")
            self.agent_info[agent_id]["status"] = "backend_only"
            return

        backend_port = info.get("backend_port", Config.BASE_BACKEND_PORT)
        log.info(f"[MC] Launching Minecraft for {agent_id}…")
        try:
            mc_proc = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self.ultimmc_launcher.launch_agent(
                    agent_id=agent_id,
                    server_addr=server_addr,
                    backend_url=f"ws://127.0.0.1:{backend_port}",
                    memory_mb=memory_mb,
                    headless=False,
                    agent_type=agent_type,
                    custom_name=custom_name,
                ),
            )
            if mc_proc:
                self.minecraft_processes[agent_id] = mc_proc
                self.agent_info[agent_id]["minecraft_pid"] = mc_proc.pid
                log.info(f"✅ [MC] Minecraft launched for {agent_id} (PID {mc_proc.pid})")
            else:
                log.warning(f"[MC] launch_agent returned None for {agent_id}")
                self.agent_info[agent_id]["status"] = "backend_only"
        except Exception as e:
            log.error(f"[MC] Launch error for {agent_id}: {e}")
            self.agent_info[agent_id]["status"] = "backend_only"

    # ------------------------------------------------------------------
    # Log monitor
    # ------------------------------------------------------------------

    async def _monitor_logs(self, agent_id: str, process: subprocess.Popen):
        loop = asyncio.get_event_loop()
        try:
            while process.poll() is None:
                if process.stdout:
                    try:
                        line = await loop.run_in_executor(
                            None, process.stdout.readline
                        )
                        if line:
                            log.info(f"[{agent_id}] {line.strip()}")
                    except Exception:
                        pass
                await asyncio.sleep(0.1)
        except Exception as e:
            log.error(f"Log monitor error ({agent_id}): {e}")
        finally:
            self.agent_processes.pop(agent_id, None)
            if agent_id in self.agent_info:
                self.agent_info[agent_id]["status"]    = "stopped"
                self.agent_info[agent_id]["exit_code"] = process.returncode

    # ------------------------------------------------------------------
    # Stop / list / status
    # ------------------------------------------------------------------

    def stop_agent_process(self, agent_id: str) -> bool:
        if agent_id not in self.agent_processes:
            return False
        try:
            if agent_id in self.minecraft_processes:
                try:
                    self.minecraft_processes[agent_id].terminate()
                    self.minecraft_processes[agent_id].wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.minecraft_processes[agent_id].kill()
                    self.minecraft_processes[agent_id].wait()
                del self.minecraft_processes[agent_id]
            proc = self.agent_processes[agent_id]
            proc.terminate()
            try:
                proc.wait(timeout=30)   # brain save (90MB torch.save) takes up to 30s
            except subprocess.TimeoutExpired:
                log.warning(f"Agent {agent_id} did not stop in 30s — force killing")
                proc.kill()
                proc.wait()
            log.info(f"Stopped agent {agent_id}")
            return True
        except Exception as e:
            log.error(f"Stop error ({agent_id}): {e}")
            return False

    def list_running_agents(self) -> List[str]:
        return list(self.agent_processes.keys())

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        return self.agent_info.get(agent_id)

    def cleanup_all(self):
        for aid in list(self.minecraft_processes):
            try:
                self.ultimmc_launcher.stop_agent(aid)
            except Exception:
                pass
        for aid in list(self.agent_processes):
            try:
                self.stop_agent_process(aid)
            except Exception:
                pass
        if hasattr(self.spawner, "cleanup_all"):
            self.spawner.cleanup_all()
        self.agent_processes.clear()
        self.agent_info.clear()
        log.info("Agent cleanup complete")


# =============================================================================
# FastAPI app
# =============================================================================

startup_time = 0


@asynccontextmanager
async def lifespan(app: FastAPI):
    global startup_time
    startup_time = asyncio.get_event_loop().time()
    log.info("=" * 60)
    log.info("  🎮 Divine World Management Server  v3.0.0")
    log.info("=" * 60)

    # FIX B-04: Wire BreedingSystem into app.state so /api/breeding/event
    # routes through the full pregnancy lifecycle (cooldowns, birth timing,
    # growth stages, brain-capsule persistence, reward events) rather than
    # the direct-spawn fallback.
    try:
        from py_backend.breeding_system import BreedingSystem
        spawner = getattr(agent_manager, 'spawner', None) or agent_manager
        breeding = BreedingSystem(spawner)
        app.state.breeding_system = breeding

        # Cross-wire: EnhancedAgentSpawner._post_spawn() checks
        # self._breeding_system to auto-attach new agents.  Without this,
        # newly spawned agents never get attach_to_agent() called and their
        # pregnancy state is never saved in brain capsules.
        if hasattr(spawner, '_breeding_system'):
            spawner._breeding_system = breeding

        # Background tick task: processes births and updates child growth.
        # Runs every 10 real seconds (≈0.5 MC ticks at 20 min/MC day).
        async def _breeding_tick_loop():
            import asyncio as _asyncio
            while True:
                try:
                    births = breeding.tick()
                    for mother_id, child in births:
                        log.info(f"🍼 Birth: {mother_id} → {child.agent_id}")
                except Exception as _te:
                    log.debug(f"Breeding tick error: {_te}")
                await _asyncio.sleep(10)

        import asyncio as _asyncio
        _asyncio.create_task(_breeding_tick_loop())

        log.info("✅ BreedingSystem wired (spawner cross-wired, tick task started)")
    except Exception as _be:
        log.warning(f"BreedingSystem startup wiring failed: {_be}")
        app.state.breeding_system = None

    # ── Auto-join all packaged agents on startup ───────────────────────────
    _auto = getattr(app.state, "auto_connect", None)
    if _auto:
        _agents = _auto.scan_agents_folder()
        log.info(f"[Startup] {len(_agents)} auto-connect agent(s) found")
        if _agents:
            asyncio.ensure_future(_auto.launch_all_agents(agent_manager.spawner))
    else:
        log.debug("[Startup] No auto_connect state — skipping auto-join")

    yield
    log.info("🛑 Shutting down…")
    agent_manager.cleanup_all()
    log.info("✅ Shutdown complete")


app = FastAPI(
    title="Divine World Management Server",
    version="3.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=False,  # FIX M-01: must be False with wildcard origin
    allow_methods=["*"], allow_headers=["*"],
)

agent_manager = AgentProcessManager()
integrate_with_backend(app, agent_manager)


# =============================================================================
# GUI — served as a self-contained HTML page
# =============================================================================

GUI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Divine World — Agent Control Centre</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&display=swap');

  :root {
    --bg:       #0a0c12;
    --panel:    #10141f;
    --border:   #1e2a40;
    --accent:   #00d4ff;
    --gold:     #f5c542;
    --red:      #ff4444;
    --green:    #00e676;
    --orange:   #ff9800;
    --text:     #c8d8f0;
    --dim:      #5a6a80;
    --font:     'Rajdhani', sans-serif;
    --mono:     'Share Tech Mono', monospace;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; background: var(--bg); color: var(--text);
               font-family: var(--font); font-size: 15px; }

  /* ── layout ──────────────────────────────────────────────────── */
  .root { display: grid; grid-template-rows: 48px 1fr; height: 100%; }

  header {
    display: flex; align-items: center; gap: 16px; padding: 0 20px;
    background: var(--panel); border-bottom: 1px solid var(--border);
  }
  header h1 { font-size: 18px; font-weight: 700; color: var(--accent);
               letter-spacing: 2px; text-transform: uppercase; }
  .hbadge { font-size: 11px; padding: 2px 8px; border-radius: 3px;
             background: #00d4ff22; color: var(--accent); font-family: var(--mono); }
  .hsep { flex: 1; }
  .conn-dot { width: 8px; height: 8px; border-radius: 50%;
              background: var(--red); }
  .conn-dot.on { background: var(--green); animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  .workspace {
    display: grid;
    grid-template-columns: 260px 1fr 340px;
    grid-template-rows: 1fr 200px;
    gap: 1px; background: var(--border); overflow: hidden;
  }

  .panel {
    background: var(--panel); overflow: hidden;
    display: flex; flex-direction: column;
  }
  .panel-head {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 14px; border-bottom: 1px solid var(--border);
    font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
    text-transform: uppercase; color: var(--dim);
  }
  .panel-head .icon { font-size: 14px; }
  .panel-body { flex: 1; overflow-y: auto; padding: 10px; }

  /* scrollbar */
  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  /* ── left: agent list ─────────────────────────────────────────── */
  .agent-card {
    border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px;
    margin-bottom: 8px; cursor: pointer; transition: border-color .15s;
    position: relative;
  }
  .agent-card:hover { border-color: var(--accent); }
  .agent-card.selected { border-color: var(--accent);
                          background: #00d4ff0a; }
  .agent-card .name { font-weight: 700; font-size: 15px; }
  .agent-card .meta { font-size: 11px; color: var(--dim); margin-top: 2px;
                       font-family: var(--mono); }
  .agent-card .type-badge {
    position: absolute; top: 8px; right: 10px;
    font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: 3px;
  }
  .type-npc  { background: #00e67622; color: var(--green); }
  .type-god  { background: #f5c54222; color: var(--gold); }
  .type-stopped { background: #ff444422; color: var(--red); }

  /* ── centre: detail / editor ─────────────────────────────────── */
  .centre { grid-column: 2; grid-row: 1; display: flex; flex-direction: column; }

  .tab-bar {
    display: flex; border-bottom: 1px solid var(--border);
    background: var(--panel);
  }
  .tab {
    padding: 10px 18px; font-size: 12px; font-weight: 700;
    letter-spacing: 1px; cursor: pointer; color: var(--dim);
    border-bottom: 2px solid transparent; transition: color .15s;
    text-transform: uppercase;
  }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }

  .tab-pane { display: none; flex: 1; overflow-y: auto; padding: 16px; }
  .tab-pane.active { display: block; }

  /* personality sliders */
  .trait-row { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .trait-label { width: 150px; font-size: 13px; color: var(--text); }
  .trait-slider { flex: 1; accent-color: var(--accent); cursor: pointer; }
  .trait-val { width: 42px; text-align: right; font-family: var(--mono);
               font-size: 12px; color: var(--accent); }

  /* memory editor */
  .mem-toolbar { display: flex; gap: 8px; margin-bottom: 10px; }
  .mem-search { flex: 1; background: #0d1220; border: 1px solid var(--border);
                color: var(--text); border-radius: 4px; padding: 5px 10px;
                font-family: var(--mono); font-size: 12px; }
  .mem-search:focus { outline: none; border-color: var(--accent); }

  .mem-event {
    border: 1px solid var(--border); border-radius: 4px; padding: 8px 10px;
    margin-bottom: 6px; font-family: var(--mono); font-size: 11px;
    cursor: grab; transition: border-color .15s;
    display: flex; gap: 8px; align-items: flex-start;
  }
  .mem-event:hover { border-color: var(--accent); }
  .mem-event.dragging { opacity: .4; cursor: grabbing; }
  .mem-event .ev-type { color: var(--accent); min-width: 100px; font-weight: 700; }
  .mem-event .ev-text { flex: 1; color: var(--dim); word-break: break-all; }
  .mem-event .ev-del { color: var(--red); cursor: pointer; font-size: 14px;
                        align-self: center; opacity: .6; }
  .mem-event .ev-del:hover { opacity: 1; }

  .mem-drop-zone {
    border: 2px dashed var(--border); border-radius: 6px; padding: 14px;
    text-align: center; color: var(--dim); font-size: 12px; margin-top: 10px;
    transition: border-color .2s, color .2s;
  }
  .mem-drop-zone.drag-over { border-color: var(--accent); color: var(--accent); }

  /* agent config */
  .cfg-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
  .cfg-label { width: 120px; font-size: 13px; color: var(--dim); }
  .cfg-select, .cfg-input {
    flex: 1; background: #0d1220; border: 1px solid var(--border);
    color: var(--text); border-radius: 4px; padding: 6px 10px;
    font-family: var(--font); font-size: 13px;
  }
  .cfg-select:focus, .cfg-input:focus { outline: none; border-color: var(--accent); }
  .cfg-note { font-size: 11px; color: var(--dim); margin-top: -8px; margin-bottom: 10px; }

  /* ── right: spawn controls ────────────────────────────────────── */
  .spawn-section { margin-bottom: 18px; }
  .spawn-section h3 { font-size: 11px; font-weight: 700; letter-spacing: 1.5px;
                       text-transform: uppercase; color: var(--dim);
                       margin-bottom: 10px; }
  .form-row { margin-bottom: 8px; }
  .form-label { font-size: 12px; color: var(--dim); margin-bottom: 3px; display: block; }
  .form-input {
    width: 100%; background: #0d1220; border: 1px solid var(--border);
    color: var(--text); border-radius: 4px; padding: 6px 10px;
    font-family: var(--mono); font-size: 12px;
  }
  .form-input:focus { outline: none; border-color: var(--accent); }
  select.form-input option { background: #10141f; }

  /* buttons */
  .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; border-radius: 4px; font-family: var(--font);
    font-size: 13px; font-weight: 700; letter-spacing: .5px;
    cursor: pointer; border: none; transition: all .15s;
  }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-primary:hover { filter: brightness(1.15); }
  .btn-gold    { background: var(--gold); color: #000; }
  .btn-gold:hover { filter: brightness(1.15); }
  .btn-red     { background: var(--red);  color: #fff; }
  .btn-red:hover { filter: brightness(1.15); }
  .btn-ghost   { background: transparent; color: var(--text);
                  border: 1px solid var(--border); }
  .btn-ghost:hover { border-color: var(--accent); color: var(--accent); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }
  .btn-block { width: 100%; justify-content: center; margin-bottom: 6px; }

  /* ── bottom: log ──────────────────────────────────────────────── */
  .log-panel { grid-column: 1 / -1; grid-row: 2; background: #080b10;
               border-top: 1px solid var(--border); display: flex; flex-direction: column; }
  .log-body  { flex: 1; overflow-y: auto; padding: 6px 12px;
               font-family: var(--mono); font-size: 11px; }
  .log-line  { padding: 1px 0; border-bottom: 1px solid #ffffff05; }
  .log-line .ts  { color: #3a4a60; margin-right: 6px; }
  .log-line .lv  { margin-right: 6px; font-weight: 700; min-width: 50px; display: inline-block; }
  .log-line .nm  { color: #4a6080; margin-right: 6px; }
  .lv-INFO    { color: var(--dim); }
  .lv-WARNING { color: var(--orange); }
  .lv-ERROR   { color: var(--red); }
  .lv-CRITICAL{ color: #ff0080; }
  .lv-DEBUG   { color: #334455; }

  /* divider / utils */
  hr.divider { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
  .empty { color: var(--dim); font-size: 12px; text-align: center; padding: 20px; }
  .toast {
    position: fixed; bottom: 220px; right: 20px; z-index: 9999;
    background: var(--accent); color: #000; padding: 8px 16px;
    border-radius: 6px; font-weight: 700; font-size: 13px;
    transition: opacity .4s; pointer-events: none;
  }
  .toast.err { background: var(--red); color: #fff; }
  .toast.fade { opacity: 0; }
</style>
</head>
<body>
<div class="root">

  <!-- HEADER -->
  <header>
    <h1>⚔ Divine World</h1>
    <span class="hbadge">AGENT CONTROL CENTRE v3.0</span>
    <div class="hsep"></div>
    <small style="color:var(--dim);font-size:11px;margin-right:8px" id="agent-count">0 agents</small>
    <span class="conn-dot" id="ws-dot" title="WebSocket"></span>
  </header>

  <!-- WORKSPACE -->
  <div class="workspace">

    <!-- LEFT: AGENT LIST -->
    <div class="panel">
      <div class="panel-head"><span class="icon">👥</span> Agents</div>
      <div class="panel-body" id="agent-list">
        <div class="empty">No agents running</div>
      </div>
    </div>

    <!-- CENTRE: TABS -->
    <div class="panel centre">
      <div class="tab-bar">
        <div class="tab active" onclick="showTab('personality')">Personality</div>
        <div class="tab" onclick="showTab('memories')">Memories</div>
        <div class="tab" onclick="showTab('config')">Config</div>
      </div>

      <!-- PERSONALITY TAB -->
      <div id="tab-personality" class="tab-pane active">
        <div id="personality-content">
          <div class="empty">Select an agent to edit their personality</div>
        </div>
      </div>

      <!-- MEMORIES TAB -->
      <div id="tab-memories" class="tab-pane">
        <div id="memories-content">
          <div class="empty">Select an agent to view their memories</div>
        </div>
      </div>

      <!-- CONFIG TAB -->
      <div id="tab-config" class="tab-pane">
        <div id="config-content">
          <div class="empty">Select an agent to edit their configuration</div>
        </div>
      </div>
    </div>

    <!-- RIGHT: SPAWN CONTROLS -->
    <div class="panel" style="overflow-y:auto">
      <div class="panel-head"><span class="icon">🧬</span> Spawn &amp; Control</div>
      <div class="panel-body">

        <div class="spawn-section">
          <h3>🌟 Genesis</h3>
          <div class="form-row">
            <label class="form-label">Server</label>
            <input id="genesis-server" class="form-input" value="127.0.0.1:25565">
          </div>
          <button class="btn btn-primary btn-block" onclick="doGenesis()">
            ✦ Spawn Adam &amp; Eve
          </button>
        </div>

        <hr class="divider">

        <div class="spawn-section">
          <h3>🧑 Spawn NPC</h3>
          <div class="form-row">
            <label class="form-label">Name (optional)</label>
            <input id="npc-name" class="form-input" placeholder="auto-select">
          </div>
          <div class="form-row">
            <label class="form-label">Gender</label>
            <select id="npc-gender" class="form-input">
              <option value="random">Random</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">Server</label>
            <input id="npc-server" class="form-input" value="127.0.0.1:25565">
          </div>
          <button class="btn btn-primary btn-block" onclick="doSpawnNPC()">
            ＋ Spawn NPC
          </button>
        </div>

        <hr class="divider">

        <div class="spawn-section">
          <h3>👑 Spawn God</h3>
          <div class="form-row">
            <label class="form-label">God Type</label>
            <select id="god-type" class="form-input">
              <option value="">Auto-select</option>
              <option value="ender_dragon">Ender Dragon</option>
              <option value="wither">Wither</option>
              <option value="warden">Warden</option>
              <option value="oracle">Oracle</option>
              <option value="elder_guardian">Elder Guardian</option>
              <option value="creaking">Creaking</option>
            </select>
          </div>
          <div class="form-row">
            <label class="form-label">Name (optional)</label>
            <input id="god-name" class="form-input" placeholder="auto-select">
          </div>
          <div class="form-row">
            <label class="form-label">Server</label>
            <input id="god-server" class="form-input" value="127.0.0.1:25565">
          </div>
          <button class="btn btn-gold btn-block" onclick="doSpawnGod()">
            ⚡ Spawn God
          </button>
        </div>

        <hr class="divider">

        <div class="spawn-section">
          <h3>🔴 Server Actions</h3>
          <button class="btn btn-red btn-block" onclick="doDivineReset()">
            ☠ Divine Reset
          </button>
        </div>

      </div>
    </div>

    <!-- BOTTOM: LOG -->
    <div class="log-panel">
      <div class="panel-head" style="justify-content:space-between">
        <span><span class="icon">📋</span> Live Log</span>
        <div style="display:flex;gap:8px">
          <select id="log-filter" onchange="filterLogs()" style="background:#0d1220;border:1px solid var(--border);color:var(--text);border-radius:3px;font-size:11px;padding:2px 6px;">
            <option value="">All levels</option>
            <option value="INFO">INFO+</option>
            <option value="WARNING">WARN+</option>
            <option value="ERROR">ERROR</option>
          </select>
          <button class="btn btn-ghost btn-sm" onclick="clearLog()">Clear</button>
          <label style="display:flex;align-items:center;gap:4px;font-size:11px;cursor:pointer">
            <input type="checkbox" id="log-auto-scroll" checked> Auto-scroll
          </label>
        </div>
      </div>
      <div class="log-body" id="log-body"></div>
    </div>

  </div>
</div>
<div id="toast" class="toast" style="opacity:0"></div>

<script>
// ============================================================
// State
// ============================================================
let ws            = null;
let selectedAgent = null;
let agents        = {};
let memories      = {};   // agent_id → [events]
let dragData      = null; // { agentId, index }
const TRAITS = [
  'openness','conscientiousness','extraversion',
  'agreeableness','neuroticism','boldness','curiosity','sociability'
];
const GOD_TYPES = ['ender_dragon','wither','warden','oracle','elder_guardian','creaking'];

// ============================================================
// WebSocket
// ============================================================
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws/gui`);
  ws.onopen = () => {
    document.getElementById('ws-dot').classList.add('on');
    ws.send(JSON.stringify({type:'hello'}));
    refreshAgents();
  };
  ws.onclose  = () => {
    document.getElementById('ws-dot').classList.remove('on');
    setTimeout(connect, 2000);
  };
  ws.onmessage = e => {
    const msg = JSON.parse(e.data);
    if (msg.type === 'ping')   return;  // keepalive — ignore
    if (msg.type === 'log')    appendLog(msg);
    if (msg.type === 'agents') updateAgentList(msg.agents);
    if (msg.type === 'brain')  updateBrainData(msg);
  };
}

// ============================================================
// Tabs
// ============================================================
function showTab(name) {
  document.querySelectorAll('.tab,.tab-pane').forEach(el => {
    el.classList.remove('active');
  });
  document.querySelectorAll('.tab').forEach(t => {
    if (t.getAttribute('onclick').includes(name)) t.classList.add('active');
  });
  document.getElementById(`tab-${name}`).classList.add('active');
  if (name === 'memories' && selectedAgent) loadMemories(selectedAgent);
}

// ============================================================
// Agent list
// ============================================================
async function refreshAgents() {
  const r = await api('/api/agents/list');
  if (!r) return;
  agents = {};
  // combine running + stopped (brains)
  (r.running || []).forEach(id => {
    agents[id] = { ...(r.running_details?.[id] || {}), status:'running', agent_id:id };
  });
  (r.available_brains || []).forEach(b => {
    if (!agents[b.agent_id]) agents[b.agent_id] = { ...b, status:'stopped' };
  });
  renderAgentList();
}

function renderAgentList() {
  const el = document.getElementById('agent-list');
  const ids = Object.keys(agents);
  document.getElementById('agent-count').textContent = `${ids.length} agents`;
  if (!ids.length) { el.innerHTML = '<div class="empty">No agents</div>'; return; }
  el.innerHTML = ids.map(id => {
    const a = agents[id];
    const typeClass = a.status === 'stopped' ? 'type-stopped'
                     : (a.agent_type||'').startsWith('god') ? 'type-god' : 'type-npc';
    const typeLbl   = a.status === 'stopped' ? '⬛ stopped'
                     : (a.agent_type||'').startsWith('god') ? '⚡ god' : '🧑 npc';
    return `<div class="agent-card ${selectedAgent===id?'selected':''}"
              onclick="selectAgent('${id}')">
      <div class="name">${a.custom_name || id}</div>
      <div class="meta">${id} · ${a.mode||'?'}</div>
      <span class="type-badge ${typeClass}">${typeLbl}</span>
    </div>`;
  }).join('');
}

function selectAgent(id) {
  selectedAgent = id;
  renderAgentList();
  loadBrain(id);
}

// ============================================================
// Brain data
// ============================================================
async function loadBrain(id) {
  const r = await api(`/api/agents/${id}/brain`);
  if (r) updateBrainData({...r, agent_id: id});
}

function updateBrainData(msg) {
  const id = msg.agent_id;
  if (!id || id !== selectedAgent) return;

  // Personality tab
  const traits = msg.personality || {};
  document.getElementById('personality-content').innerHTML =
    TRAITS.map(t => {
      const val = parseFloat(traits[t] ?? 0).toFixed(2);
      return `<div class="trait-row">
        <span class="trait-label">${t}</span>
        <input type="range" min="-1" max="1" step="0.01" class="trait-slider"
          id="trait-${t}" value="${val}"
          oninput="updateTraitVal('${t}',this.value)"
          onchange="savePersonality('${id}')">
        <span class="trait-val" id="tv-${t}">${val}</span>
      </div>`;
    }).join('') +
    `<br><button class="btn btn-primary btn-sm" onclick="savePersonality('${id}')">
       💾 Save Personality
     </button>`;

  // Memory tab (cache)
  memories[id] = msg.memories || [];
  if (document.getElementById('tab-memories').classList.contains('active')) {
    renderMemories(id);
  }

  // Config tab
  const info   = agents[id] || {};
  const atype  = (msg.agent_type || info.agent_type || 'npc');
  const gender = msg.gender || 'male';
  document.getElementById('config-content').innerHTML = `
    <div class="cfg-row">
      <span class="cfg-label">Agent Type</span>
      <select class="cfg-select" id="cfg-type-${id}" onchange="toggleGodSelect('${id}')">
        <option value="npc" ${atype==='npc'?'selected':''}>NPC</option>
        ${GOD_TYPES.map(g=>`<option value="god_${g}" ${atype===`god_${g}`?'selected':''}>${g.replace('_',' ')}</option>`).join('')}
      </select>
    </div>
    <div class="cfg-row" id="god-type-row-${id}" style="display:${atype.startsWith('god')?'flex':'none'}">
      <span class="cfg-label">God Subtype</span>
      <select class="cfg-select" id="cfg-godtype-${id}">
        ${GOD_TYPES.map(g=>`<option value="${g}" ${atype===`god_${g}`?'selected':''}>${g.replace('_',' ')}</option>`).join('')}
      </select>
    </div>
    <div class="cfg-row">
      <span class="cfg-label">Gender</span>
      <select class="cfg-select" id="cfg-gender-${id}">
        <option value="male" ${gender==='male'?'selected':''}>Male</option>
        <option value="female" ${gender==='female'?'selected':''}>Female</option>
        <option value="dual" ${gender==='dual'?'selected':''}>Dual (god)</option>
      </select>
    </div>
    <div class="cfg-row">
      <span class="cfg-label">Server</span>
      <input class="cfg-input" id="cfg-server-${id}"
             value="${info.server_addr || '127.0.0.1:25565'}">
    </div>
    <div class="cfg-row">
      <span class="cfg-label">Backend Port</span>
      <input class="cfg-input" id="cfg-port-${id}"
             value="${info.backend_port || ''}">
    </div>
    <hr class="divider">
    <button class="btn btn-primary btn-sm" style="margin-right:6px"
            onclick="saveConfig('${id}')">💾 Apply Config</button>
    <button class="btn btn-ghost btn-sm" style="margin-right:6px"
            onclick="doPackage('${id}')">📦 Package</button>
    <button class="btn btn-red btn-sm" onclick="doStop('${id}')">⏹ Stop</button>
    <br><br>
    <div style="font-size:11px;color:var(--dim)">
      Agent ID: <span style="color:var(--accent);font-family:var(--mono)">${id}</span><br>
      PID: ${info.pid || 'n/a'} · UUID: <span style="font-family:var(--mono)">${info.uuid || 'n/a'}</span>
    </div>
  `;
}

function toggleGodSelect(id) {
  const val = document.getElementById(`cfg-type-${id}`).value;
  document.getElementById(`god-type-row-${id}`).style.display =
    val.startsWith('god') ? 'flex' : 'none';
}

// ============================================================
// Memories
// ============================================================
async function loadMemories(id) {
  const r = await api(`/api/agents/${id}/brain`);
  if (!r) return;
  memories[id] = r.memories || [];
  renderMemories(id);
}

function renderMemories(id) {
  const evts = memories[id] || [];
  const search = (document.getElementById('mem-search-val')||{}).value || '';
  const filtered = evts.filter(e =>
    !search || JSON.stringify(e).toLowerCase().includes(search.toLowerCase())
  );

  document.getElementById('memories-content').innerHTML = `
    <div class="mem-toolbar">
      <input class="mem-search" id="mem-search-val" placeholder="Search memories…"
             oninput="renderMemories('${id}')" value="${search}">
      <button class="btn btn-ghost btn-sm" onclick="addMemory('${id}')">＋ Add</button>
      <button class="btn btn-primary btn-sm" onclick="saveMemories('${id}')">💾 Save</button>
    </div>
    ${filtered.length ? filtered.map((ev, i) => `
      <div class="mem-event" draggable="true"
           ondragstart="memDragStart(event,'${id}',${i})"
           ondragend="this.classList.remove('dragging')"
           id="mev-${i}">
        <span class="ev-type">${ev.type||'event'}</span>
        <span class="ev-text">${esc(JSON.stringify(ev.payload||ev.text||''))}</span>
        <span class="ev-del" onclick="deleteMemory('${id}',${i})">×</span>
      </div>`).join('') : '<div class="empty">No memories</div>'}
    <div class="mem-drop-zone" id="drop-zone-${id}"
         ondragover="event.preventDefault();this.classList.add('drag-over')"
         ondragleave="this.classList.remove('drag-over')"
         ondrop="memDrop(event,'${id}')">
      Drop memories from another agent here to transfer them
    </div>
  `;
}

function addMemory(id) {
  const text = prompt('Memory text (plain):', '');
  if (!text) return;
  if (!memories[id]) memories[id] = [];
  memories[id].unshift({ type: 'manual_entry', text, tags: ['manual'], timestamp: Date.now()/1000 });
  renderMemories(id);
}

function deleteMemory(id, i) {
  memories[id].splice(i, 1);
  renderMemories(id);
}

async function saveMemories(id) {
  const r = await api(`/api/agents/${id}/brain/memories`, 'POST', {
    memories: memories[id]
  });
  toast(r ? '✅ Memories saved' : '❌ Save failed', !r);
}

// drag from source agent
function memDragStart(ev, agentId, index) {
  dragData = { agentId, index };
  ev.target.classList.add('dragging');
  ev.dataTransfer.effectAllowed = 'copy';
}

// drop into target agent
function memDrop(ev, targetId) {
  ev.preventDefault();
  ev.currentTarget.classList.remove('drag-over');
  if (!dragData) return;
  const { agentId: srcId, index } = dragData;
  dragData = null;
  const event = (memories[srcId] || [])[index];
  if (!event) return;
  if (!memories[targetId]) memories[targetId] = [];
  const copy = { ...event, transferred_from: srcId, timestamp: Date.now()/1000 };
  memories[targetId].push(copy);
  toast(`✅ Memory transferred from ${srcId}`);
  if (selectedAgent === targetId) renderMemories(targetId);
}

// ============================================================
// Personality
// ============================================================
function updateTraitVal(trait, val) {
  document.getElementById(`tv-${trait}`).textContent = parseFloat(val).toFixed(2);
}

async function savePersonality(id) {
  const traits = {};
  TRAITS.forEach(t => {
    const el = document.getElementById(`trait-${t}`);
    if (el) traits[t] = parseFloat(el.value);
  });
  const r = await api(`/api/agents/${id}/brain/personality`, 'POST', { traits });
  toast(r ? '✅ Personality saved' : '❌ Save failed', !r);
}

// ============================================================
// Config
// ============================================================
async function saveConfig(id) {
  const typeEl   = document.getElementById(`cfg-type-${id}`);
  const gtEl     = document.getElementById(`cfg-godtype-${id}`);
  const genEl    = document.getElementById(`cfg-gender-${id}`);
  const srvEl    = document.getElementById(`cfg-server-${id}`);
  const portEl   = document.getElementById(`cfg-port-${id}`);

  let agent_type = typeEl ? typeEl.value : 'npc';
  if (agent_type.startsWith('god') && gtEl)
    agent_type = `god_${gtEl.value}`;

  const r = await api(`/api/agents/${id}/brain/config`, 'POST', {
    agent_type,
    gender:      genEl  ? genEl.value  : undefined,
    server_addr: srvEl  ? srvEl.value  : undefined,
    backend_port:portEl && portEl.value ? parseInt(portEl.value) : undefined,
  });
  toast(r ? '✅ Config applied' : '❌ Apply failed', !r);
}

// ============================================================
// Spawn actions
// ============================================================
async function doGenesis() {
  const server_addr = document.getElementById('genesis-server').value.trim();
  const r = await api('/api/genesis/spawn', 'POST', {
    event:'genesis', spawner:'GUI', world:'minecraft:overworld',
    spawn_count:2, server_addr,
    spawn_positions:[
      {x:0,y:64,z:0,gender:'male'},
      {x:2,y:64,z:0,gender:'female'},
    ]
  });
  if (r) { toast('✅ Genesis complete'); refreshAgents(); }
  else    toast('❌ Genesis failed', true);
}

async function doSpawnNPC() {
  const name   = document.getElementById('npc-name').value.trim();
  const gender = document.getElementById('npc-gender').value;
  const server = document.getElementById('npc-server').value.trim();
  const r = await api('/api/agents/spawn_single', 'POST', {
    agent_name: name || undefined,
    gender: gender === 'random' ? undefined : gender,
    server_addr: server,
    mode: 'minecraft',
    spawner: 'GUI',
  });
  if (r) { toast(`✅ NPC spawned: ${r.agent_name}`); refreshAgents(); }
  else    toast('❌ NPC spawn failed', true);
}

async function doSpawnGod() {
  const god_type = document.getElementById('god-type').value;
  const name     = document.getElementById('god-name').value.trim();
  const server   = document.getElementById('god-server').value.trim();
  const r = await api('/api/gods/spawn', 'POST', {
    event:'spawn_god',
    god_type: god_type || undefined,
    custom_name: name || undefined,
    server_addr: server,
    spawner:'GUI', world:'minecraft:overworld',
    spawn_position:{x:0,y:64,z:0},
  });
  if (r) { toast(`✅ God spawned: ${r.display_name}`); refreshAgents(); }
  else    toast('❌ God spawn failed', true);
}

async function doDivineReset() {
  if (!confirm('☠ Divine Reset will kill ALL agents and delete their memories. Continue?')) return;
  const ids = Object.keys(agents);
  const r = await api('/api/divine_reset', 'POST', {
    event:'divine_reset', world:'minecraft:overworld',
    agent_count:ids.length, agent_ids:ids
  });
  if (r) { toast('✅ Divine Reset complete'); agents={}; renderAgentList(); }
  else    toast('❌ Divine Reset failed', true);
}

async function doPackage(id) {
  const r = await api(`/api/agents/${id}/package`, 'POST', {});
  toast(r ? `✅ ${id} packaged` : `❌ Package failed`, !r);
}

async function doStop(id) {
  const r = await api(`/api/agents/${id}/stop`, 'POST', {});
  if (r) { toast(`⏹ ${id} stopped`); refreshAgents(); }
  else    toast(`❌ Stop failed`, true);
}

// ============================================================
// Log
// ============================================================
const LOG_LEVEL = { DEBUG:0,INFO:1,WARNING:2,ERROR:3,CRITICAL:4 };
let logLines = [];

function appendLog(entry) {
  logLines.push(entry);
  if (logLines.length > 1000) logLines.shift();
  const filter = document.getElementById('log-filter').value;
  if (filter && LOG_LEVEL[entry.level] < LOG_LEVEL[filter]) return;
  renderLogLine(entry);
}

function renderLogLine(entry) {
  const body  = document.getElementById('log-body');
  const d     = new Date(entry.ts*1000);
  const ts    = d.toTimeString().slice(0,8);
  const line  = document.createElement('div');
  line.className = 'log-line';
  line.innerHTML = `<span class="ts">${ts}</span>`
    + `<span class="lv lv-${entry.level}">${entry.level}</span>`
    + `<span class="nm">${(entry.name||'').slice(0,20)}</span>`
    + esc(entry.message||'');
  body.appendChild(line);
  const auto = document.getElementById('log-auto-scroll');
  if (auto && auto.checked) body.scrollTop = body.scrollHeight;
}

function filterLogs() {
  const body   = document.getElementById('log-body');
  const filter = document.getElementById('log-filter').value;
  body.innerHTML = '';
  logLines.forEach(e => {
    if (!filter || LOG_LEVEL[e.level] >= LOG_LEVEL[filter]) renderLogLine(e);
  });
}

function clearLog() {
  logLines = [];
  document.getElementById('log-body').innerHTML = '';
}

// ============================================================
// Helpers
// ============================================================
function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function toast(msg, isErr=false) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className   = 'toast' + (isErr ? ' err' : '');
  el.style.opacity = '1';
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.classList.add('fade'); }, 2200);
}

async function api(url, method='GET', body=undefined) {
  try {
    const opts = { method, headers:{'Content-Type':'application/json'} };
    if (body !== undefined) opts.body = JSON.stringify(body);
    const r = await fetch(url, opts);
    if (!r.ok) { toast(`❌ ${method} ${url} → ${r.status}`, true); return null; }
    return await r.json();
  } catch(e) {
    toast(`❌ Network: ${e.message}`, true); return null;
  }
}

// ============================================================
// Boot
// ============================================================
connect();
setInterval(refreshAgents, 8000);
</script>
</body>
</html>"""


@app.get("/gui", response_class=HTMLResponse)
async def serve_gui():
    """Serve the self-contained control centre GUI."""
    return GUI_HTML


# =============================================================================
# GUI WebSocket — live log + agent push
# =============================================================================

_gui_sockets: List[WebSocket] = []


@app.websocket("/ws/gui")
async def ws_gui(ws: WebSocket):
    await ws.accept()
    _gui_sockets.append(ws)
    loop = asyncio.get_running_loop()
    _gui_log_handler.subscribe(ws, loop)

    async def _ping():
        """Send a ping frame every 20 s so proxies/browsers never idle-timeout."""
        try:
            while True:
                await asyncio.sleep(20)
                await ws.send_json({"type": "ping"})
        except Exception:
            pass  # connection already closed — ping task will be cancelled

    ping_task = asyncio.create_task(_ping())
    try:
        # Replay buffered logs so the GUI is up-to-date immediately
        for entry in _gui_log_handler.get_buffer():
            await ws.send_json({"type": "log", **entry})
        # Push current agent list
        await _push_agents(ws)
        # Receive loop — handles hello messages and detects clean disconnects
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "hello":
                await _push_agents(ws)
            # Ignore pong / unknown types silently
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        ping_task.cancel()
        _gui_log_handler.unsubscribe(ws)
        if ws in _gui_sockets:
            _gui_sockets.remove(ws)


async def _push_agents(ws: WebSocket):
    try:
        await ws.send_json({
            "type":   "agents",
            "agents": {
                aid: agent_manager.get_agent_status(aid)
                for aid in agent_manager.list_running_agents()
            },
        })
    except Exception:
        pass


# =============================================================================
# Brain editor endpoints (GUI-only)
# =============================================================================

@app.get("/api/agents/{agent_id}/brain")
async def get_brain(agent_id: str):
    """Return brain data (personality + memories) for the GUI editor."""
    brain_path = Config.get_agent_brain_path(agent_id)
    if not brain_path.exists():
        raise HTTPException(status_code=404, detail="Brain not found")
    try:
        from ai_core.brain_capsule import BrainCapsule
        caps = BrainCapsule.load(str(brain_path))
        info = agent_manager.get_agent_status(agent_id) or {}
        return {
            "agent_id":   agent_id,
            "personality": caps.personality or {},
            "memories":   caps.memory_snapshot or [],
            "gender":     caps.gender,
            "agent_type": caps.metadata.get("agent_type", info.get("agent_type", "npc")),
            "metadata":   caps.metadata,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/brain/personality")
async def save_personality(agent_id: str, request: Request):
    """Overwrite personality traits in the brain capsule."""
    data       = await request.json()
    traits     = data.get("traits", {})
    brain_path = Config.get_agent_brain_path(agent_id)
    if not brain_path.exists():
        raise HTTPException(status_code=404, detail="Brain not found")
    try:
        from ai_core.brain_capsule import BrainCapsule
        caps = BrainCapsule.load(str(brain_path))
        if caps.personality is None:
            caps.personality = {}
        caps.personality.update(
            {k: max(-1.0, min(1.0, float(v))) for k, v in traits.items()}
        )
        caps.save(str(brain_path))
        log.info(f"[GUI] Personality updated for {agent_id}: {traits}")
        return {"status": "success", "agent_id": agent_id, "traits": caps.personality}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/brain/memories")
async def save_memories(agent_id: str, request: Request):
    """Replace the memory snapshot in the brain capsule."""
    data       = await request.json()
    new_mems   = data.get("memories", [])
    brain_path = Config.get_agent_brain_path(agent_id)
    if not brain_path.exists():
        raise HTTPException(status_code=404, detail="Brain not found")
    try:
        from ai_core.brain_capsule import BrainCapsule
        caps = BrainCapsule.load(str(brain_path))
        caps.memory_snapshot = new_mems
        caps.save(str(brain_path))
        log.info(f"[GUI] Memories updated for {agent_id}: {len(new_mems)} events")
        return {"status": "success", "agent_id": agent_id,
                "memory_count": len(new_mems)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/brain/config")
async def save_agent_config(agent_id: str, request: Request):
    """
    Update agent type, gender, server, and port in the brain capsule.
    For a running agent the change takes effect on next restart.
    """
    data       = await request.json()
    brain_path = Config.get_agent_brain_path(agent_id)
    if not brain_path.exists():
        raise HTTPException(status_code=404, detail="Brain not found")
    try:
        from ai_core.brain_capsule import BrainCapsule
        caps = BrainCapsule.load(str(brain_path))
        if data.get("agent_type"):
            caps.metadata["agent_type"] = data["agent_type"]
        if data.get("gender"):
            caps.gender = data["gender"]
        caps.save(str(brain_path))

        # Update live info dict if agent is running
        if agent_id in agent_manager.agent_info:
            if data.get("agent_type"):
                agent_manager.agent_info[agent_id]["agent_type"] = data["agent_type"]
            if data.get("server_addr"):
                agent_manager.agent_info[agent_id]["server_addr"] = data["server_addr"]
            if data.get("backend_port"):
                agent_manager.agent_info[agent_id]["backend_port"] = data["backend_port"]

        log.info(f"[GUI] Config updated for {agent_id}")
        return {"status": "success", "agent_id": agent_id,
                "note": "Changes take effect on next agent restart"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# All existing REST endpoints (unchanged from document)
# =============================================================================

@app.post("/api/server/configure")
async def configure_server_folder():
    registered = list_registered_agents()
    return {
        "status": "success",
        "message": "Server folder read from Config",
        "server_folder": str(Config.SERVER_FOLDER),
        "existing_agents": registered,
    }


@app.get("/api/server/status")
async def get_server_status():
    folder = Config.SERVER_FOLDER
    registered = list_registered_agents()
    return {
        "status": "configured" if folder.exists() else "folder_missing",
        "server_folder": str(folder),
        "registered_agents": registered,
        "agent_count": len(registered),
    }


@app.get("/api/server/agents")
async def list_server_agents():
    registered = server_integration.list_registered_agents()
    return {"status": "success", "agents": registered, "count": len(registered)}


@app.post("/api/agents/spawn_single")
async def spawn_single_agent(request: Request):
    import random as _rng
    data         = await request.json()
    agent_name   = data.get("agent_name")
    mode         = data.get("mode", "minecraft")
    spawner_name = data.get("spawner")
    spawn_pos    = data.get("spawn_position", {})
    gender       = data.get("gender") or _rng.choice(["male", "female"])
    server_addr  = data.get("server_addr", Config.DEFAULT_SERVER)
    personality  = data.get("personality") or {
        "boldness": 0.7, "curiosity": 0.8, "agreeableness": 0.7,
        "conscientiousness": 0.7, "neuroticism": 0.3,
        "openness": 0.7, "sociability": 0.7,
    }

    if not agent_name:
        agent_name = name_manager.get_random_name("NPCs", gender) or "Unnamed"

    base_id  = sanitize_agent_id(agent_name)
    existing = 0
    if Config.NPC_APPLICATIONS_DIR.exists():
        pat = re.compile(rf"^{re.escape(base_id)}(_\d+)?$")
        existing = sum(
            1 for d in Config.NPC_APPLICATIONS_DIR.iterdir()
            if d.is_dir() and pat.match(d.name)
        )
    agent_id = f"{base_id}_{existing + 1}"
    name_manager.add_name("NPCs", gender, agent_name)

    sx, sy, sz = spawn_pos.get("x", 0), spawn_pos.get("y", 64), spawn_pos.get("z", 0)

    ok = agent_manager.start_agent_process(
        agent_id=agent_id, mode=mode, server_addr=server_addr,
        additional_args=[
            "--gender", gender,
            "--personality", json.dumps(personality),
            "--spawn-x", str(sx), "--spawn-y", str(sy), "--spawn-z", str(sz),
        ],
        agent_type="npc", custom_name=agent_name,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to spawn {agent_name}")
    return {
        "status": "success", "agent_id": agent_id, "agent_name": agent_name,
        "gender": gender, "spawner": spawner_name,
        "position": {"x": sx, "y": sy, "z": sz},
        "personality": personality,
        "brain_path": str(Config.get_agent_brain_path(agent_id)),
    }


@app.post("/api/player_event")
async def handle_player_event(request: Request):
    data       = await request.json()
    agent_id   = data.get("agent_id")
    player_uuid = data.get("player_uuid")
    agent_type = data.get("agent_type")
    event      = data.get("event")

    # Feed auto-connect system
    if event == "connected" and agent_id:
        ac = getattr(app.state, "auto_connect", None)
        if ac:
            ac.mark_connected(agent_id)

    if event == "connected":
        if agent_id not in agent_manager.agent_processes:
            args = ["--gender", "dual"] if (agent_type or "").startswith("god_") else []
            agent_manager.start_agent_process(
                agent_id=agent_id, mode="minecraft",
                additional_args=args,
                agent_type=agent_type or "npc",
            )

        # Return stored spawn_pos so Java can teleport the agent immediately on join.
        # If no spawn_pos was registered (e.g. auto-connect), omit the field and
        # Java will leave the player at vanilla spawn.
        info = agent_manager.agent_info.get(agent_id, {})
        spawn_pos = info.get("spawn_pos", {})
        resp = {"status": "success", "message": f"{agent_id} connected", "agent_id": agent_id}
        if spawn_pos:
            resp["spawn_pos"] = spawn_pos
        return resp

    elif event == "disconnected":
        return {"status": "success", "message": f"{agent_id} disconnected"}

    return {"status": "unknown_event", "event": event}


@app.post("/api/breeding/event")
async def handle_breeding_event(request: Request):
    """
    Breeding event from Java BreedingEventHandler.

    FIX B-04: now routes through BreedingSystem.initiate_breeding() so the
    full pregnancy lifecycle runs: cooldowns, trait inheritance, birth timing,
    growth stages, brain-capsule persistence, and reward events.

    pa_type / pb_type ("god" or "npc") are used to:
      - Skip the beds requirement for god participants
      - Log which type of pair bred
    Offspring are always NPC regardless of parent types.

    The handler still falls back to direct spawn if BreedingSystem is
    unavailable (e.g. during tests or early startup).
    """
    import random as _rng
    data     = await request.json()
    pa       = data.get("parent_a_id")
    pb       = data.get("parent_b_id")
    pa_type  = data.get("parent_a_type", "npc")   # "npc" or "god"
    pb_type  = data.get("parent_b_type", "npc")

    if not pa or not pb:
        raise HTTPException(status_code=400, detail="parent_a_id and parent_b_id required")

    # ── Primary path: delegate to BreedingSystem ──────────────────────────
    breeding_sys = getattr(app.state, "breeding_system", None)
    if breeding_sys is not None:
        try:
            # Gods waive the adjacent-beds requirement — pass beds_adjacent=True
            # when at least one parent is a god (Java already checked proximity)
            has_god      = (pa_type == "god" or pb_type == "god")
            beds_adjacent = True if has_god else True  # Java already verified beds

            pregnancy = breeding_sys.initiate_breeding(pa, pb)
            if pregnancy is None:
                # check_can_breed failed — return the reason without error
                return {
                    "status": "rejected",
                    "reason": "Breeding conditions not met (cooldown, pregnancy, or compatibility)",
                }

            return {
                "status":          "success",
                "female_id":       pregnancy.female_id,
                "male_id":         pregnancy.male_id,
                "child_gender":    str(pregnancy.child_gender),
                "due_real_minutes": (pregnancy.due_time - __import__("time").time()) / 60,
                "pa_type":         pa_type,
                "pb_type":         pb_type,
            }
        except Exception as e:
            log.error(f"BreedingSystem.initiate_breeding() failed: {e}", exc_info=True)
            # Fall through to direct-spawn fallback

    # ── Fallback path: direct spawn (no BreedingSystem available) ────────
    # Preserves functionality during startup / tests.  Logs a warning so
    # the operator knows to wire BreedingSystem into app.state.
    log.warning(
        "BreedingSystem not available — using direct-spawn fallback. "
        "Set app.state.breeding_system after startup to enable full lifecycle."
    )

    offspring_id     = f"offspring_{pa}_{pb}_{int(__import__('time').time())}"
    offspring_gender = _rng.choice(["male", "female"])

    pa_pers, pb_pers = {}, {}
    for pid, store in [(pa, "pa_pers"), (pb, "pb_pers")]:
        try:
            bp = Config.get_agent_brain_path(pid)
            if bp.exists():
                from ai_core.brain_capsule import BrainCapsule
                c = BrainCapsule.load(str(bp))
                pers = c.personality or {}
                if store == "pa_pers":
                    pa_pers = pers
                else:
                    pb_pers = pers
        except Exception:
            pass

    all_traits    = set(pa_pers) | set(pb_pers)
    offspring_pers = {
        t: max(-1.0, min(1.0,
            (pa_pers.get(t, 0.0) + pb_pers.get(t, 0.0)) / 2
            + _rng.uniform(-0.1, 0.1)))
        for t in all_traits if t != "gender"
    }
    offspring_name = name_manager.get_random_name("NPCs", offspring_gender) or "Unnamed"
    name_manager.add_name("NPCs", offspring_gender, offspring_name)

    ok = agent_manager.start_agent_process(
        agent_id=offspring_id, mode="minecraft",
        additional_args=[
            "--parent-a",    pa,
            "--parent-b",    pb,
            "--gender",      offspring_gender,
            "--personality", json.dumps(offspring_pers),
        ],
        agent_type="npc", custom_name=offspring_name,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to spawn offspring")
    return {
        "status":          "success",
        "offspring_id":    offspring_id,
        "offspring_gender":offspring_gender,
        "inherited_personality": offspring_pers,
        "path":            "fallback",
    }


@app.post("/api/agents/chat_heard")
async def agent_chat_heard(request: Request):
    """
    HTTP fallback for god agents that overheard proximity chat.

    NPC agents receive chat via their WebSocket (/ws/agent text frame).
    God agents run a separate LLM brain (LLMOracleBrain) and are not
    connected via a persistent WebSocket, so ProximityChatHandler on the
    server mod notifies them via this endpoint instead.

    The endpoint injects the message into a per-agent asyncio.Queue that
    the agent's cognitive loop drains on each cycle.
    """
    data      = await request.json()
    hearer_id = data.get("hearer_id")
    speaker   = data.get("speaker_name", "unknown")
    message   = data.get("message", "")

    if not hearer_id or not message:
        raise HTTPException(status_code=400, detail="hearer_id and message required")

    info = agent_manager.get_agent_status(hearer_id)
    if info is None:
        return {"status": "ignored", "reason": "agent not running"}

    q = agent_manager.get_chat_queue(hearer_id)
    if q is not None:
        try:
            q.put_nowait({"type": "chat_heard", "speaker": speaker, "message": message})
        except Exception:
            pass  # queue full — drop rather than block

    log.debug(f"[chat_heard] {hearer_id} overheard {speaker}: {message[:60]}")
    return {"status": "ok", "hearer": hearer_id}


@app.post("/api/genesis/spawn")
async def genesis_spawn(request: Request):
    data           = await request.json()
    spawner_name   = data.get("spawner")
    world_name     = data.get("world")
    mode           = data.get("mode", "minecraft")
    spawn_positions = data.get("spawn_positions", [])
    server_addr    = data.get("server_addr", Config.DEFAULT_SERVER)

    GENESIS = {
        "male": {
            "name": "Adam",
            "personality": {
                "boldness": 0.8, "curiosity": 0.9, "agreeableness": 0.5,
                "conscientiousness": 0.6, "neuroticism": 0.3,
                "openness": 0.7, "sociability": 0.6,
            },
        },
        "female": {
            "name": "Eve",
            "personality": {
                "boldness": 0.6, "curiosity": 0.7, "agreeableness": 0.9,
                "conscientiousness": 0.8, "neuroticism": 0.4,
                "openness": 0.7, "sociability": 0.8,
            },
        },
    }

    spawned = []
    import random as _rng
    for sp in spawn_positions:
        gender = sp.get("gender", _rng.choice(["male", "female"]))
        g_cfg  = GENESIS.get(gender, GENESIS["male"])
        display_name = g_cfg["name"]
        personality  = g_cfg["personality"]

        name_manager.add_name("NPCs", gender, display_name)

        base_id  = sanitize_agent_id(display_name)
        existing = 0
        if Config.NPC_APPLICATIONS_DIR.exists():
            pat = re.compile(rf"^{re.escape(base_id)}(_\d+)?$")
            existing = sum(
                1 for d in Config.NPC_APPLICATIONS_DIR.iterdir()
                if d.is_dir() and pat.match(d.name)
            )
        agent_id = f"{base_id}_{existing + 1}"

        ok = agent_manager.start_agent_process(
            agent_id=agent_id,
            mode=sp.get("mode", mode),
            server_addr=server_addr,
            additional_args=[
                "--gender", gender,
                "--personality", json.dumps(personality),
                "--spawn-x", str(sp.get("x", 0)),
                "--spawn-y", str(sp.get("y", 64)),
                "--spawn-z", str(sp.get("z", 0)),
                "--genesis-ancestor", "true",
            ],
            agent_type="npc", custom_name=display_name, memory_mb=2048,
        )
        if ok:
            spawned.append({"agent_id": agent_id, "display_name": display_name,
                             "gender": gender, "personality": personality})

    return {
        "status": "success",
        "message": f"Genesis complete — {len(spawned)} agents spawned",
        "agents": spawned,
    }


@app.post("/api/divine_reset")
async def divine_reset(request: Request):
    data       = await request.json()
    agent_ids  = data.get("agent_ids", [])
    killed, deleted = [], 0
    for aid in agent_ids:
        if aid in agent_manager.agent_processes:
            agent_manager.stop_agent_process(aid)
            killed.append(aid)
        bp = Config.get_agent_brain_path(aid)
        if bp.exists():
            bp.unlink()
            deleted += 1
    return {"status": "success", "agents_killed": len(killed), "brains_deleted": deleted}


@app.post("/api/agents/clear_memories")
async def clear_memories(request: Request):
    data       = await request.json()
    agent_ids  = data.get("agent_ids", [])
    exceptions = data.get("exceptions", [])
    results    = {}
    for aid in agent_ids:
        if aid in exceptions:
            results[aid] = {"status": "skipped"}
            continue
        bp = Config.get_agent_brain_path(aid)
        if not bp.exists():
            results[aid] = {"status": "not_found"}
            continue
        try:
            from ai_core.brain_capsule import BrainCapsule
            c = BrainCapsule.load(str(bp))
            c.memory_snapshot  = []
            c.language_state   = None
            c.save(str(bp))
            results[aid] = {"status": "success"}
        except Exception as e:
            results[aid] = {"status": "error", "error": str(e)}
    return {"status": "success", "results": results}


@app.post("/api/gods/spawn")
async def spawn_god(request: Request):
    GOD_CONFIGS = {
        "wither":         {"memory_mb": 3072, "persona_traits": {"boldness": 0.9, "agreeableness": -0.8, "neuroticism": 0.7, "curiosity": 0.3}},
        "warden":         {"memory_mb": 3072, "persona_traits": {"boldness": 0.9, "curiosity": 0.3, "neuroticism": 0.1, "agreeableness": -0.7}},
        "ender_dragon":   {"memory_mb": 4096, "persona_traits": {"boldness": 1.0, "sociability": -0.9, "openness": 0.5, "neuroticism": -0.3}},
        "oracle":         {"memory_mb": 2048, "persona_traits": {"curiosity": 0.9, "sociability": 0.7, "openness": 0.9, "conscientiousness": 0.6}},
        "creaking":       {"memory_mb": 2048, "persona_traits": {"curiosity": 0.8, "boldness": 0.4, "neuroticism": 0.6, "sociability": -0.2}},
        "elder_guardian": {"memory_mb": 2560, "persona_traits": {"boldness": 0.85, "agreeableness": -0.6, "conscientiousness": 0.7, "sociability": -0.5}},
    }

    data       = await request.json()
    god_type   = data.get("god_type")
    spawner_name = data.get("spawner")
    spawn_pos  = data.get("spawn_position", {})
    custom_name = data.get("custom_name")
    server_addr = data.get("server_addr", Config.DEFAULT_SERVER)

    # Auto-select god type if not given
    if not god_type or god_type not in GOD_CONFIGS:
        import random as _rng
        god_type = _rng.choice(list(GOD_CONFIGS.keys()))
        log.info(f"Auto-selected god type: {god_type}")

    cfg          = GOD_CONFIGS[god_type]
    display_name = (
        custom_name
        or name_manager.get_random_name("GODs", god_type)
        or "Unnamed"
    )

    base_id  = sanitize_agent_id(display_name)
    existing = 0
    if Config.NPC_APPLICATIONS_DIR.exists():
        pat = re.compile(rf"^{re.escape(base_id)}(_\d+)?$")
        existing = sum(
            1 for d in Config.NPC_APPLICATIONS_DIR.iterdir()
            if d.is_dir() and pat.match(d.name)
        )
    agent_id = f"{base_id}_{existing + 1}"
    name_manager.add_name("GODs", god_type, display_name)

    sx, sy, sz = spawn_pos.get("x", 0), spawn_pos.get("y", 64), spawn_pos.get("z", 0)

    ok = agent_manager.start_agent_process(
        agent_id=agent_id, mode="minecraft", server_addr=server_addr,
        additional_args=[
            "--gender", "dual",
            "--personality", json.dumps(cfg["persona_traits"]),
            "--memory-mb", str(cfg["memory_mb"]),
            "--spawn-x", str(sx), "--spawn-y", str(sy), "--spawn-z", str(sz),
        ],
        agent_type=f"god_{god_type}", custom_name=display_name,
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to spawn god {god_type}")
    return {
        "status": "success", "god_type": god_type, "agent_id": agent_id,
        "display_name": display_name, "gender": "dual",
        "brain_path": str(Config.get_agent_brain_path(agent_id)),
    }


@app.post("/api/gods/ability")
async def god_ability(request: Request):
    data = await request.json()
    return {"status": "success", "agent_id": data.get("agent_id"),
            "ability": data.get("ability")}


@app.post("/api/gods/transform")
async def god_transform(request: Request):
    data = await request.json()
    return {"status": "success", "agent_id": data.get("agent_id"),
            "target_mob": data.get("target_mob")}



@app.get("/api/agents/list")
async def list_agents():
    running = agent_manager.list_running_agents()
    brains: List[Dict] = []
    if Config.BRAINS_DIR.exists():
        for d in Config.BRAINS_DIR.iterdir():
            if d.is_dir():
                bf = d / "brain.pcap"
                if bf.exists():
                    brains.append({
                        "agent_id": d.name,
                        "brain_path": str(bf),
                        "size_mb": bf.stat().st_size / 1_048_576,
                    })
    return {
        "running": running,
        "running_count": len(running),
        "available_brains": brains,
        "running_details": {
            aid: agent_manager.get_agent_status(aid) for aid in running
        },
    }


@app.post("/api/agents/start")
async def start_agent(request: Request):
    data     = await request.json()
    agent_id = data.get("agent_id")
    if not agent_id:
        raise HTTPException(status_code=400, detail="Missing agent_id")
    ok = agent_manager.start_agent_process(
        agent_id=agent_id,
        mode=data.get("mode", "autonomous"),
        load_brain=data.get("load_brain"),
        additional_args=data.get("args", []),
        agent_type=data.get("agent_type", "npc"),
        custom_name=data.get("custom_name"),
    )
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to start {agent_id}")
    return {"status": "success", "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/stop")
async def stop_agent(agent_id: str):
    ok = agent_manager.stop_agent_process(agent_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"{agent_id} not running")
    return {"status": "success", "agent_id": agent_id}


@app.get("/api/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    s = agent_manager.get_agent_status(agent_id)
    if not s:
        raise HTTPException(status_code=404, detail=f"{agent_id} not found")
    return s


@app.post("/api/agents/{agent_id}/package")
async def package_agent(agent_id: str):
    bp = Config.get_agent_brain_path(agent_id)
    if not bp.exists():
        raise HTTPException(status_code=404, detail="Brain not found")
    pkg = agent_manager.spawner.package_agent(
        agent_id=agent_id, brain_path=str(bp),
        agent_type="npc", custom_name=agent_id,
    )
    if not pkg:
        raise HTTPException(status_code=500, detail="Packaging failed")
    return {"status": "success", "package_path": str(pkg)}


@app.post("/api/agents/{agent_id}/cleanup")
async def cleanup_agent(agent_id: str, delete_brain: bool = False):
    if agent_id in agent_manager.agent_processes:
        agent_manager.stop_agent_process(agent_id)
    if delete_brain:
        bp = Config.get_agent_brain_path(agent_id)
        if bp.exists():
            bp.unlink()
    return {"status": "success", "agent_id": agent_id, "brain_deleted": delete_brain}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "agents_running": len(agent_manager.list_running_agents()),
        "uptime": asyncio.get_event_loop().time() - startup_time,
    }


@app.get("/health/detailed")
async def health_detailed():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    return {
        "status": "healthy",
        "uptime": asyncio.get_event_loop().time() - startup_time,
        "agents": agent_manager.list_running_agents(),
        "system": {
            "cpu_percent": cpu,
            "memory_percent": mem.percent,
            "memory_available_mb": mem.available / 1_048_576,
        },
    }


@app.get("/")
async def root():
    return {
        "service": "Divine World Management Server",
        "version": "3.0.0",
        "gui": "Open /gui in your browser for the graphical control centre",
        "running_agents": agent_manager.list_running_agents(),
    }


# =============================================================================
# chat_launcher helper (used when main.py is imported as a module)
# =============================================================================

def start_chat_interface(agent_id: str, brain_path: str,
                          config: Dict[str, Any]):
    """
    Launch the chat interface for a single agent.
    Starts uvicorn in a subprocess then opens the React frontend.
    """
    from ai_core.agent import NPCAgent
    agent = NPCAgent(agent_id)
    if Path(brain_path).exists():
        log.info(f"Loading brain: {brain_path}")
        agent.load(brain_path)
    else:
        log.warning("Brain not found — fresh state")

    backend_port = config.get("backend_port", Config.BASE_BACKEND_PORT)
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "py_backend.main:app",
         "--host", "0.0.0.0", "--port", str(backend_port)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    log.info(f"Backend on port {backend_port}")
    time.sleep(2)

    frontend_dir = Config.FRONTEND_DIR
    if frontend_dir.exists():
        if (frontend_dir / "dist").exists():
            subprocess.run(
                ["npx", "serve", "-s", "dist", "-p", "8765"],
                cwd=frontend_dir,
            )
        else:
            subprocess.run(["npm", "run", "dev"], cwd=frontend_dir)
    else:
        print(f"\nChat backend: http://localhost:{backend_port}")
        print("GUI control centre: http://localhost:{backend_port}/gui")
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        backend_proc.terminate()


# =============================================================================
# Entry point — asks CLI or GUI
# =============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Divine World Management Server"
    )
    parser.add_argument("--port",   type=int,  default=Config.BASE_BACKEND_PORT)
    parser.add_argument("--host",   type=str,  default="0.0.0.0")
    parser.add_argument("--reload", action="store_true")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--cli", action="store_true",
                             help="Skip prompt, run as CLI server")
    mode_group.add_argument("--gui", action="store_true",
                             help="Skip prompt, launch browser GUI")
    args = parser.parse_args()

    # ── mode selection ─────────────────────────────────────────────────
    if not args.cli and not args.gui:
        print()
        print("╔══════════════════════════════════════════╗")
        print("║   ⚔  Divine World Management Server     ║")
        print("╠══════════════════════════════════════════╣")
        print("║  [1]  CLI mode  — terminal server        ║")
        print("║  [2]  GUI mode  — open browser dashboard ║")
        print("╚══════════════════════════════════════════╝")
        print()
        choice = input("  Select mode [1/2]: ").strip()
        args.gui = choice == "2"

    if args.gui:
        print(f"\n🌐 Starting GUI server on http://{args.host}:{args.port}")
        print(f"   Opening control centre → http://localhost:{args.port}/gui\n")
        # Try to open browser after a short delay
        import threading
        def _open():
            time.sleep(2.5)
            import webbrowser
            webbrowser.open(f"http://localhost:{args.port}/gui")
        threading.Thread(target=_open, daemon=True).start()
    else:
        print(f"\n🖥  Starting CLI server on {args.host}:{args.port}\n")

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )