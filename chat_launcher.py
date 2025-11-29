"""
py_backend/chat_launcher.py - Chat Interface Launcher

Starts the React-based chat interface for an agent.
"""

import subprocess
import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any

log = logging.getLogger("chat_launcher")

def start_chat_interface(agent_id: str, brain_path: str, config: Dict[str, Any]):
    """
    Launches the chat interface for an agent.
    
    Args:
        agent_id: Agent identifier
        brain_path: Path to brain capsule
        config: Agent configuration
    """
    
    log.info(f"Starting chat interface for {agent_id}")
    
    # Import agent system
    try:
        from ai_core.agent import NPCAgent
        from ai_core.brain_capsule import BrainCapsule
    except ImportError as e:
        log.error(f"Failed to import agent modules: {e}")
        raise
    
    # Load agent
    agent = NPCAgent(agent_id)
    
    if Path(brain_path).exists():
        log.info(f"Loading brain from {brain_path}")
        agent.load(brain_path)
    else:
        log.warning(f"Brain not found, starting with fresh state")
    
    # Start backend server in background
    backend_port = config.get('backend_port', 11400)
    
    backend_process = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn', 'py_backend.main:app', 
         '--host', '0.0.0.0', '--port', str(backend_port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    log.info(f"Backend started on port {backend_port}")
    
    # Wait for backend to be ready
    time.sleep(2)
    
    # Start React frontend
    frontend_dir = Path(__file__).parent.parent / 'dw_agent' / 'react-app'
    
    if frontend_dir.exists():
        log.info("Starting React frontend...")
        
        # Start development server or serve built files
        if (frontend_dir / 'dist').exists():
            # Serve built files
            subprocess.run([
                'npx', 'serve', '-s', 'dist', '-p', '8765'
            ], cwd=frontend_dir)
        else:
            # Development mode
            subprocess.run(['npm', 'run', 'dev'], cwd=frontend_dir)
    else:
        log.error("Frontend not found, starting backend only")
        print(f"\nChat backend running at http://localhost:{backend_port}")
        print("Open your browser to interact with the agent.")
        
        try:
            backend_process.wait()
        except KeyboardInterrupt:
            backend_process.terminate()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 3:
        print("Usage: python chat_launcher.py <agent_id> <brain_path>")
        sys.exit(1)
    
    start_chat_interface(sys.argv[1], sys.argv[2], {})