# Divine World Agent - Quick Start Guide

## 🚀 30-Second Setup

### 1. Install UltimMC (One Time)
```bash
# Download from: https://github.com/UltimMC/Launcher/releases
# Place in: ~/UltimMC/ or ~/.ultimmc/
# Configure Minecraft 1.20.1 with Forge
```

### 2. Build Agents
```bash
cd /home/devlord/divine-world-core
chmod +x build_agents.sh
./build_agents.sh all
```

### 3. Run Agent
```bash
# Without Minecraft
./build/agents/dist/DW_Agent_alice --agent-id alice

# With Minecraft
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft
```

---

## 📋 Common Commands

### Build Operations
```bash
# Build specific agents
./build_agents.sh alice bob eve

# Build single agent
./build_agents.sh alice

# Build all agents
./build_agents.sh all
```

### Run Operations
```bash
# Basic run
./build/agents/dist/DW_Agent_alice --agent-id alice

# Run multiple agents (different ports)
./build/agents/dist/DW_Agent_alice --agent-id alice --port 8001 &
./build/agents/dist/DW_Agent_bob --agent-id bob --port 8002 &
./build/agents/dist/DW_Agent_eve --agent-id eve --port 8003 &

# Run with Minecraft
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft

# Run with custom UltimMC path
./build/agents/dist/DW_Agent_alice --agent-id alice \
  --minecraft \
  --ultimmc-path ~/UltimMC/ultimmc

# Stop all agents
pkill -f "DW_Agent_"
```

### Access Web UI
```
http://localhost:8001/   # Alice
http://localhost:8002/   # Bob  
http://localhost:8003/   # Eve
```

### Debugging
```bash
# Run with verbose logging
./build/agents/dist/DW_Agent_alice --agent-id alice --debug

# Check if port is in use
lsof -i :8001

# Monitor agent process
ps aux | grep DW_Agent

# View agent logs
tail -f ./data/logs/alice.log
```

---

## 🎮 UltimMC Setup Checklist

- [ ] Downloaded UltimMC from GitHub Releases
- [ ] Placed in `~/UltimMC/` or similar location
- [ ] Created Minecraft 1.20.1 game instance
- [ ] Installed Forge for that instance
- [ ] Closed UltimMC (agents manage it)
- [ ] Verified location with: `ls -la ~/UltimMC/`

**Still missing UltimMC?**
Check: `./build/agents/dist/ULTIMMC_SETUP_ALICE.txt`

---

## ⚙️ Configuration

### Ports (Default)
- Alice: 8001
- Bob: 8002
- Eve: 8003
- Default: 8001

### Edit Defaults
File: `py_backend/ai_core/config.py`
- `BASE_BACKEND_PORT` - Starting port
- `MINECRAFT_VERSION` - Game version
- `MINECRAFT_SERVER_HOST` - Server address

---

## 🐛 Troubleshooting

### "UltimMC not found"
- Install UltimMC (see 30-second setup #1)
- Or: `--ultimmc-path /path/to/ultimmc`

### Port already in use
```bash
# Kill process on port
lsof -i :8001 | grep LISTEN
kill -9 <PID>

# Or use different port
./build/agents/dist/DW_Agent_alice --agent-id alice --port 9001
```

### Agent crashes
```bash
# Run with debug output
./build/agents/dist/DW_Agent_alice --agent-id alice --debug

# Check logs
tail -f ./data/logs/alice.log

# Verify Python version (3.9+)
python3 --version
```

### Minecraft won't launch
- Check UltimMC installation
- Verify game instance exists in UltimMC
- Check Java is installed: `java -version`
- See: `./build/agents/dist/ULTIMMC_SETUP_ALICE.txt`

---

## 📚 Documentation

| Document | Purpose |
|----------|---------|
| [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) | Full deployment reference |
| [README_STANDALONE_AGENTS.md](./README_STANDALONE_AGENTS.md) | Build system details |
| [SYSTEM_ARCHITECTURE.md](./README/SYSTEM_ARCHITECTURE.md) | System design overview |

---

## 🔗 Useful Links

- **UltimMC Releases**: https://github.com/UltimMC/Launcher/releases
- **GitHub Issues**: Report bugs here
- **Project Repo**: https://github.com/divine-world-core

---

## 💡 Pro Tips

1. **Multiple agents**: Use different ports with `--port` flag
2. **Performance**: Run agents in background with `&`
3. **Monitoring**: Web UI shows real-time agent status
4. **Logs**: Check `./data/logs/` for detailed diagnostics
5. **Docker**: Use `docker-compose up -d` for containerized deployment

---

**Version**: 1.0.0 | **Updated**: 2024
