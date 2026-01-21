# Quick Start: Automated Agent Spawning with UltimMC

## TL;DR - Get Agents in Minecraft in 3 Steps

### Step 1: Install UltimMC (one-time)

```bash
# Clone UltimMC
git clone https://github.com/UltimMC/Launcher
cd Launcher
./gradlew build

# Install to PATH
mkdir -p ~/.local/bin
cp build/distributions/UltimMC ~/.local/bin/ultimmc
chmod +x ~/.local/bin/ultimmc

# Verify
ultimmc --version
```

### Step 2: Build Mods (one-time)

```bash
cd /home/devlord/divine-world-core

# Build DWClientBot
cd DWClientBot && ./gradlew build && cd ..

# Build DivineWorld  
cd DivineWorld && ./gradlew build && cd ..

# Verify jars exist
ls -lh DWClientBot/build/libs/DWClientBot.jar
ls -lh DivineWorld/build/libs/DivineWorld-1.0.0.jar
```

### Step 3: Spawn Agents (run anytime)

```bash
# Start backend
cd py_backend
source dw_env/bin/activate
python main.py

# In another terminal, spawn agents
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"

# Wait 30-60 seconds...
# Agents "adam" and "eve" should appear in your Minecraft server!
```

That's it! 🎮

---

## What Just Happened?

When you called `/api/genesis/spawn`, the system automatically:

1. ✅ Created Minecraft accounts (`adam`, `eve`)
2. ✅ Created Minecraft instances with Forge
3. ✅ Installed mods (DWClientBot, DivineWorld)
4. ✅ Launched Minecraft with system properties pointing to the backend
5. ✅ DWClientBot mod connected to backend
6. ✅ Agents joined the Minecraft server
7. ✅ AI brains started controlling the agents

**No manual Minecraft setup required!**

---

## Verify Agents Are Running

### Check via API

```bash
# List all agents
curl "http://127.0.0.1:11400/agents" | jq

# Get specific agent
curl "http://127.0.0.1:11400/agents/adam" | jq
```

### Check in Minecraft

1. Launch your Minecraft server (if not already running)
2. Look in the server player list — you should see `adam` and `eve`
3. They'll be moving around, mining, fighting — all controlled by AI!

### Check Running Processes

```bash
# See Java clients running
ps aux | grep "dw.agentId"

# Check UltimMC instances
ls ~/.ultimmc/instances/
```

---

## Configuration

### Change Minecraft Server

```bash
export DW_SERVER=my-server.com:25565
# Then spawn agents — they'll join your custom server
```

### Allocate More Memory

```bash
export DW_CLIENT_MEMORY=4096  # 4GB per agent
# Then spawn agents with more memory
```

### Disable UltimMC (fallback to legacy)

```bash
export DW_USE_ULTIMMC=false
# System will use legacy Java client launch
```

---

## Troubleshooting

### UltimMC Not Found

```
ERROR: UltimMC not found
```

**Fix:**
```bash
# Check if installed
which ultimmc

# If not, reinstall (see Step 1)

# Or set path explicitly
export DW_ULTIMMC_PATH=/full/path/to/ultimmc
```

### Mods Not Found

```
ERROR: Failed to install DWClientBot mod
```

**Fix:**
```bash
# Rebuild mods (Step 2)
cd DWClientBot && ./gradlew clean build
cd ../DivineWorld && ./gradlew clean build

# Or set paths explicitly
export DW_CLIENT_JAR=/path/to/DWClientBot.jar
export DW_MOD_JAR=/path/to/DivineWorld-1.0.0.jar
```

### Agents Not Appearing

**Checklist:**
1. Is server running? (Separate Minecraft server instance)
2. Check backend logs for errors: `tail -f backend.log`
3. Check system has enough disk space: `df -h`
4. Check Java is installed: `java -version` (needs 17+)
5. Try spawning again: sometimes takes 30-60 seconds

---

## Common Tasks

### List Active Agents

```bash
curl "http://127.0.0.1:11400/agents" | jq '.agents | keys'
```

### Get Agent Perception

```bash
# What the agent sees
curl "http://127.0.0.1:11400/agents/adam/perception" | jq
```

### Send Agent a Command

```bash
# Make agent move forward
curl -X POST "http://127.0.0.1:11400/agents/adam/action" \
  -H "Content-Type: application/json" \
  -d '{"action": "move_forward", "duration": 5}'
```

### Despawn Agent

```bash
curl -X POST "http://127.0.0.1:11400/agents/adam/despawn"
```

---

## Environment Cheat Sheet

```bash
# Enable/disable UltimMC
export DW_USE_ULTIMMC=true

# Where UltimMC is installed
export DW_ULTIMMC_PATH=/path/to/ultimmc

# Minecraft version and Forge
export DW_MINECRAFT_VERSION=1.20.1
export DW_FORGE_VERSION=47.3.0

# Server to join
export DW_SERVER=127.0.0.1:25565

# Memory per client
export DW_CLIENT_MEMORY=2048

# Mod jar locations
export DW_CLIENT_JAR=/path/to/DWClientBot.jar
export DW_MOD_JAR=/path/to/DivineWorld-1.0.0.jar

# Backend port
export DW_BACKEND_PORT=11400
```

---

## Performance

**Spawn Time per Agent:**
- Account creation: <1 sec
- Instance setup: 2-3 sec
- Mod installation: 1-2 sec
- Minecraft launch: 10-30 sec
- **Total: ~15-40 sec per agent**

For 2 agents (adam, eve): ~30-80 seconds total

**Disk Usage per Agent:**
- Minecraft instance: ~500MB
- Mods: ~50MB
- **Total: ~550MB per agent**

For 10 agents: ~5.5GB

---

## Next Steps

1. **Customize Agent Behavior** — Edit agent personas in `ai_core/personality.py`
2. **Add More Agents** — Extend `/api/genesis/spawn` to spawn more agents
3. **Interactive Control** — Send commands to agents via REST API
4. **Monitor Performance** — Check backend metrics via `/health`
5. **Persistent Storage** — Save agent brains and memories

---

## Full Documentation

For detailed configuration, troubleshooting, and advanced features, see:
- **ULTIMMC_AUTOMATION.md** — Comprehensive UltimMC guide
- **AGENT_SPAWNING_AND_MINECRAFT_INTEGRATION.md** — Agent architecture
- **py_backend/config.py** — Configuration reference

---

**Questions?** Check the logs:
```bash
# Backend logs
grep -i ultimmc backend.log

# Agent client logs
grep "Client:" backend.log

# All errors
grep "ERROR\|WARN" backend.log
```

Happy agent spawning! 🤖🎮
