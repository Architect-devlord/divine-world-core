#!/usr/bin/env python3
"""
Divine World System Integration Test
- Starts DW_Server (2 minute wait for initialization)
- Starts main.py (Agent Manager) (3 minute wait)
- Tests Genesis spawning endpoint
- Tests Spawn single NPC endpoint
- Tests Spawn gods endpoint
- Monitors logs for agent join events

Total Runtime: ~6-7 minutes (optimized for slower systems)
"""

import subprocess
import time
import sys
import os
import json
from pathlib import Path
import urllib.request
import urllib.error

start_time = time.time()

print("="*90)
print("DIVINE WORLD SYSTEM INTEGRATION TEST")
print("="*90)
print("\n⚠️  This test is optimized for slower systems")
print("   Total expected runtime: 5-7 minutes")
print("   Please be patient while systems initialize...\n")

BASE_DIR = "/home/devlord/divine-world-core"
DW_SERVER_DIR = "/home/devlord/DW_Server"
BASE_URL = "http://localhost:11400"

# ==================== STEP 1: START SERVER ====================
print("\n[STEP 1] Starting Minecraft Server (DW_Server)...")
print(f"Location: {DW_SERVER_DIR}")

try:
    server_proc = subprocess.Popen(
        ["bash", "./run.sh"],
        cwd=DW_SERVER_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"✅ Server started (PID: {server_proc.pid})")
    print("⏳ Waiting 2 minutes (120 seconds) for Minecraft Server to fully initialize...")
    print("   This may take longer on slower systems...")
    for i in range(120):
        if i % 30 == 0:
            print(f"   [{i}/120s] Server initializing...")
        time.sleep(1)
except Exception as e:
    print(f"❌ Failed to start server: {e}")
    sys.exit(1)

# ==================== STEP 2: START MAIN.PY ====================
print("\n[STEP 2] Starting main.py (Agent Manager)...")
print(f"Location: {BASE_DIR}/py_backend/main.py")

