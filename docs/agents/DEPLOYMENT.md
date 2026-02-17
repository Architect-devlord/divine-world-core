# Quick Deployment & Testing Guide

## What Changed

### Python Backend (`py_backend/`)

1. **New File:** `utils/agents_json_manager.py`
   - Manages agents.json creation and updates
   - Handles NPC and God registration
   - Cross-platform Documents/Desktop search

2. **Modified:** `main.py`
   - Added import: `from utils.agents_json_manager import get_manager`
   - Updated `MinecraftServerIntegration.register_agent()` to accept agent metadata
   - Now writes to agents.json on every agent spawn

### Java Mod (`DivineWorld/src/main/java/com/divineworld/`)

1. **Updated:** `commands/CommandRegistrar.java`
   - Added import for `AgentConfigLoader`
   - Pre-loads agent config on startup
   - Logs agent registry statistics

2. **Enhanced:** `commands/DivineCommands.java`
   - Added import for `AgentConfigLoader`
   - Updated `/spawn_god` to validate types
   - Enhanced `/genesis` to display available agents
   - Updated `/list_agents` to show registry stats
   - Added autocomplete suggestions from config

## Deployment Steps

### Step 1: Update Python Backend

```bash
# Navigate to backend
cd /home/devlord/divine-world-core/py_backend

# Create/verify utils/__init__.py exists
touch utils/__init__.py

# Test import
python3 -c "from utils.agents_json_manager import get_manager; print('✅ OK')"
```

### Step 2: Rebuild Java Mod

```bash
# Navigate to mod directory
cd /home/devlord/divine-world-core/DivineWorld

# Clean and build
./gradlew clean build

# If build succeeds, you'll see:
# BUILD SUCCESSFUL
```

### Step 3: Deploy to Minecraft

```bash
# Copy built mod to mods folder
cp build/libs/DivineWorld-*.jar ~/minecraft/mods/

# Restart Minecraft server
```

## Testing Checklist

### Test 1: File Creation

```bash
# Run Python backend
cd /home/devlord/divine-world-core/py_backend
python3 main.py

# Check if agents.json is created
ls ~/Documents/agents.json
# Should show: /home/devlord/Documents/agents.json
```

### Test 2: Backend API - Genesis Spawn

```bash
# In another terminal, spawn genesis agents
curl -X POST http://localhost:8000/api/genesis/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "spawner": "TestPlayer",
    "world": "minecraft:overworld",
    "spawn_positions": [
      {"x": 100, "y": 64, "z": 200, "gender": "male"},
      {"x": 102, "y": 64, "z": 200, "gender": "female"}
    ]
  }'

# Check agents.json was updated
cat ~/Documents/agents.json
# Should show Adam in male array, Eve in female array
```

### Test 3: Backend API - Single NPC Spawn

```bash
curl -X POST http://localhost:8000/api/agents/spawn_single \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "Alice",
    "spawner": "TestPlayer",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200},
    "gender": "female"
  }'

# Check agents.json
cat ~/Documents/agents.json
# Should show Alice in female NPCs
```

### Test 4: Backend API - God Spawn

```bash
curl -X POST http://localhost:8000/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{
    "god_type": "wither",
    "spawner": "TestPlayer",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200}
  }'

# Check agents.json
cat ~/Documents/agents.json
# Should show god type in Gods.dual list
```

### Test 5: Java Mod Commands

In Minecraft:

```
# Command 1: List agents (includes registry stats)
/list_agents
# Output should show:
# [AI Agents] Total: X
# [Agent Registry] (agents.json)
#   Male NPCs: X
#   Female NPCs: X
#   Gods: X

# Command 2: Genesis (shows available agents)
/genesis
# Output should show:
# [Genesis] Available agents in registry:
#   Male: Adam, ...
#   Female: Eve, Alice, ...

# Command 3: Spawn god (with validation)
/spawn_god wither
# Should work if wither is registered

# Command 4: Spawn god with autocomplete
/spawn_god <TAB>
# Should suggest available god types
```

## Verification

### Check Backend is Working

```bash
# View backend logs
tail -f ~/divine-world-core/data/logs/agent_manager.log

# Look for entries like:
# ✅ Registered NPC: Adam (male) in agents.json
# ✅ Registered GOD: Wither in agents.json
```

### Check Java Mod is Loaded

```bash
# View mod logs (in Minecraft server)
# Look for entries like:
# [CommandRegistrar] Agent Configuration loaded:
#   - Male NPCs: 1
#   - Female NPCs: 1
#   - Gods: 1
```

### Check agents.json Format

```bash
# Verify JSON structure
python3 -c "
import json
with open('~/Documents/agents.json'.replace('~', os.path.expanduser('~')), 'r') as f:
    config = json.load(f)
    print('NPCs:')
    print(f'  Male: {config[\"NPCs\"][\"male\"]}')
    print(f'  Female: {config[\"NPCs\"][\"female\"]}')
    print('GODs:')
    print(f'  Dual: {config[\"GODs\"][\"dual\"]}')
"
```

## Troubleshooting

### Issue: agents.json not created

**Solution:**
```python
# Manually trigger creation
from utils.agents_json_manager import AgentsJsonManager
manager = AgentsJsonManager()
manager.load_config()  # Creates if not exists
```

### Issue: Backend not registering agents

1. Check server folder is configured:
```bash
curl -X POST http://localhost:8000/api/server/configure \
  -H "Content-Type: application/json" \
  -d '{"server_folder": "/path/to/minecraft/server"}'
```

2. Check backend logs for errors:
```bash
tail -f /path/to/backend/logs
```

### Issue: Java mod doesn't see agents

1. Verify agents.json location:
```bash
ls ~/Documents/agents.json
ls ~/Desktop/agents.json
```

2. Force config reload in mod:
```java
AgentConfigLoader.reloadConfig();
```

### Issue: Compilation errors in Java

```bash
cd /home/devlord/divine-world-core/DivineWorld
./gradlew clean build --stacktrace

# This will show detailed error messages
```

## Performance Considerations

- agents.json is cached for 30 seconds (Java side)
- Python writes are synchronous but fast (<10ms typically)
- No performance impact on agent spawning

## Rollback Instructions

If you need to revert changes:

### Python: Revert to cached behavior
```bash
cd py_backend
git checkout main.py utils/
```

### Java: Revert to non-cached behavior
```bash
cd DivineWorld
git checkout src/main/java/com/divineworld/commands/
```

## Next Steps

1. **Monitor logs** during first deployment
2. **Test all spawning endpoints** to ensure registration works
3. **Verify in-game commands** show correct agent counts
4. **Check agents.json** contains expected agents
5. **Validate breeding** registration if implemented

## Support

For issues or questions:
1. Check SYNC_SYSTEM.md (detailed documentation)
2. Review backend logs in `data/logs/`
3. Review Minecraft server logs
4. Check Java mod compilation errors with `--stacktrace`
