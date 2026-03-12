# ai_core/audio_processor.py
"""
Audio Processing Module for Autonomous AI Agents
=================================================
Real-time audio capture, transcription, and feature extraction.

Design alignment with brain_core / reward_system
-------------------------------------------------
- process_audio_chunk() no longer hardcodes emotion detection heuristics.
  Audio events are routed through brain.evaluate_event() so the full
  RewardSystem pipeline (personality weights, curiosity, emotion deltas,
  personality pressure) handles how hearing something feels to THIS agent.
- detect_emotion() is kept as a lightweight signal source — its output
  is passed as payload data into the reward event, not applied directly
  to emotion_system.
- The cognitive loop drives when listening starts/stops via
  brain.should_listen() (checked in _think) — AudioProcessor is a tool,
  not a decision maker.
"""

import numpy as np
import logging
from typing import Dict, Any, Optional
from collections import deque
import time

log = logging.getLogger("audio_processor")

# ── Optional dependency guards ────────────────────────────────────────────────

try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    log.warning("pyaudio not available — install with: pip install pyaudio")

try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    log.warning("speech_recognition not available — install with: pip install SpeechRecognition")

try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    log.warning("librosa not available — install with: pip install librosa")


# ============================================================================
# Audio capture
# ============================================================================

class AudioCapture:
    """Real-time audio capture from microphone via PyAudio."""

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        if not PYAUDIO_AVAILABLE:
            raise RuntimeError("pyaudio required: pip install pyaudio")

        self.sample_rate  = sample_rate
        self.chunk_size   = chunk_size
        self.audio        = pyaudio.PyAudio()
        self.stream       = None
        self.is_recording = False
        self.audio_buffer = deque(maxlen=100)   # ~6 seconds at 16 kHz
        log.info(f"AudioCapture initialised: {sample_rate}Hz chunk={chunk_size}")

    def start_recording(self):
        if self.is_recording:
            return
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback,
        )
        self.stream.start_stream()
        self.is_recording = True
        log.info("🎤 Audio recording started")

    def stop_recording(self):
        if not self.is_recording:
            return
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.is_recording = False
        log.info("🛑 Audio recording stopped")

    def _audio_callback(self, in_data, frame_count, time_info, status):
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        self.audio_buffer.append(audio_data)
        return (in_data, pyaudio.paContinue)

    def get_audio_chunk(self, duration: float = 3.0) -> Optional[np.ndarray]:
        if not self.audio_buffer:
            return None
        chunks_needed = int((duration * self.sample_rate) / self.chunk_size)
        chunks_needed = min(chunks_needed, len(self.audio_buffer))
        if chunks_needed == 0:
            return None
        recent = list(self.audio_buffer)[-chunks_needed:]
        return np.concatenate(recent)

    def close(self):
        self.stop_recording()
        self.audio.terminate()


# ============================================================================
# Speech recognition
# ============================================================================

class SpeechRecognizer:
    """Speech-to-text via Google Speech Recognition (offline models optional)."""

    def __init__(self):
        if not SPEECH_RECOGNITION_AVAILABLE:
            raise RuntimeError(
                "speech_recognition required: pip install SpeechRecognition"
            )
        self.recognizer      = sr.Recognizer()
        self.noise_adjusted  = False
        log.info("SpeechRecognizer initialised")

    def transcribe(self, audio_data: np.ndarray,
                   sample_rate: int = 16000) -> Optional[str]:
        try:
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            audio       = sr.AudioData(audio_bytes, sample_rate, 2)

            if not self.noise_adjusted:
                self.recognizer.adjust_for_ambient_noise(audio, duration=0.5)
                self.noise_adjusted = True

            return self.recognizer.recognize_google(audio)

        except sr.UnknownValueError:
            return None   # speech not understood — not an error
        except sr.RequestError as e:
            log.error(f"Speech recognition API error: {e}")
            return None
        except Exception as e:
            log.error(f"Transcription error: {e}")
            return None


# ============================================================================
# Audio feature extractor
# ============================================================================

