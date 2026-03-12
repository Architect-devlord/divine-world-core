# py_backend/minecraft_launcher.py
"""
UltimMC automation layer for Minecraft client setup and launching.
===================================================================
Provides:

  UltimMCLauncher    — wraps a single UltimMC installation.
                       Handles account creation, instance creation,
                       mod installation, and per-agent process launch.

  MultiAgentLauncher — manages N agents simultaneously by giving each
                       agent its own UltimMC folder copy (bypasses the
                       single-instance lock).  This is the object that
                       agent_spawner.UltimMCAgentSpawner uses directly.

Design notes
------------
- Each agent's UltimMC copy lives at npc_applications/<agent_id>/UltimMC/
- JVM args (-Ddw.agent.id, -Ddw.backend.url, -Ddw.backend.port, -Ddw.server)
  are injected via the INST_JAVA environment variable that UltimMC forwards
  to Java.  Property names match DWClientMod.loadConfiguration() exactly.
- headless=True wraps the command with xvfb-run -a (requires Xvfb).
- _find_ultimmc() uses the same multi-location search as packager.py so
  both code paths find UltimMC regardless of installation style.
"""

import json
import logging
import os
import shutil
import subprocess
import time
import uuid as _uuid_mod
from pathlib import Path
from typing import Any, Dict, List, Optional

from py_backend.config import Config
from py_backend.utils.mc_uuid import get_minecraft_uuid

log = logging.getLogger("minecraft_launcher")
log.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# UltimMCLauncher
# ---------------------------------------------------------------------------

