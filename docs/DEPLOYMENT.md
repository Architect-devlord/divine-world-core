# Divine World Deployment Guide

This document covers deploying Divine World in production environments using Docker or manual setups.

---

## 🐳 Docker Deployment

The easiest way to deploy Divine World is using Docker Compose. This starts the management server, a ScyllaDB instance (optional), and handles agent lifecycle management.

### Prerequisites
- Docker and Docker Compose installed.

### Build and Run
```bash
docker-compose up -d --build
```
The server will be available at `http://localhost:11400`.

### Configuration
The `docker-compose.yml` file allows you to define agent environments and ports:
```yaml
services:
  py_backend:
    build:
      context: .
      dockerfile: py_backend/Dockerfile
    environment:
      DW_BACKEND_PORT: 11400
      DW_ULTIMMC_PATH: /app/UltimMC
    volumes:
      - ./data:/app/npc_applications/data
    ports:
      - "11400:11400"
```

---

## 🏗️ Manual Production Setup

For manual setups, it is recommended to use a process manager like **systemd** or **PM2** to keep the management server running.

### Example systemd Service
Create `/etc/systemd/system/divine-world.service`:
```ini
[Unit]
Description=Divine World Management Server
After=network.target

[Service]
User=youruser
WorkingDirectory=/path/to/divine-world-core
ExecStart=/path/to/divine-world-core/venv/bin/python py_backend/main.py --cli
Restart=always

[Install]
WantedBy=multi-user.target
```

### Resource Considerations
Each agent requires significant RAM (2GB+ recommended). Monitor your system's memory usage when spawning multiple agents.

---

## 🛰️ Networking

- **Port 11400**: Default Management Server port (REST/WebSockets).
- **Port 11401+**: Individual agent backends (assigned dynamically).
- **Port 25565**: Default Minecraft server port (if running locally).

Ensure these ports are open in your firewall if you are accessing the server or agents from a remote machine.

---

## 🧠 Persistence

Ensure the `data/` and `npc_applications/` directories are backed up. These contain:
- **`brain.pcap`**: Agent weights, memories, and personality.
- **`agents.json`**: The agent registry.
- **`config.json`**: Agent-specific settings.
