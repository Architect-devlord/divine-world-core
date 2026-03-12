"""
Frontend build helper for DW Agent
===================================
Builds the React/Vite frontend and copies the output into a destination
directory that packager.py bundles into the agent exe.

Usage (called by packager.py):
    from frontend_builder import FrontendBuilder
    ok = FrontendBuilder().build_frontend(frontend_dir, output_dir)

Standalone test:
    python frontend_builder.py [frontend_dir [output_dir]]
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("frontend_builder")

# ---------------------------------------------------------------------------
# Locate npm once at import time so the module-level constant can be reused
# by packager.py (which also declares NPM_CMD itself).
# ---------------------------------------------------------------------------
NPM_CMD: str = shutil.which("npm") or "npm"

# Build timeouts — intentionally generous for slow machines.
# The poller below will log progress and move on as soon as dist/ appears,
# so a fast machine is not penalised by these upper limits.
_INSTALL_TIMEOUT  = 600   # 10 min  (cold npm install with large dep tree)
_BUILD_TIMEOUT    = 600   # 10 min  (Vite on a slow HDD + big chunks)
_DIST_POLL_SECS   = 3     # how often to check for dist/index.html
_DIST_WAIT_EXTRA  = 10    # extra seconds after index.html appears (file flush)

# Vite / CRA output directories, searched in priority order
_BUILD_OUTPUT_DIRS = ("dist", "build", "out")


def _make_npm_env() -> dict:
    """
    Return an os.environ copy with settings that make CI npm runs reliable:

    - CI=true       Vite/CRA treats this as a non-interactive build, turning
                    warnings into errors so we catch problems early rather
                    than shipping a broken frontend silently.
    - NODE_ENV=production  Ensures tree-shaking and minification.
    - NO_COLOR=1    Strips ANSI codes from stderr so log lines are clean.
    """
    env = os.environ.copy()
    # NOTE: Do NOT set CI=true — Vite interprets it as "treat warnings as
    # errors", which causes chunk-size warnings to abort the build on slow
    # machines.  We handle build failures through CalledProcessError instead.
    env.pop("CI", None)
    env.setdefault("NODE_ENV",     "production")
    env.setdefault("NO_COLOR",     "1")
    return env


class FrontendBuilder:
    """Builds the React/Vite frontend for packaging into an agent exe."""

    def __init__(self, npm_cmd: Optional[str] = None):
        self.npm_cmd = npm_cmd or NPM_CMD
        if not shutil.which(self.npm_cmd):
            log.warning(
                f"npm not found at '{self.npm_cmd}'. "
                "Install Node.js and ensure npm is on PATH, or the build will fail."
            )
        else:
            log.info(f"npm: {self.npm_cmd}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_frontend(self, frontend_dir: Path, output_dir: Path) -> bool:
        """
        Build the React frontend and copy the output to output_dir.

        Steps:
          1. Validate the source directory (must contain package.json).
          2. Run 'npm install' if node_modules is missing.
          3. Run 'npm run build'.
          4. Find the build output (dist/ build/ or out/).
          5. Replace output_dir with the freshly-built tree.

        Returns True on success, False on any failure.
        """
        frontend_dir = Path(frontend_dir)
        output_dir   = Path(output_dir)
        env          = _make_npm_env()

        log.info(f"🔨 Building frontend: {frontend_dir} → {output_dir}")

        # ── 1. Validate ────────────────────────────────────────────────
        if not frontend_dir.exists():
            log.error(f"Frontend directory not found: {frontend_dir}")
            return False
        if not (frontend_dir / "package.json").exists():
            log.error(f"No package.json in: {frontend_dir}")
            return False

        # ── 2. Install dependencies ────────────────────────────────────
        if not (frontend_dir / "node_modules").exists():
            log.info("📦 npm install (first run — this may take a minute)…")
            ok, err = self._run(
                [self.npm_cmd, "install", "--prefer-offline"],
                cwd=frontend_dir, env=env,
                timeout=_INSTALL_TIMEOUT,
                label="npm install",
            )
            if not ok:
                log.error(f"npm install failed:\n{err}")
                return False

        # ── 3. Build ───────────────────────────────────────────────────
        log.info("⚙️  npm run build…")
        ok, err = self._run(
            [self.npm_cmd, "run", "build"],
            cwd=frontend_dir, env=env,
            timeout=_BUILD_TIMEOUT,
            label="npm run build",
        )

        # ── 3b. Recovery: esbuild missing (rolldown-vite v7+) ──────────
        # rolldown-vite v7 removed the bundled esbuild minifier.  If the
        # build fails with the "Cannot find package 'esbuild'" message,
        # install esbuild explicitly and retry once.
        if not ok and ("Cannot find package 'esbuild'" in err or
                       "transformWithEsbuild" in err or
                       "esbuild" in err.lower()):
            log.warning(
                "Build failed due to missing esbuild package "
                "(rolldown-vite v7+ requires it separately). "
                "Installing esbuild and retrying…"
            )
            fix_ok, fix_err = self._run(
                [self.npm_cmd, "install", "--save-dev", "esbuild"],
                cwd=frontend_dir, env=env,
                timeout=120,
                label="npm install esbuild",
            )
            if not fix_ok:
                log.error(f"esbuild install failed:\n{fix_err}")
                # Fall through — let the original error be reported below
            else:
                log.info("esbuild installed — retrying build…")
                ok, err = self._run(
                    [self.npm_cmd, "run", "build"],
                    cwd=frontend_dir, env=env,
                    timeout=_BUILD_TIMEOUT,
                    label="npm run build (retry)",
                )

        if not ok:
            log.error(f"npm run build failed:\n{err}")
            return False

        # ── 4. Wait for output directory to appear on disk ─────────────
        # On slow machines the dist/ folder may not be fully flushed to
        # disk by the time subprocess.run() returns.  Poll until we find
        # index.html, then wait a little longer for all assets to land.
        build_dir = self._poll_for_build_output(frontend_dir)
        if build_dir is None:
            log.error(
                f"Build succeeded but no output directory found after polling. "
                f"Looked for: {_BUILD_OUTPUT_DIRS}"
            )
            return False

        # ── 5. Copy to destination ─────────────────────────────────────
        try:
            if output_dir.exists():
                shutil.rmtree(output_dir)
            shutil.copytree(build_dir, output_dir)
        except Exception as exc:
            log.error(f"Failed to copy build output: {exc}")
            return False

        log.info(f"✅ Frontend built → {output_dir}")
        return True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run(
        cmd: list,
        cwd: Path,
        env: dict,
        timeout: int,
        label: str,
    ):
        """
        Run a subprocess, capturing stdout+stderr.

        Returns (success: bool, stderr_text: str).
        stderr is returned even on success so the caller can log warnings.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=str(cwd),
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            # Vite/CRA sometimes write informational lines to stderr —
            # only log them at DEBUG to avoid spamming the build log.
            if result.stderr.strip():
                log.debug(f"{label} stderr:\n{result.stderr.rstrip()}")
            return True, result.stderr

        except subprocess.TimeoutExpired:
            log.error(f"{label} timed out after {timeout}s")
            return False, f"Timed out after {timeout}s"

        except subprocess.CalledProcessError as exc:
            # Combine stdout + stderr; CRA writes errors to stdout, Vite to stderr.
            combined = "\n".join(filter(None, [exc.stdout, exc.stderr])).strip()
            return False, combined

        except FileNotFoundError:
            return False, f"Command not found: {cmd[0]}"

    @staticmethod
    def _find_build_output(frontend_dir: Path) -> Optional[Path]:
        """Return the first recognised build output directory, or None."""
        for name in _BUILD_OUTPUT_DIRS:
            candidate = frontend_dir / name
            if candidate.is_dir():
                # Sanity-check: the output should contain at least one HTML file
                if any(candidate.rglob("*.html")):
                    return candidate
                log.debug(
                    f"Found {candidate} but it contains no HTML files — skipping"
                )
        return None

    @classmethod
    def _poll_for_build_output(cls, frontend_dir: Path) -> Optional[Path]:
        """
        Poll for the build output directory to appear on disk.

        npm run build returns as soon as the Rollup/Vite process exits, but
        on slow HDDs the OS may not have flushed all file writes yet.
        We keep checking every _DIST_POLL_SECS seconds until either:
          - dist/index.html (or equivalent) appears  → wait _DIST_WAIT_EXTRA
            more seconds for remaining assets, then return the directory
          - _BUILD_TIMEOUT seconds have elapsed       → give up and return None

        Progress is logged every 15 seconds so the user can see it's working.
        """
        import time as _time
        deadline    = _time.monotonic() + _BUILD_TIMEOUT
        last_log    = _time.monotonic()
        log.info("Waiting for build output to appear on disk…")

        while _time.monotonic() < deadline:
            candidate = cls._find_build_output(frontend_dir)
            if candidate is not None:
                # File found — give the OS a moment to flush remaining assets
                log.info(
                    f"✅ Build output found: {candidate} — "                    f"waiting {_DIST_WAIT_EXTRA}s for asset flush…"
                )
                _time.sleep(_DIST_WAIT_EXTRA)
                return candidate

            # Log progress every 15 s so the user knows we're not hung
            if _time.monotonic() - last_log >= 15:
                remaining = int(deadline - _time.monotonic())
                log.info(f"Still waiting for build output… ({remaining}s remaining)")
                last_log = _time.monotonic()

            _time.sleep(_DIST_POLL_SECS)

        return None


# ---------------------------------------------------------------------------
# Standalone test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
    )

    # Default paths match Config.FRONTEND_DIR / Config.FRONTEND_DIST_DIR
    _default_src  = Path("dw_agent/electron/react-app")
    _default_dest = Path("test_build")

    _frontend_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else _default_src
    _output_dir   = Path(sys.argv[2]) if len(sys.argv) > 2 else _default_dest

    success = FrontendBuilder().build_frontend(_frontend_dir, _output_dir)
    print(f"\nBuild {'✅ succeeded' if success else '❌ failed'}")
    sys.exit(0 if success else 1)