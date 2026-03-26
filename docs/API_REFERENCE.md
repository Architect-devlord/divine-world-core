# Divine World API Reference (v3.0.0)

The Divine World management server provides a robust set of REST and WebSocket endpoints for controlling agents, god entities, and the simulation state.

## 🛠️ Base URLs

- **REST API**: `http://localhost:11400`
- **Control Centre (GUI)**: `http://localhost:11400/gui`
- **Management WebSocket (Logs/Agent Status)**: `ws://localhost:11400/ws/gui`
- **Agent WebSocket (Mod Communication)**: `ws://localhost:11400/ws/agent`

---

## 🧩 Agent Management

### 1. List Agents
Retrieve a list of running agents and available brain files.
- **Endpoint**: `GET /api/agents/list`
- **Returns**:
  ```json
  {
    "running": ["alice_1", "bob_1"],
    "available_brains": [{"agent_id": "alice_1", "brain_path": "...", "size_mb": 42}],
    "running_details": { ... }
  }
  ```

### 2. Spawn NPC
Spawn a new autonomous NPC agent.
- **Endpoint**: `POST /api/agents/spawn_single`
- **Body**:
  ```json
  {
    "agent_name": "Alice",
    "mode": "minecraft",
    "gender": "female",
    "server_addr": "127.0.0.1:25565",
    "personality": { "boldness": 0.8, ... }
  }
  ```

### 3. Start Agent
Start an existing agent process.
- **Endpoint**: `POST /api/agents/start`
- **Body**: `{"agent_id": "alice_1", "mode": "minecraft"}`

### 4. Stop Agent
Gracefully stop a running agent and save its brain.
- **Endpoint**: `POST /api/agents/{agent_id}/stop`

### 5. Package Agent
Trigger manual packaging of an agent into a portable `.exe`.
- **Endpoint**: `POST /api/agents/{agent_id}/package`

### 6. Cleanup Agent
Stop an agent and optionally delete its brain.
- **Endpoint**: `POST /api/agents/{agent_id}/cleanup?delete_brain=true`

---

## 👑 God Entities

### 1. Spawn God
Spawns a god-tier entity with specialized abilities.
- **Endpoint**: `POST /api/gods/spawn`
- **Body**:
  ```json
  {
    "god_type": "oracle",
    "custom_name": "Draconis",
    "server_addr": "127.0.0.1:25565"
  }
  ```
- **Valid Types**: `wither`, `warden`, `ender_dragon`, `oracle`, `creaking`, `elder_guardian`.

### 2. God Ability
Triggers a specific god ability.
- **Endpoint**: `POST /api/gods/ability`
- **Body**: `{"agent_id": "...", "ability": "summon_minions"}`

---

## 🧠 Brain Management (GUI-only)

These endpoints are used by the Control Centre to modify agent personalities and memories.

### 1. Get Brain Data
- **Endpoint**: `GET /api/agents/{agent_id}/brain`
- **Returns**: Complete brain capsule state (personality, memories, gender).

### 2. Update Personality
- **Endpoint**: `POST /api/agents/{agent_id}/brain/personality`
- **Body**: `{"traits": {"boldness": 0.9, "curiosity": 0.5}}`

### 3. Update Memories
- **Endpoint**: `POST /api/agents/{agent_id}/brain/memories`
- **Body**: `{"memories": [...]}`

### 4. Update Agent Config
- **Endpoint**: `POST /api/agents/{agent_id}/brain/config`
- **Body**: `{"agent_type": "npc", "gender": "male", "server_addr": "..."}`

---

## 🎮 Game Simulation & Events

### 1. Genesis Spawn
Initialize the world with the first agents (Adam & Eve).
- **Endpoint**: `POST /api/genesis/spawn`

### 2. Player/Agent Connect
Notifies the backend when an agent connects to the Minecraft server.
- **Endpoint**: `POST /api/player_event`
- **Body**: `{"agent_id": "...", "event": "connected", "agent_type": "npc"}`

### 3. Breeding Event
Triggers the breeding lifecycle between two agents.
- **Endpoint**: `POST /api/breeding/event`
- **Body**: `{"parent_a_id": "adam_1", "parent_b_id": "eve_1"}`

### 4. Divine Reset
Reset the entire simulation.
- **Endpoint**: `POST /api/divine_reset`
- **Body**: `{"agent_ids": ["..."]}`

---

## 🏥 Health & System

### 1. Health Checks
- `GET /health` (uptime, status)
- `GET /health/detailed` (CPU, memory, active agents)

### 2. Root API Info
- `GET /` (version and active agents overview)
