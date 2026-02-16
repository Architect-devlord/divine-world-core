# Agents.json Configuration Sync System

## Overview

This guide explains how the Divine World backend and Java mod now synchronize agent registration through a shared `agents.json` configuration file. All agents (NPCs and Gods) created via the backend are automatically registered in `agents.json` and available to the Java mod.

## Configuration File Location

The `agents.json` file is searched for in the following locations (in order):
- **Documents/agents.json** (Windows, macOS, Linux)
- **Desktop/agents.json** (Windows, macOS, Linux)

If not found, a new one is automatically created in the Documents folder.

## agents.json Format

```json
{
  "NPCs": {
    "male": ["Adam", "Bob", "Charlie", "David"],
    "female": ["Eve", "Alice", "Diana", "Emily"]
  },
  "GODs": {
    "dual": ["Zeus", "Odin", "Ra", "Amaterasu"]
  }
}
```

### Structure:
- **NPCs.male**: List of registered male NPC names
- **NPCs.female**: List of registered female NPC names
- **GODs.dual**: List of registered god entity names (all are dual-gendered)

## Backend Integration (Python)

### New Module: `py_backend/utils/agents_json_manager.py`

A new utility module has been added to manage agents.json operations:

```python
from utils.agents_json_manager import get_manager

manager = get_manager()

# Register NPC
manager.register_npc("Alice", "female")

# Register God
manager.register_god("Zeus", "dual")

# Get statistics
stats = manager.get_stats()
print(f"Total agents: {stats['total_agents']}")
```

### Automatic Registration on Agent Spawn

When any agent is created via the API endpoints, it's automatically registered in agents.json:

1. **Genesis Spawn** (`POST /api/genesis/spawn`)
   - Adam (male) → registered as male NPC
   - Eve (female) → registered as female NPC

2. **Single NPC Spawn** (`POST /api/agents/spawn_single`)
   - Agent name → registered with detected or specified gender

3. **God Spawn** (`POST /api/gods/spawn`)
   - God name → registered as dual-gendered god entity

### Implementation Details

The `MinecraftServerIntegration.register_agent()` method now:
1. Updates `usercache.json` (Minecraft server)
2. Updates `usernamecache.json` (Minecraft server)
3. **NEW:** Updates `agents.json` via `AgentsJsonManager`

```python
server_integration.register_agent(
    agent_id="adam",
    agent_uuid=uuid,
    agent_type="npc",  # or "god_wither", etc.
    custom_name="Adam"  # Display name
)
```

## Java Mod Integration

### Updated: `DivineWorld/src/main/java/com/divineworld/commands/CommandRegistrar.java`

Now automatically loads and logs agent configuration on startup:

```java
public static void register() {
    MinecraftForge.EVENT_BUS.register(new CommandRegistrar());
    
    // Pre-load agent configuration
    AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
    DWMod.LOGGER.info("[CommandRegistrar] Agent Configuration loaded:");
    DWMod.LOGGER.info("  - Male NPCs: {}", config.getMaleNPCNames().size());
    DWMod.LOGGER.info("  - Female NPCs: {}", config.getFemaleNPCNames().size());
    DWMod.LOGGER.info("  - Gods: {}", config.getGodTypes().size());
    
    // ... rest of registration
}
```

### Enhanced: `DivineWorld/src/main/java/com/divineworld/commands/DivineCommands.java`

Commands now use agent registry for validation and suggestions:

#### `/genesis`
- Displays available male/female NPCs from registry
- Spawns Adam & Eve with proper gender-based traits

#### `/spawn_god <type>`
- Validates god type against registered gods
- Suggests available god types with autocomplete
- Shows available gods if invalid type is specified

#### `/list_agents`
- Lists currently active agents
- Shows agent registry statistics (total counts by type)

### Using AgentConfigLoader

The Java mod uses the existing `AgentConfigLoader.java` utility:

```java
// Load configuration
AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();

// Get all male NPCs
List<String> maleNPCs = config.getMaleNPCNames();

// Get all female NPCs
List<String> femaleNPCs = config.getFemaleNPCNames();

// Get all gods
List<String> gods = config.getGodTypes();

// Random selections
String randomMale = AgentConfigLoader.getRandomMaleNPCName();
String randomFemale = AgentConfigLoader.getRandomFemaleNPCName();

// Validate god type
if (AgentConfigLoader.isValidGodType(godType)) {
    // Spawn god
}
```

## Workflow: Agent Creation to Registry

### Example: Spawning Adam & Eve (Genesis)

1. **Python Backend** receives genesis spawn request:
   ```python
   POST /api/genesis/spawn
   {
       "spawner": "PlayerName",
       "world": "minecraft:overworld",
       "spawn_positions": [
           {"x": 100, "y": 64, "z": 200, "gender": "male"},
           {"x": 102, "y": 64, "z": 200, "gender": "female"}
       ]
   }
   ```

2. **Backend** spawns agents with proper UUIDs

3. **Backend** calls `register_agent()`:
   ```python
   # For Adam
   server_integration.register_agent(
       agent_id="adam",
       agent_uuid=uuid,
       agent_type="npc",
       custom_name="Adam"
   )
   # For Eve
   server_integration.register_agent(
       agent_id="eve",
       agent_uuid=uuid,
       agent_type="npc",
       custom_name="Eve"
   )
   ```

