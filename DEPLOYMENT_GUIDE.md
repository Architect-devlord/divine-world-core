# Divine World Agent - Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [UltimMC Setup](#ultimmc-setup)
3. [Building Agents](#building-agents)
4. [Running Agents](#running-agents)
5. [Minecraft Integration](#minecraft-integration)
6. [Troubleshooting](#troubleshooting)
7. [Docker Deployment](#docker-deployment)

---

## Prerequisites

### System Requirements
- **OS**: Linux, macOS, or Windows (with WSL2)
- **Python**: 3.13 (Python 3.9+ minimum)
- **RAM**: 8GB minimum (16GB for multiple agents)
- **Disk Space**: 10GB+ (includes Minecraft, agents, models)

### Required Software
```bash
# Python development tools
sudo apt-get install python3-dev python3-pip python3-venv

# For building from source (optional)
sudo apt-get install git curl wget

# Java (for Minecraft)
sudo apt-get install default-jre
```

### Verify Installation
```bash
python3 --version
pip3 --version
java -version
```

---

## UltimMC Setup

### What is UltimMC?

UltimMC is a Minecraft launcher that Divine World agents use to automatically:
- Launch Minecraft clients
- Join servers
- Install mods (DivineWorld, DWClientBot)
- Manage game instances
- Connect to the Divine World backend

### Installation Steps

#### Step 1: Download UltimMC

Download the appropriate version for your OS:

**Linux:**
```bash
# Download latest release
wget https://github.com/UltimMC/Launcher/releases/download/latest/UltimMC-linux-x64.AppImage

# Make executable
chmod +x UltimMC-linux-x64.AppImage

# Run or place in preferred location
./UltimMC-linux-x64.AppImage
```

**macOS:**
```bash
# Download from GitHub Releases
# https://github.com/UltimMC/Launcher/releases
# Look for: UltimMC-macOS-x64.dmg

# After download, double-click to install
open ~/Downloads/UltimMC-macOS-x64.dmg
```

**Windows (or WSL2):**
```bash
# Download from GitHub Releases
# Look for: UltimMC-windows-x64.exe
# Then run the installer
```

#### Step 2: Place UltimMC in Standard Location

Agents will search for UltimMC in these locations (in order):
- `~/UltimMC/` (home directory)
- `~/.ultimmc/` (hidden folder)
- `~/.local/share/ultimmc/` (Linux standard)
- `/opt/ultimmc/` (system-wide Linux)
- `/Applications/UltimMC.app/` (macOS)

**Recommended Setup:**
```bash
# Linux
mkdir -p ~/UltimMC
cd ~/UltimMC

# Place UltimMC executable here
# Then create symlink for convenience (optional)
ln -s ~/UltimMC/UltimMC-linux-x64.AppImage ~/UltimMC/ultimmc
```

#### Step 3: Configure UltimMC

1. Launch UltimMC application
2. Create/select a game instance
3. Install Minecraft version (1.20.1 recommended)
4. Install Forge (for mod support)
5. Close UltimMC (agents will manage it automatically)

#### Step 4: Verify Installation

```bash
# Agents will auto-detect UltimMC location
# Or specify manually
./DW_Agent_alice --ultimmc-path ~/UltimMC/ultimmc --minecraft
```

---

## Building Agents

### Prerequisites for Building

```bash
# Install PyInstaller
pip3 install pyinstaller

# Or install all dependencies
cd /home/devlord/divine-world-core
pip3 install -r requirements.txt
```

### Build All Agents

```bash
cd /home/devlord/divine-world-core

# Make script executable
chmod +x build_agents.sh

# Build all known agents
./build_agents.sh all

# Or build specific agents
./build_agents.sh alice bob eve
```

### Build Output

Executables are created in: `build/agents/dist/`

```
build/agents/dist/
├── DW_Agent_alice         # Executable for Alice agent
├── DW_Agent_bob           # Executable for Bob agent
├── DW_Agent_eve           # Executable for Eve agent
├── frontend/              # Web UI assets
├── mods/                  # Minecraft mods
│   ├── divineworld-1.0.0-all.jar
│   └── DWClientBot.jar
└── ULTIMMC_SETUP_*.txt    # Setup guides per agent
```

### Bundled Assets

Each executable includes:
- **Frontend**: React web UI for monitoring/control
- **Mods**: DivineWorld and DWClientBot mod JARs
- **Documentation**: UltimMC setup guide
- **Configuration**: All AI core modules and dependencies

---

## Running Agents

### Basic Agent Launch

```bash
# Start agent on default port (8001)
./build/agents/dist/DW_Agent_alice --agent-id alice

# Specify custom port
./build/agents/dist/DW_Agent_alice --agent-id alice --port 8002

# Enable verbose logging
./build/agents/dist/DW_Agent_alice --agent-id alice --debug
```

### With Minecraft Integration

```bash
# Launch agent WITH Minecraft client
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft

# Specify UltimMC path explicitly
./build/agents/dist/DW_Agent_alice --agent-id alice \
  --minecraft \
  --ultimmc-path ~/UltimMC/ultimmc

# Custom server (if not using default)
./build/agents/dist/DW_Agent_alice --agent-id alice \
  --minecraft \
  --server localhost:25565
```

### CLI Arguments Reference

```
--agent-id ID              Agent identifier (alice, bob, eve, etc.)
--port PORT               Server port (default: 8001)
--minecraft               Launch Minecraft client with agent
--ultimmc-path PATH       Path to UltimMC executable
--debug                   Enable debug logging
--server HOST:PORT        Target Minecraft server
--personality TYPE        Personality type (default: balanced)
```

### Multiple Agents (Same Machine)

```bash
# Launch agents on different ports in background
./build/agents/dist/DW_Agent_alice --agent-id alice --port 8001 &
./build/agents/dist/DW_Agent_bob --agent-id bob --port 8002 &
./build/agents/dist/DW_Agent_eve --agent-id eve --port 8003 &

# Check if agents are running
ps aux | grep DW_Agent

# Stop an agent
pkill -f "DW_Agent_alice"

# Stop all agents
pkill -f "DW_Agent_"
```

### Access Agent Web UI

Each agent includes a web UI accessible at:
```
http://localhost:8001/   # Alice (default port)
http://localhost:8002/   # Bob (if running)
http://localhost:8003/   # Eve (if running)
```

Features:
- Monitor agent mental state
- View perception data
- Send commands
- Check Minecraft connection status
- View logs and performance metrics

---

## Minecraft Integration

### How It Works

1. Agent starts and initializes
2. If `--minecraft` flag set, agent detects UltimMC
3. UltimMC launcher opens (may be visible on screen)
4. Game instance loads with DivineWorld mod
5. Agent connects to Minecraft world
6. Bidirectional communication via WebSocket

### Server Configuration

Edit `py_backend/ai_core/config.py` to customize:

```python
# Minecraft connection settings
MINECRAFT_VERSION = "1.20.1"
FORGE_VERSION = "47.2.0"
USE_ULTIMMC = True
ULTIMMC_PATH = None  # Auto-detect if None

# Game server (must match UltimMC instance)
MINECRAFT_SERVER_HOST = "localhost"
MINECRAFT_SERVER_PORT = 25565

# Agent behavior
AGENT_TICK_RATE = 20  # ticks per second
AGENT_UPDATE_FREQUENCY = 1.0  # seconds
```

### Mod Installation

The DivineWorld and DWClientBot mods are automatically included in executables.

If building custom versions:

```bash
# Build DivineWorld mod
cd DivineWorld
gradle build

# Build DWClientBot mod
cd DWClientBot
gradle build

# Verify JAR creation
ls -lah DivineWorld/build/libs/*.jar
ls -lah DWClientBot/build/libs/*.jar
```

### Common Minecraft Issues

**Issue: "UltimMC not found"**
- Ensure UltimMC is installed in one of the standard locations
- Or specify path: `--ultimmc-path /path/to/ultimmc`
- See [UltimMC Setup](#ultimmc-setup) section

**Issue: "Minecraft version mismatch"**
- Check UltimMC game instance matches config version (1.20.1)
- Update config.py if using different version

**Issue: "Mod loading failed"**
- Ensure Forge is installed in UltimMC
- Check mod JAR files are not corrupted
- Verify Java version matches Minecraft requirements

---

## Troubleshooting

### General Diagnostics

```bash
# Check Python environment
python3 -m venv --help

# Verify ai_core modules
python3 -c "from ai_core.config import Config; print(Config.AGENT_ID)"

# Test PyInstaller compilation
python3 -m PyInstaller --version

# Check open ports
netstat -tuln | grep LISTEN
```

### Agent Won't Start

```bash
# Run with verbose output
./build/agents/dist/DW_Agent_alice --agent-id alice --debug

# Check for port conflict
lsof -i :8001

# Verify executable permissions
chmod +x ./build/agents/dist/DW_Agent_alice

# Run syntax check
python3 -m py_compile ./build/agents/dist/DW_Agent_alice
```

### Connection Issues

```bash
# Test backend connectivity
curl http://localhost:8001/health

# Check firewall
sudo ufw status
sudo ufw allow 8001/tcp

# Monitor network traffic
tcpdump -i lo port 8001

# Test WebSocket connection
python3 -c "
import asyncio
import aiohttp
async def test():
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect('ws://localhost:8001/ws') as ws:
            print('✅ WebSocket connected')
asyncio.run(test())
"
```

### Memory/Performance Issues

```bash
# Monitor resource usage
top -p $(pgrep -f "DW_Agent_alice")

# Limit agent memory usage
ulimit -v 4194304  # 4GB limit

# Check disk space
df -h
du -sh ./build/agents/dist/

# Profile agent execution
python3 -m cProfile -s cumulative ./build/agents/dist/DW_Agent_alice
```

### Minecraft Connection Issues

```bash
# Check if Minecraft server is running
ping localhost

# Verify port accessibility
nc -zv localhost 25565

# Check UltimMC logs
cat ~/.ultimmc/logs/latest.log

# Force UltimMC location
export ULTIMMC_PATH=~/UltimMC/ultimmc
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft
```

---

## Docker Deployment

### Docker Prerequisites

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Verify installation
docker --version
```

### Build Docker Image

A Dockerfile is provided in `py_backend/`:

```bash
cd py_backend

# Build image
docker build -t divine-world-agent:latest .

# Verify build
docker images | grep divine-world
```

### Run Agent in Docker

```bash
# Single agent
docker run -p 8001:8001 \
  -e AGENT_ID=alice \
  -e MINECRAFT_ENABLED=true \
  divine-world-agent:latest

# Multiple agents
docker run -p 8002:8002 \
  -e AGENT_ID=bob \
  -e PORT=8002 \
  divine-world-agent:latest &

docker run -p 8003:8003 \
  -e AGENT_ID=eve \
  -e PORT=8003 \
  divine-world-agent:latest &
```

### Docker Compose Setup

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  agent-alice:
    build: ./py_backend
    container_name: divine-alice
    environment:
      AGENT_ID: alice
      PORT: 8001
      MINECRAFT_ENABLED: "true"
    ports:
      - "8001:8001"
    volumes:
      - ./data/brains:/data/brains
      - ./data/logs:/data/logs

  agent-bob:
    build: ./py_backend
    container_name: divine-bob
    environment:
      AGENT_ID: bob
      PORT: 8002
    ports:
      - "8002:8002"
    volumes:
      - ./data/brains:/data/brains
      - ./data/logs:/data/logs

  agent-eve:
    build: ./py_backend
    container_name: divine-eve
    environment:
      AGENT_ID: eve
      PORT: 8003
    ports:
      - "8003:8003"
    volumes:
      - ./data/brains:/data/brains
      - ./data/logs:/data/logs
```

Run all agents:
```bash
docker-compose up -d

# Monitor
docker-compose logs -f

# Stop
docker-compose down
```

---

## Advanced Configuration

### Custom Personality

Edit `py_backend/ai_core/agent.py`:

```python
# Define custom personality
CUSTOM_PERSONALITIES = {
    "adventurous": {
        "curiosity": 0.9,
        "bravery": 0.8,
        "empathy": 0.6,
    },
    "cautious": {
        "curiosity": 0.5,
        "bravery": 0.3,
        "empathy": 0.8,
    }
}
```

Run with custom personality:
```bash
./build/agents/dist/DW_Agent_alice --agent-id alice --personality adventurous
```

### Custom Server

Modify `py_backend/ai_core/config.py`:

```python
# Connect to specific Minecraft server
MINECRAFT_SERVER_HOST = "your-server.com"
MINECRAFT_SERVER_PORT = 25565
```

Or at runtime:
```bash
./build/agents/dist/DW_Agent_alice --server your-server.com:25565
```

### Enable GPU Acceleration

```bash
# Install PyTorch with CUDA
pip3 install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Rebuild agents
./build_agents.sh all

# Verify GPU usage
nvidia-smi
```

---

## Support & Resources

### Documentation
- [System Architecture](./README/SYSTEM_ARCHITECTURE.md)
- [Agent Spawning Guide](./README/AGENT_SPAWNING_AND_MINECRAFT_INTEGRATION.md)
- [Standalone Agent Setup](./README_STANDALONE_AGENTS.md)
- [Mental Matrix Guide](./README/MENTAL_MATRIX_GUIDE.md)

### Community
- GitHub: [divine-world-core](https://github.com/divine-world-core)
- Issues: Report bugs via GitHub Issues
- Discussions: Join community discussions

### Getting Help

If you encounter issues:

1. Check [Troubleshooting](#troubleshooting) section
2. Review agent logs: `./data/logs/`
3. Check UltimMC logs: `~/.ultimmc/logs/`
4. Search GitHub issues
5. Create detailed bug report with:
   - OS and version
   - Python version
   - Error logs
   - Steps to reproduce

---

## License

Divine World is licensed under the terms specified in [License.txt](./License.txt).

For commercial deployment, see [Authorization.txt](./Authorization.txt).

---

**Last Updated**: 2024
**Version**: 1.0.0