class AudioFeatureExtractor:
    """
    Extract acoustic features from raw audio.

    Output is used as payload data in brain.evaluate_event() — the
    RewardSystem decides how to feel about what was heard based on the
    agent's personality. detect_emotion() provides a lightweight label
    that enriches the event payload but does NOT directly update emotions.
    """

    def extract_features(self, audio_data: np.ndarray,
                          sample_rate: int = 16000) -> Dict[str, Any]:
        features: Dict[str, Any] = {}

        if not LIBROSA_AVAILABLE:
            features['volume'] = float(np.abs(audio_data).mean())
            features['peak']   = float(np.abs(audio_data).max())
            return features

        try:
            af = audio_data.astype(np.float32) / 32767.0

            features['volume'] = float(librosa.feature.rms(y=af).mean())
            features['zcr']    = float(
                librosa.feature.zero_crossing_rate(af).mean()
            )

            sc = librosa.feature.spectral_centroid(y=af, sr=sample_rate)
            features['spectral_centroid'] = float(sc.mean())

            pitches, magnitudes = librosa.piptrack(y=af, sr=sample_rate)
            pitch = pitches[
                magnitudes.argmax(axis=0),
                np.arange(magnitudes.shape[1]),
            ]
            active = pitch[pitch > 0]
            features['pitch_mean'] = float(active.mean()) if len(active) > 0 else 0.0

            tempo, _ = librosa.beat.beat_track(y=af, sr=sample_rate)
            features['tempo'] = float(tempo)

        except Exception as e:
            log.error(f"Feature extraction error: {e}")

        return features

    def detect_emotion(self, features: Dict[str, Any]) -> str:
        """
        Heuristic acoustic emotion label.

        This is a SIGNAL SOURCE for the reward event payload — it tells
        the brain something about the emotional tone of what was heard.
        The agent's own emotional RESPONSE is computed by the RewardSystem
        based on personality weights, not by this function.
        """
        volume = features.get('volume',     0.0)
        pitch  = features.get('pitch_mean', 0.0)
        tempo  = features.get('tempo',      0.0)

        if volume > 0.3 and pitch > 200:
            return 'excited' if tempo > 100 else 'angry'
        if volume < 0.1 and pitch < 150:
            return 'sad' if tempo < 80 else 'calm'
        return 'neutral'


# ============================================================================
# AudioProcessor — main integration class
# ============================================================================