4. **register_agent()** performs three registrations:
   - Updates `usercache.json` for Minecraft server
   - Updates `usernamecache.json` for Minecraft server
   - **NEW:** Updates `agents.json`:
     - Adds "Adam" to NPCs.male
     - Adds "Eve" to NPCs.female

5. **Java Mod** reads agents.json via `AgentConfigLoader`:
   ```java
   AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();
   String randomMale = config.getMaleNPCNames().get(0);  // "Adam"
   String randomFemale = config.getFemaleNPCNames().get(0);  // "Eve"
   ```

## Features

### Automatic File Management
- Creates agents.json if it doesn't exist
- Automatically finds it in standard locations
- Cross-platform support (Windows, macOS, Linux)

### Duplicate Prevention
- Prevents duplicate agent names
- Validates gender for NPCs
- Checks existing registrations

### Real-time Sync
- Updates happen immediately on agent spawn
- No additional configuration needed
- Zero latency between backend and mod

### Extensible Design
- Easy to add new agent types
- Support for custom god types
- Flexible gender system

### Logging
- Detailed logging of all registration events
- Console output for debugging
- File logging in Python backend

## Usage Examples

### Python Backend Usage

```python
from utils.agents_json_manager import get_manager

# Get manager instance
manager = get_manager()

# Register a new male NPC
success = manager.register_npc("John", "male")
if success:
    print("John registered!")

# Register a god
success = manager.register_god("Apollo", "dual")

# Get all registered agents
male_npcs = manager.get_all_male_npcs()  # ["Adam", "John"]
female_npcs = manager.get_all_female_npcs()  # ["Eve"]
gods = manager.get_all_gods()  # ["Apollo"]

# Get statistics
stats = manager.get_stats()
print(f"Total registered agents: {stats['total_agents']}")
```

### Java Mod Usage

```java
import com.divineworld.utils.AgentConfigLoader;

// Load configuration
AgentConfigLoader.AgentConfig config = AgentConfigLoader.loadConfig();

// Validate before spawning
if (AgentConfigLoader.isValidGodType("Zeus")) {
    spawnGod("Zeus");
}

// Get random name for new agent
String maleNPCName = AgentConfigLoader.getRandomMaleNPCName();
String femaleNPCName = AgentConfigLoader.getRandomFemaleNPCName();

// Force reload configuration
config = AgentConfigLoader.reloadConfig();
```

## API Endpoints (Updated)

### POST /api/agents/spawn_single
Spawns a single NPC agent. The agent is automatically registered in agents.json.

**Request:**
```json
{
    "agent_name": "Alice",
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200},
    "gender": "female"
}
```

**Response:**
```json
{
    "status": "success",
    "agent_id": "npc1",
    "agent_name": "Alice",
    "gender": "female",
    "message": "NPC agent spawned and registered in agents.json"
}
```

### POST /api/genesis/spawn
Spawns Genesis agents (Adam & Eve). Both are automatically registered.

**Request:**
```json
{
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_positions": [
        {"x": 100, "y": 64, "z": 200, "gender": "male"},
        {"x": 102, "y": 64, "z": 200, "gender": "female"}
    ]
}
```

**Response:**
```json
{
    "status": "success",
    "agents": [
        {"agent_id": "adam", "display_name": "Adam", "gender": "male"},
        {"agent_id": "eve", "display_name": "Eve", "gender": "female"}
    ]
}
```

### POST /api/gods/spawn
Spawns a God entity. Automatically registered in agents.json as dual-gendered.

**Request:**
```json
{
    "god_type": "wither",
    "spawner": "PlayerName",
    "world": "minecraft:overworld",
    "spawn_position": {"x": 100, "y": 64, "z": 200}
}
```

**Response:**
```json
{
    "status": "success",
    "god_type": "wither",
    "agent_id": "god1",
    "gender": "dual",
    "message": "God spawned and registered in agents.json"
}
```

## Troubleshooting

### agents.json not found
- Check Documents folder first
- Check Desktop folder
- If not found, backend will create it automatically

### Agents not registering
1. Check Python backend logs for errors
2. Verify server_folder is configured: `POST /api/server/configure`
3. Restart backend if needed

### Java mod not seeing agents
1. Ensure agents.json is in Documents or Desktop
2. Use `/reloadconfig` command to refresh (if implemented)
3. Check mod logs for loading errors

### Duplicate agent names
- Backend prevents duplicates automatically
- If needed, manually edit agents.json

## Technical Details

### Gender Detection (NPC Registration)

The Python backend automatically detects gender based on:
1. Provided gender parameter (highest priority)
2. Agent ID (eve, genesis_2_female, etc.)
3. Common female names list
4. Default to male (fallback)

### God Type Mapping

Gods are always registered as "dual" type, but store the specific god type:
1. Wither
2. Warden
3. Ender Dragon
4. Oracle
5. Creaking
6. Elder Guardian
7. Custom types (extensible)

### UUID Generation

Each agent gets a unique offline-mode UUID based on:
- Agent type (NPC or GOD)
- Minecraft username (display name)
- Generated consistently for reproducibility

## Security Notes

- agents.json is stored in user's home directory
- No authentication required (local file)
- File permissions should be restricted by OS

## Future Enhancements

- [ ] Breeding system integration
- [ ] Agent lineage tracking
- [ ] Migration system
- [ ] Backup/restore functionality
- [ ] Web UI for agent management
- [ ] Stats dashboard
