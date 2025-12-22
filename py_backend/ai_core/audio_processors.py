# ai_core/audio_processor.py - Audio Processing for AI Agents
"""
Audio Processing Module for Autonomous AI Learning
===================================================
Allows AI agents to listen to and process audio input.
Features:
- Real-time audio capture
- Speech-to-text transcription
- Audio feature extraction
- Emotion detection from voice
- Integration with cognitive loop
"""

import numpy as np
import logging
from typing import Dict, Any, Optional, List
from collections import deque
import time

# Audio processing imports
try:
    import pyaudio
    import wave
    PYAUDIO_AVAILABLE = True
except ImportError:
    PYAUDIO_AVAILABLE = False
    logging.warning("pyaudio not available - install with: pip install pyaudio")

# Speech recognition
try:
    import speech_recognition as sr
    SPEECH_RECOGNITION_AVAILABLE = True
except ImportError:
    SPEECH_RECOGNITION_AVAILABLE = False
    logging.warning("speech_recognition not available - install with: pip install SpeechRecognition")

# Audio analysis
try:
    import librosa
    LIBROSA_AVAILABLE = True
except ImportError:
    LIBROSA_AVAILABLE = False
    logging.warning("librosa not available - install with: pip install librosa")

log = logging.getLogger("audio_processor")


class AudioCapture:
    """Real-time audio capture from microphone"""
    
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        if not PYAUDIO_AVAILABLE:
            raise RuntimeError("pyaudio required: pip install pyaudio")
        
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.is_recording = False
        
        # Audio buffer
        self.audio_buffer = deque(maxlen=100)  # ~6 seconds at 16kHz
        
        log.info(f"AudioCapture initialized: {sample_rate}Hz, chunk={chunk_size}")
    
    def start_recording(self):
        """Start capturing audio from microphone"""
        if self.is_recording:
            return
        
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback
        )
        
        self.stream.start_stream()
        self.is_recording = True
        log.info("🎤 Audio recording started")
    
    def stop_recording(self):
        """Stop capturing audio"""
        if not self.is_recording:
            return
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        
        self.is_recording = False
        log.info("🛑 Audio recording stopped")
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """Callback for audio stream"""
        # Convert bytes to numpy array
        audio_data = np.frombuffer(in_data, dtype=np.int16)
        self.audio_buffer.append(audio_data)
        
        return (in_data, pyaudio.paContinue)
    
    def get_audio_chunk(self, duration: float = 3.0) -> Optional[np.ndarray]:
        """Get recent audio chunk"""
        if not self.audio_buffer:
            return None
        
        # Calculate how many chunks needed
        chunks_needed = int((duration * self.sample_rate) / self.chunk_size)
        chunks_needed = min(chunks_needed, len(self.audio_buffer))
        
        if chunks_needed == 0:
            return None
        
        # Get recent chunks
        recent_chunks = list(self.audio_buffer)[-chunks_needed:]
        audio_data = np.concatenate(recent_chunks)
        
        return audio_data
    
    def close(self):
        """Close audio resources"""
        self.stop_recording()
        self.audio.terminate()


class SpeechRecognizer:
    """Speech-to-text transcription"""
    
    def __init__(self):
        if not SPEECH_RECOGNITION_AVAILABLE:
            raise RuntimeError("speech_recognition required: pip install SpeechRecognition")
        
        self.recognizer = sr.Recognizer()
        
        # Adjust for ambient noise on first run
        self.noise_adjusted = False
        
        log.info("SpeechRecognizer initialized")
    
    def transcribe(self, audio_data: np.ndarray, sample_rate: int = 16000) -> Optional[str]:
        """Transcribe audio to text"""
        try:
            # Convert numpy array to AudioData
            audio_bytes = (audio_data * 32767).astype(np.int16).tobytes()
            audio = sr.AudioData(audio_bytes, sample_rate, 2)
            
            # Adjust for ambient noise (once)
            if not self.noise_adjusted:
                self.recognizer.adjust_for_ambient_noise(audio, duration=0.5)
                self.noise_adjusted = True
            
            # Recognize speech using Google Speech Recognition
            text = self.recognizer.recognize_google(audio)
            
            return text
        
        except sr.UnknownValueError:
            # Speech not understood
            return None
        except sr.RequestError as e:
            log.error(f"Speech recognition error: {e}")
            return None
        except Exception as e:
            log.error(f"Transcription error: {e}")
            return None


class AudioFeatureExtractor:
    """Extract features from audio for analysis"""
    
    def __init__(self):
        if not LIBROSA_AVAILABLE:
            log.warning("librosa not available - feature extraction limited")
        
        self.librosa_available = LIBROSA_AVAILABLE
    
    def extract_features(self, audio_data: np.ndarray, 
                        sample_rate: int = 16000) -> Dict[str, Any]:
        """Extract audio features"""
        features = {}
        
        if not self.librosa_available:
            # Basic features without librosa
            features['volume'] = float(np.abs(audio_data).mean())
            features['peak'] = float(np.abs(audio_data).max())
            return features
        
        try:
            # Convert to float
            audio_float = audio_data.astype(np.float32) / 32767.0
            
            # Volume (RMS energy)
            features['volume'] = float(librosa.feature.rms(y=audio_float).mean())
            
            # Zero crossing rate (voice activity)
            features['zcr'] = float(librosa.feature.zero_crossing_rate(audio_float).mean())
            
            # Spectral features
            spectral_centroid = librosa.feature.spectral_centroid(y=audio_float, sr=sample_rate)
            features['spectral_centroid'] = float(spectral_centroid.mean())
            
            # Pitch (fundamental frequency)
            pitches, magnitudes = librosa.piptrack(y=audio_float, sr=sample_rate)
            pitch = pitches[magnitudes.argmax(axis=0), np.arange(magnitudes.shape[1])]
            features['pitch_mean'] = float(pitch[pitch > 0].mean()) if len(pitch[pitch > 0]) > 0 else 0.0
            
            # Tempo estimation
            tempo, _ = librosa.beat.beat_track(y=audio_float, sr=sample_rate)
            features['tempo'] = float(tempo)
            
        except Exception as e:
            log.error(f"Feature extraction error: {e}")
        
        return features
    
    def detect_emotion(self, features: Dict[str, Any]) -> str:
        """Simple emotion detection from audio features"""
        # This is a simplified heuristic model
        # In production, use a trained model
        
        volume = features.get('volume', 0)
        pitch = features.get('pitch_mean', 0)
        tempo = features.get('tempo', 0)
        
        # High volume + high pitch = excited/angry
        if volume > 0.3 and pitch > 200:
            return 'excited' if tempo > 100 else 'angry'
        
        # Low volume + low pitch = sad/calm
        if volume < 0.1 and pitch < 150:
            return 'sad' if tempo < 80 else 'calm'
        
        # Medium = neutral
        return 'neutral'


