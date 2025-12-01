# ai_core/reasoning_visualizer.py
"""
CLI-based visualization of agent reasoning.
Shows mental workspace, causal chains, and logical state in terminal.
Ultra-lightweight - no GUI dependencies.
"""

import numpy as np
from typing import Dict, Any, List, Optional
import logging

log = logging.getLogger("reasoning_viz")


# ============================================================================
# ASCII 3D WORKSPACE VISUALIZATION
# ============================================================================

def visualize_workspace_3d_cli(workspace, slice_axis: str = 'y', 
                                slice_index: Optional[int] = None):
    """
    Visualize 3D mental workspace as ASCII art in terminal.
    Shows slice-by-slice view of voxel space.
    
    Args:
        workspace: MentalWorkspace3D instance
        slice_axis: 'x', 'y', or 'z'
        slice_index: Which slice to show (None = middle)
    """
    
    print("\n" + "="*70)
    print("           🧠 MENTAL WORKSPACE (3D Simulation)")
    print("="*70)
    
    # Get workspace dimensions
    res_x, res_y, res_z = workspace.resolution
    
    # Determine slice index
    if slice_index is None:
        if slice_axis == 'x':
            slice_index = res_x // 2
        elif slice_axis == 'y':
            slice_index = res_y // 2
        else:
            slice_index = res_z // 2
    
    # Extract slice
    if slice_axis == 'y':
        # Top-down view (most useful for games)
        print(f"\nTop-down view (y={slice_index}):\n")
        
        # Build slice from objects
        slice_grid = [[' ' for _ in range(res_x)] for _ in range(res_z)]
        
        for obj in workspace.objects:
            x, y, z = obj['position']
            x, y, z = int(x), int(y), int(z)
            
            # Check if in this slice (with tolerance)
            if abs(y - slice_index) <= 1:
                if 0 <= x < res_x and 0 <= z < res_z:
                    obj_type = obj.get('type', 'unknown')
                    
                    # Choose symbol based on type
                    if 'block' in obj_type:
                        symbol = '█'
                    elif 'entity' in obj_type or 'agent' in obj_type:
                        symbol = '▓'
                    elif 'item' in obj_type:
                        symbol = '•'
                    else:
                        symbol = '▪'
                    
                    slice_grid[z][x] = symbol
        
        # Print slice
        print("   +" + "-" * res_x + "+")
        for row in slice_grid:
            print("   |" + "".join(row) + "|")
        print("   +" + "-" * res_x + "+")
        
        print(f"\nLegend: █=block ▓=entity •=item  =empty")
    
    elif slice_axis == 'x':
        # Side view
        print(f"\nSide view (x={slice_index}):\n")
        
        slice_grid = [[' ' for _ in range(res_z)] for _ in range(res_y)]
        
        for obj in workspace.objects:
            x, y, z = obj['position']
            x, y, z = int(x), int(y), int(z)
            
            if abs(x - slice_index) <= 1:
                if 0 <= y < res_y and 0 <= z < res_z:
                    slice_grid[res_y - 1 - y][z] = '█'
        
        print("   +" + "-" * res_z + "+")
        for row in slice_grid:
            print("   |" + "".join(row) + "|")
        print("   +" + "-" * res_z + "+")
    
    # Print objects list
    print(f"\nObjects in workspace: {len(workspace.objects)}")
    if workspace.objects:
        print("\nDetailed objects:")
        for i, obj in enumerate(workspace.objects[:10]):  # Show first 10
            pos = obj['position']
            obj_type = obj.get('type', 'unknown')
            props = obj.get('properties', {})
            
            print(f"  [{i}] {obj_type} at ({pos[0]:.1f}, {pos[1]:.1f}, {pos[2]:.1f})")
            if props:
                print(f"      Properties: {props}")
        
        if len(workspace.objects) > 10:
            print(f"  ... and {len(workspace.objects) - 10} more")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# CAUSAL GRAPH VISUALIZATION
# ============================================================================

