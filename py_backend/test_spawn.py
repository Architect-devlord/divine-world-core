#OPTION A: Via Test Script
#  test_spawn.py
from ai_core.agent_spawner import AgentSpawner

# Initialize spawner (with Minecraft support)
spawner = AgentSpawner(
    client_jar_path="DWClientBot.jar"  # Your compiled mod JAR
)

# Spawn NPC
agent = spawner.spawn_npc(
    agent_id="AI_Test_001",
    server_addr="127.0.0.1:25565",  # Your MC server
    memory_mb=2048
)

print(f"Agent spawned: {agent.agent_id}")
print(f"Backend port: {agent.client_process.backend_port}")
"""

**Option B: Via Mod Directly**

1. Launch Minecraft with mod installed
2. Join server
3. Mod should auto-connect to backend
4. Check backend logs for connection

---

## **Phase 4: Vision & Perception Tests**

### **4.1 Verify Vision Capture**

**In Backend Logs**, look for:
```
[VisionCapture] Initialized: 640x480 @ 0.75
[WebSocket] Received PERCEPTION frame from AI_Test_001
"""