class AudioProcessor:
    """
    Complete audio processing pipeline for AI agents.

    process_audio_chunk() routes audio events through brain.evaluate_event()
    so the full RewardSystem handles how hearing something affects the agent —
    personality-weighted, curiosity-aware, emotion-updating — exactly like any
    other agent experience.
    """

    def __init__(self, agent):
        self.agent = agent

        self.capture           = None
        self.recognizer        = None
        self.feature_extractor = AudioFeatureExtractor()

        try:
            self.capture = AudioCapture()
        except Exception as e:
            log.warning(f"Audio capture not available: {e}")

        try:
            self.recognizer = SpeechRecognizer()
        except Exception as e:
            log.warning(f"Speech recognition not available: {e}")

        self.is_listening             = False
        self.last_transcription_time  = 0.0
        self.transcription_cooldown   = 3.0   # seconds between transcriptions

        self.stats = {
            'total_transcriptions':      0,
            'successful_transcriptions': 0,
            'words_heard':               0,
            'last_heard':                None,
        }

        log.info(f"AudioProcessor initialised for {agent.agent_id}")

    # ── Listening control ─────────────────────────────────────────────────

    def start_listening(self) -> bool:
        if not self.capture:
            log.error("Audio capture not available")
            return False
        if self.is_listening:
            return True
        self.capture.start_recording()
        self.is_listening = True
        log.info(f"🎤 {self.agent.agent_id} started listening")
        return True

    def stop_listening(self):
        if not self.is_listening:
            return
        if self.capture:
            self.capture.stop_recording()
        self.is_listening = False
        log.info(f"🛑 {self.agent.agent_id} stopped listening")

    # ── Audio processing ──────────────────────────────────────────────────

    def process_audio_chunk(self,
                             duration: float = 3.0) -> Optional[Dict[str, Any]]:
        """
        Process a recent audio chunk.

        Key change from original
        ────────────────────────
        Audio events are now routed through brain.evaluate_event() so the
        RewardSystem computes how hearing this affects the agent — personality-
        weighted curiosity, emotion deltas, personality pressure — exactly the
        same pipeline as visual, action, and language events.

        Returns a result dict for the cognitive loop, or None if nothing heard.
        """
        if not self.is_listening or not self.capture:
            return None

        now = time.time()
        if now - self.last_transcription_time < self.transcription_cooldown:
            return None

        audio_data = self.capture.get_audio_chunk(duration)
        if audio_data is None:
            return None

        result: Dict[str, Any] = {
            'timestamp':     now,
            'transcription': None,
            'features':      {},
            'emotion_label': None,   # renamed from 'emotion' to clarify it's a label
        }

        # ── Feature extraction ────────────────────────────────────────────
        features = self.feature_extractor.extract_features(
            audio_data,
            self.capture.sample_rate if self.capture else 16000,
        )
        result['features'] = features

        # Acoustic emotion label (payload data, not direct emotion update)
        emotion_label          = self.feature_extractor.detect_emotion(features)
        result['emotion_label'] = emotion_label

        # ── Transcription (only if volume suggests speech) ────────────────
        transcription = None
        if features.get('volume', 0.0) > 0.05 and self.recognizer:
            transcription = self.recognizer.transcribe(
                audio_data,
                self.capture.sample_rate if self.capture else 16000,
            )
            self.stats['total_transcriptions'] += 1
            if transcription:
                self.stats['successful_transcriptions'] += 1
                self.stats['words_heard'] += len(transcription.split())
                self.stats['last_heard']   = transcription
                result['transcription']    = transcription
                log.info(f"🎤 Heard: \"{transcription}\"")

        # ── Route through brain.evaluate_event() ─────────────────────────
        # evaluate_event is self-contained: RewardSystem or table fallback
        # handles all emotion and personality updates internally.
        event = {
            'type': 'audio_input',
            'tags': ['audio', 'perception',
                     'speech' if transcription else 'ambient'],
            'payload': {
                'volume':        features.get('volume', 0.0),
                'pitch':         features.get('pitch_mean', 0.0),
                'emotion_label': emotion_label,
                'has_speech':    transcription is not None,
                'word_count':    len(transcription.split()) if transcription else 0,
            },
        }

        try:
            self.agent.brain.evaluate_event(event)
        except Exception as e:
            log.debug(f"Audio event evaluation failed: {e}")

        # ── Store in memory ───────────────────────────────────────────────
        # Only store if there's something worth remembering
        if transcription or emotion_label not in ('neutral', None):
            self.agent.memory.remember({
                'type':          'audio_input',
                'transcription': transcription,
                'emotion_label': emotion_label,
                'features':      features,
                'timestamp':     now,
                # Include text for language learning
                'text':          transcription or '',
            }, tags=['audio', 'perception', 'speech' if transcription else 'ambient'])

        self.last_transcription_time = now
        return result

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            'is_listening':   self.is_listening,
            'has_capture':    self.capture    is not None,
            'has_recognizer': self.recognizer is not None,
        }

    def close(self):
        self.stop_listening()
        if self.capture:
            self.capture.close()



# ============================================================================
# Minecraft sound adapter
# ============================================================================

# Minecraft sound category → semantic tags the RewardSystem understands
_MC_SOUND_TAGS: Dict[str, list] = {
    # Danger
    'entity.creeper':          ['audio', 'danger', 'mob'],
    'entity.skeleton':         ['audio', 'danger', 'mob'],
    'entity.zombie':           ['audio', 'danger', 'mob'],
    'entity.spider':           ['audio', 'danger', 'mob'],
    'entity.enderman':         ['audio', 'danger', 'mob'],
    'entity.wither':           ['audio', 'danger', 'mob', 'boss'],
    'entity.ender_dragon':     ['audio', 'danger', 'mob', 'boss'],
    'entity.warden':           ['audio', 'danger', 'mob', 'boss'],
    # Explosion / combat
    'entity.generic.explode':  ['audio', 'danger', 'explosion'],
    'entity.player.attack':    ['audio', 'combat'],
    'entity.player.hurt':      ['audio', 'danger', 'hurt'],
    'entity.player.death':     ['audio', 'danger', 'death'],
    # Environment
    'block.lava':              ['audio', 'danger', 'environment'],
    'ambient.cave':            ['audio', 'ambient', 'environment'],
    'weather.rain':            ['audio', 'ambient', 'environment'],
    'block.portal':            ['audio', 'ambient', 'environment'],
    # Social / neutral
    'entity.villager':         ['audio', 'social', 'speech'],
    'entity.player':           ['audio', 'social'],
    # Positive
    'entity.experience_orb':   ['audio', 'reward'],
    'block.note_block':        ['audio', 'aesthetic'],
    'music':                   ['audio', 'aesthetic'],
}

