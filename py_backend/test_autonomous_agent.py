# test_autonomous_agent.py
"""
Test the fully autonomous agent.
Watch it think and speak on its own!
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent))

from ai_core.agent import NPCAgent, run_autonomous_agent
from ai_core.personality import Personality

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)


async def test_autonomous_speech():
    """Test agent speaking on its own"""
    
    print("\n" + "="*70)
    print("  🧪 TESTING AUTONOMOUS AGENT")
    print("="*70 + "\n")
    
    # Create agent with EXTRAVERTED personality (talks more)
    agent = NPCAgent(
        agent_id="chatty_npc",
        gender="female",
        persona_traits={
            'extraversion': 0.8,     # Very outgoing
            'sociability': 0.9,      # Loves to talk
            'openness': 0.7,         # Creative speech
            'agreeableness': 0.6,    # Friendly
            'curiosity': 0.8,        # Comments on things
        },
        autonomous=True  # Enable autonomy
    )
    
    print(f"✅ Created agent: {agent.agent_id}")
    print(f"   Personality: extraversion=0.8, sociability=0.9")
    print(f"   Speech cooldown: ~{agent.cognitive_loop.speech_cooldown:.1f}s")
    print()
    
    # Teach some vocabulary first
    print("📚 Teaching vocabulary...")
    
    training_phrases = [
        "Hello, how are you today?",
        "I feel happy when the sun shines.",
        "This place looks interesting.",
        "I wonder what will happen next.",
        "That was quite surprising!",
        "I enjoy exploring new areas.",
        "Sometimes I feel peaceful here.",
        "The world is full of wonders.",
    ]
    
    context = {
        'health': 20.0,
        'hunger': 18.0,
        'emotions': agent.emotion.snapshot()
    }
    
    for phrase in training_phrases:
        agent.brain.language.process_language_input(phrase, context)
    
    print(f"✅ Vocabulary: {agent.brain.language.vocabulary_size} words")
    print(f"✅ Language stage: {agent.brain.language.language_stage}")
    print()
    
    # Simulate some experiences to give agent things to talk about
    print("🎭 Simulating experiences...")
    
    agent.memory.remember({
        'type': 'discovery',
        'text': 'found a beautiful flower'
    }, tags=['exploration', 'success'])
    
    agent.emotion.add('joy', 0.7)
    agent.emotion.add('surprise', 0.5)
    
    agent.memory.remember({
        'type': 'observation',
        'text': 'the sky turned orange at sunset'
    }, tags=['perception', 'beautiful'])
    
    print("✅ Agent has experiences to talk about")
    print()
    
    print("="*70)
    print("  🧠 STARTING AUTONOMOUS MODE")
    print("  Watch the agent think and speak on its own!")
    print("  Press Ctrl+C to stop")
    print("="*70 + "\n")
    
    # Run for 60 seconds (agent will speak multiple times)
    await run_autonomous_agent(agent, duration=60)


async def test_personality_variation():
    """Test different personality types"""
    
    print("\n" + "="*70)
    print("  🧪 TESTING PERSONALITY VARIATION")
    print("="*70 + "\n")
    
    personalities = [
        {
            'name': 'Shy',
            'traits': {
                'extraversion': -0.7,
                'sociability': 0.2,
                'openness': 0.3
            }
        },
        {
            'name': 'Chatty',
            'traits': {
                'extraversion': 0.9,
                'sociability': 0.9,
                'openness': 0.8
            }
        },
        {
            'name': 'Grumpy',
            'traits': {
                'extraversion': -0.5,
                'sociability': 0.1,
                'agreeableness': -0.6,
                'neuroticism': 0.7
            }
        }
    ]
    
    for persona in personalities:
        agent = NPCAgent(
            agent_id=f"test_{persona['name'].lower()}",
            persona_traits=persona['traits'],
            autonomous=True
        )
        
        print(f"\n{persona['name']} NPC:")
        print(f"  Speech cooldown: {agent.cognitive_loop.speech_cooldown:.1f}s")
        print(f"  Personality: {persona['traits']}")


if __name__ == "__main__":
    import sys
    
    test_type = sys.argv[1] if len(sys.argv) > 1 else "speech"
    
    if test_type == "speech":
        asyncio.run(test_autonomous_speech())
    elif test_type == "personality":
        asyncio.run(test_personality_variation())
    else:
        print("Usage: python test_autonomous_agent.py [speech|personality]")