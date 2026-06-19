# py_backend/agent_runner.py
"""
Phase 7 — Per-Agent Process Entry Point
=========================================
Called by AgentProcessManager as:
    python agent_runner.py /tmp/dw_agent_alice.json

Each agent runs in complete isolation — one process, one brain, one port.
No shared memory with any other agent.

Config JSON keys:
    agent_id   str   required — unique identifier
    port       int   required — FastAPI/WS port this agent listens on
    god_type   str   optional — 'wither', 'oracle', etc. (None for NPC)
    gender     str   optional — 'male', 'female', 'dual'
    mode       str   optional — 'minecraft' | 'chat' (default: 'minecraft')
    any other keys are passed through to NPCAgent constructor
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)-8s %(name)s — %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('agent_runner')


async def _main(config: dict):
    agent_id = config['agent_id']
    port     = config.get('port', 11401)
    god_type = config.get('god_type')
    mode     = config.get('mode', 'minecraft')

    log.info(f"Starting agent '{agent_id}' | port={port} | god={god_type} | mode={mode}")

    # ── Import agent (deferred so config errors are caught early) ──────────
    try:
        from ai_core.agent import NPCAgent
    except ImportError as e:
        log.error(f"Cannot import NPCAgent: {e}")
        sys.exit(1)

    # ── Instantiate ───────────────────────────────────────────────────────
    agent = NPCAgent(
        agent_id=agent_id,
        god_type=god_type,
        **{k: v for k, v in config.items()
           if k not in ('agent_id', 'port', 'mode')},
    )
    agent.mode = mode

    # ── Attach Phase 2–5 components ───────────────────────────────────────
    # FIX Step 1: ObservationImitator removed entirely. It bolted external,
    # curiosity-gated imitation data into the CL buffer from a teacher
    # (oracle/human/other agent) — a meaning-by-label shortcut that
    # contradicts the governing principle: reward via GRPO + the
    # WorldModel's own surprise signal is the only teacher. Focus-task
    # selection now comes entirely from inside the loop (Step 8's N=5
    # curiosity+surprise streak resolving via Step 9's dual trigger —
    # specialisation signal or weakest tracked skill), never from watching
    # someone else.
    try:
        from ai_core.policy_bridge           import PolicyBridge
        from ai_core.self_supervised_trainer import SelfSupervisedTrainer, grpo_update
        from ai_core.skill_tracker           import SkillTracker

        if (hasattr(agent, 'policy') and
                hasattr(agent, 'continual_learner') and
                hasattr(agent, 'obs_dim') and
                hasattr(agent, 'action_dim')):

            agent.policy_bridge = PolicyBridge(
                transformer_policy = agent.policy,
                cl_policy_net      = agent.continual_learner.policy_net,
                obs_dim            = agent.obs_dim,
                action_dim         = agent.action_dim,
            )
            # Monkeypatch grpo_update onto the policy model — NOT added to
            # the TransformerPolicy/GodTransformerPolicy class definitions
            # themselves, which stay completely untouched.
            import types
            agent.policy.grpo_update = types.MethodType(
                lambda self, scored_actions, obs, lr=1e-4:
                    grpo_update(self, scored_actions, obs, lr),
                agent.policy,
            )

            # world_model is frequently still None here — the brain capsule
            # loads further down, after this block. SelfSupervisedTrainer
            # resolves it lazily from agent.brain.world_model on every
            # train_step() call instead of caching it once at construction.
            agent.self_supervised_trainer = SelfSupervisedTrainer(
                world_model    = agent.brain.world_model,
                brain          = agent.brain,
                emotion_system = agent.emotion,
            )

            agent.skill_tracker = SkillTracker(agent.continual_learner)

            # FIX Step 12: agent.active_focus_task is already set to None by
            # NPCAgent.__init__() (Step 6) — only set it here defensively, in
            # case an older/cached agent instance predates that change.
            if not hasattr(agent, 'active_focus_task'):
                agent.active_focus_task = None

            log.info(f"[{agent_id}] Phase 2, 3, 5 components attached ✅ (Phase 4/ObservationImitator removed)")
        else:
            log.warning(
                f"[{agent_id}] Cannot attach Phase 2/3/5 components "
                "(missing policy / continual_learner / obs_dim / action_dim)"
            )
    except ImportError as e:
        log.warning(f"[{agent_id}] Phase 2/3/5 import failed (non-fatal): {e}")

    # ── Load existing brain capsule (if any) ──────────────────────────────
    from py_backend.config import Config
    capsule_path = Config.get_agent_brain_path(agent_id)
    if capsule_path.exists():
        try:
            agent.load(str(capsule_path))
            log.info(f"[{agent_id}] Brain loaded from {capsule_path}")
        except Exception as e:
            log.warning(f"[{agent_id}] Could not load brain: {e}")
    else:
        log.info(f"[{agent_id}] No brain capsule found — starting fresh")

    # ── Start cognitive loop ───────────────────────────────────────────────
    try:
        from ai_core.cognitive_loop import CognitiveLoop
        loop = CognitiveLoop(agent)
    except ImportError as e:
        log.error(f"Cannot import CognitiveLoop: {e}")
        sys.exit(1)

    await loop.start()
    log.info(f"[{agent_id}] CognitiveLoop started on port {port}")

    # ── Keep alive + auto-save every 60 seconds ────────────────────────────
    try:
        while True:
            await asyncio.sleep(60)
            try:
                agent.save(str(capsule_path))
                log.debug(f"[{agent_id}] Brain auto-saved")
            except Exception as e:
                log.warning(f"[{agent_id}] Auto-save failed: {e}")
    except (asyncio.CancelledError, KeyboardInterrupt):
        log.info(f"[{agent_id}] Shutting down…")
        try:
            await loop.stop()
        except Exception:
            pass
        try:
            agent.save(str(capsule_path))
            log.info(f"[{agent_id}] Final brain save complete")
        except Exception as e:
            log.error(f"[{agent_id}] Final save failed: {e}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python agent_runner.py <config.json>")
        sys.exit(1)

    config_path = Path(sys.argv[1])
    if not config_path.exists():
        print(f"Config not found: {config_path}")
        sys.exit(1)

    config = json.loads(config_path.read_text())
    asyncio.run(_main(config))