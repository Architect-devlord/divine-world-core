# Divine World Backend API Documentation

## Quick Start

### Start the Backend
```bash
cd /home/devlord/divine-world-core/py_backend
source dw_env/bin/activate
python3 main.py
```

Backend will run on: `http://127.0.0.1:11400`
WebSocket: `ws://127.0.0.1:11400/ws/agent`

### Check Status
```bash
curl http://127.0.0.1:11400/
```

---

## Divine World Mod Commands API

All Divine World commands are available via REST API at `/api/divineworld/*`

### 1. Genesis Command
**Spawn 2 AI agents**

```bash
curl -X POST http://127.0.0.1:11400/api/genesis/spawn
```

**Response:**
```json
{
  "status": "success",
  "command": "genesis",
  "agents": [...],
  "message": "Genesis spawned 2 agents",
  "timestamp": 1703790000.0
}
```

---

### 2. Divine Reset
**Kill all agents and clear their memories**

```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/divine_reset
```

**Response:**
```json
{
  "status": "success",
  "command": "divine_reset",
  "agents_cleared": ["genesis_1", "genesis_2"],
  "count": 2,
  "message": "Divine Reset cleared 2 agents and their memories",
  "timestamp": 1703790000.0
}
```

---

### 3. Clear Memories
**Selectively clear agent memories**

```bash
# Clear all agent memories
curl -X POST http://127.0.0.1:11400/api/agents/clear_memories \
  -H "Content-Type: application/json" \
  -d '{"target": "all"}'

# Clear specific agent memory
curl -X POST http://127.0.0.1:11400/api/agents/clear_memories \
  -H "Content-Type: application/json" \
  -d '{"target": "npc_alice_123456789"}'

# Clear all except specific agents
curl -X POST http://127.0.0.1:11400/api/agents/clear_memories \
  -H "Content-Type: application/json" \
  -d '{"target": "all", "exceptions": ["npc_alice_123456789"]}'
```

**Response:**
```json
{
  "status": "success",
  "command": "clear_memories",
  "target": "all",
  "exceptions": [],
  "cleared": ["genesis_1", "genesis_2"],
  "count": 2,
  "message": "Cleared memories for 2 agents",
  "timestamp": 1703790000.0
}
```

---

### 4. Spawn God
**Spawn god-tier entity**

**Available Types:** `oracle`, `wither`, `dragon`, `warden`, `creaking`

```bash
curl -X POST http://127.0.0.1:11400/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{"god_type": "oracle"}'
```

**Response:**
```json
{
  "status": "success",
  "command": "spawn_god",
  "god_type": "oracle",
  "agent_id": "god_oracle_1703790000000",
  "message": "Spawned oracle god: god_oracle_1703790000000",
  "timestamp": 1703790000.0
}
```

---

### 5. God Ability
**Activate god ability**

```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/god_ability \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "god_oracle_1703790000000",
    "ability": "summon_entities",
    "params": {"count": 5, "type": "zombie"}
  }'
```

**Response:**
```json
{
  "status": "success",
  "command": "god_ability",
  "agent_id": "god_oracle_1703790000000",
  "ability": "summon_entities",
  "params": {"count": 5, "type": "zombie"},
  "message": "god_oracle_1703790000000 activated ability: summon_entities",
  "timestamp": 1703790000.0
}
```

---

### 6. God Transform
**Transform god into different mob**

**Available Mobs:** `player`, `villager`, `pig`, `cow`, `zombie`, `skeleton`, `wither`, `dragon`

```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/god_transform \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "god_oracle_1703790000000",
    "target_mob": "wither"
  }'
```

**Response:**
```json
{
  "status": "success",
  "command": "god_transform",
  "agent_id": "god_oracle_1703790000000",
  "original_form": "god_oracle",
  "new_form": "wither",
  "message": "god_oracle_1703790000000 transformed into wither",
  "timestamp": 1703790000.0
}
```

---

### 7. List Agents
**List all NPCs and gods**

```bash
curl http://127.0.0.1:11400/api/divineworld/list_agents
```

**Response:**
```json
{
  "status": "success",
  "command": "list_agents",
  "agents": [
    {
      "agent_id": "genesis_1",
      "agent_type": "npc",
      "is_god": false,
      "health": 20.0,
      "hunger": 20.0,
      "memory_size": 42
    },
    {
      "agent_id": "god_oracle_1703790000000",
      "agent_type": "god_oracle",
      "is_god": true,
      "god_type": "oracle",
      "health": 20.0,
      "hunger": 20.0,
      "memory_size": 5
    }
  ],
  "total": 2,
  "npc_count": 1,
  "god_count": 1,
  "timestamp": 1703790000.0
}
```

---

### 8. Spawn NPC
**Spawn a new NPC**

```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/npc/spawn \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}'
```

**Response:**
```json
{
  "status": "success",
  "command": "npc_spawn",
  "npc_name": "Alice",
  "agent_id": "npc_alice_1703790000000",
  "message": "Spawned NPC: Alice",
  "timestamp": 1703790000.0
}
```

