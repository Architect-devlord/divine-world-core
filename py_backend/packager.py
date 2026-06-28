# py_backend/packager.py
"""
Production agent packager.
===========================
Creates a self-contained .exe (via PyInstaller) for each agent, bundling:
  - config.json
  - React frontend (optional)
  - DivineWorld + DWClientBot mod jars (optional)
  - UltimMC launcher (optional, for Minecraft auto-join)

brain.pcap is NOT bundled into the exe — it lives next to the exe in the
{agent_id}/ folder and is read/written at runtime.  Bundling it would mean
auto-saves overwrite a copy inside _MEIPASS which gets discarded on exit.

Hidden-import list is read from Config.AGENT_HIDDEN_IMPORTS and the
exclusion list from Config.AGENT_EXCLUDE_MODULES — add new agent modules
or server-only exclusions there; no changes needed here.

Output layout
-------------
All output goes to:  npc_applications/{agent_id}/
  DW_{agent_id}          ← standalone executable
  brain.pcap             ← agent state (NOT inside the exe)
  brain.pcap.json        ← human-readable sidecar
  config.json            ← agent config
  frontend/              ← React dist (optional)
  mods/                  ← DivineWorld + DWClientBot jars (optional)
  UltimMC/               ← Minecraft launcher (optional)
  README.md

PyInstaller intermediate artefacts (dist/, build/, *.spec) are written to a
temp directory under npc_applications/.build_tmp/ and cleaned up afterwards
so they never pollute the project root or any other location.
"""

import os
import sys
import shutil
import json
import subprocess
import tempfile
from pathlib import Path
import time
from typing import Optional, Dict, Any
import logging

from frontend_builder import FrontendBuilder
from py_backend.config import Config
from py_backend.utils.mc_uuid import get_minecraft_uuid

log = logging.getLogger("packager")
log.setLevel(logging.INFO)

NPM_CMD = shutil.which("npm") or "npm"
frontend_builder = FrontendBuilder()


