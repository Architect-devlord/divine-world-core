# Divine World Backend - Setup & Deployment Guide

## Overview

The Divine World Backend is a FastAPI-powered server that provides:

1. **REST API** for all Divine World Minecraft mod commands
2. **WebSocket** support for real-time agent communication  
3. **Agent Management** for spawning NPCs and god entities
4. **Memory Management** with persistent brain storage
5. **Binary Protocol** for high-performance video/image streaming

---

## Quick Start

### 1. Activate Environment & Start Backend

```bash
cd /home/devlord/divine-world-core/py_backend
./start_backend.sh
```

The backend will start on `http://127.0.0.1:11400`

### 2. Check Status

```bash
curl http://127.0.0.1:11400/
```

Should return complete API documentation with feature list.

### 3. Test API Endpoints

In another terminal:

```bash
cd /home/devlord/divine-world-core/py_backend
./test_divine_api.sh
```

---

## Configuration Files

### `config.py` - Central Configuration
- **Backend Port:** `11400`
- **Data Directory:** `/npc_applications/data/`
- **Brains Directory:** `/npc_applications/data/brains/`
- **Client JAR:** Auto-detects `DWClientBot/build/libs/DWClientBot.jar`
- **Default Server:** `127.0.0.1:25565`

### `main.py` - FastAPI Application
- **CORS:** Enabled for all origins (dev mode)
- **WebSocket:** Binary protocol with JSON fallback
- **Endpoints:** 20+ REST API endpoints
- **Authentication:** None (add as needed)

### `auto_packager.py` - Agent Packaging System
- **Auto-packaging:** Enabled by default
- **Brain wait time:** 30 seconds
- **Output directory:** `/npc_applications/`

---

## API Endpoints

### Divine World Commands (10 endpoints)

All commands mapped from Java `/commands/` to REST API:

| Command | Endpoint | Method |
|---------|----------|--------|
| Genesis | `/api/genesis/spawn` | POST |
| Divine Reset | `/api/divineworld/divine_reset` | POST |
| Clear Memories | `/api/agents/clear_memories` | POST |
| Spawn God | `/api/gods/spawn` | POST |
| God Ability | `/api/divineworld/god_ability` | POST |
| God Transform | `/api/divineworld/god_transform` | POST |
| List Agents | `/api/divineworld/list_agents` | GET |
| Spawn NPC | `/api/divineworld/npc/spawn` | POST |
| Remove NPC | `/api/divineworld/npc/remove` | POST |
| NPC Info | `/api/divineworld/npc/info/{id}` | GET |

### Health & Diagnostic (3 endpoints)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Quick health check |
| `/health/detailed` | GET | Full system status |
| `/` | GET | API documentation |

### Other Endpoints (7+ endpoints)

- `/ws/agent` - WebSocket for real-time communication
- `/api/agents/{id}/audio/*` - Audio capture/streaming
- `/api/agents/{id}/status` - Agent status
- `/api/agents/{id}/patterns` - Pattern recognition
- `/api/chat` - Chat messaging
- `/api/upload` - File uploads
- `/api/agents/{id}/save` - Brain saving

---

## Files Structure

```
py_backend/
├── main.py                          # 🔴 Core FastAPI application
├── config.py                        # 🔴 Configuration management  
├── auto_packager.py                 # Agent auto-packaging system
├── communication_protocol.py         # Binary/WebSocket protocol
├── start_backend.sh                 # 🟢 Startup script (NEW)
├── test_divine_api.sh              # 🟢 API test script (NEW)
├── DIVINE_WORLD_API.md             # 🟢 API documentation (NEW)
├── SETUP_GUIDE.md                  # 🟢 This file
├── ai_core/                        # AI agent implementation
│   ├── agent.py                    # NPCAgent class
│   ├── brain_core.py               # Brain implementation
│   ├── agent_spawner.py            # Agent spawning
│   ├── memory.py                   # Memory systems
│   ├── emotion.py                  # Emotion system
│   ├── personality.py              # Personality traits
│   └── ...
├── dw_env/                         # Virtual environment (venv)
├── utils/                          # Utilities
├── tests/                          # Test files
└── requirements.txt                # Python dependencies
```

**Legend:** 🔴 = Updated  |  🟢 = New

