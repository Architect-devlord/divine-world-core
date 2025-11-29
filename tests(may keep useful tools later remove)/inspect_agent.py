import pprint
from ai_core.agent import NPCAgent

if __name__ == "__main__":
    agent = NPCAgent("inspector", autosave_path="./data/inspector_brain")
    print("=== Personality ===")
    pprint.pprint(agent.personality.traits)
    print("\n=== Emotions ===")
    pprint.pprint(agent.emotion.emotions)
    print("\n=== Memory (last 10) ===")
    pprint.pprint(agent.memory.recall(10))

    # if BrainCapsule has a value table or learned state
    brain = agent.export_brain(as_json=False)
    if hasattr(brain, "model_state") and brain.model_state:
        print("\n=== Brain Model State Keys ===")
        print(list(brain.model_state.keys()))
    else:
        print("\n(No model_state in brain yet)")

    # Debug: value table (if later attached to RL)
    if hasattr(agent, "value_table"):
        print("\n=== Value Table ===")
        pprint.pprint(agent.value_table)
    else:
        print("\n(No value_table in agent yet)")