class UltimMCLauncher:
    """Wraps a single UltimMC installation."""

    MINECRAFT_VERSION = Config.MINECRAFT_VERSION
    FORGE_VERSION     = Config.FORGE_VERSION

    def __init__(self,
                 ultimmc_path:       Optional[str]  = None,
                 client_jar_path:    Optional[str]  = None,
                 mod_jar_path:       Optional[str]  = None,
                 custom_ultimmc_dir: Optional[Path] = None):
        self.source_ultimmc_path = self._find_ultimmc(ultimmc_path)
        self.client_jar          = self._find_jar(client_jar_path, "dwclient-1.0.0.jar")
        self.mod_jar             = self._find_jar(mod_jar_path,    "divineworld-1.0.0-all.jar")

        self.ultimmc_dir:        Optional[Path] = custom_ultimmc_dir
        self.ultimmc_executable: Optional[Path] = None

        if self.ultimmc_dir:
            self._locate_executable()

        if self.source_ultimmc_path:
            log.info(f"✅ UltimMC source: {self.source_ultimmc_path}")
        else:
            log.warning(
                "⚠️  UltimMC not found. "
                "Install from https://github.com/UltimMC/Launcher "
                "or set DW_ULTIMMC_PATH."
            )
        for jar, label in [(self.client_jar, "dwclient"), (self.mod_jar, "divineworld")]:
            if jar:
                log.info(f"✅ {label}: {jar}")
            else:
                log.warning(f"⚠️  {label} jar not found")

    # ------------------------------------------------------------------
    # Path discovery
    # ------------------------------------------------------------------

    def _find_ultimmc(self, explicit: Optional[str]) -> Optional[Path]:
        """
        Search for UltimMC in priority order:
          1. Explicit path (env var / constructor arg)
          2. Project-relative (workspace root / UltimMC)
          3. Standard user-home locations
          4. Linux system prefixes
          5. PATH (handles symlinked / system-installed builds)
          6. macOS app bundle
        """
        if explicit:
            p = Path(os.path.expanduser(explicit))
            if p.exists():
                return p
            log.warning(f"Provided UltimMC path not found: {p}")

        cwd  = Path.cwd()
        root = cwd.parent if cwd.name == "py_backend" else cwd

        candidates = [
            # Project-relative
            root / "UltimMC",
            # User home
            Path.home() / "UltimMC",
            Path.home() / ".ultimmc",
            Path.home() / ".local" / "share" / "ultimmc",
            Path.home() / ".local" / "bin" / "UltimMC",
            Path.home() / ".local" / "bin" / "ultimmc",
            # System prefixes
            Path("/opt/ultimmc"),
            Path("/opt/UltimMC"),
            Path("/usr/local/bin/ultimmc"),
            Path("/usr/local/bin/UltimMC"),
        ]

        for path in candidates:
            if path.exists():
                # Accept either install root (has bin/UltimMC) or direct binary
                if (path / "bin" / "UltimMC").exists() or path.is_file():
                    log.info(f"Found UltimMC: {path}")
                    return path

        # PATH fallback — handles symlinked builds
        exe = shutil.which("ultimmc") or shutil.which("UltimMC")
        if exe:
            exe_path     = Path(exe)
            install_root = exe_path.parent.parent if exe_path.parent.name == "bin" else exe_path.parent
            log.info(f"Found UltimMC in PATH: {install_root}")
            return install_root

        # macOS bundle
        mac = Path("/Applications/UltimMC.app")
        if mac.exists():
            return mac

        log.info(
            "UltimMC not found — set DW_ULTIMMC_PATH or install to ~/UltimMC"
        )
        return None

    def _find_jar(self, explicit: Optional[str], filename: str) -> Optional[Path]:
        """Find a jar by explicit path or recursive search."""
        if explicit:
            p = Path(explicit)
            if p.exists():
                return p

        search_dirs = [
            Path.cwd(),
            Path.cwd() / "py_backend",
            Path.cwd() / "divine-world",
            Path("/opt/divine-world"),
        ]
        for d in search_dirs:
            if d.exists():
                hits = list(d.glob(f"**/{filename}"))
                if hits:
                    return hits[0]
        return None

    def _locate_executable(self):
        """
        Find the UltimMC binary inside self.ultimmc_dir.

        We always prefer <ultimmc_dir>/bin/UltimMC so that:
          • accounts.json lives at <ultimmc_dir>/bin/accounts.json  (correct)
          • "-d <ultimmc_dir>" passed to UltimMC resolves data paths correctly
        The flat-layout fallbacks are kept only for unusual build layouts but
        they should never be reached for a normal UltimMC installation.
        """
        if not self.ultimmc_dir:
            return
        # Primary: standard layout — binary is inside bin/
        primary = self.ultimmc_dir / "bin" / "UltimMC"
        if primary.exists() and os.access(primary, os.X_OK):
            self.ultimmc_executable = primary
            log.info(f"UltimMC executable: {primary}")
            return
        # Fallbacks for non-standard builds
        for candidate in [
            self.ultimmc_dir / "UltimMC",
            self.ultimmc_dir / "ultimmc",
        ]:
            if candidate.exists() and os.access(candidate, os.X_OK):
                self.ultimmc_executable = candidate
                log.warning(
                    f"UltimMC executable found in non-standard location: {candidate}. "
                    f"accounts.json should still be at {self.ultimmc_dir}/bin/accounts.json"
                )
                return
        log.warning(f"No executable found in {self.ultimmc_dir}")

    # ------------------------------------------------------------------
    # Installation copy
    # ------------------------------------------------------------------

    def copy_ultimmc_installation(self, dest_dir: Path) -> bool:
        """
        Copy the entire UltimMC installation tree to dest_dir.

        source_root resolution rules (in order):
          1. If source path is a file (bare binary) → walk up to parent.
          2. If that parent is named "bin"          → walk up again to
             the install root (so we copy the whole tree, not just bin/).
             BUT only do this when the grandparent actually looks like a
             real UltimMC root (contains a bin/ subdirectory) — otherwise
             a system binary at /usr/local/bin/ultimmc would cause us to
             copy /usr/local/ into the agent folder.
          3. If source path is already a directory   → use as-is.
        """
        if not self.source_ultimmc_path:
            log.error("Source UltimMC not found — cannot copy")
            return False

        source_root = self.source_ultimmc_path.resolve()

        # Step 1: unwrap bare binary
        if source_root.is_file():
            source_root = source_root.parent

        # Step 2: unwrap bin/ sub-folder only when parent is a real install root
        if source_root.name == "bin":
            candidate_root = source_root.parent
            # A real UltimMC root has bin/UltimMC inside it
            if (candidate_root / "bin" / "UltimMC").exists():
                source_root = candidate_root
            else:
                log.warning(
                    f"Source is inside a 'bin' dir but parent does not look "
                    f"like a UltimMC install root ({candidate_root}). "
                    f"Using bin/ directory directly: {source_root}"
                )

        if dest_dir.exists():
            log.info(f"UltimMC copy already exists: {dest_dir}")
            self.ultimmc_dir = dest_dir
            self._locate_executable()
            # Verify the expected binary is present in the copy
            if not self.ultimmc_executable:
                log.error(
                    f"Existing copy at {dest_dir} has no executable — "
                    f"delete it and retry to force a fresh copy"
                )
                return False
            return True

        log.info(f"Copying UltimMC: {source_root} → {dest_dir}")
        try:
            shutil.copytree(source_root, dest_dir, symlinks=True)
            self.ultimmc_dir = dest_dir
            self._locate_executable()
            if not self.ultimmc_executable:
                log.error(
                    f"Copy succeeded but no executable found in {dest_dir}. "
                    f"Source tree may not contain bin/UltimMC."
                )
                return False
            os.chmod(self.ultimmc_executable, 0o755)
            log.info(f"✅ UltimMC copied to {dest_dir} "
                     f"(executable: {self.ultimmc_executable})")
            return True
        except Exception as e:
            log.error(f"❌ Copy failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def create_account(self, username: str, make_active: bool = True,
                       custom_uuid: Optional[str] = None) -> bool:
        """
        Create an offline-mode Minecraft account in UltimMC's accounts.json.

        accounts.json lives at <ultimmc_dir>/bin/accounts.json — inside the
        bin/ subdirectory, next to the UltimMC executable.  UltimMC reads it
        from there when launched with -d <ultimmc_dir>.
        """
        if not self.ultimmc_dir:
            log.error("ultimmc_dir not set")
            return False

        # Ensure bin/ exists (it should after copy, but be defensive)
        bin_dir = self.ultimmc_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        accounts_file = bin_dir / "accounts.json"
        if accounts_file.exists():
            try:
                data = json.loads(accounts_file.read_text())
                if "accounts" not in data:
                    data = {"accounts": [], "formatVersion": 3}
            except json.JSONDecodeError:
                log.warning("Corrupted accounts.json — resetting")
                data = {"accounts": [], "formatVersion": 3}
        else:
            data = {"accounts": [], "formatVersion": 3}

        account_uuid = custom_uuid or self._offline_uuid(username)
        log.info(f"Creating account: {username} ({account_uuid})")

        new_account: Dict[str, Any] = {
            "type": "Local",
            "profile": {
                "id":     account_uuid.replace("-", ""),
                "name":   username,
                "skin":   {"id": "", "url": "", "variant": ""},
                "capes":  [],
            },
            "entitlement": {
                "canPlayMinecraft": True,
                "ownsMinecraft":    True,
            },
            "ygg": {
                "extra": {
                    "clientToken": _uuid_mod.uuid4().hex,
                    "userName":    username,
                },
                "iat": int(time.time()),
            },
        }

        if make_active:
            for acc in data["accounts"]:
                acc.pop("active", None)
            new_account["active"] = True

        # Update or append
        for i, acc in enumerate(data["accounts"]):
            if acc.get("profile", {}).get("name") == username:
                data["accounts"][i] = new_account
                break
        else:
            data["accounts"].append(new_account)

        try:
            accounts_file.write_text(json.dumps(data, indent=4))
            log.info(f"✅ Account saved: {username}")
            return True
        except Exception as e:
            log.error(f"❌ accounts.json write failed: {e}")
            return False

    @staticmethod
    def _offline_uuid(username: str) -> str:
        """Generate Minecraft-standard offline UUID."""
        namespace = _uuid_mod.UUID("00000000-0000-0000-0000-000000000000")
        return str(_uuid_mod.uuid3(namespace, f"OfflinePlayer:{username}"))

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    def create_instance(self, instance_name: str, forge_install: bool = True) -> bool:
        """Create a Minecraft Forge instance in UltimMC."""
        if not self.ultimmc_dir:
            log.error("ultimmc_dir not set")
            return False

        instance_dir = self.ultimmc_dir / "instances" / instance_name
        instance_dir.mkdir(parents=True, exist_ok=True)

        # instance.cfg
        (instance_dir / "instance.cfg").write_text(
            f"InstanceType=OneSix\n"
            f"name={instance_name}\n"
            f"iconKey=default\n"
            f"notes=Divine World Agent Instance\n"
            f"OverrideJavaArgs=true\n"
            f"OverrideMemory=true\n"
            f"MaxMemAlloc=2048\n"
            f"MinMemAlloc=512\n"
            f"ShowConsole=false\n"
        )

        # mmc-pack.json
        components = [
            {
                "cachedName": "LWJGL 3", "cachedVersion": "3.3.1",
                "cachedVolatile": True, "dependencyOnly": True,
                "uid": "org.lwjgl3", "version": "3.3.1",
            },
            {
                "cachedName": "Minecraft",
                "cachedRequires": [{"uid": "org.lwjgl3"}],
                "cachedVersion": self.MINECRAFT_VERSION,
                "important": True,
                "uid": "net.minecraft",
                "version": self.MINECRAFT_VERSION,
            },
        ]
        if forge_install:
            components.append({
                "cachedName": "Forge",
                "cachedVersion": self.FORGE_VERSION,
                "uid": "net.minecraftforge",
                "version": self.FORGE_VERSION,
            })

        (instance_dir / "mmc-pack.json").write_text(
            json.dumps({"components": components, "formatVersion": 1}, indent=2)
        )

        log.info(f"✅ Instance created: {instance_name}")
        return True

    def install_mods(self, instance_name: str) -> bool:
        """Install DivineWorld + DWClientBot mods into instance."""
        if not self.ultimmc_dir:
            log.error("ultimmc_dir not set")
            return False

        mods_dir = (
            self.ultimmc_dir / "instances" / instance_name / ".minecraft" / "mods"
        )
        mods_dir.mkdir(parents=True, exist_ok=True)

        ok = True
        for jar, label in [(self.mod_jar, "DivineWorld"), (self.client_jar, "DWClientBot")]:
            if not jar:
                continue
            try:
                shutil.copy(jar, mods_dir / jar.name)
                log.info(f"✅ Installed {label}: {jar.name}")
            except Exception as e:
                log.error(f"❌ Failed to install {label}: {e}")
                ok = False
        return ok

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def launch_instance(self, instance_name: str,
                        server_addr:     Optional[str]       = None,
                        profile_name:    Optional[str]       = None,
                        offline:         bool                 = True,
                        offline_name:    Optional[str]       = None,
                        agent_id:        Optional[str]       = None,
                        backend_url:     Optional[str]       = None,
                        memory_mb:       int                  = Config.CLIENT_MEMORY_MB,
                        extra_jvm_args:  Optional[List[str]] = None,
                        headless:        bool                 = False) -> Optional[subprocess.Popen]:
        """
        Launch a Minecraft instance via UltimMC's built-in flags.
        JVM system properties are passed via the INST_JAVA env var.
        """
        if not self.ultimmc_executable:
            log.error("No UltimMC executable — cannot launch")
            return None

        # Resolve to absolute so cwd doesn't interfere
        exe = self.ultimmc_executable.resolve()

        # Safety check: reject root-level shell scripts.
        # The real binary lives at <ultimmc_dir>/bin/UltimMC.
        # A UltimMC shell wrapper at the install root has the same name but
        # is NOT the binary — running it from the wrong cwd fails silently.
        if exe.parent.name != "bin":
            # Try to find the real binary one level deeper before giving up
            real_bin = exe.parent / "bin" / "UltimMC"
            if real_bin.exists() and os.access(real_bin, os.X_OK):
                log.warning(
                    f"ultimmc_executable points at install root ({exe}), "
                    f"correcting to real binary: {real_bin}"
                )
                exe = real_bin.resolve()
                self.ultimmc_executable = real_bin
                # Also fix ultimmc_dir to the folder that contains bin/
                self.ultimmc_dir = real_bin.parent.parent
            else:
                log.error(
                    f"ultimmc_executable ({exe}) is not inside a bin/ directory "
                    f"and no bin/UltimMC found alongside it. "
                    f"Expected: {exe.parent / 'bin' / 'UltimMC'}"
                )
                return None

        if not exe.exists():
            log.error(f"UltimMC binary not found: {exe}")
            return None
        if not os.access(exe, os.X_OK):
            log.warning(f"UltimMC binary not executable — fixing permissions: {exe}")
            os.chmod(exe, 0o755)

        cmd = []
        if headless:
            cmd.extend(["xvfb-run", "-a"])

        # Use the validated absolute binary and derive the data dir from it.
        # ultimmc_dir must be the folder that CONTAINS bin/ (not bin/ itself),
        # so that -d <dir> makes UltimMC find accounts.json at <dir>/bin/accounts.json
        # and instances/ at <dir>/instances/.
        data_dir = exe.parent.parent   # .../UltimMC/bin/UltimMC → .../UltimMC/
        cmd += [
            str(exe),
            "-d", str(data_dir / "bin"), # Executive live along side accounts.json and the -d flag of UltimMC should point to the bin containing the accounts.json and the UltimMC executable.
            "--alive",
            "-l", 1.20.1, #launches the 1.20.1 instance of minecraft in UltimMC if other version of instance is to be use it should be created then specified here 
        ]

        if server_addr:
            cmd += ["-s", server_addr]

        # Always pass -a so UltimMC selects exactly the right pre-configured
        # account from accounts.json.  Without -a UltimMC picks whichever
        # account is marked active=true, which may be wrong if the per-agent
        # copy has multiple entries.  profile_name takes precedence over
        # offline_name since it's the explicit caller override.
        _account_name = profile_name or offline_name
        if _account_name:
            cmd += ["-a", _account_name]

        if offline:
            cmd.append("-o")
            if offline_name:
                cmd += ["-n", offline_name]

        jvm = [f"-Xmx{memory_mb}M", f"-Xms{memory_mb}M"]
        if agent_id:
            # DWClientMod.loadConfiguration() reads dw.agent.id (not dw.agentId)
            jvm.append(f"-Ddw.agent.id={agent_id}")
        if backend_url:
            # DWClientMod reads dw.backend.url and dw.backend.port separately.
            # backend_url arrives as "ws://127.0.0.1:<port>" — split it so the
            # client gets the right WebSocket host and the correct agent port.
            # WebSocketManager builds:  dw.backend.url + ":" + dw.backend.port + "/ws/agent"
            try:
                from urllib.parse import urlparse
                parsed = urlparse(backend_url)
                ws_host = f"{parsed.scheme}://{parsed.hostname}"
                ws_port = parsed.port or 11400
            except Exception:
                ws_host = "ws://127.0.0.1"
                ws_port = 11400
            jvm.append(f"-Ddw.backend.url={ws_host}")
            jvm.append(f"-Ddw.backend.port={ws_port}")
        if server_addr:
            jvm.append(f"-Ddw.server={server_addr}")
        if extra_jvm_args:
            jvm.extend(extra_jvm_args)

        env              = os.environ.copy()
        env["INST_JAVA"] = " ".join(jvm)

        log.info(
            f"Launching UltimMC: instance={instance_name} "
            f"executable={exe} "
            f"data_dir={data_dir} "
            f"accounts={data_dir / 'bin' / 'accounts.json'} "
            f"server={server_addr} offline_name={offline_name} "
            f"ws_backend={backend_url} headless={headless}"
        )
        try:
            process = subprocess.Popen(
                cmd, cwd=str(data_dir), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            log.info(f"✅ Launched PID {process.pid}")
            return process
        except Exception as e:
            log.error(f"❌ Launch failed: {e}")
            return None


# ---------------------------------------------------------------------------
# MultiAgentLauncher
# ---------------------------------------------------------------------------

class MultiAgentLauncher:
    """
    Manages N independent agents by giving each its own UltimMC folder copy.
    This is the object UltimMCAgentSpawner in agent_spawner.py uses directly.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        # base_dir is only used as a fallback when the packaged UltimMC copy
        # doesn't exist yet.  We default to NPC_APPLICATIONS_DIR so any
        # fallback clones land alongside the agent folders.
        self.base_dir = Path(base_dir) if base_dir else Path(Config.NPC_APPLICATIONS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.launchers: Dict[str, UltimMCLauncher] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        log.info(f"MultiAgentLauncher base: {self.base_dir}")

    # ------------------------------------------------------------------
    # Per-agent setup
    # ------------------------------------------------------------------

    def create_launcher_for_agent(
        self, agent_id: str,
        source_launcher: Optional[UltimMCLauncher] = None,
    ) -> Optional[UltimMCLauncher]:
        """
        Return a UltimMCLauncher for this agent.

        The canonical path is:
            npc_applications/<agent_id>/UltimMC/bin/UltimMC

        packager._setup_ultimmc() copies the UltimMC tree to
        npc_applications/<agent_id>/UltimMC/, so:
            ultimmc_dir        = npc_applications/<agent_id>/UltimMC/
            ultimmc_executable = npc_applications/<agent_id>/UltimMC/bin/UltimMC
            accounts.json      = npc_applications/<agent_id>/UltimMC/bin/accounts.json

        If that copy doesn't exist yet (agent not packaged), we fall back to
        cloning the system UltimMC into base_dir/<agent_id>/UltimMC/.
        """
        # ── Option 1: use the packaged per-agent UltimMC (correct path) ───────
        # packager copies to:  npc_applications/<id>/UltimMC/
        # executable lives at: npc_applications/<id>/UltimMC/bin/UltimMC
        packaged_dir  = Config.NPC_APPLICATIONS_DIR / agent_id / "UltimMC"
        packaged_exe  = packaged_dir / "bin" / "UltimMC"
        if packaged_exe.exists() and os.access(packaged_exe, os.X_OK):
            log.info(f"Using packaged UltimMC for {agent_id}: {packaged_dir}")
            launcher = UltimMCLauncher.__new__(UltimMCLauncher)
            launcher.source_ultimmc_path = packaged_dir
            launcher.client_jar          = source_launcher.client_jar if source_launcher else None
            launcher.mod_jar             = source_launcher.mod_jar    if source_launcher else None
            launcher.ultimmc_dir         = packaged_dir          # -d <dir> arg
            launcher.ultimmc_executable  = packaged_exe
            os.chmod(packaged_exe, 0o755)
            log.info(
                f"✅ Agent {agent_id} → "
                f"executable: {packaged_exe} | "
                f"accounts:   {packaged_dir / 'bin' / 'accounts.json'}"
            )
            self.launchers[agent_id] = launcher
            return launcher

        # ── Option 2: fall back to cloning the system UltimMC ────────────────
        log.info(
            f"Packaged UltimMC not found for {agent_id} at {packaged_exe} "
            f"— falling back to per-agent clone in {self.base_dir}"
        )
        dest = self.base_dir / agent_id / "UltimMC"
        launcher = UltimMCLauncher(
            ultimmc_path    = str(source_launcher.source_ultimmc_path) if (source_launcher and source_launcher.source_ultimmc_path) else None,
            client_jar_path = str(source_launcher.client_jar)          if (source_launcher and source_launcher.client_jar)          else None,
            mod_jar_path    = str(source_launcher.mod_jar)             if (source_launcher and source_launcher.mod_jar)             else None,
        )
        if not launcher.copy_ultimmc_installation(dest):
            log.error(f"Failed to copy UltimMC for {agent_id}")
            return None

        # Sanity-check: executable must point inside dest
        if launcher.ultimmc_executable:
            try:
                launcher.ultimmc_executable.relative_to(dest)
            except ValueError:
                log.error(
                    f"BUG: ultimmc_executable {launcher.ultimmc_executable} "
                    f"is outside {dest} — aborting"
                )
                return None
            log.info(
                f"✅ Agent {agent_id} (fallback clone) → "
                f"executable: {launcher.ultimmc_executable} | "
                f"accounts:   {dest / 'bin' / 'accounts.json'}"
            )

        self.launchers[agent_id] = launcher
        return launcher

    def setup_agent(self, agent_id: str,
                    server_addr:     str  = Config.DEFAULT_SERVER,
                    custom_uuid:     Optional[str]             = None,
                    agent_type:      str  = 'npc',
                    custom_name:     Optional[str]             = None,
                    source_launcher: Optional[UltimMCLauncher] = None) -> bool:
        """
        Full per-agent setup: copy UltimMC, create account,
        create Forge instance, install mods.
        """
        launcher = self.create_launcher_for_agent(agent_id, source_launcher)
        if launcher is None:
            return False

        # Determine Minecraft username
        if custom_name and custom_name != "Unnamed":
            username = custom_name
        elif agent_type.startswith("god_"):
            username = f"DWGOD_{agent_type.replace('god_','').upper()}_{agent_id}"
        else:
            username = f"DW_{agent_id}"

        if not custom_uuid:
            custom_uuid = get_minecraft_uuid(username)

        instance_name = f"agent_{agent_id}"

        if not launcher.create_account(username, make_active=True, custom_uuid=custom_uuid):
            log.error(f"Account creation failed for {agent_id}")
            return False
        if not launcher.create_instance(instance_name, forge_install=True):
            return False
        if not launcher.install_mods(instance_name):
            log.warning(f"Some mods failed for {agent_id}")

        log.info(f"✅ Agent {agent_id} set up as {username!r}")
        return True

    # ------------------------------------------------------------------
    # Launch
    # ------------------------------------------------------------------

    def launch_agent(self, agent_id: str, server_addr: str,
                     backend_url: str,
                     memory_mb:       int  = Config.CLIENT_MEMORY_MB,
                     extra_jvm_args:  Optional[List[str]] = None,
                     headless:        bool = False,
                     agent_type:      str  = 'npc',
                     custom_name:     Optional[str] = None) -> Optional[subprocess.Popen]:
        """Launch a single agent's Minecraft client."""
        if agent_id not in self.launchers:
            log.error(f"No launcher for {agent_id} — call setup_agent() first")
            return None

        launcher      = self.launchers[agent_id]
        instance_name = f"agent_{agent_id}"

        if custom_name and custom_name != "Unnamed":
            offline_name = custom_name
        elif agent_type.startswith("god_"):
            offline_name = f"DWGOD_{agent_type.replace('god_','').upper()}_{agent_id}"
        else:
            offline_name = f"DW_{agent_id}"

        process = launcher.launch_instance(
            instance_name=instance_name,
            server_addr=server_addr,
            # Pass profile_name = offline_name so UltimMC's -a flag selects
            # exactly this agent's pre-configured account.  Without this the
            # account selection depends on which entry has active=true in
            # accounts.json, which is fragile across multiple agents.
            profile_name=offline_name,
            offline=True, offline_name=offline_name,
            agent_id=agent_id, backend_url=backend_url,
            memory_mb=memory_mb, extra_jvm_args=extra_jvm_args,
            headless=headless,
        )
        if process:
            self.processes[agent_id] = process
        return process

    def launch_multiple_agents(
        self,
        agent_configs:          List[Dict[str, Any]],
        delay_between_launches: float = 2.0,
        source_launcher:        Optional[UltimMCLauncher] = None,
        headless:               bool = False,
    ) -> Dict[str, subprocess.Popen]:
        """Launch a fleet of agents with a configurable inter-launch delay."""
        launched: Dict[str, subprocess.Popen] = {}

        for i, cfg in enumerate(agent_configs):
            aid = cfg["id"]
            log.info(f"Launching agent {i+1}/{len(agent_configs)}: {aid}")

            if aid not in self.launchers:
                ok = self.setup_agent(
                    agent_id=aid,
                    server_addr=cfg.get("server", Config.DEFAULT_SERVER),
                    custom_uuid=cfg.get("uuid"),
                    agent_type=cfg.get("agent_type", "npc"),
                    source_launcher=source_launcher,
                )
                if not ok:
                    log.error(f"Setup failed: {aid}")
                    continue

            process = self.launch_agent(
                agent_id=aid,
                server_addr=cfg.get("server",  Config.DEFAULT_SERVER),
                backend_url=cfg.get("backend", f"http://127.0.0.1:{Config.BASE_BACKEND_PORT}"),
                memory_mb=cfg.get("memory",    Config.CLIENT_MEMORY_MB),
                extra_jvm_args=cfg.get("extra_jvm_args"),
                headless=cfg.get("headless", headless),
                agent_type=cfg.get("agent_type", "npc"),
            )
            if process:
                launched[aid] = process
                log.info(f"✅ Launched {aid}")
            else:
                log.error(f"❌ Failed to launch {aid}")

            if i < len(agent_configs) - 1:
                log.info(f"Waiting {delay_between_launches}s…")
                time.sleep(delay_between_launches)

        log.info(f"Launched {len(launched)}/{len(agent_configs)} agents")
        return launched

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def stop_agent(self, agent_id: str, timeout: int = 10) -> bool:
        process = self.processes.get(agent_id)
        if process is None:
            log.warning(f"No running process for {agent_id}")
            return False
        try:
            process.terminate()
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        del self.processes[agent_id]
        log.info(f"✅ Stopped {agent_id}")
        return True

    def stop_all_agents(self) -> int:
        return sum(self.stop_agent(aid) for aid in list(self.processes.keys()))

    def get_running_agents(self) -> List[str]:
        dead = [aid for aid, p in list(self.processes.items()) if p.poll() is not None]
        for aid in dead:
            del self.processes[aid]
        return [aid for aid in self.processes if self.processes[aid].poll() is None]