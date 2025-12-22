# test_god_transform.py
from ai_core.agent_spawner import AgentSpawner

spawner = AgentSpawner()
agent = spawner.spawn_god('elder_guardian', server_addr="127.0.0.1:25565")

# Test transformation
agent.useAbility('transform', 'player')

# Verify
assert agent.isInPlayerForm() == True

# Revert
agent.useAbility('revert')
assert agent.isInPlayerForm() == False

