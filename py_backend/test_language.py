# Test script
from ai_core.agent import NPCAgent

agent = NPCAgent("test_agent")

# Simulate diverse experiences
agent.memory.remember({
    'type': 'action',
    'action_type': 'explore',
    'result': 'found_item'
}, tags=['action', 'success'])

agent.memory.remember({
    'type': 'emotion',
    'emotion': 'joy',
    'intensity': 0.8
}, tags=['emotion', 'positive'])

# Language input
context = {
    'health': 20.0,
    'hunger': 15.0,
    'emotions': agent.emotion.snapshot()
}

response = agent.brain.language.process_language_input(
    "Hello! How are you?",
    context
)

print(f"Agent: {response}")
# Should generate response informed by:
# - Recent exploration success
# - High joy emotion
# - Personality traits