# UltimMC Automation for Divine World Agents

## Overview

Divine World now supports **fully automated agent spawning** using UltimMC, an open-source Minecraft launcher. When you call `/api/genesis/spawn`, the system automatically:

1. ✅ Creates a local Minecraft account (offline mode)
2. ✅ Installs a Minecraft 1.20.1 instance with Forge
3. ✅ Installs mods (DivineWorld + DWClientBot)
4. ✅ Launches Minecraft with the correct system properties
5. ✅ Agent joins server and starts receiving perception
6. ✅ Agent is controlled by the AI brain in real-time

**Zero user intervention required** — from genesis spawn to agent playing in Minecraft!

---

## Installation

### Prerequisites
- Linux system (tested on Linux, macOS/Windows via WSL)
- Java 17+ installed
- ~2GB disk space for each Minecraft instance

### Install UltimMC

#### Option 1: From Source (Recommended)
```bash
git clone https://github.com/UltimMC/Launcher
cd Launcher
./gradlew build

# Install to ~/.local/bin
mkdir -p ~/.local/bin
cp build/distributions/UltimMC ~/.local/bin/ultimmc
chmod +x ~/.local/bin/ultimmc

# Verify installation
ultimmc --version
```

#### Option 2: Pre-built Binary
Download from: https://github.com/UltimMC/Launcher/releases

Extract and add to PATH:
```bash
tar -xzf UltimMC-*.tar.gz -C ~/.local/bin/
chmod +x ~/.local/bin/ultimmc
```

#### Option 3: Docker (If Preferred)
```bash
docker run -it -v ~/.ultimmc:/root/.ultimmc ultimmc/launcher:latest
```

### Verify Installation
```bash
which ultimmc
ultimmc --version
```

If UltimMC is not found, set the path explicitly:
```bash
export DW_ULTIMMC_PATH=/path/to/ultimmc
```

---

## Configuration

### Environment Variables

Control UltimMC behavior via environment variables:

```bash
# Enable/disable UltimMC automation (default: true)
export DW_USE_ULTIMMC=true

# UltimMC executable path (auto-detect if not set)
export DW_ULTIMMC_PATH=/path/to/ultimmc

# Minecraft version to install (default: 1.20.1)
export DW_MINECRAFT_VERSION=1.20.1

# Forge version for the Minecraft version (default: 47.3.0)
export DW_FORGE_VERSION=47.3.0

# Minecraft server address (default: 127.0.0.1:25565)
export DW_SERVER=127.0.0.1:25565

# Client memory allocation in MB (default: 2048)
export DW_CLIENT_MEMORY=2048

# Paths to mod jars (auto-detect if not set)
export DW_CLIENT_JAR=/path/to/DWClientBot.jar
export DW_MOD_JAR=/path/to/DivineWorld-1.0.0.jar
```

### Config File

Settings are also available in `py_backend/config.py`:

```python
# Enable UltimMC automation
USE_ULTIMMC = True

# Minecraft/Forge versions
MINECRAFT_VERSION = "1.20.1"
FORGE_VERSION = "47.3.0"

# Mods are auto-detected from build output
MOD_JAR = Path("DivineWorld/build/libs/DivineWorld-1.0.0.jar")
CLIENT_JAR = Path("DWClientBot/build/libs/DWClientBot.jar")
```

---

## How It Works

### Flow Diagram

```
POST /api/genesis/spawn
         │
         ▼
┌─────────────────────────────────────┐
│ EnhancedAgentSpawner.spawn_npc()    │
└─────────────────────────────────────┘
         │
         ├─────────────────────────────────────┐
         │                                     │
         ▼                                     ▼
  ┌───────────────────┐          ┌──────────────────────┐
  │ Create Agent      │          │ UltimMC Automation   │
  │ - Personality     │          │ 1. Create account    │
  │ - Gender          │          │ 2. Create instance   │
  │ - Memory          │          │ 3. Install Forge     │
  └───────────────────┘          │ 4. Copy mods         │
         │                       │ 5. Launch Minecraft  │
         │                       └──────────────────────┘
         │                            │
         └────────────┬───────────────┘
                      │
         ┌────────────▼──────────┐
         │  Launch Java Client   │
         │  with system props:   │
         │  - dw.agentId=adam    │
         │  - dw.server=...      │
         │  - dw.backend=...     │
         └────────────┬──────────┘
                      │
         ┌────────────▼──────────────┐
         │  DWClientBot Mod Loads    │
         │  - Reads system properties│
         │  - Connects to backend    │
         │  - Joins server          │
         └────────────┬──────────────┘
                      │
         ┌────────────▼──────────────┐
         │  Agent in Minecraft!      │
         │  - Receives perception    │
         │  - Brain makes decisions  │
         │  - Executes actions       │
         └───────────────────────────┘
```

### Key Components

#### 1. UltimMCLauncher (minecraft_launcher.py)

Handles all Minecraft setup:

