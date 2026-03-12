# py_backend/chat_launcher.py
"""
Chat Interface Launcher
=======================
Starts the React-based chat interface for a single agent.
Can be run standalone:

    python chat_launcher.py <agent_id> <brain_path>

or imported and called programmatically from main.py:

    from py_backend.chat_launcher import start_chat_interface
    start_chat_interface("alice", "/path/to/brain.pcap", {})
"""

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("chat_launcher")


def start_chat_interface(agent_id: str, brain_path: str,
                          config: Dict[str, Any]):
    """
    Launch the chat interface for *agent_id*.

    Steps:
      1. Load (or create fresh) an NPCAgent for the given brain path.
      2. Start the FastAPI/uvicorn backend in a subprocess.
      3. Serve the React frontend (built dist/ or npm run dev).
      4. Block until the backend exits or KeyboardInterrupt.

    Args:
        agent_id:   Agent identifier string.
        brain_path: Absolute path to the brain capsule (brain.pcap).
        config:     Optional overrides.
                      backend_port (int)  — uvicorn port (default: Config value)
    """
    log.info(f"Starting chat interface for {agent_id}")

    # ── import agent system ──────────────────────────────────────────
    try:
        from ai_core.agent import NPCAgent
    except ImportError as e:
        log.error(f"Failed to import agent modules: {e}")
        raise

    try:
        from py_backend.config import Config
        _default_port    = Config.BASE_BACKEND_PORT
        _frontend_dir    = Config.FRONTEND_DIR
        _main_module     = "py_backend.main:app"
    except ImportError:
        _default_port    = 11400
        _frontend_dir    = Path(__file__).parent.parent / "dw_agent" / "react-app"
        _main_module     = "py_backend.main:app"

    # ── load agent ───────────────────────────────────────────────────
    agent = NPCAgent(agent_id)
    if Path(brain_path).exists():
        log.info(f"Loading brain: {brain_path}")
        agent.load(brain_path)
    else:
        log.warning("Brain not found — starting with fresh state")

    # ── start backend ────────────────────────────────────────────────
    backend_port = config.get("backend_port", _default_port)
    backend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", _main_module,
            "--host", "0.0.0.0",
            "--port", str(backend_port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    log.info(f"Backend started on port {backend_port}")

    # Give the server time to bind
    time.sleep(2)

    # ── start React frontend ─────────────────────────────────────────
    frontend_dir = Path(_frontend_dir)
    if frontend_dir.exists():
        log.info(f"Starting React frontend from {frontend_dir}")
        if (frontend_dir / "dist").exists():
            # Production build — serve the dist/ folder
            subprocess.run(
                ["npx", "serve", "-s", "dist", "-p", "8765"],
                cwd=frontend_dir,
            )
        else:
            # Development mode
            subprocess.run(["npm", "run", "dev"], cwd=frontend_dir)
    else:
        log.warning(f"React frontend not found at {frontend_dir}")
        print(f"\n  Chat backend : http://localhost:{backend_port}")
        print(f"  GUI dashboard: http://localhost:{backend_port}/gui")
        print("  Open your browser to interact with the agent.\n")

    # ── wait for backend ─────────────────────────────────────────────
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — stopping backend")
        backend_proc.terminate()


# =============================================================================
# Standalone entry point
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if len(sys.argv) < 3:
        print("Usage: python chat_launcher.py <agent_id> <brain_path> [backend_port]")
        sys.exit(1)

    _cfg: Dict[str, Any] = {}
    if len(sys.argv) >= 4:
        try:
            _cfg["backend_port"] = int(sys.argv[3])
        except ValueError:
            pass

    start_chat_interface(sys.argv[1], sys.argv[2], _cfg)