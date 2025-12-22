# minecraft_launcher.py - FIXED VERSION with agent_spawner.py integration
"""
Minecraft Client Launcher - PRODUCTION VERSION
Spawns Minecraft clients with DW Client Mod for agents
Integrated with agent_spawner.py
"""

import subprocess
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("minecraft_launcher")


class MinecraftClientLauncher:
    """
    Launches Minecraft clients with DW Client Mod
    FIXED: Works with existing agent_spawner.py structure
    """
    
    def __init__(self, 
                 minecraft_dir: Path,
                 mod_jar: str = "dwclient-1.0.0.jar",
                 java_path: str = "java"):
        
        self.minecraft_dir = Path(minecraft_dir)
        self.mod_jar = mod_jar
        self.java_path = java_path
        
        # Verify setup
        if not self.minecraft_dir.exists():
            self.minecraft_dir.mkdir(parents=True, exist_ok=True)
        
        log.info(f"Minecraft launcher initialized: {self.minecraft_dir}")
    
    def launch_client(self,
                     agent_id: str,
                     backend_port: int,
                     server_addr: str,
                     memory_mb: int,
                     is_god: bool = False,
                     god_type: Optional[str] = None) -> subprocess.Popen:
        """
        Launch Minecraft client with DW mod
        FIXED: Returns Popen object compatible with agent_spawner.py
        """
        # Create instance directory for this agent
        instance_dir = self.minecraft_dir / f"instances/{agent_id}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        # Prepare mods directory
        mods_dir = instance_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        
        # Copy mod if not already there
        mod_source = self.minecraft_dir / "mods" / self.mod_jar
        mod_dest = mods_dir / self.mod_jar
        if mod_source.exists() and not mod_dest.exists():
            import shutil
            shutil.copy(mod_source, mod_dest)
        
        # Build Java command
        jvm_args = [
            self.java_path,
            f"-Xmx{memory_mb}M",
            f"-Xms{memory_mb}M",
            
            # System properties for mod configuration
            f"-Ddw.agent.id={agent_id}",
            f"-Ddw.backend.url=ws://127.0.0.1",
            f"-Ddw.backend.port={backend_port}",
            f"-Ddw.vision.width=640",
            f"-Ddw.vision.height=480",
            f"-Ddw.vision.quality=0.75",
        ]
        
        # God agent configuration
        if is_god and god_type:
            jvm_args.append(f"-Ddw.god.type={god_type}")
        
        # Server auto-connect
        if server_addr:
            jvm_args.append(f"-Ddw.server.addr={server_addr}")
        
        # Minecraft/Forge launch arguments
        jvm_args.extend([
            "-cp", self._get_forge_classpath(instance_dir),
            "cpw.mods.bootstraplauncher.BootstrapLauncher",
            "--username", agent_id,
            "--version", "1.20.1-forge",
            "--gameDir", str(instance_dir),
            "--fml.forgeVersion", "47.4.10",
            "--fml.mcVersion", "1.20.1",
        ])
        
        # Auto-connect to server if specified
        if server_addr and ':' in server_addr:
            host, port = server_addr.split(':')
            jvm_args.extend([
                "--server", host,
                "--port", port
            ])
        
        log.info(f"Launching Minecraft client for {agent_id}")
        log.info(f"  Type: {'GOD (' + god_type + ')' if is_god else 'NORMAL'}")
        log.info(f"  Backend: ws://127.0.0.1:{backend_port}")
        log.info(f"  Server: {server_addr}")
        log.info(f"  Memory: {memory_mb}MB")
        
        # Launch process (compatible with agent_spawner.py)
        process = subprocess.Popen(
            jvm_args,
            cwd=str(instance_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        log.info(f"✅ Client launched (PID: {process.pid})")
        
        return process
    
    def _get_forge_classpath(self, instance_dir: Path) -> str:
        """Build Forge classpath"""
        # This is simplified - in production, use Forge installer's output
        forge_dir = self.minecraft_dir / "libraries"
        
        if not forge_dir.exists():
            # Fallback to basic launcher
            return str(self.minecraft_dir / "forge-client.jar")
        
        # Build classpath from Forge libraries
        classpath_parts = []
        
        # Add all Forge libraries
        for jar_file in forge_dir.rglob("*.jar"):
            classpath_parts.append(str(jar_file))
        
        # Add mod
        mod_path = instance_dir / "mods" / self.mod_jar
        if mod_path.exists():
            classpath_parts.append(str(mod_path))
        
        return os.pathsep.join(classpath_parts)
    
    def install_forge(self):
        """
        Install Forge if not already installed
        """
        forge_installer = self.minecraft_dir / "forge-1.20.1-47.2.0-installer.jar"
        
        if not forge_installer.exists():
            log.error(f"Forge installer not found: {forge_installer}")
            log.info("Download from: https://files.minecraftforge.net/")
            return False
        
        log.info("Installing Forge...")
        
        result = subprocess.run(
            [self.java_path, "-jar", str(forge_installer), "--installClient"],
            cwd=str(self.minecraft_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            log.info("✅ Forge installed successfully")
            return True
        else:
            log.error(f"❌ Forge installation failed: {result.stderr}")
            return False
    
    def install_mod(self, mod_jar_path: Path):
        """
        Install DW Client Mod
        """
        mods_dir = self.minecraft_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        
        if not mod_jar_path.exists():
            log.error(f"Mod JAR not found: {mod_jar_path}")
            return False
        
        # Copy mod to mods directory
        import shutil
        dest = mods_dir / mod_jar_path.name
        shutil.copy(mod_jar_path, dest)
        
        log.info(f"✅ Mod installed: {dest}")
        return True


# ============================================================================
# INTEGRATION WITH EXISTING agent_spawner.py
# ============================================================================

def patch_agent_spawner(spawner_instance):
    """
    Patch existing AgentSpawner to use Minecraft launcher
    CRITICAL: This modifies the spawner's client_manager
    """
    from ai_core.agent_spawner import AgentClientManager, MinecraftClientProcess
    
    # Create launcher
    launcher = MinecraftClientLauncher(
        minecraft_dir=Path("minecraft_clients"),
        java_path="java"
    )
    
    # Store original spawn_client method
    original_spawn_client = spawner_instance.client_manager.spawn_client
    
    # Create new spawn_client that uses our launcher
    def spawn_client_with_mod(agent_id: str, server_addr: str = "127.0.0.1:25565",
                              memory_mb: int = 2048) -> Optional[MinecraftClientProcess]:
        """
        Override spawn_client to use DW mod launcher
        """
        # Check if in Minecraft mode
        if not spawner_instance.client_manager.minecraft_mode:
            return None
        
        # Allocate port
        backend_port = spawner_instance.client_manager.allocate_port(agent_id)
        
        # Determine if god agent
        is_god = False
        god_type = None
        
        # Check if this is a god spawn
        # (We'll check the agent registry or pass this info)
        
        # Launch with mod
        process = launcher.launch_client(
            agent_id=agent_id,
            backend_port=backend_port,
            server_addr=server_addr,
            memory_mb=memory_mb,
            is_god=is_god,
            god_type=god_type
        )
        
        # Create MinecraftClientProcess object
        client_process = MinecraftClientProcess(
            agent_id=agent_id,
            process=process,
            backend_port=backend_port,
            server_addr=server_addr
        )
        
        # Register in client_manager
        spawner_instance.client_manager.clients[agent_id] = client_process
        
        return client_process
    
    # Replace the method
    spawner_instance.client_manager.spawn_client = spawn_client_with_mod
    spawner_instance.minecraft_launcher = launcher
    
    log.info("✅ AgentSpawner patched with Minecraft mod launcher")
    
    return spawner_instance


# Example usage with existing code
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # This integrates with your existing agent_spawner.py
    from ai_core.agent_spawner import AgentSpawner
    
    spawner = AgentSpawner(client_jar_path="DWClientBot.jar")
    
    # Patch it to use our mod
    spawner = patch_agent_spawner(spawner)
    
    # Now spawn works with the mod!
    agent = spawner.spawn_npc(
        agent_id="AI_Test_001",
        server_addr="127.0.0.1:25565"
    )


import subprocess
import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any

log = logging.getLogger("minecraft_launcher")


class MinecraftClientLauncher:
    """
    Launches Minecraft clients with DW Client Mod
    Handles both normal agents and god agents
    """
    
    def __init__(self, 
                 minecraft_dir: Path,
                 forge_jar: str = "forge-1.20.1-47.2.0-installer.jar",
                 java_path: str = "java"):
        
        self.minecraft_dir = Path(minecraft_dir)
        self.forge_jar = forge_jar
        self.java_path = java_path
        
        # Verify setup
        if not self.minecraft_dir.exists():
            self.minecraft_dir.mkdir(parents=True, exist_ok=True)
        
        log.info(f"Minecraft launcher initialized: {self.minecraft_dir}")
    
    def launch_normal_agent(self,
                           agent_id: str,
                           backend_port: int = 11400,
                           server_addr: str = "127.0.0.1:25565",
                           memory_mb: int = 2048) -> subprocess.Popen:
        """
        Launch Minecraft client for normal agent
        """
        return self._launch_client(
            agent_id=agent_id,
            backend_port=backend_port,
            server_addr=server_addr,
            memory_mb=memory_mb,
            is_god=False
        )
    
    def launch_god_agent(self,
                        agent_id: str,
                        god_type: str,
                        backend_port: int = 11400,
                        server_addr: str = "127.0.0.1:25565",
                        memory_mb: int = 4096) -> subprocess.Popen:
        """
        Launch Minecraft client for god agent
        """
        return self._launch_client(
            agent_id=agent_id,
            backend_port=backend_port,
            server_addr=server_addr,
            memory_mb=memory_mb,
            is_god=True,
            god_type=god_type
        )
    
    def _launch_client(self,
                      agent_id: str,
                      backend_port: int,
                      server_addr: str,
                      memory_mb: int,
                      is_god: bool = False,
                      god_type: Optional[str] = None) -> subprocess.Popen:
        """
        Internal method to launch Minecraft with proper configuration
        """
        # Create instance directory for this agent
        instance_dir = self.minecraft_dir / f"instances/{agent_id}"
        instance_dir.mkdir(parents=True, exist_ok=True)
        
        # Java arguments
        jvm_args = [
            self.java_path,
            f"-Xmx{memory_mb}M",
            f"-Xms{memory_mb}M",
            
            # System properties for mod configuration
            f"-Ddw.agent.id={agent_id}",
            f"-Ddw.backend.url=ws://127.0.0.1",
            f"-Ddw.backend.port={backend_port}",
            f"-Ddw.vision.width=640",
            f"-Ddw.vision.height=480",
            f"-Ddw.vision.quality=0.75",
        ]
        
        # God agent configuration
        if is_god and god_type:
            jvm_args.append(f"-Ddw.god.type={god_type}")
        
        # Minecraft/Forge arguments
        jvm_args.extend([
            "-jar",
            str(self.minecraft_dir / "forge-client.jar"),
            "--username", agent_id,
            "--version", "1.20.1-forge",
            "--gameDir", str(instance_dir),
            "--assetsDir", str(self.minecraft_dir / "assets"),
            "--assetIndex", "1.20",
        ])
        
        # Auto-connect to server
        if server_addr:
            host, port = server_addr.split(":")
            jvm_args.extend([
                "--server", host,
                "--port", port
            ])
        
        log.info(f"Launching Minecraft client for {agent_id}")
        log.info(f"  Type: {'GOD (' + god_type + ')' if is_god else 'NORMAL'}")
        log.info(f"  Backend: ws://127.0.0.1:{backend_port}")
        log.info(f"  Server: {server_addr}")
        log.info(f"  Memory: {memory_mb}MB")
        
        # Launch process
        process = subprocess.Popen(
            jvm_args,
            cwd=str(self.minecraft_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        log.info(f"✅ Client launched (PID: {process.pid})")
        
        return process
    
    def install_forge(self):
        """
        Install Forge if not already installed
        """
        installer_path = self.minecraft_dir / self.forge_jar
        
        if not installer_path.exists():
            log.error(f"Forge installer not found: {installer_path}")
            return False
        
        log.info("Installing Forge...")
        
        result = subprocess.run(
            [self.java_path, "-jar", str(installer_path), "--installClient"],
            cwd=str(self.minecraft_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            log.info("✅ Forge installed successfully")
            return True
        else:
            log.error(f"❌ Forge installation failed: {result.stderr}")
            return False
    
    def install_mod(self, mod_jar_path: Path):
        """
        Install DW Client Mod
        """
        mods_dir = self.minecraft_dir / "mods"
        mods_dir.mkdir(exist_ok=True)
        
        if not mod_jar_path.exists():
            log.error(f"Mod JAR not found: {mod_jar_path}")
            return False
        
        # Copy mod to mods directory
        import shutil
        dest = mods_dir / mod_jar_path.name
        shutil.copy(mod_jar_path, dest)
        
        log.info(f"✅ Mod installed: {dest}")
        return True


# Integration with existing agent spawner
def integrate_with_agent_spawner(spawner):
    """
    Add Minecraft launcher to AgentSpawner
    """
    launcher = MinecraftClientLauncher(
        minecraft_dir=Path("minecraft_clients"),
        java_path="java"
    )
    
    # Override spawn methods
    original_spawn_npc = spawner.spawn_npc
    original_spawn_god = spawner.spawn_god
    
    def spawn_npc_with_client(agent_id: str, server_addr: str = "127.0.0.1:25565", **kwargs):
        # Spawn agent backend
        agent = original_spawn_npc(agent_id, server_addr, **kwargs)
        
        # Launch Minecraft client
        backend_port = getattr(agent, 'backend_port', 11400)
        process = launcher.launch_normal_agent(
            agent_id=agent_id,
            backend_port=backend_port,
            server_addr=server_addr
        )
        
        agent.minecraft_process = process
        return agent
    
    def spawn_god_with_client(god_type: str, server_addr: str = "127.0.0.1:25565", **kwargs):
        # Spawn agent backend
        agent = original_spawn_god(god_type, server_addr, **kwargs)
        
        # Launch Minecraft client
        backend_port = getattr(agent, 'backend_port', 11400)
        process = launcher.launch_god_agent(
            agent_id=agent.agent_id,
            god_type=god_type,
            backend_port=backend_port,
            server_addr=server_addr
        )
        
        agent.minecraft_process = process
        return agent
    
    spawner.spawn_npc = spawn_npc_with_client
    spawner.spawn_god = spawn_god_with_client
    spawner.minecraft_launcher = launcher
    
    log.info("✅ Minecraft launcher integrated with spawner")


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    launcher = MinecraftClientLauncher(
        minecraft_dir=Path("minecraft_clients")
    )
    
    # Install Forge and mod (one-time setup)
    # launcher.install_forge()
    # launcher.install_mod(Path("mods/dwclient-1.0.0.jar"))
    
    # Launch a normal agent
    process = launcher.launch_normal_agent(
        agent_id="AI_Test_001",
        backend_port=11400,
        server_addr="127.0.0.1:25565"
    )
    
    # Launch a god agent
    god_process = launcher.launch_god_agent(
        agent_id="GOD_CREAKING_001",
        god_type="creaking",
        backend_port=11401,
        server_addr="127.0.0.1:25565"
    )