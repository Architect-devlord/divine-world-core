# test_gods.py
from ai_core.agent_spawner import AgentSpawner

spawner = AgentSpawner(client_jar_path="DWClientBot.jar")

# Test each god type
god_types = ['wither', 'warden', 'dragon', 'oracle', 'creaking']

for god_type in god_types:
    print(f"\n🔱 Spawning {god_type}...")
    
    agent = spawner.spawn_god(
        god_type=god_type,
        server_addr="127.0.0.1:25565"
    )
    
    print(f"✅ {god_type.upper()} spawned!")
    print(f"   Agent ID: {agent.agent_id}")
    print(f"   Personality: {agent.personality.traits}")
    print(f"   Backend Port: {agent.client_process.backend_port}")