---

## Environment Variables

Set before running `start_backend.sh`:

```bash
export DW_BACKEND_PORT=11400              # Backend port (default: 11400)
export DW_CLIENT_MEMORY=2048              # Client RAM in MB (default: 2048)
export DW_LOG_LEVEL=INFO                  # Log level (default: INFO)
export DW_SERVER=127.0.0.1:25565         # Minecraft server (default)
export DW_CLIENT_JAR=/path/to/jar        # Client JAR path (auto-detected)
```

Example:
```bash
DW_BACKEND_PORT=11400 DW_CLIENT_MEMORY=4096 ./start_backend.sh
```

---

## Root Endpoint (`GET /`)

Returns JSON with:

```json
{
  "status": "online",
  "service": "Divine World Backend",
  "version": "2.1.0",
  "agents": {
    "spawned": 0,
    "connected": 0,
    "demo": 0,
    "websockets": 0
  },
  "endpoints": {
    "websocket": {...},
    "chat": {...},
    "audio": {...},
    "divineworld": {...}
  },
  "features": {
    "binary_websocket": true,
    "divine_world_integration": true,
    "god_entities": true,
    "npc_management": true
  },
  "divine_world_info": {
    "mod_id": "divineworld",
    "mod_version": "1.20.1",
    "available_god_types": ["oracle", "wither", "dragon", "warden", "creaking"],
    "available_mobs": ["player", "villager", ...]
  },
  "storage": {
    "data_dir": "/npc_applications/data/",
    "brains_dir": "/npc_applications/data/brains/",
    ...
  },
  "timestamp": 1703790000.0
}
```

---

## Divine World API Examples

### Example 1: Spawn Genesis Agents

```bash
curl -X POST http://127.0.0.1:11400/api/genesis/spawn
```

**Response:**
```json
{
  "status": "success",
  "command": "genesis",
  "agents": [
    {"agent_id": "genesis_1", "status": "spawning", "type": "npc"},
    {"agent_id": "genesis_2", "status": "spawning", "type": "npc"}
  ],
  "message": "Genesis spawned 2 agents",
  "timestamp": 1703790000.0
}
```

### Example 2: Spawn Oracle God

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

### Example 3: List All Agents

```bash
curl http://127.0.0.1:11400/api/divineworld/list_agents | jq .
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

### Example 4: Get NPC Details

```bash
curl http://127.0.0.1:11400/api/divineworld/npc/info/genesis_1 | jq .
```

---

## Storage Structure

Data stored in `/npc_applications/data/`:

```
data/
├── brains/                  # Agent brain files (PCAP format)
│   ├── genesis_1/
│   │   └── brain.pcap      # Serialized brain state
│   ├── npc_alice_123456/
│   │   └── brain.pcap
│   └── god_oracle_789456/
│       └── brain.pcap
├── uploads/                 # File uploads per agent
│   ├── genesis_1/
│   └── npc_alice_123456/
├── agents/                  # Agent metadata
├── demos/                   # Demo agent data
├── teaching_materials/      # Learning resources
└── logs/                    # Application logs
```

---

## Starting the Backend

### Method 1: Using Startup Script (Recommended)

```bash
cd /home/devlord/divine-world-core/py_backend
./start_backend.sh
```

Features:
- ✅ Checks virtual environment
- ✅ Activates environment
- ✅ Verifies dependencies
- ✅ Validates configuration
- ✅ Shows startup info with all URLs
- ✅ Starts server with proper settings

### Method 2: Manual Startup

```bash
cd /home/devlord/divine-world-core/py_backend
source dw_env/bin/activate
python3 main.py
```

### Method 3: With Custom Port

```bash
cd /home/devlord/divine-world-core/py_backend
DW_BACKEND_PORT=8080 ./start_backend.sh
```

---

## Testing

### Run Full Test Suite

```bash
./test_divine_api.sh
```

Tests all 10 Divine World endpoints + health checks.

### Manual Test with curl

```bash
# Health check
curl http://127.0.0.1:11400/health

# List agents
curl http://127.0.0.1:11400/api/divineworld/list_agents

# Spawn NPC
curl -X POST http://127.0.0.1:11400/api/divineworld/npc/spawn \
  -H "Content-Type: application/json" \
  -d '{"name": "TestNPC"}'
