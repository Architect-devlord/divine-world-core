# Divine World API Reference

The Divine World backend provides a comprehensive REST and WebSocket API for controlling the simulation, managing agents, and interacting with the Minecraft world.

## Base URL
- **REST API**: `http://localhost:11400`
- **WebSocket**: `ws://localhost:11400/ws/agent`

---

## Agent Management Endpoints

### 1. Genesis Spawn
Spawns two default AI agents.
- **Endpoint**: `POST /api/genesis/spawn`
- **Response**: List of spawned agents.

### 2. Spawn NPC
Spawns a custom NPC.
- **Endpoint**: `POST /api/divineworld/npc/spawn`
- **Body**: `{"name": "Alice"}`

### 3. List Agents
Lists all active NPCs and God entities.
- **Endpoint**: `GET /api/divineworld/list_agents`

### 4. Remove NPC
Removes a specific NPC by ID.
- **Endpoint**: `POST /api/divineworld/npc/remove`
- **Body**: `{"agent_id": "npc_alice_..."}`

---

## God Entity Endpoints

### 1. Spawn God
Spawns a god-tier entity (Types: `oracle`, `wither`, `dragon`, `warden`, `creaking`).
- **Endpoint**: `POST /api/gods/spawn`
- **Body**: `{"god_type": "oracle"}`

### 2. God Ability
Activates a specific ability for a god entity.
- **Endpoint**: `POST /api/divineworld/god_ability`
- **Body**: `{"agent_id": "...", "ability": "summon_entities", "params": {...}}`

---

## System Control Endpoints

### 1. Divine Reset
Kills all agents and clears their memories.
- **Endpoint**: `POST /api/divineworld/divine_reset`

### 2. Clear Memories
Selectively clears agent memories.
- **Endpoint**: `POST /api/agents/clear_memories`
- **Body**: `{"target": "all"}` or `{"target": "agent_id"}`

### 3. Health Checks
- **Basic**: `GET /health`
- **Detailed**: `GET /health/detailed`

---

## WebSocket Protocol

Connect to `ws://localhost:11400/ws/agent` to receive real-time updates from agents.

### Message Format
The protocol supports both JSON and a high-performance binary format (magic bytes `0x44574149`).

**Sample Event (JSON):**
```json
{
  "type": "agent_speech",
  "agent_id": "alice",
  "text": "Hello, world!",
  "timestamp": 1703790000.0
}
```

---

## Mental Matrix API

Endpoints for interacting with the 3D mental simulation:
- `POST /mental-matrix/add-object/{agent_id}`
- `GET /mental-matrix/status/{agent_id}`
- `WS /mental-matrix/ws`
