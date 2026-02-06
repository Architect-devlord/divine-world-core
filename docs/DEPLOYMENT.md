# Divine World Deployment Guide

This document covers deploying Divine World in production environments using Docker or manual setups.

## Docker Deployment

The easiest way to deploy multiple agents is using Docker Compose.

### Prerequisites
- Docker and Docker Compose installed.

### Build and Run
```bash
docker-compose up -d --build
```

### Configuration
The `docker-compose.yml` file allows you to define multiple agents and their environments:

```yaml
services:
  agent-alice:
    build: ./py_backend
    environment:
      AGENT_ID: alice
      PORT: 8001
    ports:
      - "8001:8001"
```

---

## Production Readiness

Before deploying, run the production check script to ensure all dependencies and configurations are correct:

```bash
chmod +x production_ready_check.sh
./production_ready_check.sh
```

### Key Considerations
- **Resource Limits**: Each agent requires significant RAM (2GB+). Monitor memory usage with `docker stats`.
- **Persistence**: Ensure the `./data` directory is mounted as a volume to persist agent brains and logs.
- **Network**: The backend needs to be accessible by both the frontend and the Minecraft clients.

---

## Manual Production Setup

If not using Docker, it is recommended to use a process manager like **PM2** or **systemd** to keep the backend running.

### Example systemd Service
```ini
[Unit]
Description=Divine World Backend
After=network.target

[Service]
User=devlord
WorkingDirectory=/home/devlord/divine-world-core/py_backend
ExecStart=/home/devlord/divine-world-core/py_backend/start_backend.sh
Restart=always

[Install]
WantedBy=multi-user.target
```
