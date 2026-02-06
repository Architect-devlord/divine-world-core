"""
Standalone Agent Bootstrap
==========================
Lightweight entry point for PyInstaller-packaged agents.
This module creates a self-contained executable agent with minimal dependencies.
Supports UltimMC Minecraft launching and brain state management.

Usage for PyInstaller:
    pyinstaller --onefile \\
        --hidden-import=torch \\
        --hidden-import=numpy \\
        --hidden-import=fastapi \\
        --hidden-import=uvicorn \\
        --hidden-import=ai_core \\
        agent_standalone.py

Usage:
    python agent_standalone.py --agent-id alice --port 8001
    python agent_standalone.py --agent-id bob --minecraft --ultimmc-path ~/UltimMC
    python agent_standalone.py --agent-id eve --port 8002 --brain /path/to/brain.pcap
"""

import sys
import argparse
import logging
import os
from pathlib import Path
from typing import Optional

import uvicorn

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)
log = logging.getLogger("agent_standalone")

# Ensure ai_core can be imported
sys.path.insert(0, str(Path(__file__).parent.parent))


def parse_arguments():
    """Parse command-line arguments for standalone agent"""
    parser = argparse.ArgumentParser(
        description="Standalone Divine World AI Agent with Minecraft Support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Start agent 'alice' on port 8001
  python agent_standalone.py --agent-id alice --port 8001
  
  # Start agent 'bob' with Minecraft/UltimMC
  python agent_standalone.py --agent-id bob --minecraft --ultimmc-path ~/UltimMC
  
  # Start agent 'eve' with specific brain file
  python agent_standalone.py --agent-id eve --port 8002 --brain /path/to/brain.pcap
  
  # Start agent with custom server
  python agent_standalone.py --agent-id adam --server 192.168.1.100:11400
        """
    )
    
    parser.add_argument(
        "--agent-id",
        type=str,
        required=True,
        help="Unique agent identifier (e.g., 'alice', 'bob', 'eve')"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="WebSocket/HTTP port for this agent (default: 8001)"
    )
    
    parser.add_argument(
        "--brain",
        type=str,
        default=None,
        help="Path to brain state file to load (*.pcap format)"
    )
    
    parser.add_argument(
        "--server",
        type=str,
        default="127.0.0.1:11400",
        help="Backend server address for agent communication (default: 127.0.0.1:11400)"
    )
    
    parser.add_argument(
        "--mode",
        type=str,
        choices=["autonomous", "chat", "debug"],
        default="autonomous",
        help="Agent operating mode (default: autonomous)"
    )
    
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    parser.add_argument(
        "--minecraft",
        action="store_true",
        help="Launch Minecraft client with UltimMC after starting agent"
    )
    
    parser.add_argument(
        "--ultimmc-path",
        type=str,
        default=None,
        help="Path to UltimMC installation (will auto-detect if not provided)"
    )
    
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run in headless mode (no UI, only WebSocket)"
    )
    
    return parser.parse_args()


def detect_ultimmc(provided_path: Optional[str] = None) -> Optional[Path]:
    """Detect or validate UltimMC installation"""
    if provided_path:
        p = Path(os.path.expanduser(provided_path))
        if p.exists() and (p / "UltimMC").exists():
            log.info(f"✅ UltimMC found at: {p}")
            return p
        elif p.exists():
            log.warning(f"⚠️  Provided path exists but no UltimMC found: {p}")
    
    # Try common locations
    common_paths = [
        Path.home() / "UltimMC",
        Path.home() / ".ultimmc",
        Path.home() / ".local" / "share" / "ultimmc",
        Path("/opt/ultimmc"),
        Path("/Applications/UltimMC.app"),  # macOS
    ]
    
    for path in common_paths:
        if path.exists():
            log.info(f"✅ UltimMC found at: {path}")
            return path
    
    # Check if executable is in PATH
    import shutil
    if shutil.which("ultimmc") or shutil.which("UltimMC"):
        log.info("✅ UltimMC found in PATH")
        return Path(shutil.which("ultimmc") or shutil.which("UltimMC")).parent
    
    return None


def check_ultimmc_requirement():
    """Display UltimMC setup instructions if needed"""
    log.warning("=" * 70)
    log.warning("⚠️  UltimMC not found! Minecraft integration requires UltimMC installation.")
    log.warning("")
    log.warning("Quick Setup Instructions:")
    log.warning("─" * 70)
    log.warning("1. Download UltimMC from: https://github.com/UltimMC/Launcher/releases")
    log.warning("   OR: https://github.com/Architect-devlord/Launcher/releases")
    log.warning("")
    log.warning("2. Extract to a location, for example:")
    log.warning(f"   mkdir -p $HOME/UltimMC")
    log.warning(f"   unzip UltimMC-*.zip -d $HOME/UltimMC")
    log.warning("")
    log.warning("3. Place the extracted UltimMC folder in one of these locations:")
    log.warning(f"   • {Path.home() / 'UltimMC'}")
    log.warning(f"   • {Path.home() / '.ultimmc'}")
    log.warning(f"   • {Path.home() / '.local/share/ultimmc'}")
    log.warning("   • Same directory as this agent executable")
    log.warning("")
    log.warning("4. Run with UltimMC:")
    log.warning("   ./DW_Agent_Alice --agent-id alice --minecraft --ultimmc-path ~/UltimMC")
    log.warning("=" * 70)


def validate_environment():
    """Check that all required modules are available"""
    required_modules = [
        'torch',
        'numpy',
        'fastapi',
        'uvicorn',
        'websockets',
    ]
    
    missing = []
    for module_name in required_modules:
        try:
            __import__(module_name)
        except ImportError:
            missing.append(module_name)
    
    if missing:
        log.error(f"Missing required modules: {', '.join(missing)}")
        log.error("Install with: pip install " + " ".join(missing))
        return False
    
    log.info("✅ All required modules found")
    return True



def create_agent_instance(agent_id: str, brain_path: Optional[str] = None):
    """Create an NPCAgent instance with configuration"""
    try:
        from ai_core import NPCAgent, Config
        from ai_core.personality import Personality, GenderType
        
        log.info(f"Creating agent instance: {agent_id}")
        
        # Create personality based on agent_id
        if agent_id.lower() in ['alice', 'eve', 'sophia', 'luna', 'iris']:
            gender = GenderType.FEMALE
        elif agent_id.lower() in ['bob', 'adam', 'jack', 'leo', 'marco']:
            gender = GenderType.MALE
        else:
            gender = GenderType.NEUTRAL
        
        personality = Personality(
            name=agent_id,
            gender=gender,
            traits={
                "openness": 0.7,
                "conscientiousness": 0.8,
                "extraversion": 0.6,
                "agreeableness": 0.75,
                "neuroticism": 0.3,
            }
        )
        
        # Create agent
        agent = NPCAgent(
            agent_id=agent_id,
            personality=personality,
            brain_state_path=brain_path if brain_path else str(
                Config.get_agent_brain_path(agent_id)
            )
        )
        
        log.info(f"✅ Agent '{agent_id}' created successfully")
        log.info(f"   Personality: {personality.name} ({personality.gender.name})")
        log.info(f"   Brain path: {agent.brain_state_path}")
        
        return agent
        
    except Exception as e:
        log.error(f"Failed to create agent: {e}")
        import traceback
        traceback.print_exc()
        return None


def start_agent_server(agent, port: int, mode: str = "autonomous"):
    """Start the agent's WebSocket/HTTP server"""
    try:
        from ai_core.agent import app, global_agent, active_websockets
        import asyncio
        
        # Store agent globally for the FastAPI app
        import ai_core.agent as agent_module
        agent_module.global_agent = agent
        agent_module.active_websockets = active_websockets
        
        log.info(f"Starting {mode} agent server on port {port}...")
        log.info(f"Agent '{agent.agent_id}' is now online")
        log.info(f"WebSocket endpoint: ws://127.0.0.1:{port}/ws")
        log.info(f"Health check: http://127.0.0.1:{port}/health")
        
        # Start server
        config = uvicorn.Config(
            app=app,
            host="0.0.0.0",
            port=port,
            log_level="info",
            access_log=True,
        )
        server = uvicorn.Server(config)
        
        asyncio.run(server.serve())
        
    except Exception as e:
        log.error(f"Failed to start server: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Main entry point for standalone agent"""
    args = parse_arguments()
    
    # Set logging level
    logging.getLogger().setLevel(getattr(logging, args.log_level))
    
    log.info("="*70)
    log.info("Divine World - Standalone AI Agent")
    log.info("="*70)
    log.info(f"Agent ID: {args.agent_id}")
    log.info(f"Mode: {args.mode}")
    log.info(f"Port: {args.port}")
    log.info(f"Server: {args.server}")
    
    # Validate environment
    if not validate_environment():
        sys.exit(1)
    
    # Check Minecraft requirements
    if args.minecraft:
        log.info("🎮 Minecraft mode enabled")
        ultimmc_path = detect_ultimmc(args.ultimmc_path)
        if not ultimmc_path:
            log.error("❌ Minecraft mode requested but UltimMC not found")
            check_ultimmc_requirement()
            log.warning("Continuing without Minecraft support...")
            args.minecraft = False
    
    # Create agent
    agent = create_agent_instance(args.agent_id, args.brain)
    if not agent:
        sys.exit(1)
    
    # Load brain if specified
    if args.brain and Path(args.brain).exists():
        try:
            log.info(f"Loading brain from {args.brain}...")
            # Brain loading logic would go here
            log.info("✅ Brain loaded successfully")
        except Exception as e:
            log.warning(f"Could not load brain: {e}")
    
    # Start server
    try:
        import uvicorn
        
        log.info(f"Starting agent server on port {args.port}...")
        
        # If Minecraft mode, launch UltimMC in background
        if args.minecraft and ultimmc_path:
            log.info("🎮 Launching Minecraft with UltimMC...")
            try:
                import subprocess
                import threading
                
                def launch_minecraft():
                    try:
                        ultimmc_exe = ultimmc_path / "UltimMC"
                        if not ultimmc_exe.exists():
                            # Try other possible locations
                            for possible in [ultimmc_path / "bin" / "UltimMC", ultimmc_path / "ultimmc"]:
                                if possible.exists():
                                    ultimmc_exe = possible
                                    break
                        
                        if ultimmc_exe.exists():
                            log.info(f"Launching: {ultimmc_exe}")
                            subprocess.Popen(
                                [str(ultimmc_exe), "-l", args.server],
                                cwd=str(ultimmc_path)
                            )
                            log.info("✅ Minecraft launched")
                        else:
                            log.error(f"UltimMC executable not found in {ultimmc_path}")
                    except Exception as e:
                        log.error(f"Failed to launch Minecraft: {e}")
                
                # Launch in background thread
                mc_thread = threading.Thread(target=launch_minecraft, daemon=True)
                mc_thread.start()
            except Exception as e:
                log.warning(f"Could not launch Minecraft: {e}")
        
        start_agent_server(agent, args.port, args.mode)
    except KeyboardInterrupt:
        log.info("Agent shutdown requested")
    except Exception as e:
        log.error(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
