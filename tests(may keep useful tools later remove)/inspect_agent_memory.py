# tests/inspect_agent_memory.py
"""
Test script to display an agent's value_table and recent memory.
Usage: python tests/inspect_agent_memory.py [agent_id]
If agent_id not given, uses 'inspector'.
"""
import sys
import pprint
from ai_core.agent import NPCAgent

agent_id = sys.argv[1] if len(sys.argv) > 1 else "inspector"
agent = NPCAgent(agent_id, autosave_path=f"./data/{agent_id}_brain")

print(f"=== Agent '{agent_id}' Personality Traits ===")
pprint.pprint(agent.personality.traits)

print(f"\n=== Agent '{agent_id}' Emotions ===")
pprint.pprint(agent.emotion.emotions)

print(f"\n=== Recent Memory (up to 10 events) ===")
recent = agent.memory.recall(10)
for ev in recent:
    msg = ev.get('payload', {}).get('text') or str(ev.get('payload'))
    tags = ev.get('tags', [])
    novelty = getattr(ev, 'novelty', 'N/A')
    print(f"  - {ev['type']}: tags={tags}, novelty={novelty}, payload={msg}")

print("\n=== Value Table ===")
if hasattr(agent, "value_table"):
    pprint.pprint(agent.value_table)
else:
    print("(No value_table on agent)")
