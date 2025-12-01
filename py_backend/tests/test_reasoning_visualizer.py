"""
Ultra-lightweight CLI-only reasoning visualizer.
No OpenGL, no GPU, runs on old CPUs.

This replaces:
 - visualize_workspace_3d_cli
 - visualize_causal_chain_cli
 - visualize_causal_prediction_cli
 - visualize_logical_state_cli
 - show_reasoning_dashboard

Everything now prints using ASCII blocks.
"""

import sys
import os

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(PROJECT_ROOT)

import logging
logging.basicConfig(level=logging.INFO)


# -------------------------------------------------------------------
# ASCII RENDER HELPERS
# -------------------------------------------------------------------

def ascii_bar(label, value, max_val=1.0, width=30):
    """Render a small horizontal bar."""
    filled = int(width * min(value, max_val))
    empty = width - filled
    return f"{label:<12} [{'#' * filled}{'.' * empty}] {value:.2f}"


def ascii_box(title, content):
    """Render a boxed section."""
    lines = content.strip().split("\n")
    width = max(len(title), *(len(l) for l in lines)) + 4
    top = "┌" + "─" * width + "┐"
    bot = "└" + "─" * width + "┘"
    mid = f"│ {title:<{width-2}} │"
    body = "\n".join(f"│ {l:<{width-2}} │" for l in lines)
    return f"{top}\n{mid}\n{body}\n{bot}"


# -------------------------------------------------------------------
# ASCII VISUALIZERS
# -------------------------------------------------------------------

def visualize_workspace_3d_cli(workspace):
    """Simple ASCII representation of the 3D mental workspace."""
    out = []
    out.append("Workspace3D Objects:")
    for obj in workspace.objects:
        out.append(f" - {obj['type']} @ {obj['position']}")

    print(ascii_box("3D WORKSPACE", "\n".join(out)))


def visualize_causal_chain_cli(causal_graph, target):
    """Follow chain backwards from the target node."""
    if target not in causal_graph.nodes:
        print(ascii_box("CAUSAL CHAIN", "Target node not found."))
        return

    chain = []
    current = target
    visited = set()

    while current and current not in visited:
        visited.add(current)
        chain.append(current)
        # find any parent that leads to this node
        parent = None
        for node, data in causal_graph.nodes.items():
            if current in data.effects:
                parent = node
                break
        current = parent

    chain_display = " -> ".join(chain[::-1])
    print(ascii_box("CAUSAL CHAIN", chain_display))


def visualize_causal_prediction_cli(causal_graph, source):
    """Predict what effects source will cause."""
    if source not in causal_graph.nodes:
        print(ascii_box("CAUSAL PREDICTION", "Source node not found."))
        return

    effects = causal_graph.nodes[source].effects
    if not effects:
        body = "No predicted effects."
    else:
        body = "\n".join(f" - {e}" for e in effects)

    print(ascii_box(f"PREDICTION FROM {source}", body))


def visualize_logical_state_cli(logic):
    """Show facts & rules with bar confidence."""
    out = []

    out.append("FACTS:")
    if not logic.facts:
        out.append(" (none)")
    else:
        for fact, conf in logic.facts.items():
            out.append(ascii_bar(fact, conf))

    out.append("\nRULES:")
    if not logic.rules:
        out.append(" (none)")
    else:
        for r in logic.rules:
            p = ", ".join(x[0] for x in r["premise"])
            c = r["conclusion"][0]
            out.append(f" IF {p} ⇒ {c} (str={r['strength']})")

    print(ascii_box("LOGIC ENGINE STATE", "\n".join(out)))


def show_reasoning_dashboard(brain):
    """Full combined display."""
    r = brain.reasoning
    body = [
        f"Workspace objects: {len(r.mental_workspace.objects)}",
        f"Causal nodes:      {len(r.causal_graph.nodes)}",
        f"Facts:             {len(r.logic_engine.facts)}",
        f"Rules:             {len(r.logic_engine.rules)}",
        f"Mode:              test"
    ]
    print(ascii_box("REASONING DASHBOARD", "\n".join(body)))


# -------------------------------------------------------------------
# BELOW THIS IS YOUR SAME TEST CODE (UNCHANGED)
# -------------------------------------------------------------------

from ai_core.reasoning_core import (
    MentalWorkspace3D,
    CausalGraph,
    LogicEngine
)


class TestBrain:
    def __init__(self):
        self.reasoning = TestReasoning()


class TestReasoning:
    def __init__(self):
        self.mental_workspace = MentalWorkspace3D(resolution=(16, 16, 16))
        self.mental_workspace.add_object({'type': 'block', 'position': (5, 8, 7)})
        self.mental_workspace.add_object({'type': 'entity', 'position': (8, 8, 9)})
        self.mental_workspace.add_object({'type': 'item', 'position': (3, 8, 4)})

        self.causal_graph = CausalGraph()
        self.causal_graph.add_node('action:attack', 'action')
        self.causal_graph.add_node('result:damage', 'result')
        self.causal_graph.add_node('result:retaliation', 'result')
        self.causal_graph.add_edge('action:attack', 'result:damage')
        self.causal_graph.add_edge('result:damage', 'result:retaliation')

        self.logic_engine = LogicEngine()
        self.logic_engine.add_fact('is_hungry', confidence=0.9)
        self.logic_engine.add_fact('has_food', confidence=1.0)

        self.logic_engine.add_rule(
            [('is_hungry', ()), ('has_food', ())],
            ('should_eat', ()),
            strength=0.8
        )

    def get_reasoning_stats(self):
        return {
            'workspace_objects': len(self.mental_workspace.objects),
            'causal_nodes': len(self.causal_graph.nodes),
            'known_facts': len(self.logic_engine.facts),
            'logical_rules': len(self.logic_engine.rules),
            'current_mode': 'test'
        }


def count_causal_edges(causal_graph):
    total = 0
    for n in causal_graph.nodes.values():
        total += len(n.effects)
    return total


if __name__ == '__main__':
    print("\n🧪 Testing ASCII reasoning visualizer...\n")

    brain = TestBrain()
    reasoning = brain.reasoning

    visualize_workspace_3d_cli(reasoning.mental_workspace)
    visualize_causal_chain_cli(reasoning.causal_graph, 'result:retaliation')
    visualize_causal_prediction_cli(reasoning.causal_graph, 'action:attack')
    visualize_logical_state_cli(reasoning.logic_engine)
    show_reasoning_dashboard(brain)

    stats = reasoning.get_reasoning_stats()
    print("\nSUMMARY:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print(f"Causal edges: {count_causal_edges(reasoning.causal_graph)}")
    print("\n✔ Test completed.\n")