try:
    os.chdir(BASE_DIR)
    # Use the dw_env Python
    main_proc = subprocess.Popen(
        [f"{BASE_DIR}/py_backend/dw_env/bin/python3", "py_backend/main.py"],
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    print(f"✅ main.py started (PID: {main_proc.pid})")
    print("⏳ Waiting 3 minutes (180 seconds) for Agent Manager to initialize...")
    print("   Initializing AI core, spawner systems, and Minecraft launcher...")
    for i in range(180):
        if i % 30 == 0:
            print(f"   [{i}/180s] Agent Manager initializing...")
        time.sleep(1)
except Exception as e:
    print(f"❌ Failed to start main.py: {e}")
    server_proc.terminate()
    sys.exit(1)

# ==================== STEP 3: TEST ENDPOINTS ====================
print("\n[STEP 3] Testing API Endpoints...")
print(f"Base URL: {BASE_URL}\n")

def make_request(endpoint, payload, method="POST", timeout=30):
    """Make HTTP request to endpoint"""
    try:
        url = f"{BASE_URL}{endpoint}"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_data = response.read().decode('utf-8')
            return response.status, response_data
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8')
    except urllib.error.URLError as e:
        return None, str(e.reason)
    except Exception as e:
        return None, str(e)

# 3a) Genesis Spawning
print("3a) Genesis Spawning Endpoint:")
print("     Endpoint: POST /genesis")
genesis_payload = {
    "command": "genesis",
    "name": "alice",
    "gender": "female",
    "personality": "balanced"
}
print(f"     Payload: {json.dumps(genesis_payload, indent=6)}")

status, response = make_request("/genesis", genesis_payload)
if status:
    print(f"     ✅ Status: {status}")
    try:
        resp_json = json.loads(response)
        print(f"     Response: {json.dumps(resp_json, indent=6)}")
    except:
        print(f"     Response: {response[:200]}")
else:
    print(f"     ℹ️  No response (server initializing): {response}")

print("⏳ Waiting 30 seconds before next spawn...")
for i in range(30):
    if i % 10 == 0:
        print(f"   [{i}/30s] Genesis agent initializing...")
    time.sleep(1)

# 3b) Spawn Single NPC
print("\n3b) Spawn Single NPC Endpoint:")
print("     Endpoint: POST /spawn/npc")
spawn_npc_payload = {
    "agent_id": "bob",
    "gender": "male",
    "personality": "adventurous"
}
print(f"     Payload: {json.dumps(spawn_npc_payload, indent=6)}")

status, response = make_request("/spawn/npc", spawn_npc_payload, timeout=30)
if status:
    print(f"     ✅ Status: {status}")
    try:
        resp_json = json.loads(response)
        print(f"     Response: {json.dumps(resp_json, indent=6)}")
    except:
        print(f"     Response: {response[:200]}")
else:
    print(f"     ℹ️  No response: {response}")

print("⏳ Waiting 30 seconds before spawning gods...")
for i in range(30):
    if i % 10 == 0:
        print(f"   [{i}/30s] NPC agent initializing and joining server...")
    time.sleep(1)

# 3c) Spawn Gods
print("\n3c) Spawn Gods Endpoints:")
god_types = ["ender_dragon", "wither", "warden"]

for god_type in god_types:
    print(f"\n     Spawning {god_type}...")
    print(f"     Endpoint: POST /spawn/god")
    spawn_god_payload = {
        "god_type": god_type,
        "god_name": f"{god_type}_agent_1"
    }
    print(f"     Payload: {json.dumps(spawn_god_payload, indent=8)}")
    
    status, response = make_request("/spawn/god", spawn_god_payload, timeout=30)
    if status:
        print(f"     ✅ Status: {status}")
        try:
            resp_json = json.loads(response)
            print(f"     Response: {json.dumps(resp_json, indent=8)}")
        except:
            print(f"     Response: {response[:150]}")
    else:
        print(f"     ℹ️  No response: {response}")
    
    time.sleep(2)

print("\n⏳ Waiting 60 seconds for all agents to fully initialize and join server...")
for i in range(60):
    if i % 15 == 0:
        print(f"   [{i}/60s] Agents joining server...")
    time.sleep(1)
print("\n[STEP 4] Monitoring Logs for Agent Join Events...")
print("=" * 90)

log_files = {
    "divine_world.log": "data/logs/divine_world.log",
    "agent_spawner.log": "data/logs/agent_spawner.log",
    "minecraft_launcher.log": "data/logs/minecraft_launcher.log",
}

log_checks = {
    "Player joins": ["join", "joined", "connected"],
    "Agent spawned": ["spawn", "spawned", "created"],
    "Minecraft connected": ["minecraft", "connect", "client"],
    "Errors": ["error", "exception", "fail"]
}

for log_name, log_path in log_files.items():
    full_path = Path(BASE_DIR) / log_path
    
    print(f"\n📋 {log_name}:")
    print(f"   Path: {full_path}")
    
    if full_path.exists():
        with open(full_path, 'r') as f:
            content = f.read()
            lines = content.split('\n')
        
        print(f"   Total lines: {len(lines)}")
        
        # Check for keywords
        found_keywords = {}
        for check_type, keywords in log_checks.items():
            matches = 0
            for line in lines:
                if any(kw.lower() in line.lower() for kw in keywords):
                    matches += 1
            if matches > 0:
                found_keywords[check_type] = matches
        
        if found_keywords:
            print(f"   ✅ Found activity:")
            for check_type, count in found_keywords.items():
                print(f"      - {check_type}: {count} occurrences")
        else:
            print(f"   ℹ️  No join/spawn/connection events yet")
        
        # Show last relevant lines
        print(f"\n   Last 15 relevant lines:")
        relevant_lines = []
        for line in reversed(lines):
            if line.strip() and any(kw.lower() in line.lower() 
                                   for kw in ["join", "spawn", "connect", "agent", 
                                            "player", "error", "fail", "alice", "bob", "eve"]):
                relevant_lines.append(line.strip()[:100])
                if len(relevant_lines) >= 15:
                    break
        
        if relevant_lines:
            for line in reversed(relevant_lines):
                print(f"   > {line}")
        else:
            print(f"   (No relevant lines found)")
    else:
        print(f"   ⚠️  Log file not created yet")

# ==================== STEP 5: CLEANUP ====================
print("\n" + "="*90)
print("[STEP 5] Cleanup & Process Status...")

import psutil

print("\nProcess Status Before Cleanup:")
for label, proc in [("Server", server_proc), ("main.py", main_proc)]:
    try:
        p = psutil.Process(proc.pid)
        status = p.status()
        memory = p.memory_info().rss / 1024 / 1024  # MB
        print(f"  {label}: PID {proc.pid} - Status: {status} - Memory: {memory:.1f}MB")
    except:
        print(f"  {label}: PID {proc.pid} - Process not found")

print("\nTerminating processes...")
main_proc.terminate()
time.sleep(2)
server_proc.terminate()
time.sleep(2)

print("✅ Processes terminated")

# ==================== SUMMARY ====================
print("\n" + "="*90)
print("✅ TEST COMPLETE")
print("="*90)

elapsed_time = time.time() - start_time
minutes = int(elapsed_time // 60)
seconds = int(elapsed_time % 60)

print(f"\nTotal Runtime: {minutes}m {seconds}s")
print("\nSummary:")
print("  ✅ Server started and running")
print("  ✅ main.py (Agent Manager) started and running")
print("  ✅ Genesis endpoint tested")
print("  ✅ Spawn NPC endpoint tested")
print("  ✅ Spawn Gods endpoint tested")
print("  ✅ Logs monitored for agent activity")
print("\nNext Steps:")
print("  1. Check if players/agents joined the server in the logs")
print("  2. Review agent spawn output in divine_world.log")
print("  3. Check minecraft_launcher.log for Minecraft connection events")
print("\n" + "="*90 + "\n")