# Danger sounds that boost urgency
_DANGER_PREFIXES = (
    'entity.creeper', 'entity.wither', 'entity.ender_dragon',
    'entity.warden', 'entity.generic.explode', 'entity.player.hurt',
    'entity.player.death', 'block.lava',
)


class MinecraftSoundAdapter:
    """
    Receives structured sound events from the Minecraft mod over WebSocket
    and converts them into the same format as AudioProcessor results so the
    cognitive loop handles them identically.

    The Minecraft mod sends JSON sound events on the /ws/agent socket:
        {
          "type": "sound_event",
          "sound_id": "entity.creeper.primed",
          "volume": 0.8,
          "distance": 12.3,
          "category": "hostile",
          "position": {"x": 10, "y": 64, "z": -5}
        }

    This adapter converts them into AudioProcessor-compatible result dicts
    and routes them through brain.evaluate_event() so the full RewardSystem
    pipeline handles the emotional and learning response.

    No microphone or PyAudio required — works in any environment where the
    Minecraft mod can send WebSocket events.
    """

    # Volume threshold below which sound is too quiet to care about
    MIN_VOLUME = 0.05
    # Distance above which sound is background noise
    MAX_MEANINGFUL_DISTANCE = 30.0

    def __init__(self, agent):
        self.agent = agent
        self.stats = {
            'sounds_received':   0,
            'sounds_processed':  0,
            'danger_sounds':     0,
            'last_sound_time':   0.0,
            'last_sound_id':     None,
        }
        log.info(f"MinecraftSoundAdapter initialised for {agent.agent_id}")

    def _get_tags(self, sound_id: str, category: str) -> list:
        """Map a Minecraft sound ID to semantic tags."""
        for prefix, tags in _MC_SOUND_TAGS.items():
            if sound_id.startswith(prefix):
                return tags
        # Fallback: use category
        cat_map = {
            'hostile': ['audio', 'danger', 'mob'],
            'neutral': ['audio', 'ambient'],
            'player':  ['audio', 'social'],
            'ambient': ['audio', 'ambient', 'environment'],
            'music':   ['audio', 'aesthetic'],
            'record':  ['audio', 'aesthetic'],
            'block':   ['audio', 'ambient'],
            'master':  ['audio', 'ambient'],
        }
        return cat_map.get(category, ['audio', 'ambient'])

    def _is_danger(self, sound_id: str, category: str) -> bool:
        return (
            category == 'hostile' or
            any(sound_id.startswith(p) for p in _DANGER_PREFIXES)
        )

    def receive_sound_event(self, sound_event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process one Minecraft sound event from the mod WebSocket.

        Args:
            sound_event — dict from mod with keys:
                sound_id  (str)   e.g. 'entity.creeper.primed'
                volume    (float) 0.0-1.0 in-game volume
                distance  (float) blocks from agent
                category  (str)   Minecraft sound category
                position  (dict)  optional {x, y, z}

        Returns a result dict in the same shape as AudioProcessor.process_audio_chunk()
        or None if the sound is too quiet / far away to notice.
        """
        self.stats['sounds_received'] += 1

        sound_id = sound_event.get('sound_id', 'unknown')
        volume   = float(sound_event.get('volume',   0.0))
        distance = float(sound_event.get('distance', 0.0))
        category = sound_event.get('category', 'master')

        # Attenuate by distance (inverse square approximation)
        perceived_volume = volume / max(1.0, (distance / 5.0) ** 2)

        if perceived_volume < self.MIN_VOLUME:
            return None   # Too quiet to notice

        is_danger = self._is_danger(sound_id, category)
        tags      = self._get_tags(sound_id, category)

        if is_danger:
            self.stats['danger_sounds'] += 1

        # Synthetic features matching AudioFeatureExtractor output schema
        features = {
            'volume':           perceived_volume,
            'pitch_mean':       0.0,    # not available from mod events
            'distance':         distance,
            'in_game_volume':   volume,
        }

        # Emotion label heuristic (same role as AudioFeatureExtractor.detect_emotion)
        if is_danger:
            emotion_label = 'angry' if perceived_volume > 0.5 else 'neutral'
        elif category in ('music', 'record'):
            emotion_label = 'calm'
        elif category == 'ambient':
            emotion_label = 'calm'
        else:
            emotion_label = 'neutral'

        result = {
            'timestamp':     time.time(),
            'transcription': None,      # Minecraft sounds are not speech
            'features':      features,
            'emotion_label': emotion_label,
            'sound_id':      sound_id,
            'distance':      distance,
            'is_danger':     is_danger,
            'source':        'minecraft',
        }

        # ── Route through brain.evaluate_event() ─────────────────────────
        # Urgency modifier: danger sounds close by spike urgency payload
        urgency_hint = min(1.0, perceived_volume * (2.0 if is_danger else 0.5))

        event = {
            'type': 'audio_input',
            'tags': tags,
            'payload': {
                'volume':        perceived_volume,
                'pitch':         0.0,
                'emotion_label': emotion_label,
                'has_speech':    False,
                'word_count':    0,
                'sound_id':      sound_id,
                'distance':      distance,
                'danger':        is_danger,
                'urgency_hint':  urgency_hint,
            },
        }

        try:
            self.agent.brain.evaluate_event(event)
        except Exception as e:
            log.debug(f"Sound event evaluation failed: {e}")

        # ── Store in memory ───────────────────────────────────────────────
        if is_danger or perceived_volume > 0.3:
            self.agent.memory.remember({
                'type':          'minecraft_sound',
                'sound_id':      sound_id,
                'volume':        perceived_volume,
                'distance':      distance,
                'emotion_label': emotion_label,
                'is_danger':     is_danger,
                'timestamp':     result['timestamp'],
            }, tags=tags + ['minecraft'])

        self.stats['sounds_processed'] += 1
        self.stats['last_sound_time']   = result['timestamp']
        self.stats['last_sound_id']     = sound_id

        log.debug(
            f"🔊 Sound: {sound_id} vol={perceived_volume:.2f} "
            f"dist={distance:.1f} danger={is_danger}"
        )
        return result

    def get_stats(self) -> Dict[str, Any]:
        return dict(self.stats)


# ============================================================================
# Integration
# ============================================================================

def add_audio_processing_to_agent(agent) -> Optional[AudioProcessor]:
    """
    Attach an AudioProcessor (microphone) and a MinecraftSoundAdapter
    (in-game sounds) to *agent*.

    After this call:
      - agent.audio_processor     — microphone capture + speech recognition
      - agent.minecraft_sounds    — structured Minecraft sound event handler
      - agent.receive_minecraft_sound(event) — entry point for the mod WebSocket

    The cognitive loop controls when microphone listening starts/stops.
    Minecraft sounds arrive push-style via receive_minecraft_sound() which
    is called by the WebSocket handler in communication_protocol.py.

    Both pipelines route through brain.evaluate_event() — the RewardSystem
    handles the emotional and learning response to what the agent hears.
    """
    # Microphone pipeline (may not be available in all environments)
    processor = None
    try:
        processor             = AudioProcessor(agent)
        agent.audio_processor = processor
        log.info(f"✅ Microphone audio attached to {agent.agent_id}")
    except Exception as e:
        log.warning(f"Microphone audio not available: {e}")

    # Minecraft sound adapter (always available — no hardware required)
    mc_sounds             = MinecraftSoundAdapter(agent)
    agent.minecraft_sounds = mc_sounds

    def receive_minecraft_sound(sound_event: Dict[str, Any]) -> Optional[Dict]:
        """
        Entry point called by communication_protocol.py when the Minecraft
        mod sends a sound_event over the /ws/agent WebSocket.

        sound_event dict keys (from mod):
            sound_id  (str)   — Minecraft sound resource location
            volume    (float) — in-game volume 0.0–1.0
            distance  (float) — blocks from agent
            category  (str)   — Minecraft sound category
            position  (dict)  — optional {x, y, z}
        """
        return agent.minecraft_sounds.receive_sound_event(sound_event)

    agent.receive_minecraft_sound = receive_minecraft_sound
    log.info(f"✅ Minecraft sound adapter attached to {agent.agent_id}")

    return processor