```

### Test WebSocket Connection

Using `websocat` (if installed):
```bash
websocat ws://127.0.0.1:11400/ws/agent
```

Or with `wscat` (npm):
```bash
npm install -g wscat
wscat -c ws://127.0.0.1:11400/ws/agent
```

---

## Debugging

### Check Configuration

```bash
python3 -c "
from config import Config
print(f'Port: {Config.BASE_BACKEND_PORT}')
print(f'Data: {Config.DATA_DIR}')
print(f'JAR: {Config.CLIENT_JAR}')
print(f'Server: {Config.DEFAULT_SERVER}')
"
```

### Check Backend Health

```bash
curl http://127.0.0.1:11400/health/detailed | jq .
```

### View Backend Logs

Keep terminal with backend running, logs appear in real-time:

```
[2024-12-28 19:30:00] INFO - dw_backend - Enhanced Agent Manager initialized
[2024-12-28 19:30:01] INFO - uvicorn.access - GET / 200 OK
[2024-12-28 19:30:02] INFO - dw_backend - [Divine] Genesis invoked by console
```

### Test Individual Endpoint

```bash
# Test genesis
curl -v http://127.0.0.1:11400/api/genesis/spawn

# Test with parameters
curl -v -X POST http://127.0.0.1:11400/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{"god_type":"wither"}' \
  2>&1 | grep -A 20 "< HTTP"
```

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'torch'"

**Solution:**
```bash
source dw_env/bin/activate
pip install torch torchvision
```

### Issue: "Address already in use" on port 11400

**Solution:** 
```bash
# Find process using port 11400
lsof -i :11400

# Kill it
kill -9 <PID>

# Or use different port
DW_BACKEND_PORT=11401 ./start_backend.sh
```

### Issue: WebSocket connection fails

**Check:**
1. Backend is running: `curl http://127.0.0.1:11400/health`
2. Correct URL: `ws://127.0.0.1:11400/ws/agent`
3. Firewall allows port 11400
4. CORS is enabled (it is by default)

### Issue: Agent spawn fails

**Check:**
1. Client JAR exists: `curl http://127.0.0.1:11400/ | grep client_jar`
2. Data directory exists: `ls -la /npc_applications/data/`
3. Minecraft server running: `ping 127.0.0.1:25565`
4. Backend logs for errors

### Issue: Memory errors

**Solution:**
```bash
# Increase client memory
DW_CLIENT_MEMORY=4096 ./start_backend.sh

# Check config limits
python3 -c "from config import Config; print(f'Max Memory Events: {Config.MAX_MEMORY_EVENTS}')"
```

---

## Production Deployment

### Docker (Recommended)

See `Dockerfile` for containerization.

```bash
docker build -t divine-world-backend .
docker run -p 11400:11400 divine-world-backend
```

### PM2 Process Manager

```bash
npm install -g pm2
pm2 start "cd /path/to/py_backend && ./start_backend.sh" --name divine-backend
pm2 save
pm2 startup
```

### Systemd Service

Create `/etc/systemd/system/divine-backend.service`:

```ini
[Unit]
Description=Divine World Backend
After=network.target

[Service]
Type=simple
User=devlord
WorkingDirectory=/home/devlord/divine-world-core/py_backend
ExecStart=/home/devlord/divine-world-core/py_backend/start_backend.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable divine-backend
sudo systemctl start divine-backend
```

---

## Documentation Files

- **`DIVINE_WORLD_API.md`** - Complete REST API reference
- **`SETUP_GUIDE.md`** - This file
- **`start_backend.sh`** - Startup script with dependency checks
- **`test_divine_api.sh`** - Automated API test suite

---

## Summary

✅ **Root endpoint updated** with Divine World documentation  
✅ **10 Divine World API endpoints** added to main.py  
✅ **Configuration verified** with all paths resolved  
✅ **Startup script** for easy launching  
✅ **Test script** for API validation  
✅ **Documentation** for all features  

**To start:**
```bash
cd /home/devlord/divine-world-core/py_backend
./start_backend.sh
```

**In another terminal:**
```bash
./test_divine_api.sh
```

**Access API at:** `http://127.0.0.1:11400`
