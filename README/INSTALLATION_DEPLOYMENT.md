# Installation & Deployment Guide

## Pre-requisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+)
- **Java**: JDK 17 or higher
- **Python**: 3.9 or higher
- **Memory**: 4GB minimum (8GB recommended for 2+ agents)
- **Disk**: 10GB minimum (1GB per Minecraft instance)
- **Network**: Local network for Minecraft server

### Check Your System

```bash
# Check Java version
java -version
# Must be 17 or higher

# Check Python version
python3 --version
# Must be 3.9 or higher

# Check available disk space
df -h
# Need at least 10GB free

# Check available memory
free -h
# Need at least 4GB for agents
```

---

## Installation Steps

### Step 1: Install UltimMC (One-Time Setup)

#### Option A: Build from Source (Recommended)

```bash
# Clone repository
git clone https://github.com/UltimMC/Launcher
cd Launcher

# Build the launcher
./gradlew build

# Install to user bin
mkdir -p ~/.local/bin
cp build/distributions/UltimMC ~/.local/bin/ultimmc
chmod +x ~/.local/bin/ultimmc

# Add to PATH if not already there
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc
source ~/.bashrc

# Verify installation
ultimmc --version
which ultimmc
```

#### Option B: Pre-built Binary (Faster)

```bash
# Download latest release
cd /tmp
wget https://github.com/UltimMC/Launcher/releases/download/v1.0/UltimMC-linux.tar.gz

# Extract
tar -xzf UltimMC-linux.tar.gz

# Install
mkdir -p ~/.local/bin
cp UltimMC ~/.local/bin/ultimmc
chmod +x ~/.local/bin/ultimmc

# Verify
ultimmc --version
```

#### Option C: Docker (If Preferred)

```bash
# Use Docker image
docker pull ultimmc/launcher:latest

# Alias for convenience
alias ultimmc='docker run -v ~/.ultimmc:/root/.ultimmc ultimmc/launcher:latest'

# Verify
ultimmc --version
```

### Step 2: Build Divine World Mods (One-Time Setup)

```bash
cd /home/devlord/divine-world-core

# Build DWClientBot
cd DWClientBot
./gradlew clean build
cd ..

# Build DivineWorld
cd DivineWorld
./gradlew clean build
cd ..

# Verify JAR files exist
ls -lh DWClientBot/build/libs/DWClientBot.jar
ls -lh DivineWorld/build/libs/DivineWorld-1.0.0.jar
```

### Step 3: Setup Python Environment

```bash
cd /home/devlord/divine-world-core/py_backend

# Create virtual environment (if not already created)
python3 -m venv dw_env

# Activate environment
source dw_env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify key packages
pip list | grep -E "fastapi|uvicorn|numpy"
```

### Step 4: Configure Divine World Backend

```bash
cd /home/devlord/divine-world-core

# Set environment variables (add to ~/.bashrc for persistence)
export DW_USE_ULTIMMC=true
export DW_MINECRAFT_VERSION=1.20.1
export DW_FORGE_VERSION=47.3.0
export DW_SERVER=127.0.0.1:25565
export DW_CLIENT_MEMORY=2048
export DW_BACKEND_PORT=11400

# Optional: specify paths explicitly if auto-detection fails
# export DW_CLIENT_JAR=/path/to/DWClientBot.jar
# export DW_MOD_JAR=/path/to/DivineWorld-1.0.0.jar
# export DW_ULTIMMC_PATH=/path/to/ultimmc

# Save to bashrc for persistence
cat >> ~/.bashrc << 'EOF'
# Divine World Configuration
export DW_USE_ULTIMMC=true
export DW_MINECRAFT_VERSION=1.20.1
export DW_FORGE_VERSION=47.3.0
export DW_SERVER=127.0.0.1:25565
export DW_CLIENT_MEMORY=2048
export DW_BACKEND_PORT=11400
EOF

# Reload bashrc
source ~/.bashrc
```

### Step 5: Verify Installation

```bash
cd /home/devlord/divine-world-core

# Check UltimMC
echo "UltimMC location: $(which ultimmc)"
ultimmc --version

# Check mods
echo "DWClientBot: $(ls -lh DWClientBot/build/libs/DWClientBot.jar | awk '{print $5, $9}')"
echo "DivineWorld: $(ls -lh DivineWorld/build/libs/DivineWorld-1.0.0.jar | awk '{print $5, $9}')"

# Check Python setup
source py_backend/dw_env/bin/activate
python -c "import fastapi; import uvicorn; print('✅ Python dependencies OK')"

# Check syntax of key files
python -m py_compile py_backend/minecraft_launcher.py
python -m py_compile py_backend/ai_core/agent_spawner.py
python -m py_compile py_backend/auto_packager.py
echo "✅ All syntax checks passed"
```

Expected output:
```
UltimMC location: /home/devlord/.local/bin/ultimmc
DWClientBot: 2.3M DWClientBot/build/libs/DWClientBot.jar
DivineWorld: 1.8M DivineWorld/build/libs/DivineWorld-1.0.0.jar
✅ Python dependencies OK
✅ All syntax checks passed
```

