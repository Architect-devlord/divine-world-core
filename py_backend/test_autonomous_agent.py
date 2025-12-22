# test_autonomous.py
import asyncio
from ai_core.agent import NPCAgent

async def test_autonomous_agent():
    # Create agent
    agent = NPCAgent(
        agent_id="autonomous_test_001",
        autonomous=True
    )
    
    # Start autonomous mode
    await agent.start_autonomous_mode()
    
    print("✅ Agent running autonomously!")
    print("   Watch backend logs for cognitive loop activity")
    
    # Let it run for 5 minutes
    await asyncio.sleep(300)
    
    # Check stats
    status = agent.cognitive_loop.get_status()
    print(f"\nStats after 5 minutes:")
    print(f"  Cycles: {status['cycle_count']}")
    print(f"  Speeches: {status['speech_count']}")
    print(f"  Last speech: {status['last_speech']}")
    
    # Stop
    await agent.stop_autonomous_mode()

asyncio.run(test_autonomous_agent())