---

### 9. Remove NPC
**Remove an NPC**

```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/npc/remove \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "npc_alice_1703790000000"}'
```

**Response:**
```json
{
  "status": "success",
  "command": "npc_remove",
  "agent_id": "npc_alice_1703790000000",
  "message": "Removed NPC: npc_alice_1703790000000",
  "timestamp": 1703790000.0
}
```

---

### 10. NPC Info
**Get detailed info about an NPC**

```bash
curl http://127.0.0.1:11400/api/divineworld/npc/info/npc_alice_1703790000000
```

**Response:**
```json
{
  "status": "success",
  "agent_id": "npc_alice_1703790000000",
  "info": {
    "agent_id": "npc_alice_1703790000000",
    "agent_type": "npc",
    "health": 20.0,
    "hunger": 20.0,
    "emotions": {
      "joy": 0.5,
      "fear": 0.0,
      "anger": 0.0
    },
    "personality": {
      "openness": 0.6,
      "conscientiousness": 0.7
    },
    "memory_events": 42,
    "step_count": 125
  },
  "timestamp": 1703790000.0
}
```

---

## Root Endpoint (Documentation)

```bash
curl http://127.0.0.1:11400/
```

Returns complete API documentation including:
- All available endpoints
- Feature status
- Agent counts
- Storage locations
- Server configuration

---

## Health Checks

### Basic Health
```bash
curl http://127.0.0.1:11400/health
```

### Detailed Health
```bash
curl http://127.0.0.1:11400/health/detailed
```

---

## WebSocket Connection

Connect to: `ws://127.0.0.1:11400/ws/agent`

**Binary Protocol:**
- Magic bytes: `0x44574149` (DWAI)
- Used for high-performance video/image streaming
- Automatic fallback to JSON for text messages

**Example (JavaScript):**
```javascript
const ws = new WebSocket('ws://127.0.0.1:11400/ws/agent');

ws.onopen = () => {
  console.log('Connected to Divine World Backend');
};

ws.onmessage = (event) => {
  // Handle agent_speech, agent_action, etc.
  const data = JSON.parse(event.data);
  console.log('Agent message:', data);
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};
```

---

## Configuration

**File:** `py_backend/config.py`

### Paths
- **Data Directory:** `/home/devlord/divine-world-core/npc_applications/data/`
- **Brains Directory:** `/home/devlord/divine-world-core/npc_applications/data/brains/`
- **Uploads Directory:** `/home/devlord/divine-world-core/npc_applications/data/uploads/`

### Server
- **Backend Port:** 11400
- **Client JAR:** Auto-detected from `DWClientBot/build/libs/DWClientBot.jar`
- **Default Server:** `127.0.0.1:25565`
- **Client Memory:** 2048 MB

### Features
- ✅ Binary WebSocket Protocol
- ✅ Pattern Recognition
- ✅ Language Intelligence
- ✅ Multimodal Learning
- ✅ Continual Learning
- ✅ Request Validation
- ✅ Atomic Saves
- ✅ Divine World Integration
- ✅ God Entities
- ✅ NPC Management

---

## Troubleshooting

### Backend won't start
```bash
# Verify Python environment
source dw_env/bin/activate

# Check configuration
python3 -c "from config import Config; print(f'Port: {Config.BASE_BACKEND_PORT}')"

# Check syntax
python3 -m py_compile main.py
```

### Can't connect to WebSocket
- Ensure backend is running: `http://127.0.0.1:11400/health`
- Check CORS settings in main.py (should allow all origins)
- Verify firewall allows port 11400

### Agent spawn fails
- Check `/npc_applications/data/` directory exists
- Verify Client JAR path: `curl http://127.0.0.1:11400/ | grep client_jar`
- Check logs in backend console

### Memory errors
- Increase Client Memory: `DW_CLIENT_MEMORY=4096 python3 main.py`
- Check `Config.MAX_MEMORY_EVENTS` in config.py

---

## Development

### Adding New Divine World Commands

1. Add endpoint in `main.py`:
```python
@app.post("/api/divineworld/my_command")
async def divine_my_command(param: str = "default"):
    try:
        log.info(f"[Divine] My Command invoked (param: {param})")
        # ... implementation
        return {"status": "success", "command": "my_command", ...}
    except Exception as e:
        log.error(f"[Divine] My command failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

2. Update root endpoint documentation

3. Update this file with endpoint details

4. Test with curl before deployment

---

## Performance Notes

- **WebSocket FPS Limit:** 30 fps
- **WebSocket Max Latency:** 100 ms
- **Max Memory Events:** 10,000
- **Brain Auto-Save Interval:** 5 minutes
- **Brain Save Timeout:** 30 seconds

---

## Support

For issues or questions:
1. Check backend logs in console
2. Verify configuration: `curl http://127.0.0.1:11400/health/detailed`
3. Test individual endpoints with curl
4. Check agent memory: `curl http://127.0.0.1:11400/api/divineworld/npc/info/{agent_id}`
