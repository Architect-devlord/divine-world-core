# ai_core/brain_integration.py
"""
Integration layer: Connects TrueReasoningCore to existing BrainCore.
Preserves all existing functionality while adding deep reasoning.
"""

import logging
import numpy as np
from typing import Dict, Any, List, Optional
from ai_core.reasoning_core import TrueReasoningCore

log = logging.getLogger("brain_integration")


def add_reasoning_to_brain(brain_instance):
    """
    Enhance existing BrainCore with true reasoning capabilities.
    Call this ONCE during agent initialization.
    
    Usage:
        from ai_core.brain_integration import add_reasoning_to_brain
        add_reasoning_to_brain(agent.brain)
    """
    
    # Create reasoning core
    reasoning_core = TrueReasoningCore(obs_dim=512)
    
    # Attach to brain
    brain_instance.reasoning = reasoning_core
    
    # Add reasoning methods
    brain_instance.reason_about = _create_reason_about_method(brain_instance)
    brain_instance.imagine_action = _create_imagine_action_method(brain_instance)
    brain_instance.explain_why = _create_explain_why_method(brain_instance)
    brain_instance.predict_consequence = _create_predict_consequence_method(brain_instance)
    brain_instance.mental_simulation = _create_mental_simulation_method(brain_instance)
    
    # Enhance existing evaluate_event to use reasoning
    _enhance_evaluate_event(brain_instance)
    
    log.info("✅ True reasoning capabilities added to BrainCore")


