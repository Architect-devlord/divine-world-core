# py_backend/minecraft_launcher.py
"""
UltimMC automation layer — cross-platform (Linux / Windows / macOS).
"""
import json
import logging
import os
import platform
import shutil
import subprocess
import time
import uuid as _uuid_mod
from pathlib import Path
from typing import Any, Dict, List, Optional

from py_backend.config import Config
from py_backend.utils.mc_uuid import get_minecraft_uuid, AgentNameManager

log = logging.getLogger("minecraft_launcher")
log.setLevel(logging.INFO)

_SYSTEM = platform.system()   # "Linux" | "Windows" | "Darwin"


class UltimMCLauncher:
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
            log.warning("⚠️  UltimMC not found — set minecraft_path in agents.json or DW_ULTIMMC_PATH")
        for jar, label in [(self.client_jar, "dwclient"), (self.mod_jar, "divineworld")]:
            if jar:
                log.info(f"✅ {label}: {jar}")
            else:
                log.warning(f"⚠️  {label} jar not found")

    # ------------------------------------------------------------------
    # Path discovery — cross-platform
    # ------------------------------------------------------------------

    def _find_ultimmc(self, explicit: Optional[str]) -> Optional[Path]:
        """
        Priority:
          0. agents.json  minecraft_path  (highest)
          1. Explicit arg or DW_ULTIMMC_PATH env var
          2. Project-relative UltimMC/ folder
          3. Platform-specific user locations
          4. PATH fallback
        """
        # ── 0. agents.json ──────────────────────────────────────────────
        try:
            mc_path = AgentNameManager.get_minecraft_path()
            if mc_path and mc_path.exists():
                log.info(f"UltimMC from agents.json: {mc_path}")
                return mc_path
        except Exception:
            pass

        # ── 1. Explicit arg / env var ────────────────────────────────────
        explicit = explicit or os.environ.get("DW_ULTIMMC_PATH")
        if explicit:
            p = Path(os.path.expandvars(os.path.expanduser(explicit)))
            if p.exists():
                return p
            log.warning(f"Provided UltimMC path not found: {p}")

        cwd  = Path.cwd()
        root = cwd.parent if cwd.name == "py_backend" else cwd
        home = Path.home()

        candidates: List[Path] = [root / "UltimMC"]   # 2. project-relative

        # ── 3. Platform-specific ─────────────────────────────────────────
        if _SYSTEM == "Windows":
            appdata      = Path(os.environ.get("APPDATA", home))
            localappdata = Path(os.environ.get("LOCALAPPDATA", home))
            candidates += [
                home / "UltimMC",
                home / "Desktop" / "UltimMC",
                home / "Downloads" / "UltimMC",
                appdata / "UltimMC",
                localappdata / "UltimMC",
                Path("C:/UltimMC"),
                Path("C:/Program Files/UltimMC"),
            ]
        elif _SYSTEM == "Darwin":
            candidates += [
                Path("/Applications/UltimMC.app/Contents/MacOS/UltimMC"),
                home / "Applications/UltimMC.app/Contents/MacOS/UltimMC",
                home / "UltimMC.app/Contents/MacOS/UltimMC",
                home / "UltimMC",
                Path("/Applications/UltimMC.app"),
                home / "Applications/UltimMC.app",
            ]
        else:  # Linux
            candidates += [
                home / "UltimMC",
                home / ".ultimmc",
                home / ".local/share/ultimmc",
                home / ".local/bin/UltimMC",
                Path("/opt/ultimmc"),
                Path("/opt/UltimMC"),
                Path("/usr/local/bin/ultimmc"),
            ]

        for path in candidates:
            if not path.exists():
                continue
            if path.is_file() and os.access(path, os.X_OK):
                return path
            if path.is_dir():
                for sub in self._exe_hints(path):
                    if sub.exists():
                        return path

        # ── 4. PATH ──────────────────────────────────────────────────────
        exe = shutil.which("ultimmc") or shutil.which("UltimMC")
        if exe:
            exe_path = Path(exe)
            install_root = exe_path.parent.parent if exe_path.parent.name == "bin" else exe_path.parent
            return install_root

        log.info("UltimMC not found — set minecraft_path in agents.json")
        return None

    @staticmethod
    def _exe_hints(base: Path) -> List[Path]:
        """Return ordered list of candidate executable paths inside base."""
        if _SYSTEM == "Windows":
            return [base / "bin" / "UltimMC.exe", base / "UltimMC.exe"]
        elif _SYSTEM == "Darwin":
            return [
                base / "Contents" / "MacOS" / "UltimMC",
                base / "UltimMC.app" / "Contents" / "MacOS" / "UltimMC",
                base / "bin" / "UltimMC",
                base / "UltimMC",
            ]
        else:
            return [base / "bin" / "UltimMC", base / "UltimMC", base / "ultimmc"]

    def _find_jar(self, explicit: Optional[str], filename: str) -> Optional[Path]:
        if explicit:
            p = Path(explicit)
            if p.exists():
                return p
        for d in [Path.cwd(), Path.cwd() / "py_backend",
                  Path.cwd() / "divine-world", Path("/opt/divine-world")]:
            if d.exists():
                hits = list(d.glob(f"**/{filename}"))
                if hits:
                    return hits[0]
        return None

    def _locate_executable(self):
        """Find the UltimMC binary inside self.ultimmc_dir (cross-platform)."""
        if not self.ultimmc_dir:
            return
        for candidate in self._exe_hints(self.ultimmc_dir):
            if candidate.exists():
                if _SYSTEM != "Windows" and not os.access(candidate, os.X_OK):
                    try:
                        os.chmod(candidate, 0o755)
                    except Exception:
                        pass
                self.ultimmc_executable = candidate
                log.info(f"UltimMC executable: {candidate}")
                return
        log.warning(f"No executable found in {self.ultimmc_dir}")

    # ------------------------------------------------------------------
    # Installation copy
    # ------------------------------------------------------------------

    def copy_ultimmc_installation(self, dest_dir: Path) -> bool:
        if not self.source_ultimmc_path:
            log.error("Source UltimMC not found — cannot copy")
            return False

        source_root = self.source_ultimmc_path.resolve()
        if source_root.is_file():
            source_root = source_root.parent
        if source_root.name in ("bin", "MacOS"):
            candidate_root = source_root.parent
            if source_root.name == "MacOS":
                candidate_root = source_root.parent.parent  # Contents/MacOS -> .app root
            if any((candidate_root / h).exists() for h in self._exe_hints(candidate_root)):
                source_root = candidate_root

        if dest_dir.exists():
            log.info(f"UltimMC copy already exists: {dest_dir}")
            self.ultimmc_dir = dest_dir
            self._locate_executable()
            if not self.ultimmc_executable:
                log.error(f"Existing copy at {dest_dir} has no executable — delete and retry")
                return False
            return True

        log.info(f"Copying UltimMC: {source_root} → {dest_dir}")
        try:
            shutil.copytree(source_root, dest_dir, symlinks=True)
            self.ultimmc_dir = dest_dir
            self._locate_executable()
            if not self.ultimmc_executable:
                log.error(f"Copy succeeded but no executable found in {dest_dir}")
                return False
            if _SYSTEM != "Windows":
                os.chmod(self.ultimmc_executable, 0o755)
            log.info(f"✅ UltimMC copied to {dest_dir}")
            return True
        except Exception as e:
            log.error(f"❌ Copy failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Account management
    # ------------------------------------------------------------------

    def create_account(self, username: str, make_active: bool = True,
                       custom_uuid: Optional[str] = None) -> bool:
        if not self.ultimmc_dir:
            log.error("ultimmc_dir not set")
            return False
        bin_dir = self.ultimmc_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        accounts_file = bin_dir / "accounts.json"
        if accounts_file.exists():
            try:
                data = json.loads(accounts_file.read_text())
                if "accounts" not in data:
                    data = {"accounts": [], "formatVersion": 3}
            except json.JSONDecodeError:
                data = {"accounts": [], "formatVersion": 3}
        else:
            data = {"accounts": [], "formatVersion": 3}

        account_uuid = custom_uuid or self._offline_uuid(username)
        new_account: Dict[str, Any] = {
            "type": "Local",
            "profile": {
                "id": account_uuid.replace("-", ""), "name": username,
                "skin": {"id": "", "url": "", "variant": ""}, "capes": [],
            },
            "entitlement": {"canPlayMinecraft": True, "ownsMinecraft": True},
            "ygg": {
                "extra": {"clientToken": _uuid_mod.uuid4().hex, "userName": username},
                "iat": int(time.time()),
            },
        }
        if make_active:
            for acc in data["accounts"]:
                acc.pop("active", None)
            new_account["active"] = True

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
        namespace = _uuid_mod.UUID("00000000-0000-0000-0000-000000000000")
        return str(_uuid_mod.uuid3(namespace, f"OfflinePlayer:{username}"))

    # ------------------------------------------------------------------
    # Instance management
    # ------------------------------------------------------------------

    def create_instance(self, instance_name: str, forge_install: bool = True) -> bool:
        if not self.ultimmc_dir:
            return False
        instance_dir = self.ultimmc_dir / "instances" / instance_name
        instance_dir.mkdir(parents=True, exist_ok=True)
        (instance_dir / "instance.cfg").write_text(
            f"InstanceType=OneSix\nname={instance_name}\niconKey=default\n"
            f"notes=Divine World Agent Instance\nOverrideJavaArgs=true\n"
            f"JvmArgs=\nOverrideMemory=true\nMaxMemAlloc=2048\n"
            f"MinMemAlloc=512\nShowConsole=false\n"
        )
        components = [
            {"cachedName": "LWJGL 3", "cachedVersion": "3.3.1", "cachedVolatile": True,
             "dependencyOnly": True, "uid": "org.lwjgl3", "version": "3.3.1"},
            {"cachedName": "Minecraft", "cachedRequires": [{"uid": "org.lwjgl3"}],
             "cachedVersion": self.MINECRAFT_VERSION, "important": True,
             "uid": "net.minecraft", "version": self.MINECRAFT_VERSION},
        ]
        if forge_install:
            components.append({
                "cachedName": "Forge", "cachedVersion": self.FORGE_VERSION,
                "uid": "net.minecraftforge", "version": self.FORGE_VERSION,
            })
        (instance_dir / "mmc-pack.json").write_text(
            json.dumps({"components": components, "formatVersion": 1}, indent=2)
        )
        log.info(f"✅ Instance created: {instance_name}")
        return True

    def _update_instance_cfg(self, instance_name: str,
                              jvm_props: list, memory_mb: int = 2048) -> bool:
        if not self.ultimmc_dir:
            return False
        instance_dir = self.ultimmc_dir / "instances" / instance_name
        cfg_path     = instance_dir / "instance.cfg"
        if not instance_dir.exists():
            log.warning(f"_update_instance_cfg: instance dir not found: {instance_dir}")
            return False
        current_lines = []
        if cfg_path.exists():
            try:
                current_lines = cfg_path.read_text(encoding="utf-8").splitlines()
            except Exception:
                pass
        managed = {"OverrideJavaArgs", "JvmArgs", "OverrideMemory", "MaxMemAlloc", "MinMemAlloc"}
        filtered = [l for l in current_lines if l.split("=")[0].strip() not in managed]
        jvm_args_str = " ".join(jvm_props)
        new_keys = [
            "OverrideJavaArgs=true", f"JvmArgs={jvm_args_str}",
            "OverrideMemory=true", f"MaxMemAlloc={memory_mb}", f"MinMemAlloc={memory_mb}",
        ]
        cfg_text = "\n".join(filtered + new_keys) + "\n"
        try:
            cfg_path.write_text(cfg_text, encoding="utf-8")
            log.info(f"[InstanceCfg] {instance_name}: JvmArgs={jvm_args_str!r} mem={memory_mb}MB")
            return True
        except Exception as e:
            log.error(f"_update_instance_cfg write failed: {e}")
            return False

    def install_mods(self, instance_name: str) -> bool:
        if not self.ultimmc_dir:
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
    # Launch — cross-platform
    # ------------------------------------------------------------------

    def launch_instance(self, instance_name: str,
                        server_addr:    Optional[str]       = None,
                        profile_name:   Optional[str]       = None,
                        offline:        bool                 = True,
                        offline_name:   Optional[str]       = None,
                        agent_id:       Optional[str]       = None,
                        backend_url:    Optional[str]       = None,
                        memory_mb:      int                  = Config.CLIENT_MEMORY_MB,
                        extra_jvm_args: Optional[List[str]] = None,
                        headless:       bool                 = False) -> Optional[subprocess.Popen]:
        if not self.ultimmc_executable:
            log.error("No UltimMC executable — cannot launch")
            return None

        exe = self.ultimmc_executable.resolve()

        # Ensure exe is inside a bin/ directory (correct layout)
        if exe.parent.name not in ("bin", "MacOS"):
            real_bin_name = "UltimMC.exe" if _SYSTEM == "Windows" else "UltimMC"
            real_bin = exe.parent / "bin" / real_bin_name
            if real_bin.exists():
                log.warning(f"Correcting executable path to: {real_bin}")
                exe = real_bin.resolve()
                self.ultimmc_executable = real_bin
                self.ultimmc_dir = real_bin.parent.parent
            else:
                log.error(f"UltimMC executable in unexpected location: {exe}")
                return None

        if not exe.exists():
            log.error(f"UltimMC binary not found: {exe}")
            return None

        # Set executable permissions on Linux/macOS
        if _SYSTEM != "Windows" and not os.access(exe, os.X_OK):
            log.warning(f"Fixing permissions: {exe}")
            os.chmod(exe, 0o755)

        data_dir = exe.parent.parent   # bin/UltimMC → UltimMC root

        # Build command — headless only on Linux
        cmd: List[str] = []
        if headless and _SYSTEM == "Linux":
            cmd.extend(["xvfb-run", "-a"])

        cmd += [str(exe), "-d", str(data_dir / "bin"), "--alive", "-l", "1.20.1"]

        if server_addr:
            cmd += ["-s", server_addr]

        _account_name = profile_name or offline_name
        if _account_name:
            cmd += ["-a", _account_name]

        if offline:
            cmd.append("-o")
            if offline_name:
                cmd += ["-n", offline_name]

        # JVM args
        jvm = [f"-Xmx{memory_mb}M", f"-Xms{memory_mb}M"]
        if agent_id:
            jvm.append(f"-Ddw.agent.id={agent_id}")
        if backend_url:
            try:
                from urllib.parse import urlparse
                parsed  = urlparse(backend_url)
                ws_host = f"{parsed.scheme}://{parsed.hostname}"
                ws_port = parsed.port or 11400
            except Exception:
                ws_host, ws_port = "ws://127.0.0.1", 11400
            jvm.append(f"-Ddw.backend.url={ws_host}")
            jvm.append(f"-Ddw.backend.port={ws_port}")

        _display = offline_name or agent_id
        if _display:
            try:
                _tcp_port = AgentNameManager().get_port_for_name(_display)
                if _tcp_port:
                    jvm.append(f"-Ddw.tcp.port={_tcp_port}")
                    log.info(f"[TCPPort] {_display!r} → port {_tcp_port}")
                else:
                    log.warning(f"[TCPPort] '{_display}' not in agents.json")
            except Exception as _e:
                log.warning(f"[TCPPort] lookup failed: {_e}")

        if server_addr:
            jvm.append(f"-Ddw.server={server_addr}")
        if extra_jvm_args:
            jvm.extend(extra_jvm_args)

        if self.ultimmc_dir:
            self._update_instance_cfg(
                instance_name=instance_name,
                jvm_props=[a for a in jvm if a.startswith("-D")],
                memory_mb=memory_mb,
            )

        env = os.environ.copy()
        env.pop("INST_JAVA", None)   # INST_JAVA is the Java exe path, NOT JVM args

        log.info(
            f"Launching UltimMC [{_SYSTEM}]: instance={instance_name} "
            f"exe={exe} data={data_dir} server={server_addr} "
            f"user={offline_name} headless={headless}"
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
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = Path(base_dir) if base_dir else Path(Config.NPC_APPLICATIONS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.launchers: Dict[str, UltimMCLauncher] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        log.info(f"MultiAgentLauncher base: {self.base_dir}")

    def create_launcher_for_agent(
        self, agent_id: str,
        source_launcher: Optional[UltimMCLauncher] = None,
    ) -> Optional[UltimMCLauncher]:
        packaged_dir = Config.NPC_APPLICATIONS_DIR / agent_id / "UltimMC"
        # Find the executable inside the packaged dir
        exe_hints    = UltimMCLauncher._exe_hints(packaged_dir)
        packaged_exe = next((h for h in exe_hints if h.exists()), None)

        if packaged_exe:
            if _SYSTEM != "Windows" and not os.access(packaged_exe, os.X_OK):
                os.chmod(packaged_exe, 0o755)
            log.info(f"Using packaged UltimMC for {agent_id}: {packaged_dir}")
            launcher = UltimMCLauncher.__new__(UltimMCLauncher)
            launcher.source_ultimmc_path = packaged_dir
            launcher.client_jar          = source_launcher.client_jar if source_launcher else None
            launcher.mod_jar             = source_launcher.mod_jar    if source_launcher else None
            launcher.ultimmc_dir         = packaged_dir
            launcher.ultimmc_executable  = packaged_exe
            self.launchers[agent_id] = launcher
            return launcher

        log.info(f"Packaged UltimMC not found for {agent_id} — cloning")
        dest    = self.base_dir / agent_id / "UltimMC"
        launcher = UltimMCLauncher(
            ultimmc_path    = str(source_launcher.source_ultimmc_path) if source_launcher and source_launcher.source_ultimmc_path else None,
            client_jar_path = str(source_launcher.client_jar)          if source_launcher and source_launcher.client_jar          else None,
            mod_jar_path    = str(source_launcher.mod_jar)             if source_launcher and source_launcher.mod_jar             else None,
        )
        if not launcher.copy_ultimmc_installation(dest):
            log.error(f"Failed to copy UltimMC for {agent_id}")
            return None

        if launcher.ultimmc_executable:
            try:
                launcher.ultimmc_executable.relative_to(dest)
            except ValueError:
                log.error(f"BUG: executable outside dest dir")
                return None

        self.launchers[agent_id] = launcher
        return launcher

    def setup_agent(self, agent_id: str,
                    server_addr:     str  = Config.DEFAULT_SERVER,
                    custom_uuid:     Optional[str]             = None,
                    agent_type:      str  = "npc",
                    custom_name:     Optional[str]             = None,
                    source_launcher: Optional[UltimMCLauncher] = None) -> bool:
        launcher = self.create_launcher_for_agent(agent_id, source_launcher)
        if launcher is None:
            return False
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

    def launch_agent(self, agent_id: str, server_addr: str,
                     backend_url: str,
                     memory_mb:       int  = Config.CLIENT_MEMORY_MB,
                     extra_jvm_args:  Optional[List[str]] = None,
                     headless:        bool = False,
                     agent_type:      str  = "npc",
                     custom_name:     Optional[str] = None) -> Optional[subprocess.Popen]:
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
            instance_name=instance_name, server_addr=server_addr,
            profile_name=offline_name, offline=True, offline_name=offline_name,
            agent_id=agent_id, backend_url=backend_url,
            memory_mb=memory_mb, extra_jvm_args=extra_jvm_args, headless=headless,
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
            else:
                log.error(f"❌ Failed to launch {aid}")
            if i < len(agent_configs) - 1:
                time.sleep(delay_between_launches)
        log.info(f"Launched {len(launched)}/{len(agent_configs)} agents")
        return launched

    def stop_agent(self, agent_id: str, timeout: int = 10) -> bool:
        process = self.processes.get(agent_id)
        if process is None:
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