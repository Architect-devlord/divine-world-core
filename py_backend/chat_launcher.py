# py_backend/chat_launcher.py
"""
Chat Interface Launcher — Frontend-Only Mode
============================================
Starts the React-based chat interface for a single agent without
requiring a Minecraft server connection.

Changes from original:
  - Brain path fallback: tries Config.BRAINS_DIR/<agent_id>/brain.pcap if
    the provided path is empty or missing.
  - WebBrowser attached automatically (agentic browsing in frontend mode).
  - allowed_websites loaded from agents.json.
  - Browser auto-opened after the frontend starts (webbrowser.open).
  - Backend port defaults to agent's TCP port + WS_PORT_OFFSET when known.
"""

import logging
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict

log = logging.getLogger("chat_launcher")


def start_chat_interface(agent_id: str, brain_path: str,
                          config: Dict[str, Any]):
    """
    Launch the chat interface for *agent_id*.

    Steps:
      1. Load (or create fresh) an NPCAgent for the given brain path.
      2. Attach WebBrowser for agentic browsing (allowed_websites from agents.json).
      3. Start the FastAPI/uvicorn backend in a subprocess.
      4. Serve the React frontend (built dist/ or npm run dev).
      5. Open browser tab automatically.
      6. Block until the backend exits or KeyboardInterrupt.
    """
    log.info(f"[{agent_id}] Starting frontend-only chat interface")

    try:
        from ai_core.agent import NPCAgent
    except ImportError as e:
        log.error(f"Failed to import agent modules: {e}")
        raise

    try:
        from py_backend.config import Config
        _default_port = Config.BASE_BACKEND_PORT
        _frontend_dir = Config.FRONTEND_DIR
        _main_module  = "py_backend.main:app"
        _brains_dir   = Config.BRAINS_DIR
    except ImportError:
        _default_port = 11400
        _frontend_dir = Path(__file__).parent.parent / "dw_agent" / "react-app"
        _main_module  = "py_backend.main:app"
        _brains_dir   = Path(__file__).parent.parent / "brains"

    # ── Resolve brain path (with fallback) ───────────────────────────
    _bp = Path(brain_path) if brain_path else Path()
    if not _bp.exists():
        # Try the canonical brains directory
        _fallback = Path(_brains_dir) / agent_id / "brain.pcap"
        if _fallback.exists():
            _bp = _fallback
            log.info(f"[{agent_id}] Using brain at default location: {_bp}")
        else:
            _bp = Path()   # sentinel — no brain found

    # ── Load agent ───────────────────────────────────────────────────
    agent = NPCAgent(agent_id)
    if _bp.exists():
        log.info(f"[{agent_id}] Loading brain: {_bp}")
        agent.load(str(_bp))
    else:
        log.warning(f"[{agent_id}] No brain found — starting with fresh state")

    # ── Attach browser (frontend-only agentic browsing) ───────────────
    try:
        from ai_core.web_browser import add_web_browsing_to_agent
        browser = add_web_browsing_to_agent(agent)
        if browser:
            # Load allowed websites from agents.json
            try:
                from py_backend.utils.mc_uuid import AgentNameManager
                sites = AgentNameManager.get_allowed_websites()
                if sites:
                    browser.update_allowed_websites(sites)
                    enabled = [s["url"] for s in sites if s.get("enabled", True)]
                    log.info(
                        f"[{agent_id}] Browser attached — "
                        f"{len(enabled)} allowed domain(s)"
                    )
                else:
                    log.info(f"[{agent_id}] Browser attached — no allowed_websites in agents.json")
            except Exception as _we:
                log.warning(f"[{agent_id}] Could not load allowed_websites: {_we}")
        else:
            log.info(f"[{agent_id}] Browser not available (web_browser module missing?)")
    except ImportError:
        log.info(f"[{agent_id}] web_browser module not found — browser disabled")
    except Exception as _be:
        log.warning(f"[{agent_id}] Browser attach error: {_be}")

    # ── Resolve backend port ─────────────────────────────────────────
    # Try agents.json TCP port + WS offset, fall back to config default
    backend_port = config.get("backend_port")
    if not backend_port:
        try:
            from py_backend.utils.mc_uuid import AgentNameManager
            tcp_port = AgentNameManager().get_port_for_name(agent_id)
            if tcp_port:
                backend_port = tcp_port + 10000   # WS_PORT_OFFSET
                log.info(f"[{agent_id}] Backend port from agents.json: {backend_port}")
        except Exception:
            pass
    if not backend_port:
        backend_port = _default_port

    # ── Start backend ────────────────────────────────────────────────
    backend_proc = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn", _main_module,
            "--host", "0.0.0.0",
            "--port", str(backend_port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    log.info(f"[{agent_id}] Backend started on port {backend_port}")
    time.sleep(2)

    # ── Start React frontend ─────────────────────────────────────────
    frontend_url = f"http://localhost:{backend_port}/gui"
    frontend_dir = Path(_frontend_dir)

    if frontend_dir.exists():
        log.info(f"[{agent_id}] Starting React frontend from {frontend_dir}")
        if (frontend_dir / "dist").exists():
            frontend_url = "http://localhost:8765"
            import threading
            fe_proc = subprocess.Popen(
                ["npx", "serve", "-s", "dist", "-p", "8765"],
                cwd=frontend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1)
        else:
            frontend_url = "http://localhost:5173"
            import threading
            fe_proc = subprocess.Popen(
                ["npm", "run", "dev"],
                cwd=frontend_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)
    else:
        log.warning(f"[{agent_id}] React frontend not found at {frontend_dir}")
        frontend_url = f"http://localhost:{backend_port}/gui"
        print(f"\n  Chat backend : http://localhost:{backend_port}")
        print(f"  GUI dashboard: {frontend_url}")
        print("  Open your browser to interact with the agent.\n")

    # ── Auto-open browser ─────────────────────────────────────────────
    try:
        log.info(f"[{agent_id}] Opening browser: {frontend_url}")
        webbrowser.open(frontend_url)
    except Exception as _oe:
        log.debug(f"[{agent_id}] Could not open browser automatically: {_oe}")

    # ── Wait for backend ──────────────────────────────────────────────
    try:
        backend_proc.wait()
    except KeyboardInterrupt:
        log.info(f"[{agent_id}] KeyboardInterrupt — stopping")
        backend_proc.terminate()


# =============================================================================
# Standalone entry point
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    if len(sys.argv) < 2:
        print("Usage: python chat_launcher.py <agent_id> [brain_path] [backend_port]")
        sys.exit(1)

    _cfg: Dict[str, Any] = {}
    _brain = sys.argv[2] if len(sys.argv) >= 3 else ""
    if len(sys.argv) >= 4:
        try:
            _cfg["backend_port"] = int(sys.argv[3])
        except ValueError:
            pass

    start_chat_interface(sys.argv[1], _brain, _cfg)