---

## Running the Backend

### Quick Start (Development)

```bash
cd /home/devlord/divine-world-core

# Activate Python environment
source py_backend/dw_env/bin/activate

# Start backend
cd py_backend
python main.py

# Should see:
# INFO: Started server process [PID]
# INFO: Waiting for application startup
# INFO: Application startup complete
# INFO: Uvicorn running on http://127.0.0.1:11400
```

### Production Deployment

#### Option A: Systemd Service

```bash
# Create service file
sudo tee /etc/systemd/system/divine-world-backend.service > /dev/null << EOF
[Unit]
Description=Divine World Backend
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/home/devlord/divine-world-core/py_backend
Environment="PATH=/home/devlord/divine-world-core/py_backend/dw_env/bin"
Environment="DW_USE_ULTIMMC=true"
Environment="DW_SERVER=127.0.0.1:25565"
Environment="DW_BACKEND_PORT=11400"
ExecStart=/home/devlord/divine-world-core/py_backend/dw_env/bin/python main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable divine-world-backend
sudo systemctl start divine-world-backend

# Check status
sudo systemctl status divine-world-backend

# View logs
sudo journalctl -u divine-world-backend -f
```

#### Option B: Screen/Tmux

```bash
# Using screen
screen -S divine-world

# Inside screen session
cd /home/devlord/divine-world-core/py_backend
source dw_env/bin/activate
python main.py

# Detach: Ctrl+A then D
# Reattach: screen -r divine-world
```

#### Option C: Docker

Create `Dockerfile`:
```dockerfile
FROM python:3.9

# Install Java
RUN apt-get update && apt-get install -y openjdk-17-jdk

# Install UltimMC (simplified)
RUN curl -L https://github.com/UltimMC/Launcher/releases/download/v1.0/UltimMC \
    -o /usr/local/bin/ultimmc && chmod +x /usr/local/bin/ultimmc

# Copy Divine World
COPY . /app
WORKDIR /app/py_backend

# Setup Python
RUN python -m venv dw_env && \
    ./dw_env/bin/pip install -r requirements.txt

# Expose port
EXPOSE 11400

# Run backend
CMD ["./dw_env/bin/python", "main.py"]
```

Build and run:
```bash
docker build -t divine-world:latest .
docker run -p 11400:11400 -v ~/.ultimmc:/root/.ultimmc divine-world:latest
```

---

## Spawning Agents

### Basic Spawn

```bash
# In new terminal (keep backend running)
curl -X POST "http://127.0.0.1:11400/api/genesis/spawn"

# Response:
# {"status": "spawning", "agents": ["adam", "eve"]}
```

### Monitor Spawn Progress

```bash
# Check agent status every 10 seconds
watch -n 10 'curl -s http://127.0.0.1:11400/agents | jq ".agents | keys"'

# Or manual check
curl http://127.0.0.1:11400/agents | jq
```

### Custom Spawn Configuration

```bash
# Create config file
cat > spawn_config.json << 'EOF'
{
  "agents": ["alice", "bob", "charlie"],
  "server": "mc.example.com:25565",
  "memory_mb": 4096
}
EOF

# Use config (if API supports it)
curl -X POST "http://127.0.0.1:11400/api/spawn/custom" \
  -H "Content-Type: application/json" \
  -d @spawn_config.json
```

---

## Troubleshooting Installation

### Issue: UltimMC not found after installation

**Symptoms:** `ERROR: UltimMC not found`

**Solutions:**
```bash
# Check if installed
which ultimmc

# If not found, verify path
ls -lh ~/.local/bin/ultimmc

# Add to PATH if needed
export PATH="$PATH:$HOME/.local/bin"
echo 'export PATH="$PATH:$HOME/.local/bin"' >> ~/.bashrc

# Or set explicit path
export DW_ULTIMMC_PATH=$HOME/.local/bin/ultimmc
```

### Issue: Mods not found

**Symptoms:** `ERROR: Failed to install DWClientBot mod`

**Solutions:**
```bash
# Rebuild mods
cd /home/devlord/divine-world-core/DWClientBot
./gradlew clean build

cd ../DivineWorld
./gradlew clean build

# Verify JAR files
ls -lh */build/libs/*.jar

# Or set paths explicitly
export DW_CLIENT_JAR=/full/path/to/DWClientBot.jar
export DW_MOD_JAR=/full/path/to/DivineWorld-1.0.0.jar
```

### Issue: Backend won't start

**Symptoms:** `Address already in use` or `ModuleNotFoundError`

**Solutions:**
```bash
# Kill existing process on port
lsof -ti:11400 | xargs kill -9

# Or use different port
export DW_BACKEND_PORT=11401

# Check Python environment
source py_backend/dw_env/bin/activate
python -c "import fastapi"

# Reinstall dependencies if needed
pip install -r requirements.txt --force-reinstall
```

### Issue: Agents spawn but don't appear in Minecraft