```python
launcher = UltimMCLauncher(
    client_jar_path="DWClientBot.jar",
    mod_jar_path="DivineWorld-1.0.0.jar"
)

# Setup complete Minecraft instance for agent
launcher.setup_agent_instance(agent_id="adam", server_addr="127.0.0.1:25565")

# Launch the agent's Minecraft client
process = launcher.launch_agent(
    agent_id="adam",
    server_addr="127.0.0.1:25565",
    backend_url="http://127.0.0.1:11400",
    memory_mb=2048
)
```

#### 2. EnhancedAgentSpawner (agent_spawner.py)

Extends base spawner with UltimMC integration:

```python
spawner = EnhancedAgentSpawner(
    client_jar_path="DWClientBot.jar",
    use_ultimmc=True
)

# Automatically uses UltimMC if available
agent = spawner.spawn_npc(
    agent_id="adam",
    server_addr="127.0.0.1:25565"
)
```

#### 3. Auto-Packager Integration

The `EnhancedAgentSpawner` in `auto_packager.py` combines:
- UltimMC automation
- Auto-packaging of agents
- Brain state management

```python
manager = EnhancedAgentManager()  # Uses auto_packager.EnhancedAgentSpawner
# Spawns agent AND packages it automatically!
```

---

## Usage Examples

### Example 1: Spawn Agents via Genesis Endpoint

```bash
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

**What happens automatically:**
1. Backend creates "adam" and "eve" agents
2. UltimMC creates accounts: `adam`, `eve`
3. UltimMC creates instances: `agent_adam`, `agent_eve`
4. UltimMC installs Forge for each instance
5. DWClientBot mod copied to each instance's `mods/` folder
6. DivineWorld mod copied to each instance's `mods/` folder
7. Java launched with system properties for each agent
8. DWClientBot reads properties and connects
9. Agents appear in server as players "adam" and "eve"
10. Both agents controlled by AI brains in real-time

**Output:**
```json
{
  "status": "spawning",
  "agents": ["adam", "eve"],
  "message": "Agents spawned with UltimMC automation"
}
```

Agent "adam" is now playing Minecraft, controlled by AI!

### Example 2: Check Agent Status

```bash
curl "http://127.0.0.1:11400/agents/adam"
```

**Response:**
```json
{
  "agent_id": "adam",
  "type": "npc",
  "status": "active",
  "client": {
    "process_id": 12345,
    "backend_port": 11400,
    "server": "127.0.0.1:25565",
    "ultimmc_instance": "agent_adam"
  },
  "perception": {
    "position": [100.5, 64.0, 200.3],
    "health": 20,
    "hunger": 10
  },
  "actions": {
    "move": "forward",
    "attack": false
  }
}
```

### Example 3: Manual Configuration with Environment Variables

```bash
# Custom Minecraft version and server
export DW_MINECRAFT_VERSION=1.19.2
export DW_FORGE_VERSION=41.1.0
export DW_SERVER=mc.example.com:25565
export DW_CLIENT_MEMORY=4096

# Start backend
python py_backend/main.py

# Then spawn agents
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

---

## Troubleshooting

### UltimMC Not Found

```
ERROR: UltimMC not found - falling back to legacy client launch
```

**Solution:**
1. Install UltimMC (see Installation section)
2. Add to PATH: `export PATH="$PATH:$HOME/.local/bin"`
3. Or set explicitly: `export DW_ULTIMMC_PATH=/path/to/ultimmc`
4. Verify: `which ultimmc`

### Mods Not Installing

```
ERROR: Failed to install DWClientBot mod: [No such file or directory]
```

**Solution:**
1. Build the mods:
   ```bash
   cd DWClientBot && ./gradlew build
   cd ../DivineWorld && ./gradlew build
   ```
2. Or set paths explicitly:
   ```bash
   export DW_CLIENT_JAR=/full/path/to/DWClientBot.jar
   export DW_MOD_JAR=/full/path/to/DivineWorld-1.0.0.jar
   ```

### Minecraft Instance Failed to Create

```
ERROR: Creating Minecraft instance: agent_adam failed
```

**Solution:**
1. Check Java version: `java -version` (requires 17+)
2. Check disk space: `df -h` (need ~2GB)
3. Check UltimMC configuration: `~/.ultimmc/`
4. Check logs: `~/.ultimmc/launcher.log`

### Agent Not Appearing in Server

```
Agent spawned successfully but not visible in Minecraft server
```

**Checklist:**
1. Is Minecraft server running? `ps aux | grep java` (look for server process)
2. Is DWClientBot mod installed? Check instance `mods/` folder
3. Check backend logs for perception/action flow
4. Verify system properties were passed: Look for `-Ddw.agentId` in process list
5. Check Minecraft server logs for player join event

### Memory Issues

```
java.lang.OutOfMemoryError: Java heap space
```