class AudioProcessor:
    """
    Complete audio processing for AI agents.
    Integrates capture, transcription, and feature extraction.
    """
    
    def __init__(self, agent):
        self.agent = agent
        
        # Components
        self.capture = None
        self.recognizer = None
        self.feature_extractor = None
        
        # Try to initialize components
        try:
            self.capture = AudioCapture()
        except Exception as e:
            log.warning(f"Audio capture not available: {e}")
        
        try:
            self.recognizer = SpeechRecognizer()
        except Exception as e:
            log.warning(f"Speech recognition not available: {e}")
        
        self.feature_extractor = AudioFeatureExtractor()
        
        # Processing state
        self.is_listening = False
        self.last_transcription_time = 0
        self.transcription_cooldown = 3.0  # seconds between transcriptions
        
        # Statistics
        self.stats = {
            'total_transcriptions': 0,
            'successful_transcriptions': 0,
            'words_heard': 0,
            'listening_time': 0,
            'last_heard': None
        }
        
        log.info(f"AudioProcessor initialized for {agent.agent_id}")
    
    def start_listening(self):
        """Start listening to audio"""
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
        """Stop listening to audio"""
        if not self.is_listening:
            return
        
        if self.capture:
            self.capture.stop_recording()
        
        self.is_listening = False
        log.info(f"🛑 {self.agent.agent_id} stopped listening")
    
    def process_audio_chunk(self, duration: float = 3.0) -> Optional[Dict[str, Any]]:
        """
        Process recent audio chunk.
        Returns dict with transcription and features.
        """
        if not self.is_listening or not self.capture:
            return None
        
        # Check cooldown
        current_time = time.time()
        if current_time - self.last_transcription_time < self.transcription_cooldown:
            return None
        
        # Get audio data
        audio_data = self.capture.get_audio_chunk(duration)
        if audio_data is None:
            return None
        
        result = {
            'timestamp': current_time,
            'transcription': None,
            'features': {},
            'emotion': None
        }
        
        # Extract features
        features = self.feature_extractor.extract_features(
            audio_data, 
            self.capture.sample_rate
        )
        result['features'] = features
        
        # Detect emotion
        emotion = self.feature_extractor.detect_emotion(features)
        result['emotion'] = emotion
        
        # Transcribe (if speech detected based on volume)
        if features.get('volume', 0) > 0.05:  # Threshold for speech
            if self.recognizer:
                transcription = self.recognizer.transcribe(
                    audio_data,
                    self.capture.sample_rate
                )
                
                if transcription:
                    result['transcription'] = transcription
                    self.stats['successful_transcriptions'] += 1
                    self.stats['words_heard'] += len(transcription.split())
                    self.stats['last_heard'] = transcription
                    
                    log.info(f"🎤 Heard: \"{transcription}\"")
                
                self.stats['total_transcriptions'] += 1
        
        self.last_transcription_time = current_time
        
        # Store in agent memory
        if result['transcription'] or result['emotion'] != 'neutral':
            self.agent.memory.remember({
                'type': 'audio_input',
                'transcription': result['transcription'],
                'emotion': result['emotion'],
                'features': result['features'],
                'timestamp': result['timestamp']
            }, tags=['audio', 'perception', 'speech'])
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get audio processing statistics"""
        return {
            **self.stats,
            'is_listening': self.is_listening,
            'has_capture': self.capture is not None,
            'has_recognizer': self.recognizer is not None
        }
    
    def close(self):
        """Close audio processor"""
        self.stop_listening()
        if self.capture:
            self.capture.close()


# Integration function
def add_audio_processing_to_agent(agent):
    """
    Add audio processing capability to agent.
    
    Usage:
        from ai_core.audio_processor import add_audio_processing_to_agent
        add_audio_processing_to_agent(agent)
    """
    try:
        processor = AudioProcessor(agent)
        agent.audio_processor = processor
        
        log.info(f"✅ Audio processing added to {agent.agent_id}")
        return processor
    except Exception as e:
        log.warning(f"Audio processing not available: {e}")
        return None


# Helper for cognitive loop integration
def process_audio_if_listening(agent) -> Optional[Dict[str, Any]]:
    """
    Simple function for cognitive loop to call.
    Processes audio if agent is listening.
    """
    if not hasattr(agent, 'audio_processor'):
        return None
    
    processor = agent.audio_processor
    
    if processor.is_listening:
        return processor.process_audio_chunk()
    
    return None