**Checklist:**
1. Is Minecraft server running separately?
   ```bash
   ps aux | grep "minecraft" | grep -v grep
   ```

2. Check backend logs for errors
   ```bash
   tail -f ~/.divine-world/backend.log 2>/dev/null || \
   tail -f /tmp/divine-world.log
   ```

3. Check system properties were passed
   ```bash
   ps aux | grep "dw.agentId"
   ```

4. Verify mods are in instance
   ```bash
   ls ~/.ultimmc/instances/agent_adam/mods/
   ```

5. Try with verbose logging
   ```bash
   export DW_LOG_LEVEL=DEBUG
   python main.py
   ```

---

## Monitoring & Maintenance

### Check Backend Health

```bash
# Health check endpoint
curl http://127.0.0.1:11400/health

# List all agents
curl http://127.0.0.1:11400/agents | jq

# Get specific agent
curl http://127.0.0.1:11400/agents/adam | jq
```

### Clean Up

```bash
# Remove all Minecraft instances (careful!)
rm -rf ~/.ultimmc/instances/

# Remove all agent brains
rm -rf /home/devlord/divine-world-core/npc_applications/data/brains/

# Clean build artifacts
cd /home/devlord/divine-world-core
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete

# Clean Gradle cache (if needed)
cd DWClientBot && ./gradlew clean && cd ..
cd DivineWorld && ./gradlew clean && cd ..
```

### Backup Agent Data

```bash
# Backup brains
tar -czf divine-world-brains-$(date +%Y%m%d).tar.gz \
  /home/devlord/divine-world-core/npc_applications/data/brains/

# Backup instances
tar -czf divine-world-instances-$(date +%Y%m%d).tar.gz \
  ~/.ultimmc/instances/

# Copy to remote storage
scp divine-world-brains-*.tar.gz user@backup-server:/backups/
```

---

## Performance Tuning

### Memory Allocation

```bash
# Default: 2GB per agent
export DW_CLIENT_MEMORY=2048

# Increase for better performance
export DW_CLIENT_MEMORY=4096

# Decrease for limited systems
export DW_CLIENT_MEMORY=1024
```

### Backend Performance

```bash
# Python settings
export PYTHONUNBUFFERED=1
export PYTHONDONTWRITEBYTECODE=1

# Uvicorn workers
export UV_WORKERS=4  # Match CPU cores

# Logging level (DEBUG slows things down)
export DW_LOG_LEVEL=INFO
```

### Network Optimization

```bash
# Minecraft server configuration (in server.properties)
network-compression-threshold=256
max-tick-time=60000
view-distance=10  # Reduce for better performance
```

---

## Security Considerations

### Network Access

```bash
# Limit backend to localhost only (development)
# Edit main.py: uvicorn.run(..., host="127.0.0.1")

# Or use firewall
sudo ufw allow from 127.0.0.1 to any port 11400

# For production: use reverse proxy (Nginx, Apache)
# and implement authentication
```

### File Permissions

```bash
# Restrict access to data directories
chmod 700 ~/.ultimmc/
chmod 700 /home/devlord/divine-world-core/npc_applications/data/

# Restrict backend logs
chmod 600 /tmp/divine-world.log
```

### Environment Variables

```bash
# Don't hardcode sensitive values in scripts
# Use environment files instead
cat > ~/.divine-world-env
export DW_MINIO_ACCESS_KEY=your_key
export DW_MINIO_SECRET_KEY=your_secret

# Load before starting
source ~/.divine-world-env
python main.py
```

---

## Deployment Checklist

- [ ] Java 17+ installed
- [ ] Python 3.9+ installed  
- [ ] 10GB+ disk space available
- [ ] 4GB+ RAM available
- [ ] UltimMC installed and verified
- [ ] DWClientBot mod built
- [ ] DivineWorld mod built
- [ ] Python virtual environment created
- [ ] Dependencies installed
- [ ] Configuration variables set
- [ ] Backend starts without errors
- [ ] `/health` endpoint responds
- [ ] Can spawn agents successfully
- [ ] Agents appear in Minecraft server
- [ ] Monitoring system setup (logs, metrics)
- [ ] Backup strategy in place

---

## Next Steps

1. **Read Documentation**
   - ULTIMMC_QUICK_START.md — Quick reference
   - ULTIMMC_AUTOMATION.md — Detailed guide
   - SYSTEM_ARCHITECTURE.md — Architecture overview

2. **Test Deployment**
   - Spawn a few agents
   - Monitor their performance
   - Check logs for issues

3. **Scale Up**
   - Increase agent count
   - Monitor resource usage
   - Adjust memory/CPU as needed

4. **Customize**
   - Modify agent personas
   - Add custom behaviors
   - Integrate with other systems

---

## Support Resources

- **GitHub**: https://github.com/UltimMC/Launcher
- **Documentation**: See `*.md` files in project root
- **Logs**: `tail -f backend.log`
- **Status**: `curl http://127.0.0.1:11400/health`

Ready to deploy! 🚀