**Solution:**
Increase memory allocation:
```bash
export DW_CLIENT_MEMORY=4096  # 4GB instead of default 2GB
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

### Port Conflicts

```
ERROR: Failed to launch UltimMC: Address already in use
```

**Solution:**
1. Check occupied ports: `lsof -i :11400`
2. Kill existing process: `kill -9 <PID>`
3. Or change port: `export DW_BACKEND_PORT=11401`

---

## Architecture Details

### UltimMCLauncher Class

**Location:** `py_backend/minecraft_launcher.py`

**Key Methods:**
- `create_account(username)` — Create offline account
- `create_instance(name)` — Setup Minecraft instance with Forge
- `install_mods(instance)` — Copy DWClientBot and DivineWorld mods
- `launch_instance(...)` — Launch Minecraft with system properties
- `setup_agent_instance(agent_id)` — Complete setup pipeline

**System Properties Passed to Java:**
```
-Xmx{memory}M              # Max heap size
-Xms{memory}M              # Min heap size
-Ddw.agentId={agent_id}    # Agent identifier
-Ddw.server={server_addr}  # Minecraft server to join
-Ddw.backend={backend_url} # Backend API URL
```

DWClientBot mod reads these properties on startup and:
1. Connects to backend API
2. Joins specified server
3. Creates player with agent_id as username
4. Begins perception/action loop

### EnhancedAgentSpawner in agent_spawner.py

**Location:** `py_backend/ai_core/agent_spawner.py`

**Key Methods:**
- `spawn_npc_with_ultimmc(...)` — Spawn with full automation
- `spawn_npc(...)` — Automatically selects UltimMC if available

**Fallback Behavior:**
If UltimMC unavailable → falls back to legacy Java client launch
If legacy client jar unavailable → chat-only mode

---

## Performance Considerations

### Startup Time

- **Account creation:** <1 second
- **Instance creation:** ~2-3 seconds
- **Mod installation:** ~1-2 seconds
- **Minecraft launch:** 10-30 seconds (depends on system)
- **Total per agent:** ~15-40 seconds

With 2 agents (adam, eve): ~30-80 seconds total

### Disk Usage

- **Per instance:** ~500MB (Minecraft + Forge)
- **Mods:** ~50MB (both mods)
- **Instance metadata:** ~5MB

For 10 agents: ~5.5GB total

### Memory Usage

- **UltimMC launcher:** ~100MB
- **Per Minecraft client:** Configurable (default 2048MB)
- **Backend overhead:** ~200MB

For 2 agents at default memory: ~4.5GB total

---

## Disabling UltimMC

If you prefer not to use UltimMC, disable it:

```bash
export DW_USE_ULTIMMC=false
```

The system will:
1. Fall back to legacy Java client launch
2. Still auto-package agents
3. Still manage agent lifecycle
4. You manually handle Minecraft setup

Or modify config:
```python
# py_backend/config.py
USE_ULTIMMC = False
```

---

## Advanced Configuration

### Custom Minecraft Server

```bash
export DW_SERVER=mc.my-server.com:25565
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

Agents will join your custom server instead of localhost.

### Custom Memory Per Agent

Currently set globally via `DW_CLIENT_MEMORY`. To set per-agent, modify spawn call:

```python
spawner.spawn_npc(
    agent_id="adam",
    memory_mb=4096  # Override per agent
)
```

### Custom Minecraft Version

To use a different Minecraft version:

```bash
export DW_MINECRAFT_VERSION=1.19.2
export DW_FORGE_VERSION=41.1.0
```

Make sure Forge version matches the Minecraft version!

---

## Monitoring & Logging

### View Logs

**Backend logs:**
```bash
tail -f ~/.divine-world/backend.log
```

**UltimMC logs:**
```bash
tail -f ~/.ultimmc/launcher.log
```

**Agent client logs:**
```bash
# Client stdout/stderr piped to backend logger
grep "Client:adam" ~/.divine-world/backend.log
```

### Check Running Instances

```bash
# List all UltimMC instances
ls -la ~/.ultimmc/instances/

# Check specific agent instance
ls -la ~/.ultimmc/instances/agent_adam/mods/
```

### Monitor Agent Status

```bash
# Via REST API
curl "http://127.0.0.1:11400/agents"

# Check process
ps aux | grep "dw.agentId"
```

---

## Future Enhancements

Planned improvements:

1. **Instance Pooling** — Pre-create instances for faster spawning
2. **Auto-Update** — Keep Forge and mods updated
3. **Resource Limits** — Per-agent CPU/memory limits via cgroups
4. **Clustering** — Span agents across multiple machines
5. **Performance Monitoring** — Built-in metrics and profiling
6. **Mod Management** — Dynamic mod loading/unloading

---

## Support

If you encounter issues:

1. **Check documentation:** https://github.com/UltimMC/Launcher
2. **Review logs:** Backend and UltimMC logs
3. **Verify setup:** Ensure Java, Minecraft, Forge are available
4. **Test manually:** Try launching Minecraft manually via UltimMC to rule out issues

---

## Summary

With UltimMC automation, you now have:

✅ **Zero-intervention agent spawning** — Call one endpoint, agents play in Minecraft
✅ **Automatic setup** — Accounts, instances, mods, all created automatically  
✅ **Full control** — Backend fully controls agent actions in-game
✅ **Scalable** — Spawn as many agents as resources allow
✅ **Robust** — Fallback to legacy launch if UltimMC unavailable

**One command to spawn intelligent agents in Minecraft:**
```bash
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"
```

Done! 🎮
