# ai_core/brain_capsule.py
"""
Brain capsule — serialisable agent state container.
=====================================================
Handles everything agent.save() / agent.load() needs:

  Subsystem               Saved field
  ─────────────────────── ──────────────────────────────────────
  Personality             personality       (dict)
  EmotionSystem           emotion_snapshot  (dict[str, float])
  Memory                  memory_snapshot   (list[dict])
  LanguageModel           language_state    (state_dict via brain.language)
  Policy / WorldModel /
    Vision (nn.Module)    model_state       (nested dict of tensors)
  RewardSystem (RND/ICM)  model_state       (under key 'reward_system')
  Agent metadata          metadata          (step_count, agent_type, …)
  God type                metadata          (under key 'god_type')

Format
------
Primary file : <base>.pcap           — torch.save(dict)  (handles tensors)
Sidecar      : <base>.pcap.json      — human-readable summary (no tensors)

Legacy fallback (read-only): <base>.pcap.json + <base>.pcap.torch
"""

import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import torch
import logging

log = logging.getLogger("brain_capsule")


@dataclass
class BrainCapsule:
    """Serialisable brain state container."""

    metadata: Dict[str, Any]
    model_state: Optional[Dict[str, Any]] = None      # policy, world_model, vision, reward_system
    personality: Optional[Dict[str, Any]] = None
    memory_snapshot: Optional[List[Dict[str, Any]]] = None
    emotion_snapshot: Optional[Dict[str, float]] = None
    language_state: Optional[Dict[str, Any]] = None   # brain.language state_dict

    # Biological state — needed so agents resume with correct gender and
    # pregnancy after restart (breeding system reads these on load).
    gender: Optional[str] = None                        # 'male' | 'female' | 'dual'
    pregnancy_state: Optional[Dict[str, Any]] = None   # PregnancyData serialised, or None

    # ------------------------------------------------------------------
    # Save
    # ------------------------------------------------------------------

    def save(self, path: str):
        """
        Atomically write to <base>.pcap and <base>.pcap.json.

        Uses torch.save so nested tensors (policy weights, world model,
        RND/ICM networks) are stored correctly without manual extraction.
        Atomic write (tmp → rename) prevents corruption on crash.
        """
        base      = os.path.splitext(path)[0]
        pcap_path = base + '.pcap'
        tmp_path  = pcap_path + '.tmp'

        os.makedirs(
            os.path.dirname(base) if os.path.dirname(base) else '.',
            exist_ok=True,
        )

        try:
            torch.save({
                'metadata':         self.metadata,
                'model_state':      self.model_state,
                'personality':      self.personality,
                'memory_snapshot':  self.memory_snapshot,
                'emotion_snapshot': self.emotion_snapshot,
                'language_state':   self.language_state,
                'gender':           self.gender,
                'pregnancy_state':  self.pregnancy_state,
            }, tmp_path)

            if os.path.exists(pcap_path):
                os.remove(pcap_path)
            os.rename(tmp_path, pcap_path)

            log.info(f"✅ Brain saved: {pcap_path} ({os.path.getsize(pcap_path):,} bytes)")

        except Exception as e:
            log.error(f"❌ Failed to save brain: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

        # Human-readable sidecar (no tensors)
        json_path = base + '.pcap.json'
        try:
            with open(json_path, 'w') as f:
                f.write(self._to_json())
        except Exception as e:
            log.warning(f"⚠️  Failed to write sidecar JSON: {e}")

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    @staticmethod
    def load(path: str) -> "BrainCapsule":
        """
        Load from disk.

        Priority:
          1. <base>.pcap          — current format (torch.save)
          2. <base>.pcap.json     — legacy JSON + optional <base>.pcap.torch

        Raises FileNotFoundError if nothing is found.
        """
        base      = os.path.splitext(path)[0]
        pcap_file = base + '.pcap'

        # ── Current format ────────────────────────────────────────────
        if os.path.exists(pcap_file):
            try:
                # weights_only=False required: we store non-tensor objects
                # (dicts, lists, strings) alongside tensors in the same file.
                data = torch.load(pcap_file, map_location='cpu', weights_only=False)
                log.info(f"✅ Brain loaded: {pcap_file}")
                return BrainCapsule(
                    metadata         = data.get('metadata', {}),
                    model_state      = data.get('model_state'),
                    personality      = data.get('personality'),
                    memory_snapshot  = data.get('memory_snapshot'),
                    emotion_snapshot = data.get('emotion_snapshot'),
                    language_state   = data.get('language_state'),
                    gender           = data.get('gender'),
                    pregnancy_state  = data.get('pregnancy_state'),
                )
            except Exception as e:
                log.error(f"❌ Failed to load .pcap: {e}")
                # Fall through to legacy

        # ── Legacy format ─────────────────────────────────────────────
        json_file = base + '.pcap.json'
        if os.path.exists(json_file):
            log.warning("Loading legacy JSON format — re-save to upgrade.")
            try:
                with open(json_file, 'r') as f:
                    json_data = json.load(f)

                capsule = BrainCapsule(
                    metadata         = json_data.get('metadata', {}),
                    personality      = json_data.get('personality'),
                    emotion_snapshot = json_data.get('emotion_snapshot'),
                    memory_snapshot  = json_data.get('memory_snapshot'),
                    language_state   = json_data.get('language_state'),
                    gender           = json_data.get('gender'),
                    pregnancy_state  = json_data.get('pregnancy_state'),
                )

                torch_file = base + '.pcap.torch'
                if os.path.exists(torch_file):
                    capsule.model_state = torch.load(
                        torch_file, map_location='cpu', weights_only=False
                    )

                return capsule
            except Exception as e:
                log.error(f"❌ Failed to load legacy brain: {e}")

        raise FileNotFoundError(f"No valid brain capsule found at: {path}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_json(self) -> str:
        """
        Human-readable JSON summary.  Never includes tensors or large blobs —
        those live in the .pcap file only.
        """
        ms = self.model_state or {}

        # Summarise what neural components were saved
        saved_components = [k for k in ('policy', 'world_model', 'vision', 'reward_system')
                            if k in ms]

        # Language summary when present
        lang_summary = None
        if self.language_state:
            lang_summary = {
                'stage':           self.language_state.get('language_stage', 0),
                'vocabulary_size': self.language_state.get('vocabulary_size', 0),
                'patterns':        self.language_state.get('pattern_count', 0),
            }

        payload: Dict[str, Any] = {
            'metadata':          self.metadata,
            'personality':       self.personality,
            'emotion_snapshot':  self.emotion_snapshot,
            'memory_events':     len(self.memory_snapshot) if self.memory_snapshot else 0,
            'saved_components':  saved_components,
            'has_language':      self.language_state is not None,
            'gender':            self.gender,
            'is_pregnant':       self.pregnancy_state is not None,
        }
        if lang_summary:
            payload['language_summary'] = lang_summary

        return json.dumps(payload, indent=2, default=str)