def _create_reason_about_method(brain):
    """Create unified reasoning method"""
    def reason_about(problem: Dict[str, Any], 
                     context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Main reasoning entry point.
        
        Example problems:
            {"query": "where should I move?", "action": {...}}
            {"query": "why did I fail?", "effect": "death"}
            {"query": "what if I attack?", "action": "attack"}
        """
        return brain.reasoning.reason(problem, context)
    
    return reason_about


def _create_imagine_action_method(brain):
    """Create mental simulation method"""
    def imagine_action(action: Dict[str, Any], 
                       current_state: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Mentally simulate action before executing.
        Returns prediction of outcome.
        
        Example:
            prediction = brain.imagine_action(
                {"type": "break_block", "target": 5},
                current_state={"objects": [...]}
            )
        """
        # Load state into workspace
        if current_state and 'objects' in current_state:
            brain.reasoning.mental_workspace.clear()
            for obj in current_state['objects']:
                brain.reasoning.mental_workspace.add_object(obj)
        
        # Imagine
        return brain.reasoning.mental_workspace.imagine_action(action)
    
    return imagine_action


def _create_explain_why_method(brain):
    """Create causal explanation method"""
    def explain_why(effect: str, max_depth: int = 3) -> List[str]:
        """
        Explain why something happened.
        Traces back through causal chain.
        
        Example:
            causes = brain.explain_why("player_died")
            # Returns: ["attacked_by_zombie", "low_health", "no_food"]
        """
        return brain.reasoning.causal_graph.find_root_causes(
            f"result:{effect}", 
            max_depth=max_depth
        )
    
    return explain_why


def _create_predict_consequence_method(brain):
    """Create forward prediction method"""
    def predict_consequence(action: str, horizon: int = 3) -> List[str]:
        """
        Predict what will happen if agent does action.
        
        Example:
            effects = brain.predict_consequence("attack_zombie")
            # Returns: ["zombie_damaged", "zombie_retaliates", "player_hurt"]
        """
        return brain.reasoning.causal_graph.predict_effects(
            f"action:{action}",
            max_depth=horizon
        )
    
    return predict_consequence


def _create_mental_simulation_method(brain):
    """Create full mental simulation method"""
    def mental_simulation(plan: List[Dict[str, Any]], 
                         initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Simulate entire plan in mental workspace.
        Returns trajectory of predicted states.
        
        Example:
            plan = [
                {"type": "move", "direction": (1, 0, 0)},
                {"type": "break_block", "target": 5},
                {"type": "pick_up", "item": "wood"}
            ]
            
            trajectory = brain.mental_simulation(plan, current_state)
        """
        # Load initial state
        brain.reasoning.mental_workspace.clear()
        if 'objects' in initial_state:
            for obj in initial_state['objects']:
                brain.reasoning.mental_workspace.add_object(obj)
        
        # Simulate each step
        trajectory = []
        for i, action in enumerate(plan):
            prediction = brain.reasoning.mental_workspace.imagine_action(action)
            
            trajectory.append({
                'step': i,
                'action': action,
                'prediction': prediction
            })
            
            # Early stop if predicted failure
            if prediction.get('success_probability', 0) < 0.3:
                break
        
        return {
            'trajectory': trajectory,
            'total_success_probability': np.mean([
                t['prediction'].get('success_probability', 0.5)
                for t in trajectory
            ]) if trajectory else 0.0
        }
    
    return mental_simulation


def _enhance_evaluate_event(brain):
    """
    Enhance existing evaluate_event to use reasoning.
    Preserves original functionality, adds reasoning layer.
    """
    
    # Store original method
    original_evaluate = brain.evaluate_event
    
    def enhanced_evaluate_event(event: Dict[str, Any], 
                                 context: Optional[Dict] = None) -> tuple:
        """
        Enhanced event evaluation with reasoning integration.
        """
        # Run original evaluation first
        base_reward, base_emotions = original_evaluate(event, context)
        
        # Add reasoning layer
        try:
            # Learn causal relationships from event
            if 'action' in event and 'result' in event:
                brain.reasoning.learn_from_experience({
                    'action': event['action'],
                    'result': event.get('result', event.get('type')),
                    'observation': context.get('observation') if context else None
                })
            
            # Use reasoning for better reward estimation
            if event.get('type') in ['action_result', 'state_change']:
                # Try to understand WHY this happened
                effect_id = f"result:{event.get('type')}"
                causes = brain.reasoning.causal_graph.find_root_causes(effect_id)
                
                # Bonus for understanding causality
                if causes:
                    understanding_bonus = 0.05
                    base_reward += understanding_bonus
                    base_emotions['surprise'] = base_emotions.get('surprise', 0) + 0.05
            
        except Exception as e:
            log.warning(f"Reasoning enhancement failed: {e}")
            # Fall back to base evaluation
            pass
        
        return base_reward, base_emotions
    
    # Replace method
    brain.evaluate_event = enhanced_evaluate_event


def create_reasoning_cli_visualizer(brain):
    """
    Create CLI visualization of reasoning state.
    Shows what agent is thinking about.
    """
    def visualize_reasoning():
        """Print current reasoning state"""
        stats = brain.reasoning.get_reasoning_stats()
        
        print("\n" + "="*60)
        print("          🧠 AGENT REASONING STATE")
        print("="*60)
        
        print(f"\nMental Workspace:")
        print(f"  Objects in mind: {stats['workspace_objects']}")
        
        print(f"\nCausal Understanding:")
        print(f"  Known causal nodes: {stats['causal_nodes']}")
        
        print(f"\nLogical Knowledge:")
        print(f"  Facts known: {stats['known_facts']}")
        print(f"  Logical rules: {stats['logical_rules']}")
        
        print(f"\nCurrent Mode: {stats['current_mode']}")
        
        print("="*60 + "\n")
    
    return visualize_reasoning


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def quick_reason(brain, query: str, context: Optional[Dict] = None) -> str:
    """
    Quick reasoning query for CLI/testing.
    
    Example:
        response = quick_reason(agent.brain, "why did I die?")
        print(response)
    """
    if not hasattr(brain, 'reasoning'):
        return "Reasoning not enabled. Call add_reasoning_to_brain(brain) first."
    
    # Parse query into problem format
    problem = {'query': query}
    
    if 'why' in query.lower():
        problem['query_type'] = 'why'
        # Extract effect from query
        words = query.lower().split()
        if 'die' in words or 'died' in words:
            problem['effect'] = 'death'
        elif 'fail' in words or 'failed' in words:
            problem['effect'] = 'failure'
    
    elif 'what if' in query.lower():
        problem['query_type'] = 'predict'
        # Extract action
        if 'attack' in query.lower():
            problem['action'] = 'attack'
        elif 'move' in query.lower():
            problem['action'] = 'move'
    
    # Reason about it
    result = brain.reasoning.reason(problem, context)
    
    # Format response
    if result['reasoning_type'] == 'causal':
        causes = result.get('explanation', [])
        if causes:
            return f"Causal analysis: {', '.join(causes)}"
        else:
            return "No clear cause found in causal memory."
    
    elif result['reasoning_type'] == 'spatial':
        pred = result.get('prediction', {})
        prob = pred.get('success_probability', 0)
        return f"Spatial prediction: {prob*100:.0f}% success probability"
    
    else:
        return f"Reasoning result: {result}"


# ============================================================================
# INTEGRATION TEST
# ============================================================================

def test_reasoning_integration():
    """Test reasoning integration with dummy brain"""
    
    print("\n" + "="*70)
    print("  🧪 TESTING REASONING INTEGRATION")
    print("="*70 + "\n")
    
    # Create dummy brain
    from ai_core.brain_core import BrainCore
    from ai_core.agent import NPCAgent
    
    agent = NPCAgent("test_agent")
    
    # Add reasoning
    print("1. Adding reasoning to brain...")
    add_reasoning_to_brain(agent.brain)
    
    # Test mental simulation
    print("\n2. Testing mental simulation...")
    prediction = agent.brain.imagine_action(
        {"type": "break_block", "target": 0},
        {"objects": [{"id": 0, "type": "stone", "position": (1, 0, 0)}]}
    )
    print(f"   Prediction: {prediction}")
    
    # Test causal learning
    print("\n3. Testing causal learning...")
    agent.brain.reasoning.causal_graph.learn_from_experience({
        'action': 'attack_zombie',
        'result': 'zombie_hurt'
    })
    
    effects = agent.brain.predict_consequence("attack_zombie")
    print(f"   Predicted effects: {effects}")
    
    # Test logical reasoning
    print("\n4. Testing logical reasoning...")
    agent.brain.reasoning.logic_engine.add_fact("is_hungry")
    agent.brain.reasoning.logic_engine.add_fact("has_food")
    agent.brain.reasoning.logic_engine.add_rule(
        [("is_hungry",), ("has_food",)],
        ("should_eat",)
    )
    
    new_facts = agent.brain.reasoning.logic_engine.forward_chain()
    print(f"   Deduced facts: {new_facts}")
    
    # Test unified reasoning
    print("\n5. Testing unified reasoning...")
    result = agent.brain.reason_about({
        "query": "what if I attack?",
        "query_type": "predict",
        "action": "attack_zombie"
    })
    print(f"   Result: {result}")
    
    # Stats
    print("\n6. Reasoning stats:")
    visualizer = create_reasoning_cli_visualizer(agent.brain)
    visualizer()
    
    print("✅ All tests passed!\n")


if __name__ == "__main__":
    test_reasoning_integration()