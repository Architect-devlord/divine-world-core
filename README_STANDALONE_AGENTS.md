# Standalone Agent Build Guide

This guide explains how to build PyInstaller executables for Divine World agents that can run on any computer.

## Overview

The Divine World codebase has been restructured to consolidate all agent dependencies into `ai_core`, making it possible to create self-contained executable agents using PyInstaller.

### What's been moved to ai_core:

- **config.py** - Configuration management (paths, ports, settings)
- **communication_protocol.py** - WebSocket communication protocol
- **validation.py** - Input validation utilities
- **agent_standalone.py** - Standalone agent bootstrap entry point

These modules, combined with the existing ai_core components, allow agents to run independently on any system.

## Prerequisites

```bash
# Install PyInstaller
pip install pyinstaller

# Verify PyInstaller installation
pyinstaller --version
```

## Building Agent Executables

### Option 1: Using the build script (Recommended)

```bash
cd /home/devlord/divine-world-core

# Build single agent
./build_agents.sh alice

# Build multiple agents
./build_agents.sh alice bob eve

# Build all known agents
./build_agents.sh all
```

This creates executables in `build/agents/dist/`

### Option 2: Manual PyInstaller build

```bash
cd /home/devlord/divine-world-core/py_backend

pyinstaller \
  --onefile \
  --name DW_Agent_Alice \
  --hidden-import=torch \
  --hidden-import=numpy \
  --hidden-import=fastapi \
  --hidden-import=uvicorn \
  --hidden-import=websockets \
  --hidden-import=aiohttp \
  --hidden-import=ai_core \
  --collect-all ai_core \
  ai_core/agent_standalone.py
```

### Option 3: Using the spec file

```bash
pyinstaller build_agent.spec --name DW_Agent_Alice
```

## Running Standalone Agents

### Basic usage

```bash
# Start agent 'alice' on default port 8001
./DW_Agent_Alice --agent-id alice

# Start on specific port
./DW_Agent_Alice --agent-id alice --port 8001

# With specific brain file
./DW_Agent_Alice --agent-id bob --port 8002 --brain /path/to/brain.pcap
```

### Command-line options

```
--agent-id ID           Unique agent identifier (required)
--port PORT            WebSocket/HTTP port (default: 8001)
--brain PATH           Brain state file to load (*.pcap format)
--server ADDRESS       Backend server address (default: 127.0.0.1:11400)
--mode MODE            Operating mode: autonomous, chat, debug (default: autonomous)
--log-level LEVEL      Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)
--headless             Run without UI, WebSocket only
```

### Examples

```bash
# Autonomous agent
./DW_Agent_Alice --agent-id alice --port 8001 --mode autonomous

# Chat mode with specific server
./DW_Agent_Bob --agent-id bob --port 8002 --server 192.168.1.100:11400 --mode chat

# Debug mode with verbose logging
./DW_Agent_Eve --agent-id eve --port 8003 --mode debug --log-level DEBUG

# Load existing brain
./DW_Agent_Adam --agent-id adam --port 8004 --brain ./brains/adam_trained.pcap
```

## WebSocket API

Once an agent is running, connect to it via WebSocket:

```javascript
// JavaScript example
const ws = new WebSocket('ws://127.0.0.1:8001/ws');

ws.onopen = () => {
  console.log('Connected to agent');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Received:', message);
};

// Send chat message
ws.send(JSON.stringify({
  type: 'chat',
  message: 'Hello agent!'
}));
```

## File Structure

```
divine-world-core/
├── py_backend/
│   ├── ai_core/
│   │   ├── agent.py              # Main agent runtime
│   │   ├── agent_standalone.py  # Standalone bootstrap entry point ✨
│   │   ├── config.py            # Configuration (moved) ✨
│   │   ├── communication_protocol.py  # WebSocket protocol (moved) ✨
│   │   ├── validation.py        # Validation utilities (moved) ✨
│   │   ├── personality.py
│   │   ├── emotion.py
│   │   ├── brain_core.py
│   │   ├── world_model.py
│   │   └── ... (other ai_core modules)
│   └── config.py                # Original (kept for backend compatibility)
├── build_agent.spec             # PyInstaller spec file ✨
├── build_agents.sh              # Build script ✨
└── build/
    └── agents/
        └── dist/
            ├── DW_Agent_Alice   # Standalone executable
            ├── DW_Agent_Bob     # Standalone executable
            └── ...
```

## Deployment

### Single Machine

```bash
# Build all agents
./build_agents.sh all

# Run agents on different ports
./build/agents/dist/DW_Agent_Alice --agent-id alice --port 8001 &
./build/agents/dist/DW_Agent_Bob --agent-id bob --port 8002 &
./build/agents/dist/DW_Agent_Eve --agent-id eve --port 8003 &
```

### Multiple Machines

1. Build agents on the development machine:
   ```bash
   ./build_agents.sh all
   ```

2. Copy executables to remote machines:
   ```bash
   scp build/agents/dist/DW_Agent_* user@remote-machine:/opt/agents/
   ```

3. Run on remote machines:
   ```bash
   ssh user@remote-machine "/opt/agents/DW_Agent_Alice --agent-id alice --port 8001"
   ```

## Troubleshooting

### "ModuleNotFoundError: No module named 'ai_core'"

Ensure you're running from the correct directory and all ai_core modules are in the Python path:
```bash
cd /home/devlord/divine-world-core/py_backend
python3 -c "import ai_core; print(ai_core.__file__)"
```

### PyInstaller "Failed to find datapaths"

Explicitly collect modules:
```bash
pyinstaller \
  --onefile \
  --collect-all ai_core \
  --collect-all torch \
  ai_core/agent_standalone.py
```

### Agent won't start on specific port

Check if port is already in use:
```bash
lsof -i :8001
# Kill existing process if needed
kill -9 <PID>
```

### Missing dependencies during runtime

Add hidden imports to the build command:
```bash
pyinstaller \
  --onefile \
  --hidden-import=<module_name> \
  ai_core/agent_standalone.py
```

## Development Workflow

For development, use the Python modules directly:

```bash
# Run agent in Python (development)
cd /home/devlord/divine-world-core/py_backend
python3 -m ai_core.agent_standalone --agent-id alice --port 8001

# This is equivalent to running the compiled executable
```

## Performance Notes

- Standalone executables are ~150-300 MB depending on included libraries
- First startup may take 2-5 seconds (PyInstaller unpacking)
- Memory usage: ~500-800 MB per agent instance
- Network latency: <50ms typical WebSocket round-trip

## Next Steps

1. Build your agents:
   ```bash
   ./build_agents.sh all
   ```

2. Test locally:
   ```bash
   ./build/agents/dist/DW_Agent_Alice --agent-id alice --port 8001
   ```

3. Connect via WebSocket and verify they're responding

4. Deploy to target machines as needed

## Support

For issues or questions about standalone agent building, check:
- `ai_core/agent_standalone.py` - Main entry point
- `build_agent.spec` - PyInstaller configuration
- `build_agents.sh` - Build script with helpful comments