def visualize_causal_chain_cli(causal_graph, effect: str, max_depth: int = 5):
    """
    Visualize causal chain in terminal.
    Shows why something happened (backward trace).
    """
    
    print("\n" + "="*70)
    print("           🔗 CAUSAL CHAIN ANALYSIS")
    print("="*70)
    
    print(f"\nAnalyzing: {effect}")
    print("-" * 70)
    
    # Trace causes
    causes = causal_graph.find_root_causes(effect, max_depth=max_depth)
    
    if not causes:
        print("\n⚠️  No causal chain found (not enough experience)")
    else:
        print("\nRoot causes found:")
        
        # Build tree structure
        def print_causes_tree(node_id, depth=0, visited=None):
            if visited is None:
                visited = set()
            
            if node_id in visited or depth > max_depth:
                return
            
            visited.add(node_id)
            
            # Print current node
            indent = "  " * depth
            arrow = "└─ " if depth > 0 else ""
            
            node = causal_graph.nodes.get(node_id)
            if node:
                print(f"{indent}{arrow}{node_id} ({node.type})")
                
                # Print child causes
                for cause_id in node.causes:
                    print_causes_tree(cause_id, depth + 1, visited)
        
        print_causes_tree(effect)
    
    # Show statistics
    print("\n" + "-" * 70)
    print(f"Total causal nodes: {len(causal_graph.nodes)}")
    print(f"Total interventions recorded: {len(causal_graph.intervention_results)}")
    
    print("\n" + "="*70 + "\n")


def visualize_causal_prediction_cli(causal_graph, action: str, horizon: int = 3):
    """
    Visualize predicted effects of an action.
    Shows forward prediction: What will happen if I do X?
    """
    
    print("\n" + "="*70)
    print("           🔮 CAUSAL PREDICTION")
    print("="*70)
    
    print(f"\nIf agent does: {action}")
    print("-" * 70)
    
    # Predict effects
    effects = causal_graph.predict_effects(action, max_depth=horizon)
    
    if not effects:
        print("\n⚠️  No predictions available (action not learned)")
    else:
        print("\nPredicted effects:")
        
        for i, effect in enumerate(effects, 1):
            node = causal_graph.nodes.get(effect)
            if node:
                confidence = "high" if len(node.causes) > 2 else "medium"
                print(f"  {i}. {effect} (confidence: {confidence})")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# LOGICAL STATE VISUALIZATION
# ============================================================================

def visualize_logical_state_cli(logic_engine):
    """
    Visualize logical knowledge base in terminal.
    Shows facts, rules, and deduction capabilities.
    """
    
    print("\n" + "="*70)
    print("           📚 LOGICAL KNOWLEDGE BASE")
    print("="*70)
    
    # Facts
    print(f"\nKnown Facts ({len(logic_engine.facts)}):")
    print("-" * 70)
    
    if logic_engine.facts:
        for i, fact in enumerate(list(logic_engine.facts)[:20], 1):  # Show first 20
            confidence_bar = "█" * int(fact.confidence * 10)
            print(f"  {i}. {fact.predicate}({', '.join(fact.arguments)})")
            print(f"     Confidence: {confidence_bar} {fact.confidence:.2f}")
        
        if len(logic_engine.facts) > 20:
            print(f"  ... and {len(logic_engine.facts) - 20} more")
    else:
        print("  (No facts learned yet)")
    
    # Rules
    print(f"\nLogical Rules ({len(logic_engine.rules)}):")
    print("-" * 70)
    
    if logic_engine.rules:
        for i, rule in enumerate(logic_engine.rules[:10], 1):  # Show first 10
            # Format premise
            premise_str = " AND ".join([
                f"{f.predicate}({', '.join(f.arguments)})" 
                for f in rule.premise
            ])
            
            # Format conclusion
            conclusion_str = f"{rule.conclusion.predicate}({', '.join(rule.conclusion.arguments)})"
            
            print(f"  {i}. IF {premise_str}")
            print(f"     THEN {conclusion_str}")
            print(f"     Strength: {rule.strength:.2f}")
            print()
        
        if len(logic_engine.rules) > 10:
            print(f"  ... and {len(logic_engine.rules) - 10} more")
    else:
        print("  (No rules learned yet)")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# UNIFIED REASONING DASHBOARD
# ============================================================================

def show_reasoning_dashboard(brain):
    """
    Complete reasoning state dashboard.
    Shows all reasoning systems in one view.
    """
    
    if not hasattr(brain, 'reasoning'):
        print("\n⚠️  Reasoning not enabled. Call add_reasoning_to_brain(brain) first.\n")
        return
    
    reasoning = brain.reasoning
    
    # Header
    print("\n" + "="*70)
    print("           🧠 COMPLETE REASONING DASHBOARD")
    print("="*70)
    
    # Stats overview
    stats = reasoning.get_reasoning_stats()
    
    print("\n📊 Overview:")
    print("-" * 70)
    print(f"  Mental Objects: {stats['workspace_objects']}")
    print(f"  Causal Nodes: {stats['causal_nodes']}")
    print(f"  Logical Facts: {stats['known_facts']}")
    print(f"  Logical Rules: {stats['logical_rules']}")
    print(f"  Current Mode: {stats['current_mode']}")
    
    # Detailed views
    print("\n" + "="*70)
    print("\n[1] Mental Workspace")
    visualize_workspace_3d_cli(reasoning.mental_workspace)
    
    print("\n[2] Causal Understanding")
    print("  (Use visualize_causal_chain_cli for specific analysis)")
    
    print("\n[3] Logical Knowledge")
    visualize_logical_state_cli(reasoning.logic_engine)
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# INTERACTIVE CLI TOOLS
# ============================================================================