class AgentPackager:
    """Creates standalone executables for AI agents."""

    def __init__(self, output_dir: str = None):
        # ── Single canonical output root ──────────────────────────────────────
        # Everything goes to npc_applications/ (or the explicit override).
        # No fallback to CWD/dist, no relative paths.
        self.output_dir = Path(output_dir).resolve() if output_dir else Path(Config.NPC_APPLICATIONS_DIR).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # PyInstaller temp dir — lives inside output_dir so it stays contained
        self._build_tmp = self.output_dir / ".build_tmp"
        self._build_tmp.mkdir(parents=True, exist_ok=True)

        self.frontend_dir = self._find_frontend_dir()
        self.mod_jar      = self._find_mod_jar()
        self.client_jar   = Config.CLIENT_JAR
        self.ultimmc_path = self._find_ultimmc()

    # ------------------------------------------------------------------
    # Path discovery
    # ------------------------------------------------------------------

    def _find_frontend_dir(self) -> Optional[Path]:
        # Use Config.BASE_DIR (project root) so path is stable regardless of cwd
        root = Config.BASE_DIR
        # Config.FRONTEND_DIR is the canonical location
        if Config.FRONTEND_DIR.exists() and (Config.FRONTEND_DIR / "package.json").exists():
            log.info(f"✅ Frontend (Config): {Config.FRONTEND_DIR}")
            return Config.FRONTEND_DIR
        for path in [
            root / "dw_agent" / "electron" / "react-app",
            root / "dw_agent" / "react-app",
            root / "react-app",
            root / "frontend",
        ]:
            if path.exists() and (path / "package.json").exists():
                log.info(f"✅ Frontend: {path}")
                return path
        log.warning("⚠️  No frontend directory found")
        return None

    def _find_mod_jar(self) -> Optional[Path]:
        # Config.MOD_JAR is derived from __file__ so it's always correct
        if Config.MOD_JAR and Config.MOD_JAR.exists():
            log.info(f"✅ Mod jar (Config): {Config.MOD_JAR}")
            return Config.MOD_JAR
        root = Config.BASE_DIR
        for base in [
            root / "DivineWorld" / "build" / "libs",
            root / "DivineWorld" / "build" / "reobfJar" / "libs",
        ]:
            if not base.exists():
                continue
            for jar in sorted(base.glob("*.jar")):
                if "divine" in jar.name.lower() or "divineworld" in jar.name.lower():
                    log.info(f"✅ Mod jar: {jar}")
                    return jar
        return None

    def _find_ultimmc(self) -> Optional[Path]:
        """
        Locate UltimMC installation — cross-platform (Linux / Windows / macOS).

        Priority:
          0. agents.json  minecraft_path  (highest)
          1. DW_ULTIMMC_PATH env var
          2. Project root   UltimMC/
          3. Platform-specific user locations
          4. PATH fallback
          5. Interactive prompt (TTY only)
        """
        import platform as _plat
        _system = _plat.system()   # "Linux" | "Windows" | "Darwin"
        cwd     = Path.cwd()
        root    = cwd.parent if cwd.name == "py_backend" else cwd
        home    = Path.home()

        # ── 0. agents.json minecraft_path ────────────────────────────────────
        try:
            from py_backend.utils.mc_uuid import AgentNameManager
            mc_path = AgentNameManager.get_minecraft_path()
            if mc_path and mc_path.exists():
                log.info(f"✅ UltimMC from agents.json: {mc_path}")
                return mc_path
        except Exception:
            pass

        # ── 1. Env var ────────────────────────────────────────────────────────
        env_path = os.environ.get("DW_ULTIMMC_PATH")
        if env_path:
            p = Path(os.path.expandvars(os.path.expanduser(env_path)))
            if p.exists():
                log.info(f"✅ UltimMC from DW_ULTIMMC_PATH: {p}")
                return p
            log.warning(f"DW_ULTIMMC_PATH set but not found: {p}")

        # ── 2. Project-relative ───────────────────────────────────────────────
        candidates = [root / "UltimMC"]

        # ── 3. Platform-specific ─────────────────────────────────────────────
        if _system == "Windows":
            appdata      = Path(os.environ.get("APPDATA", str(home)))
            localappdata = Path(os.environ.get("LOCALAPPDATA", str(home)))
            candidates += [
                home / "UltimMC",
                home / "Desktop"   / "UltimMC",
                home / "Downloads" / "UltimMC",
                appdata      / "UltimMC",
                localappdata / "UltimMC",
                Path("C:/UltimMC"),
                Path("C:/Program Files/UltimMC"),
            ]
        elif _system == "Darwin":
            candidates += [
                Path("/Applications/UltimMC.app/Contents/MacOS"),
                home / "Applications/UltimMC.app/Contents/MacOS",
                home / "UltimMC.app/Contents/MacOS",
                home / "UltimMC",
                Path("/Applications/UltimMC.app"),
                home / "Applications/UltimMC.app",
            ]
        else:  # Linux
            candidates += [
                home / "UltimMC",
                home / ".ultimmc",
                home / ".local" / "share" / "ultimmc",
                home / ".local" / "bin" / "UltimMC",
                Path("/opt/ultimmc"),
                Path("/opt/UltimMC"),
                Path("/usr/local/bin/ultimmc"),
            ]

        def _has_executable(path: Path) -> bool:
            """Check if path contains a valid UltimMC executable."""
            if _system == "Windows":
                hints = [path / "bin" / "UltimMC.exe", path / "UltimMC.exe"]
            elif _system == "Darwin":
                hints = [
                    path / "bin" / "UltimMC",
                    path / "UltimMC",
                    # If path IS the MacOS dir inside the .app bundle:
                    path / "UltimMC" if path.name == "MacOS" else path / "Contents" / "MacOS" / "UltimMC",
                ]
            else:
                hints = [path / "bin" / "UltimMC", path / "UltimMC"]
            return any(h.exists() for h in hints)

        for path in candidates:
            if not path.exists():
                continue
            if path.is_file() and os.access(path, os.X_OK):
                log.info(f"✅ UltimMC: {path.parent}")
                return path.parent
            if path.is_dir() and _has_executable(path):
                log.info(f"✅ UltimMC: {path}")
                return path

        # ── 4. PATH fallback ──────────────────────────────────────────────────
        exe = shutil.which("ultimmc") or shutil.which("UltimMC")
        if exe:
            exe_path     = Path(exe)
            install_root = exe_path.parent.parent if exe_path.parent.name == "bin" else exe_path.parent
            log.info(f"✅ UltimMC found in PATH: {install_root}")
            return install_root

        # ── 5. Interactive prompt (TTY only) ──────────────────────────────────
        import sys as _sys
        if not _sys.stdin.isatty():
            log.warning(
                "⚠️  UltimMC not found and stdin is not a TTY — "
                "skipping interactive prompt. Set DW_ULTIMMC_PATH or "
                "add minecraft_path to agents.json."
            )
            return None

        log.warning("⚠️  UltimMC not found in standard locations")
        print("\n" + "="*70)
        print("UltimMC Launcher Not Found")
        print("="*70)
        print("\nSearched locations:")
        for cand in candidates[:6]:
            print(f"  • {cand}")
        if _system == "Windows":
            print("  (and %APPDATA%/UltimMC, %LOCALAPPDATA%/UltimMC)")
        print()

        while True:
            try:
                user_path = input(
                    "Enter the absolute path to your UltimMC folder "
                    "(or press Enter to skip): "
                ).strip()
            except EOFError:
                log.warning("⚠️  UltimMC prompt got EOF — skipping")
                return None

            if not user_path:
                env_p = os.getenv("DW_ULTIMMC_PATH")
                if env_p:
                    user_path = env_p
                else:
                    log.warning("⚠️  UltimMC will not be packaged with agents")
                    print("Continuing without UltimMC...\n")
                    return None

            ultimmc_candidate = Path(user_path).expanduser().resolve()

            if not ultimmc_candidate.exists():
                print(f"❌ Path does not exist: {ultimmc_candidate}")
                print("Please enter a valid path.\n")
                continue

            if not _has_executable(ultimmc_candidate):
                print(f"❌ Not a valid UltimMC installation at: {ultimmc_candidate}")
                if _system == "Windows":
                    print(f"   Expected: bin\\UltimMC.exe  or  UltimMC.exe")
                elif _system == "Darwin":
                    print(f"   Expected: bin/UltimMC  or  Contents/MacOS/UltimMC")
                else:
                    print(f"   Expected: bin/UltimMC  or  UltimMC")
                print()
                continue

            log.info(f"✅ UltimMC: {ultimmc_candidate}")
            print(f"✅ UltimMC found at: {ultimmc_candidate}\n")
            return ultimmc_candidate

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def package_agent(
        self,
        agent_id:           str,
        brain_capsule_path: str,
        agent_name:         Optional[str] = None,
        gender:             str = "neutral",
        agent_type:         str = "npc",
        # FIX (Consolidate Duplicate Implementations plan, Step 5): mode was
        # missing entirely — the packaged executable had no way to know
        # whether it should run as chat/minecraft/autonomous, so launch()
        # always did the same bare-NPCAgent-plus-FastAPI thing regardless.
        # Mirrors run_standalone_agent()'s own `mode` parameter semantics
        # exactly (agent.py) — not to be confused with agent_type above,
        # which is the god-type concept (npc/wither/oracle/etc), a
        # completely separate axis.
        mode:                str = "minecraft",
        icon_path:          Optional[str] = None,
        include_frontend:   bool = True,
        include_mod:        bool = True,
        include_client_jar: bool = True,
        backend_port:       int  = 11400,
        agent=None,         # live NPCAgent; used to auto-save brain if .pcap missing
    ) -> Dict[str, str]:
        """Build a self-contained executable for an agent."""
        log.info(f"📦 Packaging {agent_id} (type={agent_type}, gender={gender}, mode={mode})")

        if mode not in ('chat', 'minecraft', 'autonomous'):
            log.warning(f"Unknown mode '{mode}' — falling back to 'minecraft'")
            mode = 'minecraft'

        brain_path = Path(brain_capsule_path)
        if not brain_path.exists():
            raise FileNotFoundError(f"Brain capsule not found: {brain_capsule_path}")

        brain_size = brain_path.stat().st_size
        if brain_size > Config.MAX_BRAIN_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Brain too large: {brain_size / (1024*1024):.1f} MB")
        if brain_size < 100:
            raise ValueError(f"Brain suspiciously small: {brain_size} bytes")

        # ── All agent files land in output_dir/{agent_id}/ ────────────────────
        agent_dir = self.output_dir / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Derive a clean Minecraft username
        # Resolve Minecraft display name from agents.json — no DW_ / DWGOD_ prefix
        from py_backend.utils.mc_uuid import AgentNameManager as _ANM
        minecraft_name = _ANM().resolve_display_name(agent_id, agent_name)

        agent_uuid = get_minecraft_uuid(minecraft_name)

        # ── UltimMC setup ──────────────────────────────────────────────
        if self.ultimmc_path:
            self._setup_ultimmc(agent_id, agent_dir, agent_uuid, minecraft_name)

        # ── Copy brain capsule ─────────────────────────────────────────
        self._copy_brain_capsule(brain_path, agent_dir, gender, agent_type, agent=agent)

        # ── React frontend ─────────────────────────────────────────────
        frontend_included = False
        if include_frontend and self.frontend_dir:
            frontend_dest = agent_dir / "frontend"
            if frontend_builder.build_frontend(self.frontend_dir, frontend_dest):
                frontend_included = True
            else:
                log.warning("⚠️  Frontend build failed — continuing without")

        # ── Mods ───────────────────────────────────────────────────────
        mod_included = False
        if include_mod:
            mods_dest = agent_dir / "mods"
            mods_dest.mkdir(parents=True, exist_ok=True)
            if self.mod_jar:
                try:
                    shutil.copy(self.mod_jar, mods_dest / self.mod_jar.name)
                    mod_included = True
                    log.info(f"✓ DivineWorld mod included")
                except Exception as e:
                    log.warning(f"DivineWorld mod copy failed: {e}")
            if include_client_jar and self.client_jar:
                try:
                    shutil.copy(self.client_jar, mods_dest / Path(self.client_jar).name)
                    mod_included = True
                    log.info(f"✓ DWClientBot mod included")
                except Exception as e:
                    log.warning(f"DWClientBot copy failed: {e}")

        # ── Launcher + config ─────────────────────────────────────────
        launcher_path = self._create_launcher(
            agent_id, agent_dir, frontend_included, agent_type,
            backend_port, minecraft_name, mode,
        )
        config_path = self._create_config(agent_id, agent_dir, gender, agent_type, backend_port, mode)

        # ── Build .exe ────────────────────────────────────────────────
        exe_path     = self._build_executable(agent_id, launcher_path, agent_dir, icon_path, frontend_included)
        package_path = self._create_portable_package(agent_id, agent_dir, exe_path, frontend_included)

        log.info(f"✅ Packaged: {package_path / exe_path.name}")
        return {
            "agent_id":    agent_id,
            "exe_path":    str(package_path / exe_path.name),
            "package_path":str(package_path),
            "brain_path":  str(agent_dir / "brain.pcap"),
            "config_path": str(config_path),
            "has_frontend":frontend_included,
            "has_mod":     mod_included,
            "gender":      gender,
            "agent_type":  agent_type,
            "backend_port":backend_port,
        }

    # ------------------------------------------------------------------
    # UltimMC
    # ------------------------------------------------------------------

    def _setup_ultimmc(self, agent_id: str, agent_dir: Path,
                       agent_uuid: str, minecraft_name: str):
        """Clone UltimMC into the agent directory and configure it."""
        import uuid as uuid_mod
        ultimmc_dest = agent_dir / "UltimMC"
        shutil.copytree(self.ultimmc_path, ultimmc_dest, dirs_exist_ok=True)

        # accounts.json may be in bin/ (Linux/Windows) or in the app root (macOS)
        import platform as _plat2
        _bin = ultimmc_dest / "bin"
        if not _bin.exists() and _plat2.system() == "Darwin":
            _bin = ultimmc_dest / "Contents" / "MacOS"
        _bin.mkdir(parents=True, exist_ok=True)
        accounts_file = _bin / "accounts.json"
        if accounts_file.exists():
            with open(accounts_file) as f:
                data = json.load(f)
            for acc in data.get("accounts", []):
                acc["active"] = False
            data.setdefault("accounts", []).append({
                "active": True,
                "profile": {
                    "capes": [],
                    "id":    agent_uuid,
                    "name":  minecraft_name,
                    "skin":  {"id": "", "url": "", "variant": ""},
                },
                "type": "Local",
                "ygg": {
                    "extra": {
                        "clientToken": str(uuid_mod.uuid4()),
                        "userName":    minecraft_name,
                    },
                    "iat": int(time.time()),
                },
            })
            with open(accounts_file, 'w') as f:
                json.dump(data, f, indent=2)

        instance_src = self.ultimmc_path / "instances" / "1.20.1"
        if instance_src.exists():
            instance_dest = ultimmc_dest / "instances" / agent_id
            shutil.copytree(instance_src, instance_dest, dirs_exist_ok=True)
            mods_dir = instance_dest / ".minecraft" / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)
            if self.mod_jar:
                shutil.copy(self.mod_jar,    mods_dir / self.mod_jar.name)
            if self.client_jar:
                shutil.copy(self.client_jar, mods_dir / Path(self.client_jar).name)

    # ------------------------------------------------------------------
    # Brain copy
    # ------------------------------------------------------------------

    def _copy_brain_capsule(self, brain_path: Path, agent_dir: Path,
                             gender: str, agent_type: str, agent=None):
        """
        Copy brain.pcap to agent_dir.
        If the file doesn't exist yet (e.g. a god agent that was just spawned
        but never called agent.save()), call agent.save() first to produce it.
        """
        if not brain_path.exists():
            if agent is not None:
                log.info(f"Brain not found at {brain_path} — saving now before packaging...")
                try:
                    agent.save(str(brain_path))
                    log.info(f"Brain saved: {brain_path}")
                except Exception as e:
                    raise FileNotFoundError(
                        f"Brain capsule missing and auto-save failed: {brain_path}: {e}"
                    ) from e
            else:
                raise FileNotFoundError(
                    f"Brain capsule not found: {brain_path}\n"
                    f"Call agent.save() before packaging, or pass agent= to package_agent()."
                )
        brain_dest = agent_dir / "brain.pcap"
        shutil.copy(brain_path, brain_dest)

        resolved_gender = gender
        try:
            import torch as _torch
            data = _torch.load(brain_path, map_location='cpu', weights_only=False)
            cap_gender = data.get('gender') or (data.get('personality') or {}).get('gender')
            if cap_gender and cap_gender != "neutral":
                resolved_gender = cap_gender
                log.info(f"Gender resolved from brain capsule: {resolved_gender}")
        except Exception as eg:
            log.debug(f"Could not read gender from brain capsule: {eg}")

        brain_json = brain_path.with_suffix('.pcap.json')
        if brain_json.exists():
            with open(brain_json) as f:
                data = json.load(f)
            data.setdefault('metadata', {})['gender'] = resolved_gender
            data['metadata']['agent_type'] = agent_type
            if 'gender' in data:
                data['gender'] = resolved_gender
            with open(agent_dir / "brain.pcap.json", 'w') as f:
                json.dump(data, f, indent=2)

        log.info(f"✓ Brain capsule copied (gender={resolved_gender})")

    # ------------------------------------------------------------------
    # Launcher script
    # ------------------------------------------------------------------

    def _create_launcher(self, agent_id: str, agent_dir: Path,
                          has_frontend: bool, agent_type: str,
                          backend_port: int, minecraft_name: str,
                          mode: str = "minecraft") -> Path:
        """
        Generate launcher.py.

        FIX (Consolidate Duplicate Implementations plan, Step 5): mode was
        previously not a parameter at all — the generated launcher always
        constructed a bare NPCAgent and started only the FastAPI server,
        regardless of whether this was meant to be a chat/minecraft/
        autonomous deployment. See launch()'s body below for the actual
        mode-aware dispatch (chat -> start_autonomous_speech(), minecraft/
        autonomous -> start_autonomous_mode()/CognitiveLoop).

        When frozen (sys.frozen=True):
          - BASE_DIR  = sys._MEIPASS   (extracted bundle, read-only)
          - AGENT_DIR = directory containing the .exe  (writable, has brain.pcap)
          sys.path gets both so `import ai_core` and `from ai_core.x import y` both work.

        When run as plain Python (dev/debug):
          - BASE_DIR  = two levels up from launcher.py
                        i.e. divine-world-core/  (project root)
          - AGENT_DIR = directory containing launcher.py
                        i.e. npc_applications/{agent_id}/
          sys.path gets project root so ai_core, py_backend, rl are all importable.
        """
        sep = '=' * 60
        launcher_code = f'''"""
DW Agent Launcher — {agent_id} ({minecraft_name})
Type: {agent_type}
"""

import sys, os, socket, shutil, subprocess
from pathlib import Path

if getattr(sys, 'frozen', False):
    # ── Frozen (PyInstaller .exe) ─────────────────────────────────────
    BASE_DIR  = Path(sys._MEIPASS)          # extracted bundle (read-only)
    AGENT_DIR = Path(sys.executable).parent # folder containing the .exe
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / "ai_core"))
    sys.path.insert(0, str(BASE_DIR / "py_backend"))
    sys.path.insert(0, str(BASE_DIR / "rl"))
    sys.path.insert(0, str(BASE_DIR / "py_backend" / "utils"))
else:
    # ── Plain Python (dev / debug) ────────────────────────────────────
    # launcher.py is a DEV convenience — it requires the divine-world-core
    # project source to be present on this machine.
    #
    # If you're on a different machine with no project source, use the
    # standalone executable instead:
    #   Linux/macOS : ./DW_{agent_id}
    #   Windows     : DW_{agent_id}.exe
    #
    # We search for the project root by walking UP from AGENT_DIR until
    # we find a directory containing 'ai_core/', rather than assuming a
    # fixed number of parent levels.  This means the package can sit
    # anywhere in the filesystem and still work when run inside the
    # original dev tree.
    AGENT_DIR = Path(__file__).resolve().parent

    def _find_project_root(start: Path) -> Path:
        """Walk upward from start until ai_core/ is found."""
        current = start
        for _ in range(10):   # don't walk past filesystem root
            if (current / "ai_core").is_dir():
                return current
            if current.parent == current:
                break
            current = current.parent
        return None

    PROJECT_ROOT = _find_project_root(AGENT_DIR)

    if PROJECT_ROOT is None:
        print("=" * 60)
        print("  ERROR: launcher.py requires the divine-world-core source.")
        print()
        print("  ai_core/ was not found anywhere above this folder.")
        print("  This means you are on a machine without the project source.")
        print()
        print("  Use the standalone executable instead:")
        print(f"    ./{agent_id}          (Linux/macOS)")
        print(f"    {agent_id}.exe        (Windows)")
        print()
        print("  The exe requires no Python and runs anywhere.")
        print("=" * 60)
        sys.exit(1)

    sys.path.insert(0, str(PROJECT_ROOT))
    sys.path.insert(0, str(PROJECT_ROOT / "ai_core"))
    sys.path.insert(0, str(PROJECT_ROOT / "py_backend"))
    sys.path.insert(0, str(PROJECT_ROOT / "rl"))
    sys.path.insert(0, str(PROJECT_ROOT / "py_backend" / "utils"))
    BASE_DIR = PROJECT_ROOT

import json, logging, time, threading, webbrowser

AGENT_ID       = "{agent_id}"
MINECRAFT_NAME = "{minecraft_name}"
AGENT_TYPE     = "{agent_type}"
# FIX (Consolidate Duplicate Implementations plan, Step 5): MODE was missing
# entirely — launch() always did the same bare-NPCAgent-plus-FastAPI thing
# regardless of chat/minecraft/autonomous. Baked in at packaging time, but
# (matching how BACKEND_PORT below already works) load_config() at the
# bottom of this file lets a user override it post-packaging by editing
# config.json directly, without needing to repackage.
MODE           = "{mode}"
BRAIN_PATH     = AGENT_DIR / "brain.pcap"
CONFIG_PATH    = AGENT_DIR / "config.json"
FRONTEND_PATH  = AGENT_DIR / "frontend"
HAS_FRONTEND   = {has_frontend}
BACKEND_PORT   = {backend_port}

logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] %(levelname)s - %(message)s')
log = logging.getLogger("launcher")


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {{"agent_id": AGENT_ID, "backend_port": BACKEND_PORT,
             "mode": MODE, "default_server": "127.0.0.1:25565"}}


def is_server_up(host, port, timeout=2.0):
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def start_backend(port):
    log.info(f"Starting backend on port {{port}}…")
    try:
        import uvicorn
        try:
            # FIX: 'from agent import app' fails in frozen mode because
            # the file is at _MEIPASS/ai_core/agent.py, not _MEIPASS/agent.py.
            # Both frozen and dev paths use the ai_core.agent import since
            # sys._MEIPASS/ai_core is already in sys.path (added above).
            from ai_core.agent import app as _agent_app
        except ImportError:
            from agent import app as _agent_app  # fallback if path differs
        t = threading.Thread(
            target=lambda: uvicorn.run(_agent_app, host="127.0.0.1", port=port, log_level="error"),
            daemon=True,
        )
        t.start()
        time.sleep(1.5)
        log.info(f"✅ Backend at http://127.0.0.1:{{port}}")
        return True
    except Exception as e:
        log.error(f"Backend failed: {{e}}")
        return False


def try_ultimmc(server_addr, agent_name):
    ultimmc_dir = (AGENT_DIR / "UltimMC").resolve()
    ult = ultimmc_dir / "bin" / "UltimMC"
    if not ult.exists():
        log.warning(f"UltimMC not found at {{ult}} — manual Minecraft setup required")
        return False
    try:
        log.info(f"Launching UltimMC: instance={{AGENT_ID}}, name={{agent_name}}, server={{server_addr}}")
        subprocess.Popen([
            str(ult),
            "-d", str(ultimmc_dir),
            "-l", AGENT_ID,
            "-s", server_addr,
            "-a", agent_name,
            "-o",
            "-n", agent_name,
        ], cwd=str(ultimmc_dir))
        time.sleep(2)
        log.info(f"✅ UltimMC launched (instance={{AGENT_ID}})")
        return True
    except Exception as e:
        log.error(f"UltimMC launch failed: {{e}}")
        return False


def _run_async_loop(coro_fn):
    """
    Run an async agent loop method (start_autonomous_mode / start_autonomous_
    speech — both async def, both expected to run until stopped) on its own
    background thread with a private event loop.

    FIX (Consolidate Duplicate Implementations plan, Step 5): launch() itself
    is synchronous (mirrors start_backend()'s own daemon-thread pattern just
    above for uvicorn) — neither of those coroutines can simply be awaited
    inline here. Returns the Thread so launch()'s shutdown path can join it
    briefly, though both loops are cooperative (flag-based) and the thread is
    already a daemon, so the process exiting cleans it up regardless.
    """
    def _runner():
        import asyncio as _asyncio
        loop = _asyncio.new_event_loop()
        _asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(coro_fn())
        except Exception as e:
            log.error(f"Background agent loop failed: {{e}}")
    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    return t


def _serve_frontend(backend_port):
    """Serve the bundled frontend over HTTP and open it in the default browser."""
    import http.server, socketserver
    fp = backend_port + 1
    class H(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(FRONTEND_PATH), **kw)
        def log_message(self, *a): pass
    t = threading.Thread(
        target=lambda: socketserver.TCPServer(("", fp), H).__enter__().serve_forever(),
        daemon=True,
    )
    t.start()
    time.sleep(1)
    webbrowser.open(f"http://localhost:{{fp}}")


def launch():
    cfg            = load_config()
    backend_port   = cfg.get('backend_port', BACKEND_PORT)
    # FIX (Consolidate Duplicate Implementations plan, Step 5): read mode
    # from config.json with the baked-in MODE constant as fallback — same
    # pattern backend_port already uses, so editing config.json post-
    # packaging can change mode without repackaging.
    mode = cfg.get('mode', MODE)
    if mode not in ('chat', 'minecraft', 'autonomous'):
        log.warning(f"Unknown mode '{{mode}}' in config — falling back to 'minecraft'")
        mode = 'minecraft'
    default_server = cfg.get('default_server', '127.0.0.1:25565')
    srv_host, srv_port = (default_server.split(':') + ['25565'])[:2]

    log.info(f"Loading brain from {{BRAIN_PATH}}… (mode={{mode}})")
    if getattr(sys, 'frozen', False):
        from agent          import NPCAgent
        from brain_language import add_language_to_brain
    else:
        from ai_core.agent          import NPCAgent
        from ai_core.brain_language import add_language_to_brain

    # FIX (Consolidate Duplicate Implementations plan, Step 5): was a bare
    # NPCAgent(AGENT_ID) — mode/god_type were never passed at all, so this
    # constructor call was identical regardless of what kind of agent or
    # deployment this was supposed to be. Mirrors run_standalone_agent()'s
    # own construction call (agent.py) exactly, including the same
    # autonomous=(mode=='autonomous') convention — that flag only controls
    # whether CognitiveLoop is eagerly pre-built during __init__; the actual
    # mode-specific loop is started explicitly below regardless, since
    # start_autonomous_mode() builds CognitiveLoop itself on demand if it
    # isn't already there.
    agent = NPCAgent(
        AGENT_ID,
        mode=mode,
        god_type=(AGENT_TYPE if AGENT_TYPE != 'npc' else None),
        autonomous=(mode == 'autonomous'),
    )
    if BRAIN_PATH.exists():
        try:
            agent.load(str(BRAIN_PATH))
            log.info("✅ Brain loaded")
        except Exception as e:
            log.error(f"Brain load failed: {{e}}")

    if not getattr(getattr(agent, 'brain', None), 'language', None):
        add_language_to_brain(agent.brain)
        log.info("✅ Language initialised")

    if not start_backend(backend_port):
        sys.exit(1)

    # ── Mode-specific engagement loop ───────────────────────────────────
    # FIX (Consolidate Duplicate Implementations plan, Step 5): this is the
    # actual core fix — the packaged executable previously started nothing
    # beyond the bare FastAPI server, regardless of mode. chat mode gets the
    # lightweight start_autonomous_speech() loop (agent.py) — NOT
    # CognitiveLoop, which is built around Minecraft's perceive/deliberate
    # cycle and has no meaning for a text-only deployment. minecraft and
    # autonomous modes both get start_autonomous_mode() (CognitiveLoop) —
    # the difference between them is what act() ends up calling (Minecraft
    # actions vs. hardware/controller actions), not whether the loop runs.
    if mode == 'chat':
        _run_async_loop(agent.start_autonomous_speech)
        log.info("💬 Chat mode — autonomous speech engagement loop running")
    else:
        _run_async_loop(agent.start_autonomous_mode)
        log.info(f"🧠 {{mode}} mode — CognitiveLoop running")

    # ── Minecraft server detection — minecraft mode only ────────────────
    # FIX: was unconditional (always ran is_server_up()/try_ultimmc(),
    # regardless of mode) — chat and autonomous deployments have no
    # Minecraft server to look for at all.
    if mode == 'minecraft':
        server_up = is_server_up(srv_host, int(srv_port))
        if server_up:
            print(f"🎮 Server detected at {{default_server}}")
            if not try_ultimmc(default_server, MINECRAFT_NAME):
                log.info("Manual Minecraft join required — see README")
                print(f"\\n  ⚠️  UltimMC launch failed. Manual setup needed:")
                print(f"  Add JVM arg: -Ddw.backend=http://127.0.0.1:{{backend_port}}")
            else:
                print(f"🚀 Minecraft launching (allow 30-60 seconds for first load)...")
        elif HAS_FRONTEND and FRONTEND_PATH.exists():
            _serve_frontend(backend_port)
    elif HAS_FRONTEND and FRONTEND_PATH.exists():
        _serve_frontend(backend_port)

    print(f"\\n{sep}\\n  ✅ {{AGENT_ID}} RUNNING ({{mode}} mode)\\n  Backend: http://localhost:{{backend_port}}")
    if HAS_FRONTEND:
        print(f"  Frontend: http://localhost:{{backend_port + 1}}")
    print("  Ctrl+C to stop\\n{sep}")

    try:
        last_save = time.time()
        while True:
            time.sleep(1)
            if time.time() - last_save >= 300:
                try:
                    agent.save(str(BRAIN_PATH))
                    log.info("💾 Auto-saved")
                    last_save = time.time()
                except Exception as e:
                    log.error(f"Auto-save failed: {{e}}")
    except KeyboardInterrupt:
        log.info("Saving before exit…")
        # FIX: stop the background engagement loop cleanly before saving —
        # both start_autonomous_mode()/start_autonomous_speech() are
        # cooperative (flag-based) loops; this lets the current tick finish
        # rather than yanking the thread out from under an in-flight save.
        try:
            import asyncio as _asyncio
            if mode == 'chat':
                agent._autonomous_speech_running = False
            elif agent.cognitive_loop is not None:
                agent.cognitive_loop.running = False
        except Exception:
            pass
        try:
            agent.save(str(BRAIN_PATH))
            log.info("✅ Saved")
        except Exception as e:
            log.error(f"Save failed: {{e}}")


if __name__ == "__main__":
    try:
        if not BRAIN_PATH.exists():
            log.error(f"Brain not found: {{BRAIN_PATH}}")
            sys.exit(1)
        launch()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        log.exception(f"Fatal: {{e}}")
        sys.exit(1)
'''

        launcher_path = agent_dir / "launcher.py"
        launcher_path.write_text(launcher_code, encoding='utf-8')
        log.info("✓ Launcher created")
        return launcher_path

    # ------------------------------------------------------------------
    # Config file
    # ------------------------------------------------------------------

    def _create_config(self, agent_id: str, agent_dir: Path, gender: str,
                        agent_type: str, backend_port: int,
                        mode: str = "minecraft") -> Path:
        config = {
            "agent_id":      agent_id,
            "agent_type":    agent_type,
            # FIX (Consolidate Duplicate Implementations plan, Step 5):
            # was missing — the launcher had no config-level way to know
            # which of chat/minecraft/autonomous it should run as.
            "mode":          mode,
            "gender":        gender,
            "version":       "2.1.0",
            "default_server":"127.0.0.1:25565",
            "backend_port":  backend_port,
            "frontend_port": backend_port + 1,
            "modes":  {"chat": True, "controller": True, "headless": True},
            "features": {
                "language_intelligence": True,
                "pattern_recognition":  True,
                "multimodal_learning":  True,
                "auto_save":            True,
                "breeding":             True,
            },
        }
        config_path = agent_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        return config_path

    # ------------------------------------------------------------------
    # PyInstaller
    # ------------------------------------------------------------------

    def _build_executable(self, agent_id: str, launcher_path: Path,
                           agent_dir: Path, icon_path: Optional[str],
                           has_frontend: bool) -> Path:
        """
        Run PyInstaller with all output redirected to self._build_tmp.

        --distpath  → _build_tmp/dist/   (where PyInstaller drops the exe)
        --workpath  → _build_tmp/build/  (intermediate object files)
        --specpath  → _build_tmp/        (generated .spec file)

        After a successful build the exe is moved to agent_dir/ so it is
        co-located with brain.pcap / config.json before _create_portable_package
        copies everything to the final package folder.
        """
        log.info(f"🔨 Building executable for {agent_id}…")
        exe_name = agent_id   # no DW_ prefix — matches main.py exe_path lookup

        # FIX (crash-level bug): ai_core_path/py_backend_path were used 20 lines
        # before they were assigned, throwing UnboundLocalError on every single
        # packaging attempt before PyInstaller even ran.  Move the assignments
        # first so every reference below has a value.
        root            = Config.BASE_DIR
        py_backend_path = Config.PY_BACKEND_DIR
        ai_core_path    = Config.AI_CORE_DIR       # PY_BACKEND_DIR / "ai_core"

        # ── Pre-flight validation ─────────────────────────────────────────
        # Catch misconfiguration early rather than letting PyInstaller produce
        # an exe that silently crashes at runtime due to missing imports.
        preflight_warnings = []
        if not Config.AGENT_HIDDEN_IMPORTS:
            preflight_warnings.append("AGENT_HIDDEN_IMPORTS is empty — exe may be missing modules")
        if not ai_core_path.exists():
            raise FileNotFoundError(f"ai_core/ not found: {ai_core_path}")
        if not py_backend_path.exists():
            raise FileNotFoundError(f"py_backend/ not found: {py_backend_path}")
        # Validate every hidden import resolves from the known source paths
        import importlib.util as _ilu
        bad_imports = []
        for mod in (Config.AGENT_HIDDEN_IMPORTS or []):
            if _ilu.find_spec(mod) is None:
                bad_imports.append(mod)
        if bad_imports:
            preflight_warnings.append(
                f"These hidden imports cannot be found (exe will crash on import): "
                f"{bad_imports}"
            )
        for warn in preflight_warnings:
            log.warning(f"⚠️  Pre-flight: {warn}")

        # USER FIX: rl is inside py_backend, not at the project root
        rl_path    = py_backend_path / "rl"
        utils_path = py_backend_path / "utils"

        # ── Directories for PyInstaller intermediate/output ────────────
        dist_dir  = self._build_tmp / "dist"
        build_dir = self._build_tmp / "build"
        spec_dir  = self._build_tmp
        dist_dir.mkdir(parents=True, exist_ok=True)
        build_dir.mkdir(parents=True, exist_ok=True)

        args = [
            'pyinstaller', '--name', exe_name,
            # --onedir not --onefile: PyTorch's libtorch_cpu.so is ~2 GB and
            # zlib cannot decompress it at runtime (error code -1).
            # --onedir skips compression entirely — all .so/.dll stay as files.
            '--onedir', '--clean', '--noconfirm', '--console',
            # Tell PyInstaller exactly where to put everything
            '--distpath', str(dist_dir),
            '--workpath', str(build_dir),
            '--specpath', str(spec_dir),
            # Source search paths
            '--paths', str(root),
            '--paths', str(ai_core_path),
            '--paths', str(py_backend_path),
            '--paths', str(py_backend_path / "utils"),
        ]
        if rl_path.exists():
            args.extend(['--paths', str(rl_path)])

        # Hidden imports — agent-only modules defined in Config
        for module in Config.AGENT_HIDDEN_IMPORTS:
            args.extend(['--hidden-import', module])

        # Exclude server-manager modules
        for module in Config.AGENT_EXCLUDE_MODULES:
            args.extend(['--exclude-module', module])

        # ── Data files bundled into the exe ───────────────────────────
        # NOTE: brain.pcap is intentionally NOT included here.
        # It lives next to the exe and is read/written at runtime via AGENT_DIR.
        # Bundling it would mean auto-saves go into _MEIPASS (a temp dir that
        # disappears on exit), so the brain would never persist.
        data = [
            (agent_dir / "config.json", '.'),
        ]
        if has_frontend and (agent_dir / "frontend").exists():
            data.append((agent_dir / "frontend", 'frontend'))

        # Source trees bundled into the exe.
        # FIX (flagged multiple rounds, now actually removed): ai_core_path is
        # Config.AI_CORE_DIR = PY_BACKEND_DIR / "ai_core" — a direct subdirectory
        # of py_backend_path. Bundling py_backend_path at 'py_backend' already
        # includes py_backend/ai_core/ verbatim. The extra
        #   data.append((ai_core_path, 'ai_core'))
        # that previously followed created a SECOND copy at the bundle root
        # ('ai_core/' alongside 'py_backend/'), adding dead weight (identical
        # files twice) without any benefit — imports work fine through the
        # 'py_backend/ai_core' copy since the launcher's sys.path already
        # adds py_backend/ before ai_core/ is ever resolved as a bare module.
        data.append((py_backend_path, 'py_backend'))
        if rl_path.exists():
            data.append((rl_path,     'rl'))
        if utils_path.exists():
            data.append((utils_path,  'py_backend/utils'))

        for src, dst in data:
            args.extend(['--add-data', f'{src}{os.pathsep}{dst}'])

        if icon_path and Path(icon_path).exists():
            args.extend(['--icon', icon_path])

        args.append(str(launcher_path))

        log.info("Running PyInstaller… (this may take 30–60 s)")
        try:
            subprocess.run(args, check=True, capture_output=True,
                           text=True, timeout=3000,
                           start_new_session=True)   # isolate from parent SIGINT
        except subprocess.CalledProcessError as e:
            log.error(f"PyInstaller failed:\n{e.stdout}\n{e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            log.error("PyInstaller timed out")
            raise

        exe_name_full = f"{exe_name}.exe" if sys.platform == "win32" else exe_name

        # --onedir: PyInstaller outputs dist/{exe_name}/ (a folder, not a single file).
        # The actual executable is dist/{exe_name}/{exe_name}[.exe].
        # Move the whole folder into agent_dir/bin/ so every .so/.dll travels
        # with the exe — this is what lets it run without decompression.
        onedir_folder = dist_dir / exe_name
        if not onedir_folder.exists():
            raise FileNotFoundError(
                f"PyInstaller onedir folder not found: {onedir_folder}\n"
                f"Contents of dist_dir: {list(dist_dir.iterdir()) if dist_dir.exists() else 'missing'}"
            )

        bin_dest = agent_dir / "bin"
        if bin_dest.exists():
            shutil.rmtree(bin_dest)
        shutil.move(str(onedir_folder), str(bin_dest))

        final_exe = bin_dest / exe_name_full
        if not final_exe.exists():
            raise FileNotFoundError(f"Executable not found inside bin/: {final_exe}")

        log.info(f"✅ Executable: {final_exe} ({final_exe.stat().st_size / (1024*1024):.1f} MB)")
        return final_exe

    # ------------------------------------------------------------------
    # Portable package
    # ------------------------------------------------------------------

    def _create_portable_package(self, agent_id: str, agent_dir: Path,
                                   exe_path: Path, has_frontend: bool) -> Path:
        """
        Assemble the final portable folder at output_dir/{agent_id}/.

        agent_dir is already output_dir/{agent_id}/ — the exe was moved there
        by _build_executable, so most files are already in place.
        We just need to ensure UltimMC, mods, and frontend are present.
        """
        pkg_dir = self.output_dir / agent_id
        pkg_dir.mkdir(parents=True, exist_ok=True)

        # exe + brain + config are already in agent_dir == pkg_dir
        # (agent_dir IS pkg_dir — same path)
        # Nothing to copy for those; just assert they're there.
        for required in [exe_path, agent_dir / "brain.pcap", agent_dir / "config.json"]:
            if not required.exists():
                log.warning(f"⚠️  Expected file missing in package: {required}")

        # Read backend_port for README
        backend_port = 11400
        try:
            config_path = agent_dir / "config.json"
            if config_path.exists():
                with open(config_path) as f:
                    cfg = json.load(f)
                    backend_port = cfg.get("backend_port", 11400)
        except Exception as e:
            log.warning(f"Could not read backend_port from config: {e}")

        # mods/ — already copied into agent_dir during package_agent()
        # frontend/ — same
        # UltimMC/ — same

        readme = f"""# {agent_id} — Divine World AI Agent (v2.1.0)

## Quick Start
1. Run the agent executable:
   - Linux/macOS: `./bin/{exe_path.name}`
   - Windows:     `bin\\{exe_path.name}`
2. UltimMC will automatically launch Minecraft and log in
3. The agent backend starts on port {backend_port}

## Package Contents
- `bin/{exe_path.name}` — executable + all bundled libraries (PyTorch, ai_core, etc.)
- `bin/_internal/` — shared .so/.dll files (required, do not delete)
- `brain.pcap` — complete agent state (weights, memory, personality, pregnancy)
- `brain.pcap.json` — human-readable brain summary
- `config.json` — agent configuration and backend settings
- `UltimMC/` — Minecraft launcher with pre-configured {Config.MINECRAFT_VERSION}
- `mods/` — DivineWorld + DWClientBot Minecraft mods
{"- `frontend/` — web-based chat UI" if has_frontend else ""}

## Portability
**Fully portable** — copy this entire folder to any PC and run `{exe_path.name}`.
No Python installation required on the target machine.

## Backend API
- REST API:  http://localhost:{backend_port}
- WebSocket: ws://localhost:{backend_port}/ws

## Notes
- Auto-saves brain every 5 minutes
- Each agent gets its own Minecraft instance and JVM

## Minecraft Integration
- Minecraft: {Config.MINECRAFT_VERSION}
- Forge:     {Config.FORGE_VERSION}
- Server:    {Config.DEFAULT_SERVER}
"""
        (pkg_dir / "README.md").write_text(readme, encoding='utf-8')
        log.info(f"✅ Portable package: {pkg_dir}")
        return pkg_dir

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup_build_artifacts(self):
        """Remove PyInstaller temp dirs. Call after packaging if desired."""
        if self._build_tmp.exists():
            try:
                shutil.rmtree(self._build_tmp)
                log.info(f"🧹 Cleaned build tmp: {self._build_tmp}")
            except Exception as e:
                log.warning(f"Could not clean build tmp: {e}")

    def get_package_info(self, agent_id: str) -> Optional[Dict[str, Any]]:
        pkg_dir = self.output_dir / agent_id
        if not pkg_dir.exists():
            return None
        exe_name = f"{agent_id}.exe" if sys.platform == "win32" else f"{agent_id}"  # no DW_ prefix
        return {
            "agent_id":    agent_id,
            "package_dir": str(pkg_dir),
            "exe_path":    str(pkg_dir / exe_name),
            "brain_path":  str(pkg_dir / "brain.pcap"),
            "config_path": str(pkg_dir / "config.json"),
            "exists":      (pkg_dir / exe_name).exists(),
        }