# 🚀 Divine World Backend - Quick Reference

## Start Backend

```bash
cd py_backend
./start_backend.sh
```

Backend runs on: `http://127.0.0.1:11400`

---

## Test All Endpoints

```bash
cd py_backend
./test_divine_api.sh
```

---

## API Examples

### Genesis (Spawn 2 Agents)
```bash
curl -X POST http://127.0.0.1:11400/api/genesis/spawn
```

### Spawn God
```bash
curl -X POST http://127.0.0.1:11400/api/gods/spawn \
  -H "Content-Type: application/json" \
  -d '{"god_type":"oracle"}'
```

### List All Agents
```bash
curl http://127.0.0.1:11400/api/divineworld/list_agents
```

### Spawn NPC
```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/npc/spawn \
  -H "Content-Type: application/json" \
  -d '{"name":"Alice"}'
```

### Get NPC Info
```bash
curl http://127.0.0.1:11400/api/divineworld/npc/info/npc_alice_123456
```

### Clear Memories
```bash
curl -X POST http://127.0.0.1:11400/api/agents/clear_memories \
  -H "Content-Type: application/json" \
  -d '{"target":"all"}'
```

### Divine Reset (Kill All)
```bash
curl -X POST http://127.0.0.1:11400/api/divineworld/divine_reset
```

---

## Endpoints (10 Divine World Commands)

| Command | URL | Method |
|---------|-----|--------|
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

---

## God Types
`oracle`, `wither`, `dragon`, `warden`, `creaking`

## Available Mobs
`player`, `villager`, `pig`, `cow`, `zombie`, `skeleton`, `wither`, `dragon`

---

## Health Checks

```bash
curl http://127.0.0.1:11400/health
curl http://127.0.0.1:11400/health/detailed
```

---

## Configuration

**File:** `py_backend/config.py`

| Setting | Value |
|---------|-------|
| Port | 11400 |
| Data Dir | `/npc_applications/data/` |
| Brains Dir | `/npc_applications/data/brains/` |
| Server | `127.0.0.1:25565` |
| Client JAR | Auto-detected |
| Client Memory | 2048 MB |

---

## Documentation

- **`DIVINE_WORLD_API.md`** - Full API reference
- **`SETUP_GUIDE.md`** - Comprehensive setup guide
- **`DIVINE_WORLD_SETUP_COMPLETE.md`** - Summary of changes

---

## Environment Variables

```bash
DW_BACKEND_PORT=11400              # Backend port
DW_CLIENT_MEMORY=2048              # Client RAM (MB)
DW_LOG_LEVEL=INFO                  # Log level
DW_SERVER=127.0.0.1:25565         # Minecraft server
```

---

## Files Updated

✅ `main.py` - Root endpoint + 13 Divine World endpoints  
✅ `config.py` - Verified all paths resolve  
✅ `start_backend.sh` - Startup script (NEW)  
✅ `test_divine_api.sh` - Test suite (NEW)  
✅ `DIVINE_WORLD_API.md` - API docs (NEW)  
✅ `SETUP_GUIDE.md` - Setup guide (NEW)  

---

## Status

✅ All endpoints functional  
✅ Configuration verified  
✅ Scripts tested and executable  
✅ Documentation complete  

**Ready to deploy!** 🚀