def interactive_reasoning_cli(brain):
    """
    Interactive CLI for exploring agent reasoning.
    User can query mental state, test predictions, etc.
    """
    
    if not hasattr(brain, 'reasoning'):
        print("\n⚠️  Reasoning not enabled.\n")
        return
    
    print("\n" + "="*70)
    print("           🎮 INTERACTIVE REASONING EXPLORER")
    print("="*70)
    print("\nCommands:")
    print("  workspace   - Show mental workspace")
    print("  causal <X>  - Show causal chain for X")
    print("  predict <X> - Predict effects of action X")
    print("  logic       - Show logical knowledge")
    print("  stats       - Show reasoning statistics")
    print("  dashboard   - Show complete dashboard")
    print("  quit        - Exit")
    print("\n" + "="*70 + "\n")
    
    while True:
        try:
            cmd = input("reasoning> ").strip().lower()
            
            if not cmd:
                continue
            
            if cmd == 'quit' or cmd == 'exit':
                break
            
            elif cmd == 'workspace':
                visualize_workspace_3d_cli(brain.reasoning.mental_workspace)
            
            elif cmd.startswith('causal '):
                effect = cmd.split(' ', 1)[1]
                visualize_causal_chain_cli(brain.reasoning.causal_graph, effect)
            
            elif cmd.startswith('predict '):
                action = cmd.split(' ', 1)[1]
                visualize_causal_prediction_cli(brain.reasoning.causal_graph, action)
            
            elif cmd == 'logic':
                visualize_logical_state_cli(brain.reasoning.logic_engine)
            
            elif cmd == 'stats':
                stats = brain.reasoning.get_reasoning_stats()
                print("\n📊 Reasoning Stats:")
                for key, value in stats.items():
                    print(f"  {key}: {value}")
                print()
            
            elif cmd == 'dashboard':
                show_reasoning_dashboard(brain)
            
            else:
                print(f"Unknown command: {cmd}")
        
        except KeyboardInterrupt:
            print("\n")
            break
        except Exception as e:
            print(f"Error: {e}")


# ============================================================================
# EXPORT
# ============================================================================

__all__ = [
    'visualize_workspace_3d_cli',
    'visualize_causal_chain_cli',
    'visualize_causal_prediction_cli',
    'visualize_logical_state_cli',
    'show_reasoning_dashboard',
    'interactive_reasoning_cli'
]


# ============================================================================
# CLI DEMO
# ============================================================================

if __name__ == "__main__":
    print("\n🧪 Testing reasoning visualizer...\n")
    
    from ai_core.reasoning_core import MentalWorkspace3D, CausalGraph, LogicEngine
    
    # Test workspace viz
    workspace = MentalWorkspace3D(resolution=(16, 16, 16))
    workspace.add_object({'type': 'block', 'position': (5, 8, 7)})
    workspace.add_object({'type': 'entity', 'position': (8, 8, 9)})
    workspace.add_object({'type': 'item', 'position': (3, 8, 4)})
    
    visualize_workspace_3d_cli(workspace)
    
    # Test causal viz
    causal = CausalGraph()
    causal.add_node('action:attack', 'action')
    causal.add_node('result:damage', 'result')
    causal.add_node('result:retaliation', 'result')
    causal.add_edge('action:attack', 'result:damage')
    causal.add_edge('result:damage', 'result:retaliation')
    
    visualize_causal_chain_cli(causal, 'result:retaliation')
    visualize_causal_prediction_cli(causal, 'action:attack')
    
    # Test logic viz
    logic = LogicEngine()
    logic.add_fact('is_hungry', confidence=0.9)
    logic.add_fact('has_food', confidence=1.0)
    logic.add_rule([('is_hungry',), ('has_food',)], ('should_eat',))
    
    visualize_logical_state_cli(logic)
    
    print("\n✅ All visualizations working!\n")