import subprocess
import json
import os
import logging
import shutil
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
import uuid
import platform
from py_backend.utils.mc_uuid import get_minecraft_uuid

log = logging.getLogger("minecraft_launcher")
log.setLevel(logging.INFO)


class UltimMCLauncher:
    """
    UltimMC automation layer for Minecraft setup and launching.
    
    MULTI-INSTANCE SUPPORT:
    Creates separate UltimMC folder copies for each agent to bypass single-instance lock.
    Uses UltimMC's built-in --launch, --profile, --server flags.
    """
    
    # Configuration
    MINECRAFT_VERSION = "1.20.1"
    FORGE_VERSION = "47.4.10"
    
    def __init__(self, ultimmc_path: Optional[str] = None,
                 client_jar_path: Optional[str] = None,
                 mod_jar_path: Optional[str] = None,
                 custom_ultimmc_dir: Optional[Path] = None):
        """
        Initialize UltimMC launcher.
        
        Args:
            ultimmc_path: Path to UltimMC executable (source to copy from)
            client_jar_path: Path to dwclient-1.0.0.jar
            mod_jar_path: Path to divineworld-1.0.0-all.jar
            custom_ultimmc_dir: Custom UltimMC directory (if already copied)
        """
        self.source_ultimmc_path = self._find_ultimmc(ultimmc_path)
        self.client_jar = self._find_file(client_jar_path, "dwclient-1.0.0.jar")
        self.mod_jar = self._find_file(mod_jar_path, "divineworld-1.0.0-all.jar")
        
        # For custom instances, we'll set these per-agent
        self.ultimmc_dir = custom_ultimmc_dir
        self.ultimmc_executable = None
        
        if self.ultimmc_dir:
            self._find_executable_in_dir()
        
        if self.source_ultimmc_path:
            log.info(f"✅ Source UltimMC found at: {self.source_ultimmc_path}")
        else:
            log.warning("⚠️ UltimMC not found - install from https://github.com/UltimMC/Launcher or https://github.com/Architect-devlord/Launcher")
        
        if self.client_jar:
            log.info(f"✅ dwclient-1.0.0.jar found at: {self.client_jar}")
        else:
            log.warning("⚠️ dwclient-1.0.0.jar not found")
        
        if self.mod_jar:
            log.info(f"✅ divineworld-1.0.0-all.jar found at: {self.mod_jar}")
        else:
            log.warning("⚠️ divineworld-1.0.0-all.jar not found")
    
    def _find_executable_in_dir(self):
        """Find UltimMC executable in the custom directory"""
        if not self.ultimmc_dir:
            return
        
        # Look for executable
        candidates = [
            # Prefer the bundled binary under `bin/` when duplicates exist
            self.ultimmc_dir / "bin" / "UltimMC",
            self.ultimmc_dir / "UltimMC",
            self.ultimmc_dir / "ultimmc",
        ]
        
        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                self.ultimmc_executable = candidate
                log.info(f"Found UltimMC executable: {candidate}")
                return
        
        log.warning(f"No executable found in {self.ultimmc_dir}")
    
    def _find_ultimmc(self, explicit_path: Optional[str]) -> Optional[Path]:
        """Find UltimMC executable or installation directory"""
        # If explicit path provided, validate it
        if explicit_path:
            p = Path(os.path.expanduser(explicit_path))
            if p.exists():
                return p
            else:
                log.warning(f"Provided UltimMC path does not exist: {p}")

        # Try common installation paths
        common_paths = [
            Path.home() / ".local" / "bin" / "ultimmc",
            Path.home() / ".local" / "bin" / "UltimMC",
            Path("/opt/ultimmc"),
            Path("/opt/UltimMC"),
            Path("/usr/local/bin/ultimmc"),
            Path("/usr/local/bin/UltimMC"),
        ]
        
        for path in common_paths:
            if path.exists():
                log.info(f"Found UltimMC at: {path}")
                return path
        
        # Also try checking in workspace for UltimMC folder
        cwd = Path.cwd()
        if cwd.name == "py_backend":
            workspace_root = cwd.parent
        else:
            workspace_root = cwd
        
        ultimmc_folder = workspace_root / "UltimMC"
        if ultimmc_folder.exists() and (ultimmc_folder / "bin" / "UltimMC").exists():
            log.info(f"Found UltimMC folder at: {ultimmc_folder}")
            return ultimmc_folder / "bin" / "UltimMC"

        # No UltimMC found - don't prompt user, just log warning
        log.info("UltimMC executable not found in common paths; skipping automated UltimMC actions.")
        log.info("To use UltimMC, set DW_ULTIMMC_PATH environment variable or install to ~/.local/bin/")
        return None
    
    def _find_file(self, explicit_path: Optional[str], filename: str) -> Optional[Path]:
        """Find a jar file"""
        if explicit_path:
            p = Path(explicit_path)
            if p.exists():
                return p
        
        search_dirs = [
            Path.cwd(),
            Path.cwd() / "py_backend",
            Path.cwd() / "divine-world",
            Path("/opt/divine-world"),
        ]
        
        for search_dir in search_dirs:
            if search_dir.exists():
                found = list(search_dir.glob(f"**/{filename}"))
                if found:
                    return found[0]
        
        return None
    
    def copy_ultimmc_installation(self, dest_dir: Path) -> bool:
        """
        Copy the entire UltimMC installation to a new directory.
        
        Args:
            dest_dir: Destination directory for the copy
            
        Returns:
            True if successful
        """
        if not self.source_ultimmc_path:
            log.error("Source UltimMC not found - cannot copy")
            return False
        
        # Find the UltimMC installation root
        source_root = self.source_ultimmc_path.parent
        if source_root.name == "bin":
            source_root = source_root.parent
        
        log.info(f"Copying UltimMC from {source_root} to {dest_dir}")
        
        try:
            if dest_dir.exists():
                log.info(f"Destination already exists, skipping copy: {dest_dir}")
                self.ultimmc_dir = dest_dir
                self._find_executable_in_dir()
                return True
            
            shutil.copytree(source_root, dest_dir, symlinks=True)
            log.info(f"✅ Copied UltimMC installation to {dest_dir}")
            
            self.ultimmc_dir = dest_dir
            self._find_executable_in_dir()
            
            # Make executable if needed
            if self.ultimmc_executable:
                os.chmod(self.ultimmc_executable, 0o755)
            
            return True
        except Exception as e:
            log.error(f"❌ Failed to copy UltimMC: {e}")
            return False
    
    def create_account(self, username: str, make_active: bool = True, 
                      custom_uuid: Optional[str] = None) -> bool:
        """
        Create a local Minecraft account (offline mode) in UltimMC's accounts.json.
        
        Args:
            username: Account username
            make_active: Whether to set this account as the active account
            custom_uuid: Custom UUID to use (if None, generates offline UUID)
            
        Returns:
            True if successful
        """
        if not self.ultimmc_dir:
            log.error("UltimMC directory not set - cannot create account")
            return False
        
        log.info(f"Creating local account: {username}")
        
        accounts_file = self.ultimmc_dir / "bin" / "accounts.json"
        
        if accounts_file.exists():
            try:
                data = json.loads(accounts_file.read_text())
                if "accounts" not in data:
                    data = {"accounts": [], "formatVersion": 3}
            except json.JSONDecodeError:
                log.warning("Corrupted accounts.json, creating new one")
                data = {"accounts": [], "formatVersion": 3}
        else:
            data = {"accounts": [], "formatVersion": 3}
        
        if custom_uuid:
            account_uuid = custom_uuid
            log.info(f"Using custom UUID: {account_uuid}")
        else:
            account_uuid = self._generate_offline_uuid(username)
            log.info(f"Generated offline UUID: {account_uuid}")
        
        client_token = str(uuid.uuid4()).replace("-", "")
        current_time = int(time.time())
        
        new_account = {
            "type": "Local",
            "profile": {
                "id": account_uuid.replace("-", ""),
                "name": username,
                "skin": {
                    "id": "",
                    "url": "",
                    "variant": ""
                },
                "capes": []
            },
            "entitlement": {
                "canPlayMinecraft": True,
                "ownsMinecraft": True
            },
            "ygg": {
                "extra": {
                    "clientToken": client_token,
                    "userName": username
                },
                "iat": current_time
            }
        }
        
        if make_active:
            for account in data["accounts"]:
                account.pop("active", None)
            new_account["active"] = True
        
        existing_index = None
        for i, account in enumerate(data["accounts"]):
            if account.get("profile", {}).get("name") == username:
                existing_index = i
                break
        
        if existing_index is not None:
            log.info(f"Account {username} already exists, updating it")
            data["accounts"][existing_index] = new_account
        else:
            data["accounts"].append(new_account)
        
        try:
            accounts_file.write_text(json.dumps(data, indent=4))
            log.info(f"✅ Account created/updated: {username}")
            log.info(f"   UUID: {account_uuid}")
            log.info(f"   Active: {make_active}")
            return True
        except Exception as e:
            log.error(f"❌ Failed to write accounts.json: {e}")
            return False
    
    def create_instance(self, instance_name: str, forge_install: bool = True) -> bool:
        """Create a Minecraft instance with Forge."""
        if not self.ultimmc_dir:
            log.error("UltimMC directory not set - cannot create instance")
            return False
        
        instances_dir = self.ultimmc_dir / "instances"
        instances_dir.mkdir(parents=True, exist_ok=True)
        
        instance_dir = instances_dir / instance_name
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        log.info(f"Creating Minecraft instance: {instance_name}")
        
        instance_cfg = instance_dir / "instance.cfg"
        cfg_content = f"""InstanceType=OneSix
name={instance_name}
iconKey=default
notes=Divine World Agent Instance
lastLaunchTime=0
totalTimePlayed=0
OverrideCommands=false
OverrideConsole=false
OverrideGameTime=false
OverrideJavaArgs=true
OverrideJavaLocation=false
OverrideMCLaunchMethod=false
OverrideMemory=true
OverrideNativeWorkarounds=false
OverridePerformance=false
OverrideWindow=false
ShowConsole=false
MaxMemAlloc=2048
MinMemAlloc=512
WrapperCommand=
"""
        instance_cfg.write_text(cfg_content.strip())
        
        mmc_pack = instance_dir / "mmc-pack.json"
        pack_content = {
            "components": [
                {
                    "cachedName": "LWJGL 3",
                    "cachedVersion": "3.3.1",
                    "cachedVolatile": True,
                    "dependencyOnly": True,
                    "uid": "org.lwjgl3",
                    "version": "3.3.1"
                },
                {
                    "cachedName": "Minecraft",
                    "cachedRequires": [{"uid": "org.lwjgl3"}],
                    "cachedVersion": self.MINECRAFT_VERSION,
                    "important": True,
                    "uid": "net.minecraft",
                    "version": self.MINECRAFT_VERSION
                }
            ],
            "formatVersion": 1
        }
        
        if forge_install:
            pack_content["components"].append({
                "cachedName": "Forge",
                "cachedVersion": self.FORGE_VERSION,
                "uid": "net.minecraftforge",
                "version": self.FORGE_VERSION
            })
        
        mmc_pack.write_text(json.dumps(pack_content, indent=2))
        
        log.info(f"✅ Instance created: {instance_name}")
        return True
    
    def install_mods(self, instance_name: str) -> bool:
        """Copy DivineWorld and DWClientBot mods to instance."""
        if not self.ultimmc_dir:
            log.error("UltimMC directory not set")
            return False
        
        instance_dir = self.ultimmc_dir / "instances" / instance_name
        minecraft_dir = instance_dir / ".minecraft"
        minecraft_dir.mkdir(parents=True, exist_ok=True)
        
        mods_dir = minecraft_dir / "mods"
        mods_dir.mkdir(parents=True, exist_ok=True)
        
        success = True
        
        if self.mod_jar:
            try:
                shutil.copy(self.mod_jar, mods_dir / self.mod_jar.name)
                log.info(f"✅ Installed DivineWorld mod: {self.mod_jar.name}")
            except Exception as e:
                log.error(f"❌ Failed to install DivineWorld mod: {e}")
                success = False
        
        if self.client_jar:
            try:
                shutil.copy(self.client_jar, mods_dir / self.client_jar.name)
                log.info(f"✅ Installed DWClientBot mod: {self.client_jar.name}")
            except Exception as e:
                log.error(f"❌ Failed to install DWClientBot mod: {e}")
                success = False
        
        return success
    
    def launch_instance(self, instance_name: str, 
                       server_addr: Optional[str] = None,
                       profile_name: Optional[str] = None,
                       offline: bool = True,
                       offline_name: Optional[str] = None,
                       agent_id: Optional[str] = None,
                       backend_url: Optional[str] = None,
                       memory_mb: int = 2048,
                       extra_jvm_args: Optional[List[str]] = None,
                       headless: bool = False) -> Optional[subprocess.Popen]:
        """
        Launch a Minecraft instance via UltimMC using built-in flags.
        
        Args:
            instance_name: Instance to launch
            server_addr: Server address (e.g., "127.0.0.1:25565")
            profile_name: Account profile name to use
            offline: Launch in offline mode
            offline_name: Username for offline mode
            agent_id: Agent ID for system property
            backend_url: Backend URL for system property
            memory_mb: Memory allocation
            extra_jvm_args: Additional JVM arguments
            headless: Run with xvfb-run (headless)
            
        Returns:
            Process handle or None
        """
        if not self.ultimmc_executable:
            log.error("UltimMC executable not available - cannot launch")
            return None
        
        # Build UltimMC command using built-in flags
        cmd = []
        
        # Add xvfb-run for headless operation
        if headless:
            cmd.extend(["xvfb-run", "-a"])
        
        cmd.append(str(self.ultimmc_executable))
        
        # Use current directory as data dir (. = current)
        cmd.extend(["-d", "."])
        
        # Launch instance
        cmd.extend(["-l", instance_name])
        
        # Server address
        if server_addr:
            cmd.extend(["-s", server_addr])
        
        # Profile
        if profile_name:
            cmd.extend(["-a", profile_name])
        
        # Offline mode
        if offline:
            cmd.append("-o")
            if offline_name:
                cmd.extend(["-n", offline_name])
        
        # Set up environment for JVM args
        env = os.environ.copy()
        
        java_args = [
            f"-Xmx{memory_mb}M",
            f"-Xms{memory_mb}M",
        ]
        
        if agent_id:
            java_args.append(f"-Ddw.agentId={agent_id}")
        if backend_url:
            java_args.append(f"-Ddw.backend={backend_url}")
        if server_addr:
            java_args.append(f"-Ddw.server={server_addr}")
        
        if extra_jvm_args:
            java_args.extend(extra_jvm_args)
        
        env["INST_JAVA"] = " ".join(java_args)
        
        log.info(f"Launching UltimMC instance: {instance_name}")
        log.info(f"  Working directory: {self.ultimmc_dir}")
        log.info(f"  Server: {server_addr}")
        log.info(f"  Profile: {profile_name}")
        log.info(f"  Offline: {offline} (name: {offline_name})")
        log.info(f"  Agent ID: {agent_id}")
        log.info(f"  Backend: {backend_url}")
        log.info(f"  Memory: {memory_mb}MB")
        log.info(f"  Headless: {headless}")
        log.info(f"  Command: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                cwd=str(self.ultimmc_dir),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            log.info(f"✅ UltimMC launched with PID: {process.pid}")
            return process
        except Exception as e:
            log.error(f"❌ Failed to launch UltimMC: {e}")
            return None
    
    @staticmethod
    def _generate_offline_uuid(username: str) -> str:
        """Generate offline mode UUID for account (Minecraft standard)"""
        namespace = uuid.UUID("00000000-0000-0000-0000-000000000000")
        name = f"OfflinePlayer:{username}"
        return str(uuid.uuid3(namespace, name))


class MultiAgentLauncher:
    """
    Manager for launching multiple agents simultaneously.
    
    Creates separate UltimMC folder copies for each agent.
    """
    
    def __init__(self, base_dir: Optional[Path] = None):
        """
        Initialize multi-agent launcher.
        
        Args:
            base_dir: Base directory for agent UltimMC copies
        """
        if base_dir:
            self.base_dir = Path(base_dir)
        else:
            self.base_dir = Path.home() / ".divine-world" / "ultimmc_agents"
        
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.launchers: Dict[str, UltimMCLauncher] = {}
        self.processes: Dict[str, subprocess.Popen] = {}
        
        log.info(f"Multi-agent launcher initialized at: {self.base_dir}")
    
    def create_launcher_for_agent(self, agent_id: str, 
                                 source_launcher: Optional[UltimMCLauncher] = None) -> UltimMCLauncher:
        """
        Create a dedicated UltimMC copy for an agent.
        
        Args:
            agent_id: Agent identifier
            source_launcher: Source launcher to copy from (or creates new one)
            
        Returns:
            UltimMCLauncher instance for this agent
        """
        agent_ultimmc_dir = self.base_dir / agent_id
        
        # Create launcher with source paths
        if source_launcher:
            launcher = UltimMCLauncher(
                ultimmc_path=str(source_launcher.source_ultimmc_path) if source_launcher.source_ultimmc_path else None,
                client_jar_path=str(source_launcher.client_jar) if source_launcher.client_jar else None,
                mod_jar_path=str(source_launcher.mod_jar) if source_launcher.mod_jar else None
            )
        else:
            launcher = UltimMCLauncher()
        
        # Copy UltimMC installation
        if not launcher.copy_ultimmc_installation(agent_ultimmc_dir):
            log.error(f"Failed to create UltimMC copy for {agent_id}")
            return None
        
        self.launchers[agent_id] = launcher
        log.info(f"Created launcher for {agent_id} at: {agent_ultimmc_dir}")
        
        return launcher
    
    def setup_agent(self, agent_id: str, server_addr: str = "127.0.0.1:25565",
                   custom_uuid: Optional[str] = None,
                   agent_type: str = 'npc',
                   custom_name: Optional[str] = None,
                   source_launcher: Optional[UltimMCLauncher] = None) -> bool:
        """
        Setup an agent with its own UltimMC copy.
        
        Args:
            agent_id: Agent identifier
            server_addr: Server address
            custom_uuid: Custom UUID for the agent
            agent_type: 'npc' or 'god_<type>' - determines username format
            source_launcher: Source launcher to copy from
            
        Returns:
            True if setup successful
        """
        launcher = self.create_launcher_for_agent(agent_id, source_launcher)
        if not launcher:
            return False
        
        instance_name = f"agent_{agent_id}"
        
        # Generate username in clean or DW_ format (matches DWEventHandler.java Pattern 1)
        if custom_name and custom_name != "Unnamed":
            username = custom_name
        elif agent_type and agent_type.startswith('god_'):
            god_type = agent_type.replace('god_', '').upper()
            username = f"DWGOD_{god_type}_{agent_id}"
        else:
            username = f"DW_{agent_id}"
        
        # Use proper Minecraft offline UUID if not provided
        if not custom_uuid:
            custom_uuid = get_minecraft_uuid(username)

        # Create account with proper username format
        if not launcher.create_account(username, make_active=True, custom_uuid=custom_uuid):
            log.error(f"Failed to create account {username} for {agent_id}")
            return False
        
        # Create instance
        if not launcher.create_instance(instance_name, forge_install=True):
            return False
        
        # Install mods
        if not launcher.install_mods(instance_name):
            log.warning(f"Some mods failed to install for {agent_id}")
        
        log.info(f"✅ Agent {agent_id} configured with username: {username}")
        return True
    
    def launch_agent(self, agent_id: str, server_addr: str,
                    backend_url: str, memory_mb: int = 2048,
                    extra_jvm_args: Optional[List[str]] = None,
                    headless: bool = False,
                    agent_type: str = 'npc',
                    custom_name: Optional[str] = None) -> Optional[subprocess.Popen]:
        """
        Launch an agent.
        
        Args:
            agent_id: Agent identifier
            server_addr: Server address
            backend_url: Backend URL
            memory_mb: Memory allocation
            extra_jvm_args: Extra JVM arguments
            headless: Run headless with xvfb-run
            agent_type: 'npc' or 'god_<type>' - determines offline username
            
        Returns:
            Process handle or None
        """
        if agent_id not in self.launchers:
            log.error(f"Launcher not found for {agent_id}. Run setup_agent() first.")
            return None
        
        launcher = self.launchers[agent_id]
        instance_name = f"agent_{agent_id}"
        
        # Generate offline username (matches setup_agent)
        if custom_name and custom_name != "Unnamed":
            offline_username = custom_name
        elif agent_type and agent_type.startswith('god_'):
            god_type = agent_type.replace('god_', '').upper()
            offline_username = f"DWGOD_{god_type}_{agent_id}"
        else:
            offline_username = f"DW_{agent_id}"
        
        process = launcher.launch_instance(
            instance_name=instance_name,
            server_addr=server_addr,
            offline=True,
            offline_name=offline_username,  # Use properly formatted username
            agent_id=agent_id,
            backend_url=backend_url,
            memory_mb=memory_mb,
            extra_jvm_args=extra_jvm_args,
            headless=headless
        )
        
        if process:
            self.processes[agent_id] = process
        
        return process
    
    def launch_multiple_agents(self, agent_configs: List[Dict[str, Any]],
                              delay_between_launches: float = 2.0,
                              source_launcher: Optional[UltimMCLauncher] = None,
                              headless: bool = False) -> Dict[str, subprocess.Popen]:
        """
        Launch multiple agents with configurable delay.
        
        Args:
            agent_configs: List of agent configurations
            delay_between_launches: Seconds to wait between launches
            source_launcher: Source launcher for copying
            headless: Run all agents headless
            
        Returns:
            Dictionary of agent_id -> process
        """
        launched = {}
        
        for i, config in enumerate(agent_configs):
            agent_id = config["id"]
            log.info(f"Launching agent {i+1}/{len(agent_configs)}: {agent_id}")
            
            # Setup if not already done
            if agent_id not in self.launchers:
                success = self.setup_agent(
                    agent_id=agent_id,
                    server_addr=config.get("server", "127.0.0.1:25565"),
                    custom_uuid=config.get("uuid"),
                    agent_type=config.get("agent_type", "npc"),  # Pass agent_type
                    source_launcher=source_launcher
                )
                if not success:
                    log.error(f"Failed to setup {agent_id}")
                    continue
            
            # Launch
            process = self.launch_agent(
                agent_id=agent_id,
                server_addr=config.get("server", "127.0.0.1:25565"),
                backend_url=config.get("backend", "http://127.0.0.1:11400"),
                memory_mb=config.get("memory", 2048),
                extra_jvm_args=config.get("extra_jvm_args"),
                headless=config.get("headless", headless),
                agent_type=config.get("agent_type", "npc")  # Pass agent_type
            )
            
            if process:
                launched[agent_id] = process
                log.info(f"✅ Launched {agent_id}")
            else:
                log.error(f"❌ Failed to launch {agent_id}")
            
            # Wait before launching next agent
            if i < len(agent_configs) - 1:
                log.info(f"Waiting {delay_between_launches}s before next launch...")
                time.sleep(delay_between_launches)
        
        log.info(f"Launched {len(launched)}/{len(agent_configs)} agents successfully")
        return launched
    
    def stop_agent(self, agent_id: str, timeout: int = 10) -> bool:
        """Stop a running agent."""
        if agent_id not in self.processes:
            log.warning(f"No running process found for {agent_id}")
            return False
        
        process = self.processes[agent_id]
        try:
            process.terminate()
            process.wait(timeout=timeout)
            log.info(f"✅ Stopped {agent_id}")
            del self.processes[agent_id]
            return True
        except subprocess.TimeoutExpired:
            log.warning(f"Process {agent_id} didn't terminate, killing...")
            process.kill()
            process.wait()
            del self.processes[agent_id]
            return True
        except Exception as e:
            log.error(f"Failed to stop {agent_id}: {e}")
            return False
    
    def stop_all_agents(self) -> int:
        """Stop all running agents. Returns number stopped."""
        agent_ids = list(self.processes.keys())
        stopped = 0
        
        for agent_id in agent_ids:
            if self.stop_agent(agent_id):
                stopped += 1
        
        return stopped
    
    def get_running_agents(self) -> List[str]:
        """Get list of currently running agent IDs."""
        running = []
        for agent_id, process in list(self.processes.items()):
            if process.poll() is None:  # Still running
                running.append(agent_id)
            else:  # Process ended
                del self.processes[agent_id]
        
        return running


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("="*70)
    print("UltimMC Multi-Agent Launcher v2")
    print("Uses folder copies and built-in UltimMC flags")
    print("="*70)
    print()
    
    # Example: Launch multiple agents
    print("Example: Multiple Agents")
    print()
    print("# 1. Create a source launcher (finds UltimMC and mods)")
    print("source = UltimMCLauncher()")
    print()
    print("# 2. Create multi-agent launcher")
    print("multi = MultiAgentLauncher()")
    print()
    print("# 3. Define agent configs")
    print("""agent_configs = [
    {"id": "adam", "server": "127.0.0.1:25565", 
     "backend": "http://127.0.0.1:11400", "memory": 2048, "headless": True},
    {"id": "eve", "server": "127.0.0.1:25565", 
     "backend": "http://127.0.0.1:11400", "memory": 2048, "headless": True},
]""")
    print()
    print("# 4. Launch all agents")
    print("processes = multi.launch_multiple_agents(")
    print("    agent_configs, ")
    print("    delay_between_launches=3.0,")
    print("    source_launcher=source,")
    print("    headless=True  # Requires xvfb-run")
    print(")")
    print()
    print("# 5. Check running agents")
    print("print(multi.get_running_agents())")
    print()
    print("# 6. Stop all")
    print("multi.stop_all_agents()")
    print()
    print("✅ Ready to use! Uncomment examples above to test.")

    #
    # 
#1. Proper UltimMC Command Usage

#    Uses built-in flags: -l (launch), -s (server), -a (profile), -o (offline), -n (name)
#    Uses -d . to run from current directory instead of trying to specify external data dirs
#    Removed the incorrect -d usage that wasn't working

#2. Folder Copying Strategy

#    Each agent gets a complete copy of the UltimMC installation
#    Copies are stored in ~/.divine-world/ultimmc_agents/{agent_id}/
#    Each copy is independent with its own accounts, instances, and data

#3. Headless Support

#    Added headless parameter that wraps commands with xvfb-run -a
#    Useful for running multiple agents on servers without displays
#    Requires Xvfb to be installed: sudo pacman -S xorg-server-xvfb

#4. Simplified Launch Flow
#python

# Create source launcher to locate files
#source = UltimMCLauncher()

# Create multi-agent manager
#multi = MultiAgentLauncher()

# Launch agents (automatically copies UltimMC for each)
#agents = [
#    {"id": "adam", "server": "localhost:25565", 
#     "backend": "http://localhost:11400", "headless": True},
#    {"id": "eve", "server": "localhost:25565", 
#     "backend": "http://localhost:11400", "headless": True},
#]

#processes = multi.launch_multiple_agents(
#    agents, 
#    source_launcher=source,
#    headless=True
#)
