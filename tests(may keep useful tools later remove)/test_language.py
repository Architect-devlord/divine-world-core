# tests/test_language.py
import logging
import time
from ai_core.agent import NPCAgent
from ai_core.brain_language import add_language_to_brain

logging.basicConfig(level=logging.INFO)

# Create agent
agent = NPCAgent("language_demo")

# Add language (automatic in BrainCore.__init__ now)
if not hasattr(agent.brain, 'language'):
    add_language_to_brain(agent.brain)

# Build context
context = {
    'health': agent.health,
    'hunger': agent.hunger,
    'emotions': agent.emotion.snapshot(),
    'dominant_emotion': agent.emotion.dominant_emotion()
}

# Test conversation
print("=== Language Learning Demo ===\n")

conversations = [
    "Hello! How are you?",
    "I like exploring caves.",
    "Mining is fun but dangerous.",
    "Food keeps me alive.",
    "Friends make me happy.",
]

for i, msg in enumerate(conversations):
    print(f"User: {msg}")
    response = agent.brain.process_language_input(msg, context)
    print(f"Agent: {response}")
    print(f"Stage: {agent.brain.language.language_stage}, Vocab: {agent.brain.language.vocabulary_size}\n")

# Test autonomous speech
print("\n=== Autonomous Speech ===")
for _ in range(5):
    if agent.brain.should_speak():
        speech = agent.brain.generate_speech(context)
        print(f"Agent (spontaneous): {speech}")
    time.sleep(2)

# Test file learning
from pathlib import Path
test_file = Path("data/uploads/demo/story.txt")
test_file.parent.mkdir(parents=True, exist_ok=True)
test_file.write_text("""
Once upon a time, there was a brave explorer.
The explorer loved discovering new places.
Mountains were tall and dangerous.
But the view from the top was beautiful.
Every journey teaches something new.
""")

print("\n=== File Learning ===")
summary = agent.brain.learn_from_file(str(test_file), "text/plain")
print(summary)

# Show final progress
print("\n=== Final Progress ===")
progress = agent.brain.get_language_progress()
for key, value in progress.items():
    if key != 'most_frequent_words':
        print(f"{key}: {value}")

print("\nTop 5 words:", progress['most_frequent_words'][:5])