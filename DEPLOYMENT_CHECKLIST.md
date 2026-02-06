## ✅ Pre-Deployment Checklist

Use this checklist before deploying Divine World agents to production.

---

### System Requirements
- [ ] **OS**: Linux, macOS, or Windows (WSL2)
- [ ] **Python**: 3.13 installed (verify: `python3 --version`)
- [ ] **Java**: Installed for Minecraft (verify: `java -version`)
- [ ] **Disk Space**: 10GB+ available
- [ ] **RAM**: 8GB+ for development, 16GB+ for production

---

### Verification Checks

#### Pre-Build Verification
- [ ] Run system check: `./production_ready_check.sh`
  - Should show: "System is PRODUCTION READY"
- [ ] Verify build setup: `./verify_standalone_setup.sh`
  - Should show: "All checks passed ✅"
- [ ] Check AI Core modules exist:
  ```bash
  ls -la py_backend/ai_core/{config.py,communication_protocol.py,validation.py,agent_standalone.py}
  ```
  - All 4 files should exist

#### Code Quality
- [ ] Python syntax valid:
  ```bash
  python3 -m py_compile py_backend/ai_core/agent_standalone.py
  python3 -m py_compile py_backend/main.py
  ```
- [ ] Build script valid:
  ```bash
  bash -n build_agents.sh
  ```
- [ ] No uncommitted changes in critical files:
  ```bash
  git status py_backend/ai_core/
  git status build_agents.sh
  ```

#### Dependencies
- [ ] PyInstaller installed: `pip show pyinstaller`
- [ ] FastAPI installed: `pip show fastapi`
- [ ] Uvicorn installed: `pip show uvicorn`
- [ ] PyTorch installed: `pip show torch` (optional)

#### Assets Ready
- [ ] Frontend built:
  ```bash
  ls -lh dw_agent/electron/react-app/dist/
  ```
  - Should contain index.html and assets
- [ ] DivineWorld mod built:
  ```bash
  ls -lh DivineWorld/build/libs/*.jar
  ```
- [ ] DWClientBot mod built:
  ```bash
  ls -lh DWClientBot/build/libs/*.jar
  ```

#### Minecraft Integration (Optional)
- [ ] UltimMC detected (if Minecraft support needed):
  ```bash
  find ~/ -name "ultimmc" -o -name "UltimMC*" 2>/dev/null
  ```
  - At least one result expected, or
  - Plan to download and install
- [ ] Java version compatible:
  ```bash
  java -version 2>&1 | grep version
  ```
  - Java 8+ required

---

### Build Process

#### Single Agent Build Test (Recommended First)
```bash
cd /home/devlord/divine-world-core

# Test with one agent first
./build_agents.sh alice

# Verify executable created
ls -lh build/agents/dist/DW_Agent_alice
```
- [ ] Build completes without errors
- [ ] Executable is ~150-300MB
- [ ] Build time: 5-15 minutes (first time)

#### Full Build
```bash
# Build all agents
./build_agents.sh all

# Or specific agents
./build_agents.sh alice bob eve
```
- [ ] All builds complete
- [ ] All executables created
- [ ] No error messages

#### Post-Build Verification
```bash
# List executables
ls -lh build/agents/dist/DW_Agent_*

# Verify sizes
du -sh build/agents/dist/

# Check for data bundling
find build/agents/dist/ -type f | head -20
```
- [ ] All expected executables exist
- [ ] Executables are > 100MB (indicates bundling)
- [ ] Data files bundled (frontend, mods, guides)

---

### Pre-Launch Verification

#### Port Availability
```bash
# Check if default ports are available
netstat -tuln | grep -E ":8001|:8002|:8003"
```
- [ ] Ports 8001-8003 available
- [ ] Or plan to use different ports with `--port` flag

#### Configuration Ready
- [ ] config.py settings reviewed
- [ ] Ports configured correctly
- [ ] Minecraft settings appropriate
- [ ] Logging paths writable

#### Directory Structure
```bash
# Verify required directories
ls -ld data/brains data/logs build/agents/dist
```
- [ ] All directories exist
- [ ] Permissions allow writing

---

### Launch & Runtime

#### Initial Launch Test
```bash
# Start agent with debug logging
./build/agents/dist/DW_Agent_alice --agent-id alice --debug &

# Give it 5-10 seconds to start
sleep 10

# Check if running
ps aux | grep DW_Agent_alice
```
- [ ] Process starts without error
- [ ] Process appears in ps output
- [ ] No crash messages in logs

#### API Connectivity
```bash
# Test health endpoint
curl -s http://localhost:8001/health | jq .

# Test WebSocket connection
python3 << 'EOF'
import asyncio
import aiohttp

async def test_websocket():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect('ws://localhost:8001/ws') as ws:
                print("✅ WebSocket connected successfully")
                await ws.close()
    except Exception as e:
        print(f"❌ WebSocket failed: {e}")

asyncio.run(test_websocket())
EOF
```
- [ ] Health endpoint responds
- [ ] WebSocket connection succeeds

#### Web UI Access
```bash
# Open browser to:
# http://localhost:8001
```
- [ ] Page loads without errors
- [ ] Can see agent dashboard
- [ ] React frontend functional

#### Minecraft Integration Test (Optional)
```bash
# Start agent with Minecraft
./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft &

# Wait 30 seconds for Minecraft to launch
sleep 30

# Check if Minecraft process started
ps aux | grep -i minecraft | grep -v grep
```
- [ ] UltimMC detects successfully
- [ ] Minecraft client launches
- [ ] No connection errors

