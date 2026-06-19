# py_backend/process_manager.py
"""
Phase 7 — Process Isolation: One Process Per Agent
====================================================
Each agent runs as an independent Python subprocess.
No shared memory → true individuality, crash isolation, OS-level scheduling.

Usage (from main.py or auto_connect_system.py):

    manager = AgentProcessManager()
    port    = manager.spawn_agent('Alice', alice_config, port=11401)
    # Alice now runs independently in her own process

    # Health monitoring (call every N seconds from a background thread):
    manager.health_check_all()   # auto-restarts crashed agents

    # Graceful shutdown:
    manager.kill_agent('Alice')
    manager.kill_all()
"""

import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Callable, Any, IO

log = logging.getLogger("process_manager")


class AgentProcessManager:
    """
    Launches and monitors one Python subprocess per agent.
    Each subprocess runs agent_runner.py with a JSON config file.

    Inter-process communication uses HTTP (existing pattern via
    PythonBackendClient / FastAPI). This manager only handles
    lifecycle (spawn / kill / restart).
    """

    def __init__(
        self,
        base_port:   int = 11400,
        runner_path: Optional[str] = None,
        brain_dir:   str = 'brains',
    ):
        self.base_port   = base_port
        self.runner_path = runner_path or str(
            Path(__file__).parent / 'agent_runner.py'
        )
        self.brain_dir   = Path(brain_dir)
        self.brain_dir.mkdir(parents=True, exist_ok=True)

        self._processes: Dict[str, subprocess.Popen] = {}
        self._log_files: Dict[str, IO]                 = {}  # FIX Step 2f
        self._ports:     Dict[str, int]               = {}
        self._configs:   Dict[str, dict]              = {}

        # Optional crash callback: on_crash(agent_id, exit_code) → bool (True = restart)
        self.on_crash: Optional[Callable[[str, int], bool]] = None

    # ──────────────────────────────────────────────────────────────────────
    # Spawn / Kill
    # ──────────────────────────────────────────────────────────────────────

    def spawn_agent(
        self,
        agent_id:     str,
        agent_config: dict,
        port:         Optional[int] = None,
    ) -> int:
        """
        Launch an agent in its own Python process.
        Returns the port the agent is listening on.
        """
        if self.is_alive(agent_id):
            log.warning(f"Agent {agent_id} already running — skipping spawn")
            return self._ports[agent_id]

        if port is None:
            port = self.base_port + len(self._processes)

        config = {**agent_config, 'agent_id': agent_id, 'port': port}
        config_path = Path(f'/tmp/dw_agent_{agent_id}.json')
        config_path.write_text(json.dumps(config))

        # FIX Step 2f: stdout=PIPE/stderr=PIPE with nothing ever reading them
        # fills the OS pipe buffer (64KB on Linux) and the child process blocks
        # on its next write() — a guaranteed deadlock under any real log volume.
        # Redirect to a per-agent file instead; the handle is kept open and
        # closed in kill_agent() so it can be tailed live and doesn't leak fds.
        log_path = self.brain_dir / f'{agent_id}.log'
        log_file = open(log_path, 'a')
        self._log_files[agent_id] = log_file

        proc = subprocess.Popen(
            [sys.executable, self.runner_path, str(config_path)],
            stdout=log_file,
            stderr=log_file,
        )

        self._processes[agent_id] = proc
        self._ports[agent_id]     = port
        self._configs[agent_id]   = config

        log.info(
            f"Spawned agent '{agent_id}' on port {port} "
            f"(PID {proc.pid}, log={log_path})"
        )
        return port

    def kill_agent(self, agent_id: str, timeout: float = 5.0):
        """Gracefully terminate an agent process."""
        proc = self._processes.pop(agent_id, None)
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log.warning(f"Agent '{agent_id}' did not stop — sending SIGKILL")
                proc.kill()
        self._ports.pop(agent_id, None)

        # FIX Step 2f: close the per-agent log file opened in spawn_agent()
        log_file = self._log_files.pop(agent_id, None)
        if log_file is not None:
            try:
                log_file.close()
            except Exception:
                pass

        log.info(f"Killed agent '{agent_id}'")

    def kill_all(self, timeout: float = 5.0):
        """Terminate all running agent processes."""
        for agent_id in list(self._processes.keys()):
            self.kill_agent(agent_id, timeout)

    # ──────────────────────────────────────────────────────────────────────
    # Health monitoring
    # ──────────────────────────────────────────────────────────────────────

    def is_alive(self, agent_id: str) -> bool:
        proc = self._processes.get(agent_id)
        return proc is not None and proc.poll() is None

    def health_check_all(self):
        """
        Check all agents. Restart any that have crashed.
        Call this from a background thread (e.g. every 30 seconds).
        """
        for agent_id, proc in list(self._processes.items()):
            if proc.poll() is None:
                continue   # still running

            exit_code = proc.returncode
            log.warning(
                f"Agent '{agent_id}' exited with code {exit_code} — "
                f"checking restart policy"
            )

            # FIX Step 2f: close the crashed process's log handle before
            # spawn_agent() opens a fresh one for the restart (avoids an
            # accumulating fd leak across repeated crash/restart cycles).
            stale_log = self._log_files.pop(agent_id, None)
            if stale_log is not None:
                try:
                    stale_log.close()
                except Exception:
                    pass

            should_restart = True
            if self.on_crash:
                should_restart = self.on_crash(agent_id, exit_code)

            if should_restart:
                config = self._configs.get(agent_id, {})
                port   = self._ports.pop(agent_id, None)
                self._processes.pop(agent_id)
                log.info(f"Restarting agent '{agent_id}'…")
                time.sleep(2)   # brief pause before restart
                self.spawn_agent(agent_id, config, port)
            else:
                self._processes.pop(agent_id)
                self._ports.pop(agent_id, None)

    def get_status(self) -> dict:
        return {
            agent_id: {
                'alive':    self.is_alive(agent_id),
                'port':     self._ports.get(agent_id),
                'pid':      (proc.pid if proc.poll() is None else None),
                'exit':     proc.poll(),
            }
            for agent_id, proc in self._processes.items()
        }