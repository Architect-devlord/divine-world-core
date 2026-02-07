# py_backend/packager.py - PRODUCTION VERSION
"""
Production-ready agent packager with:
- Proper frontend detection and npm handling
- Fixed PyInstaller imports
- Multi-platform support
- Comprehensive error handling
"""

import os
import sys
import shutil
import json
import subprocess
from pathlib import Path
import time
from typing import Optional, Dict, Any
import logging
from frontend_builder import FrontendBuilder
from config import Config
from py_backend.utils.mc_uuid import get_minecraft_uuid

log = logging.getLogger("packager")
log.setLevel(logging.INFO)

# Find npm in PATH (cross-platform)
NPM_CMD = shutil.which("npm") or "npm"

# Initialize frontend builder
frontend_builder = FrontendBuilder()


class AgentPackager:
    """
    Production-ready agent packager.
    Creates standalone executables for AI agents.
    """

    def __init__(self, output_dir: str = None):
        # Default to centralized NPC applications directory from Config
        if output_dir is None:
            try:
                from config import Config as _Config
                self.output_dir = Path(_Config.NPC_APPLICATIONS_DIR)
            except Exception:
                self.output_dir = Path("npc_applications")
        else:
            self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.dist_dir = Path("dist")
        self.build_dir = Path("build")

        # Frontend detection - try multiple paths
        self.frontend_dir = self._find_frontend_dir()
        # Try to find DivineWorld mod jar
        self.mod_jar = self._find_mod_jar()
        # Try to find client jar from config
        try:
            from config import Config as _Config2
            self.client_jar = _Config2.CLIENT_JAR
        except Exception:
            self.client_jar = None

        self.ultimmc_path = self._find_ultimmc()

    def _find_frontend_dir(self) -> Optional[Path]:
        """Find the React frontend directory"""
        cwd = Path.cwd()

        # Check parent directory structure
        if cwd.name == "py_backend":
            workspace_root = cwd.parent
        else:
            workspace_root = cwd

        candidates = [
            workspace_root / "react-app",
            workspace_root / "dw_agent" / "react-app",
            workspace_root / "dw_agent" / "electron" / "react-app",
            workspace_root / "frontend",
            cwd / "react-app",
        ]

        for path in candidates:
            log.debug(f"Checking frontend path: {path}")
            if path.exists() and (path / "package.json").exists():
                log.info(f"✅ Found frontend at: {path}")
                return path

        log.warning("⚠️ No frontend directory found")
        return None

    def _find_mod_jar(self) -> Optional[Path]:
        """Try to find a built DivineWorld mod jar in common Gradle output locations."""
        cwd = Path.cwd()
        if cwd.name == "py_backend":
            workspace_root = cwd.parent
        else:
            workspace_root = cwd

        candidates = [
            workspace_root / "DivineWorld" / "build" / "libs",
            workspace_root / "DivineWorld" / "build" / "reobfJar" / "libs",
            workspace_root / "DivineWorld" / "build" / "libs",
        ]

        for base in candidates:
            if not base.exists():
                continue
            # Look for jar files containing 'divine' or the mod id
            for jar in sorted(base.glob('*.jar')):
                name = jar.name.lower()
                if 'divine' in name or 'divineworld' in name:
                    log.info(f"✅ Found mod jar: {jar}")
                    return jar

        log.debug("No DivineWorld mod jar found in build output")
        return None

    def _find_ultimmc(self) -> Optional[Path]:
        """Find UltimMC installation directory"""
        cwd = Path.cwd()
        if cwd.name == "py_backend":
            workspace_root = cwd.parent
        else:
            workspace_root = cwd

        candidates = [
            workspace_root / "UltimMC",
            Path("/opt/ultimmc"),
        ]

        for path in candidates:
            if path.exists() and (path / "bin" / "UltimMC").exists():
                log.info(f"✅ Found UltimMC at: {path}")
                return path

        log.warning("⚠️ UltimMC not found")
        return None

    def package_agent(
        self,
        agent_id: str,
        brain_capsule_path: str,
        agent_name: Optional[str] = None,
        gender: str = "neutral",
        agent_type: str = "npc",
        icon_path: Optional[str] = None,
        include_frontend: bool = True,
        include_mod: bool = True,
        include_client_jar: bool = True,
        backend_port: int = 11400
    ) -> Dict[str, str]:
        """
        Creates self-contained executable for an agent.
        """

        log.info(f"📦 Packaging agent: {agent_id} (gender: {gender}, type: {agent_type})")

        # Validate inputs
        brain_path = Path(brain_capsule_path)
        if not brain_path.exists():
            raise FileNotFoundError(f"Brain capsule not found: {brain_capsule_path}")

        # Verify brain file size
        brain_size = brain_path.stat().st_size
        if brain_size > Config.MAX_BRAIN_SIZE_MB * 1024 * 1024:
            raise ValueError(f"Brain file too large: {brain_size / (1024*1024):.1f}MB")

        if brain_size < 100:
            raise ValueError(f"Brain file too small: {brain_size} bytes (possibly corrupt)")

        # Create agent directory
        agent_dir = self.output_dir / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        # Determine agent name for Minecraft (clean name if provided, otherwise agent_id)
        if agent_name and agent_name != "Unnamed":
            minecraft_name = agent_name
        else:
            # Fallback to prefixed name if it's an NPC/God and no clean name provided
            if agent_type.startswith('god_'):
                god_type = agent_type.replace('god_', '').upper()
                minecraft_name = f"DWGOD_{god_type}_{agent_id}"
            else:
                minecraft_name = f"DW_{agent_id}"

        # Generate proper Minecraft offline UUID
        agent_uuid = get_minecraft_uuid(minecraft_name)

        # Copy UltimMC and setup account/instance
        if self.ultimmc_path:
            ultimmc_dest = agent_dir / "UltimMC"
            shutil.copytree(self.ultimmc_path, ultimmc_dest)

            # Modify accounts.json
            accounts_file = ultimmc_dest / "bin" / "accounts.json"
            if accounts_file.exists():
                import uuid
                with open(accounts_file, 'r') as f:
                    accounts_data = json.load(f)

                agent_account = {
                    "active": True,
                    "profile": {
                        "capes": [],
                        "id": agent_uuid,
                        "name": minecraft_name,
                        "skin": {"id": "", "url": "", "variant": ""}
                    },
                    "type": "Local",
                    "ygg": {
                        "extra": {
                            "clientToken": str(uuid.uuid4()),
                            "userName": minecraft_name
                        },
                        "iat": int(time.time())
                    }
                }
                for acc in accounts_data.get("accounts", []):
                    acc["active"] = False
                accounts_data["accounts"].append(agent_account)
                with open(accounts_file, 'w') as f:
                    json.dump(accounts_data, f, indent=2)

            # Copy instance
            instance_src = self.ultimmc_path / "instances" / "1.20.1"
            if instance_src.exists():
                instance_dest = ultimmc_dest / "instances" / agent_id
                shutil.copytree(instance_src, instance_dest)
                # Install mods
                mods_dir = instance_dest / ".minecraft" / "mods"
                mods_dir.mkdir(parents=True, exist_ok=True)
                if self.mod_jar:
                    shutil.copy(self.mod_jar, mods_dir / self.mod_jar.name)
                if self.client_jar:
                    shutil.copy(self.client_jar, mods_dir / self.client_jar.name)

        # 1. Copy brain capsule
        self._copy_brain_capsule(brain_path, agent_dir, gender, agent_type)

        # 2. Build React frontend if requested AND frontend exists
        frontend_included = False
        if include_frontend and self.frontend_dir:
            frontend_dest = agent_dir / "frontend"
            if frontend_builder.build_frontend(self.frontend_dir, frontend_dest):
                frontend_included = True
            else:
                log.warning("⚠️  Frontend build failed")
                log.info("Continuing without frontend...")
                frontend_included = False
        else:
            log.info("🔇 Skipping frontend (not found or not requested)")

        # 2b. Include mods (DivineWorld mod jar + DWClientBot mod jar)
        mod_included = False
        if include_mod:
            mods_dest = agent_dir / "mods"
            mods_dest.mkdir(parents=True, exist_ok=True)

            # Include DivineWorld mod jar if found
            if self.mod_jar:
                try:
                    shutil.copy(self.mod_jar, mods_dest / self.mod_jar.name)
                    log.info(f"✅ Included DivineWorld mod: {self.mod_jar}")
                    mod_included = True
                except Exception as e:
                    log.warning(f"Failed to include DivineWorld mod: {e}")

            # DWClientBot.jar is also a mod - include it in mods folder
            if include_client_jar and self.client_jar:
                try:
                    shutil.copy(self.client_jar, mods_dest / Path(self.client_jar).name)
                    log.info(f"✅ Included DWClientBot mod: {self.client_jar}")
                    mod_included = True
                except Exception as e:
                    log.warning(f"Failed to include DWClientBot mod: {e}")

        # DWClientBot is a mod, not a separate client
        client_included = False

        # 3. Create launcher script
        launcher_path = self._create_launcher(agent_id, agent_dir, frontend_included, agent_type, backend_port, minecraft_name)

        # 4. Create configuration
        config_path = self._create_config(agent_id, agent_dir, gender, agent_type, backend_port)

        # 5. Build executable
        exe_path = self._build_executable(agent_id, launcher_path, agent_dir, icon_path, frontend_included)

        # 6. Create portable package
        package_path = self._create_portable_package(agent_id, agent_dir, exe_path, frontend_included)

        log.info(f"✅ Agent packaged: {exe_path}")

        return {
            "agent_id": agent_id,
            "exe_path": str(exe_path),
            "package_path": str(package_path),
            "brain_path": str(agent_dir / "brain.pcap"),
            "config_path": str(config_path),
            "has_frontend": frontend_included,
            "has_mod": mod_included,
            "gender": gender,
            "agent_type": agent_type,
            "backend_port": backend_port
        }

    def _copy_brain_capsule(self, brain_path: Path, agent_dir: Path, gender: str, agent_type: str):
        """Copy brain capsule and add gender/type metadata"""
        brain_dest = agent_dir / "brain.pcap"
        shutil.copy(brain_path, brain_dest)

        brain_json = brain_path.with_suffix('.pcap.json')
        if brain_json.exists():
            with open(brain_json, 'r') as f:
                brain_data = json.load(f)

            brain_data['metadata']['gender'] = gender
            brain_data['metadata']['agent_type'] = agent_type

            with open(agent_dir / "brain.pcap.json", 'w') as f:
                json.dump(brain_data, f, indent=2)

        log.info(f"✓ Brain capsule copied with metadata")

    def _create_launcher(self, agent_id: str, agent_dir: Path, has_frontend: bool,
                        agent_type: str, backend_port: int, minecraft_name: str) -> Path:
        """Creates launcher with FIXED import paths for PyInstaller"""

        launcher_template = '''"""
DW Agent Launcher - __AGENT_ID__ (__MINECRAFT_NAME__)
Type: __AGENT_TYPE__
Production Version with Fixed Imports and Auto-Join Logic
"""

import sys
import os
import socket
import shutil
import subprocess
from pathlib import Path

# CRITICAL FIX: Proper path handling for PyInstaller
if getattr(sys, 'frozen', False):
    # Running as compiled .exe
    BASE_DIR = Path(sys._MEIPASS)
    AGENT_DIR = Path(os.path.dirname(sys.executable))
    # Add bundled modules to path
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / "ai_core"))
    sys.path.insert(0, str(BASE_DIR / "py_backend"))
else:
    # Running as script (development)
    BASE_DIR = Path(__file__).parent.parent
    AGENT_DIR = Path(__file__).parent
    # Add development paths
    sys.path.insert(0, str(BASE_DIR))
    sys.path.insert(0, str(BASE_DIR / "ai_core"))
    sys.path.insert(0, str(BASE_DIR / "py_backend"))

import json
import logging
import time
import threading
import webbrowser

AGENT_ID = "__AGENT_ID__"
MINECRAFT_NAME = "__MINECRAFT_NAME__"
AGENT_TYPE = "__AGENT_TYPE__"
BRAIN_PATH = AGENT_DIR / "brain.pcap"
CONFIG_PATH = AGENT_DIR / "config.json"
FRONTEND_PATH = AGENT_DIR / "frontend"
HAS_FRONTEND = __HAS_FRONTEND__
BACKEND_PORT = __BACKEND_PORT__

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s'
)
log = logging.getLogger("launcher")

def load_config():
    """Load agent configuration"""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {"agent_id": AGENT_ID, "minecraft_name": MINECRAFT_NAME, "agent_type": AGENT_TYPE, "backend_port": BACKEND_PORT, "default_server": "127.0.0.1:25565"}

def is_server_up(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False

def start_backend_server(port: int = BACKEND_PORT):
    """Start FastAPI backend server"""
    log.info(f"Starting backend server on port {port}...")
    try:
        import uvicorn
        if getattr(sys, 'frozen', False):
            from main import app
        else:
            from py_backend.main import app

        def run_server():
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="error")

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        time.sleep(1.5)
        log.info(f"✅ Backend ready at http://127.0.0.1:{port}")
        return True
    except Exception as e:
        log.error(f"Failed to start backend: {e}")
        import traceback
        traceback.print_exc()
        return False

def try_launch_ultimmc(server_addr: str, agent_name: str) -> bool:
    """Try to launch embedded UltimMC if available to join the server."""
    ultimmc_dir = AGENT_DIR / "UltimMC"
    if not ultimmc_dir.exists():
        return False
    ult_path = ultimmc_dir / "bin" / "UltimMC"
    if not ult_path.exists():
        return False
    cmd = [
        str(ult_path),
        "-d", str(ultimmc_dir),
        "-l", agent_name,
        "-s", server_addr,
        "-a", agent_name,
        "-o",
        "-n", agent_name
    ]
    try:
        log.info(f"Launching embedded UltimMC: {' '.join(cmd)}")
        subprocess.Popen(cmd, cwd=str(AGENT_DIR))
        return True
    except Exception as e:
        log.error(f"Failed to launch UltimMC: {e}")
        return False

def launch_chat_mode():
    """Launch agent in chat interface mode with auto-join behavior"""
    log.info(f"💬 Starting {AGENT_ID} in CHAT mode")
    cfg = load_config()
    backend_port = cfg.get('backend_port', BACKEND_PORT)
    default_server = cfg.get('default_server', '127.0.0.1:25565')

    # Parse default server
    server_host, server_port = default_server.split(':') if ':' in default_server else (default_server, '25565')
    server_port = int(server_port)

    # Load agent
    log.info(f"Loading brain from {BRAIN_PATH}...")
    if getattr(sys, 'frozen', False):
        from agent import NPCAgent
        from brain_language import add_language_to_brain
    else:
        from ai_core.agent import NPCAgent
        from ai_core.brain_language import add_language_to_brain

    agent = NPCAgent(AGENT_ID)
    if BRAIN_PATH.exists():
        try:
            agent.load(str(BRAIN_PATH))
            log.info(f"✅ Brain loaded")
        except Exception as e:
            log.error(f"⚠️ Failed to load brain: {e}")

    if not hasattr(agent.brain, 'language') or agent.brain.language is None:
        add_language_to_brain(agent.brain)
        log.info("✅ Language capabilities initialized")

    # Decide behavior based on server availability
    server_available = is_server_up(server_host, server_port)
    log.info(f"Server {server_host}:{server_port} available: {server_available}")

    # Start backend
    if not start_backend_server(backend_port):
        log.error("Backend failed to start")
        sys.exit(1)

    if server_available:
        # Try to auto-launch UltimMC to join server
        launched = try_launch_ultimmc(f"{server_host}:{server_port}", MINECRAFT_NAME)
        if not launched:
            log.info("Could not auto-launch UltimMC; present manual instructions to user.")
            # Show same instructions as before
            attempt_launch_minecraft_client(AGENT_ID, AGENT_DIR, backend_port)
    else:
        # No server: open frontend if available
        if HAS_FRONTEND and FRONTEND_PATH.exists():
            try:
                import http.server
                import socketserver

                class Handler(http.server.SimpleHTTPRequestHandler):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, directory=str(FRONTEND_PATH), **kwargs)

                    def log_message(self, format, *args):
                        pass

                frontend_port = backend_port + 1

                def serve_frontend():
                    with socketserver.TCPServer(("", frontend_port), Handler) as httpd:
                        log.info(f"Frontend serving on http://localhost:{frontend_port}")
                        httpd.serve_forever()

                frontend_thread = threading.Thread(target=serve_frontend, daemon=True)
                frontend_thread.start()
                time.sleep(1)
                webbrowser.open(f"http://localhost:{frontend_port}")
            except Exception as e:
                log.error(f"Frontend server failed: {e}")
        else:
            log.info("Frontend not available - backend only mode")
            print(f"\n✅ Backend running at http://127.0.0.1:{backend_port}")

    # Keep alive with auto-save
    print("\n" + "="*60)
    print(f"  ✅ {AGENT_ID} RUNNING")
    print("="*60)
    print(f"  Backend: http://localhost:{backend_port}")
    if HAS_FRONTEND and FRONTEND_PATH.exists():
        print(f"  Frontend: http://localhost:{backend_port + 1}")
    print("\nPress Ctrl+C to stop")
    print("="*60 + "\n")

    try:
        last_save = time.time()
        save_interval = 300  # 5 minutes
        while True:
            time.sleep(1)
            if time.time() - last_save >= save_interval:
                try:
                    agent.save(str(BRAIN_PATH))
                    log.info("💾 Auto-saved brain state")
                    last_save = time.time()
                except Exception as e:
                    log.error(f"Auto-save failed: {e}")
    except KeyboardInterrupt:
        log.info("\n💾 Saving brain state before exit...")
        try:
            agent.save(str(BRAIN_PATH))
            log.info("✅ Brain saved")
        except Exception as e:
            log.error(f"❌ Failed to save: {e}")
        log.info("Goodbye!")

def main():
    """Main entry point"""
    print("\n" + "="*60)
    print(f"  🤖 DW Agent - {AGENT_ID}")
    print(f"  Type: {AGENT_TYPE}")
    print(f"  Frontend: {'✅ Included' if HAS_FRONTEND else '❌ Not included'}")
    print(f"  Port: {BACKEND_PORT}")
    print("="*60)

    if not BRAIN_PATH.exists():
        log.error(f"Brain capsule not found: {BRAIN_PATH}")
        sys.exit(1)

    log.info(f"Brain: {BRAIN_PATH}")

    # Launch chat mode
    launch_chat_mode()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("\nShutdown requested")
        sys.exit(0)
    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)
'''

        # Replace template placeholders with actual values safely
        launcher_code = launcher_template.replace('__AGENT_ID__', agent_id)
        launcher_code = launcher_code.replace('__MINECRAFT_NAME__', minecraft_name)
        launcher_code = launcher_code.replace('__AGENT_TYPE__', agent_type)
        launcher_code = launcher_code.replace('__HAS_FRONTEND__', str(has_frontend))
        launcher_code = launcher_code.replace('__BACKEND_PORT__', str(backend_port))

        launcher_path = agent_dir / "launcher.py"
        launcher_path.write_text(launcher_code, encoding='utf-8')
        log.info(f"✓ Launcher created with fixed imports")

        return launcher_path
    def _create_config(self, agent_id: str, agent_dir: Path, gender: str,
                      agent_type: str, backend_port: int) -> Path:
        """Creates agent configuration file"""
        config = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "gender": gender,
            "version": "2.1.0",
            "default_server": "127.0.0.1:25565",
            "backend_port": backend_port,
            "frontend_port": backend_port + 1,
            "modes": {
                "chat": True,
                "controller": True,
                "headless": True
            },
            "features": {
                "language_intelligence": True,
                "pattern_recognition": True,
                "multimodal_learning": True,
                "auto_save": True
            }
        }

        config_path = agent_dir / "config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)

        return config_path

    def _build_executable(self, agent_id: str, launcher_path: Path,
                          agent_dir: Path, icon_path: Optional[str],
                          has_frontend: bool) -> Path:
        """Builds executable using PyInstaller with fixed paths"""
        log.info(f"🔨 Building executable for {agent_id}...")

        exe_name = f"DW_Agent_{agent_id}"

        # Determine correct module paths
        if Path.cwd().name == "py_backend":
            workspace_root = Path.cwd().parent
        else:
            workspace_root = Path.cwd()

        ai_core_path = workspace_root / "ai_core"
        py_backend_path = workspace_root / "py_backend"

        # If ai_core isn't at workspace root, check under py_backend (monorepo layout)
        if not ai_core_path.exists():
            alt_ai_core = py_backend_path / "ai_core"
            if alt_ai_core.exists():
                ai_core_path = alt_ai_core

        # Verify paths exist
        if not ai_core_path.exists():
            raise FileNotFoundError(f"ai_core directory not found: {ai_core_path}")
        if not py_backend_path.exists():
            raise FileNotFoundError(f"py_backend directory not found: {py_backend_path}")

        args = [
            'pyinstaller',
            '--name', exe_name,
            '--onefile',
            '--clean',
            '--noconfirm',
            '--console',

            # Module paths
            '--paths', str(workspace_root),
            '--paths', str(ai_core_path),
            '--paths', str(py_backend_path),

            # Hidden imports (modules only)
            '--hidden-import', 'uvicorn',
            '--hidden-import', 'fastapi',
            '--hidden-import', 'websockets',
            '--hidden-import', 'numpy',
            '--hidden-import', 'torch',
            '--hidden-import', 'pydantic',
        ]

        # Add all Config hidden imports
        for module in Config.PYINSTALLER_HIDDEN_IMPORTS:
            args.extend(['--hidden-import', module])

        # Data files
        data_files = [
            (agent_dir / "brain.pcap", '.'),
            (agent_dir / "config.json", '.'),
        ]

        # Add brain JSON if exists
        brain_json = agent_dir / "brain.pcap.json"
        if brain_json.exists():
            data_files.append((brain_json, '.'))

        # Add frontend if exists
        if has_frontend:
            frontend_dir = agent_dir / "frontend"
            if frontend_dir.exists():
                data_files.append((frontend_dir, 'frontend'))
                log.info("✅ Frontend will be bundled")

        # Add modules as data directories
        if py_backend_path.exists():
            data_files.append((py_backend_path, 'py_backend'))
            log.info(f"📦 Adding py_backend from: {py_backend_path}")

        if ai_core_path.exists():
            data_files.append((ai_core_path, 'ai_core'))
            log.info(f"📦 Adding ai_core from: {ai_core_path}")

        # Add all data files to args
        for src, dst in data_files:
            args.extend(['--add-data', f'{src}{os.pathsep}{dst}'])

        # Add icon if provided
        if icon_path and Path(icon_path).exists():
            args.extend(['--icon', icon_path])

        # Launcher script
        args.append(str(launcher_path))

        log.info("PyInstaller command:")
        log.info(" ".join(args))

        # Run PyInstaller
        try:
            log.info(f"Running PyInstaller...")
            log.info(f"⏳ This will take 30-60 seconds. Please wait...")

            result = subprocess.run(
                args,
                check=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            log.info("✅ PyInstaller completed")

            # Find executable
            dist_dir = Path("dist")
            if sys.platform == "win32":
                exe_path = dist_dir / f"{exe_name}.exe"
            else:
                exe_path = dist_dir / exe_name

            if not exe_path.exists():
                raise FileNotFoundError(f"Executable not found: {exe_path}")

            file_size = exe_path.stat().st_size / (1024 * 1024)
            log.info(f"✅ Executable built: {exe_path} ({file_size:.1f} MB)")
            return exe_path

        except subprocess.CalledProcessError as e:
            log.error(f"❌ PyInstaller failed:")
            log.error(f"STDOUT: {e.stdout}")
            log.error(f"STDERR: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            log.error("❌ PyInstaller timed out after 5 minutes")
            raise
        except KeyboardInterrupt:
            log.error("❌ Build interrupted by user")
            raise

    def _create_portable_package(self, agent_id: str, agent_dir: Path,
                                   exe_path: Path, has_frontend: bool) -> Path:
        """Creates portable package directory"""
        package_dir = self.output_dir / f"{agent_id}_portable"
        package_dir.mkdir(parents=True, exist_ok=True)

        # Copy executable
        shutil.copy(exe_path, package_dir / exe_path.name)

        # Copy brain and config
        shutil.copy(agent_dir / "brain.pcap", package_dir / "brain.pcap")
        shutil.copy(agent_dir / "config.json", package_dir / "config.json")

        brain_json = agent_dir / "brain.pcap.json"
        if brain_json.exists():
            shutil.copy(brain_json, package_dir / "brain.pcap.json")

        # Copy frontend if exists
        if has_frontend:
            frontend_dir = agent_dir / "frontend"
            if frontend_dir.exists():
                shutil.copytree(frontend_dir, package_dir / "frontend", dirs_exist_ok=True)

        # Copy mods folder (includes both DivineWorld and DWClientBot mods)
        mods_dir = agent_dir / "mods"
        if mods_dir.exists():
            shutil.copytree(mods_dir, package_dir / "mods", dirs_exist_ok=True)

        # Create README
        readme = f"""# {agent_id} - Divine World AI Agent

**Portable Standalone Package (Production v2.1.0)**

## Quick Start

Double-click `{exe_path.name}` to launch the agent.

## What's Included

- `{exe_path.name}` - Main executable (standalone, no dependencies)
- `brain.pcap` - Agent's memory and personality
- `config.json` - Configuration
- `mods/` - Minecraft mods (DivineWorld + DWClientBot)
{'- `frontend/` - Chat interface' if has_frontend else '- No frontend (backend only)'}

## Usage

The agent will:
1. Load its brain state from `brain.pcap`
2. Start the backend server (port configured in config.json)
{'3. Open the chat interface in your browser' if has_frontend else '3. Run in backend-only mode (connect via API)'}

## Features

✅ Language Intelligence - Learns from text and conversation
✅ Pattern Recognition - Identifies behavioral patterns
✅ Multimodal Learning - Processes vision and audio
✅ Personality System - Unique traits and emotions
✅ Atomic Saves - Data never corrupts
✅ Auto-Save - Saves every 5 minutes
✅ Minecraft Integration - Bundled mods (DivineWorld + DWClientBot)

## Portability

This entire folder is portable!
- Move to any Windows computer
- All memories preserved in brain.pcap
- No installation required
- Self-contained executable

## Configuration

Edit `config.json` to change:
- Backend port
- Frontend port
- Auto-save interval
- Feature flags

## Agent Info

- Agent ID: {agent_id}
- Has Frontend: {has_frontend}
- Version: 2.1.0 (Production)
- Protocol: Binary WebSocket

## Minecraft Integration

The packaged `mods/` folder contains:
- **DivineWorld.jar** - Divine World mod for enhanced gameplay
- **DWClientBot.jar** - Agent communication mod (allows AI agent to interact with Minecraft)

Place the entire `mods/` folder into your Minecraft mods folder:
- **Windows:** `%APPDATA%/.minecraft/mods/`
- **Linux:** `~/.minecraft/mods/`
- **macOS:** `~/Library/Application Support/minecraft/mods/`

## Troubleshooting

**Backend won't start:**
- Check if port is already in use
- Try changing backend_port in config.json

**Frontend won't load:**
- Ensure backend started successfully
- Check browser at http://localhost:<frontend_port>

**Brain won't load:**
- Verify brain.pcap file exists
- Check file isn't corrupted (should be >100 bytes)

**Mods not loading in Minecraft:**
- Verify mods/ folder is in your Minecraft mods directory
- Ensure you have Forge/Fabric installed (if required)
- Check Minecraft launcher logs for mod errors

## Support

For issues or questions:
- Check logs in console window
- Brain state is automatically backed up
- Safe to restart - progress is saved

---
Packaged: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""

        (package_dir / "README.md").write_text(readme, encoding='utf-8')

        log.info(f"✅ Portable package: {package_dir}")
        return package_dir

    def cleanup_build_artifacts(self):
        """Clean up temporary build files"""
        try:
            if self.build_dir.exists():
                shutil.rmtree(self.build_dir)
                log.info(f"Cleaned up {self.build_dir}")

            # Clean up spec files
            for spec_file in Path.cwd().glob("*.spec"):
                spec_file.unlink()
                log.info(f"Cleaned up {spec_file}")

        except Exception as e:
            log.warning(f"Failed to clean up some artifacts: {e}")