#### Multi-Agent Test
```bash
# Start multiple agents on different ports
./build/agents/dist/DW_Agent_alice --agent-id alice --port 8001 &
./build/agents/dist/DW_Agent_bob --agent-id bob --port 8002 &
./build/agents/dist/DW_Agent_eve --agent-id eve --port 8003 &

# Wait 10 seconds
sleep 10

# Verify all running
ps aux | grep "DW_Agent_" | grep -v grep

# Test all endpoints
curl -s http://localhost:8001/health
curl -s http://localhost:8002/health
curl -s http://localhost:8003/health
```
- [ ] All agents start
- [ ] All ports respond
- [ ] No port conflicts
- [ ] Each maintains separate state

#### Cleanup
```bash
# Stop all test agents
pkill -f "DW_Agent_"

# Wait for clean shutdown
sleep 5

# Verify stopped
ps aux | grep DW_Agent | grep -v grep
```
- [ ] All agents stop cleanly
- [ ] No lingering processes

---

### Logging & Monitoring

#### Logs Verified
```bash
# Check logs exist and are readable
ls -lh data/logs/

# View recent log entries
tail -20 data/logs/alice.log
```
- [ ] Log files created
- [ ] Log files contain expected data
- [ ] No error flooding

#### Performance Check
```bash
# Monitor resource usage while running
top -p $(pgrep -f "DW_Agent_alice")

# Or use
watch -n 1 'ps aux | grep DW_Agent_alice'
```
- [ ] CPU usage reasonable (<50% at idle)
- [ ] Memory stable (<500MB)
- [ ] No continuous growth

---

### Documentation Review

#### User Documentation
- [ ] QUICK_START.md reviewed
- [ ] DEPLOYMENT_GUIDE.md reviewed
- [ ] All links and references work
- [ ] Instructions are clear

#### Technical Documentation
- [ ] README_STANDALONE_AGENTS.md current
- [ ] SYSTEM_ARCHITECTURE.md available
- [ ] API documentation accessible
- [ ] Troubleshooting guide complete

---

### Security Review

#### Network Security
- [ ] Firewall configured (if applicable)
- [ ] Only needed ports exposed
- [ ] HTTPS/WSS in production (if needed)
- [ ] No hardcoded credentials in code

#### Data Security
- [ ] Logs don't contain sensitive data
- [ ] Brain files have appropriate permissions
- [ ] Configuration files not world-readable
- [ ] No secrets in git history

#### Access Control
- [ ] Only authorized users can run agents
- [ ] Proper file permissions set
- [ ] API authentication configured (if needed)
- [ ] Logging enabled for audit trail

---

### Backup & Recovery

#### Backups Created
- [ ] Brain data backed up:
  ```bash
  tar -czf backup_brains_$(date +%Y%m%d).tar.gz data/brains/
  ```
- [ ] Configuration backed up:
  ```bash
  tar -czf backup_config_$(date +%Y%m%d).tar.gz py_backend/ai_core/config.py
  ```
- [ ] Logs archived:
  ```bash
  tar -czf backup_logs_$(date +%Y%m%d).tar.gz data/logs/
  ```
- [ ] Backups stored securely

#### Recovery Plan
- [ ] Recovery procedures documented
- [ ] Backup restoration tested
- [ ] RTO/RPO defined
- [ ] Disaster recovery plan in place

---

### Production Deployment

#### Final Pre-Deploy Checklist
- [ ] All above items checked ✅
- [ ] Test environment matches production
- [ ] Load tested (if applicable)
- [ ] Capacity planning done
- [ ] Monitoring configured
- [ ] Alerting configured
- [ ] Runbooks prepared
- [ ] Team trained

#### Deployment Steps
1. [ ] Review all checklist items one final time
2. [ ] Create deployment backup
3. [ ] Stop staging/test agents if running
4. [ ] Deploy to production
5. [ ] Verify all agents start
6. [ ] Monitor first 30 minutes
7. [ ] Verify web UIs accessible
8. [ ] Check logs for errors
9. [ ] Confirm backups functional
10. [ ] Document deployment details

#### Post-Deployment
- [ ] All systems online
- [ ] Performance meets expectations
- [ ] No errors in logs
- [ ] Team notified
- [ ] Monitoring alerts active
- [ ] Schedule first check-in

---

### Troubleshooting Quick Links

If deployment fails:

| Issue | Solution |
|-------|----------|
| Port in use | Use `--port` flag |
| UltimMC not found | See [UltimMC Setup](DEPLOYMENT_GUIDE.md#ultimmc-setup) |
| Agent won't start | Check logs: `tail -f data/logs/*.log` |
| Frontend not loading | Verify http://localhost:8001 in browser |
| WebSocket errors | Run `production_ready_check.sh` |
| Memory issues | Monitor with `top` and check resource limits |
| Build errors | Verify Python version: `python3 --version` |

---

### Sign-Off

```
Deployment Date: _______________
Deployed By: ____________________
Verified By: _____________________
Production Status: ✅ READY / ⚠️ ISSUES / ❌ NOT READY

Notes:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

---

**Remember**: This checklist ensures a smooth, production-ready deployment. Keep this document updated as new requirements emerge.

**Version**: 1.0.0 | **Last Updated**: 2024
