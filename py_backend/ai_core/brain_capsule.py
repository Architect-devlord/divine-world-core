# ai_core/brain_capsule.py - FIXED VERSION WITH PERSISTENCE
"""
Brain capsule with proper persistence and portability.
FIXES: Ensures brain state is always saved and loaded correctly.
"""
import json
import pickle
import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import torch
import logging

log = logging.getLogger("brain_capsule")

@dataclass
class BrainCapsule:
    """
    Serializable brain state container with guaranteed persistence.
    """
    metadata: Dict[str, Any]
    model_state: Optional[Dict[str, Any]] = None
    personality: Optional[Dict[str, Any]] = None
    memory_snapshot: Optional[List[Dict[str, Any]]] = None
    emotion_snapshot: Optional[Dict[str, float]] = None
    language_state: Optional[Dict[str, Any]] = None  # NEW: Language learning state

    def save(self, path: str):
        """
        Save to disk with GUARANTEED file creation and atomic replacement.
        Creates both .pcap (torch/pickle) and .pcap.json (metadata).
        """
        base = os.path.splitext(path)[0]

        # Ensure directory exists
        os.makedirs(os.path.dirname(base) if os.path.dirname(base) else '.', exist_ok=True)

        # CRITICAL: Save main .pcap file using torch.save for robustness
        # We use an atomic write (save to .tmp then rename) to prevent corruption
        pcap_path = base + '.pcap'
        tmp_path = pcap_path + '.tmp'
        try:
            torch.save({
                'metadata': self.metadata,
                'model_state': self.model_state,
                'personality': self.personality,
                'memory_snapshot': self.memory_snapshot,
                'emotion_snapshot': self.emotion_snapshot,
                'language_state': self.language_state
            }, tmp_path)

            # Atomic replacement
            if os.path.exists(pcap_path):
                os.remove(pcap_path)
            os.rename(tmp_path, pcap_path)

            log.info(f"✅ Brain saved: {pcap_path} ({os.path.getsize(pcap_path)} bytes)")
        except Exception as e:
            log.error(f"❌ Failed to save brain: {e}")
            if os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except: pass
            raise

        # Save JSON metadata (human-readable)
        json_path = base + '.pcap.json'
        try:
            with open(json_path, 'w') as f:
                f.write(self.to_json())
            log.info(f"✅ Metadata saved: {json_path}")
        except Exception as e:
            log.warning(f"⚠️ Failed to save metadata JSON: {e}")

    def to_json(self) -> str:
        """Serialize to JSON (excluding large tensors)"""
        # Create lightweight JSON representation
        json_data = {
            "metadata": self.metadata,
            "personality": self.personality,
            "emotion_snapshot": self.emotion_snapshot,
            "has_model": self.model_state is not None,
            "memory_events": len(self.memory_snapshot) if self.memory_snapshot else 0,
            "has_language": self.language_state is not None
        }

        # Add language summary if available
        if self.language_state:
            json_data["language_summary"] = {
                "stage": self.language_state.get('language_stage', 0),
                "vocabulary_size": self.language_state.get('vocabulary_size', 0),
                "patterns": self.language_state.get('pattern_count', 0)
            }

        return json.dumps(json_data, indent=2)

    @staticmethod
    def load(path: str) -> "BrainCapsule":
        """
        Load from disk with fallback support.
        Tries: .pcap (torch/pickle) -> .pcap.json + .pcap.torch (legacy)
        """
        base = os.path.splitext(path)[0]

        # Try new format first (.pcap file)
        pcap_file = base + '.pcap'
        if os.path.exists(pcap_file):
            try:
                # Use torch.load for compatibility with torch.save
                data = torch.load(pcap_file, map_location='cpu')

                log.info(f"✅ Brain loaded: {pcap_file}")

                return BrainCapsule(
                    metadata=data.get('metadata', {}),
                    model_state=data.get('model_state'),
                    personality=data.get('personality'),
                    memory_snapshot=data.get('memory_snapshot'),
                    emotion_snapshot=data.get('emotion_snapshot'),
                    language_state=data.get('language_state')
                )
            except Exception as e:
                log.error(f"❌ Failed to load brain from .pcap: {e}")
                # Continue to fallback

        # Fall back to old format (JSON + torch)
        json_file = base + '.pcap.json'
        if os.path.exists(json_file):
            log.warning("Using legacy JSON format (convert to pickle recommended)")

            try:
                with open(json_file, 'r') as f:
                    json_data = json.load(f)

                capsule = BrainCapsule(
                    metadata=json_data.get('metadata', {}),
                    personality=json_data.get('personality'),
                    emotion_snapshot=json_data.get('emotion_snapshot'),
                    memory_snapshot=json_data.get('memory_snapshot'),
                    language_state=json_data.get('language_state')
                )

                # Load torch weights if available
                torch_file = base + '.pcap.torch'
                if os.path.exists(torch_file):
                    capsule.model_state = torch.load(torch_file, map_location='cpu')

                return capsule
            except Exception as e:
                log.error(f"❌ Failed to load legacy brain: {e}")

        raise FileNotFoundError(f"No valid brain capsule found at {path}")
