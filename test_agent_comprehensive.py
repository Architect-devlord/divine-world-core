#!/usr/bin/env python3
"""
Comprehensive Agent Testing Script
===================================
Tests all learning components of the Divine World agents.
"""

import asyncio
import time
import json
import os
import sys
from pathlib import Path
import requests
import subprocess
import threading
from typing import Dict, Any, List

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "py_backend"))

from ai_core.agent import NPCAgent
from ai_core.unified_memory import UnifiedMemoryStore
from ai_core.emotion import EmotionSystem
from ai_core.reward_system import ImprovedRewardSystem
from ai_core.world_model import WorldModel
import torch
import numpy as np

class AgentTester:
    """Comprehensive tester for all agent learning components"""

    def __init__(self):
        self.agent = None
        self.test_results = {}

    async def setup_agent(self):
        """Setup test agent"""
        print("🤖 Setting up test agent...")

        self.agent = NPCAgent(
            agent_id="test_agent_comprehensive",
            mode="autonomous",
            use_scylla=False  # Use in-memory
        )

        print("✅ Agent initialized")
        return self.agent

    async def test_transformer_speech(self):
        """Test transformer-based language learning"""
        print("\n🗣️  Testing Transformer Speech Learning...")

        test_messages = [
            "Hello, how are you?",
            "What is your name?",
            "Can you tell me about yourself?",
            "What do you see around you?",
            "How do you feel right now?"
        ]

        responses = []
        for msg in test_messages:
            response = await self.agent.process_chat(msg)
            responses.append((msg, response))
            print(f"  Q: {msg}")
            print(f"  A: {response}")
            await asyncio.sleep(0.5)

        # Check if language system learned
        language_progress = self.agent.brain.get_language_progress() if hasattr(self.agent.brain, 'get_language_progress') else {}
        vocab_size = language_progress.get('vocabulary_size', 0)

        self.test_results['speech_transformer'] = {
            'responses_generated': len(responses),
            'vocabulary_size': vocab_size,
            'language_stage': language_progress.get('stage', 0)
        }

        print(f"✅ Speech test complete - Vocab: {vocab_size}, Stage: {language_progress.get('stage', 0)}")

    async def test_web_browsing(self):
        """Test learning from online websites"""
        print("\n🌐 Testing Web Browsing Learning...")

        # Allow some test websites
        self.agent.web_browser.update_allowed_websites([
            {'url': 'https://en.wikipedia.org', 'enabled': True},
            {'url': 'https://example.com', 'enabled': True}
        ])

        # Test browsing
        test_urls = [
            'https://en.wikipedia.org/wiki/Artificial_intelligence',
            'https://example.com'
        ]

        pages_browsed = 0
        for url in test_urls:
            try:
                page = await self.agent.web_browser.browse(url)
                if page:
                    pages_browsed += 1
                    print(f"  ✅ Browsed: {page.title} ({len(page.text)} chars)")
                else:
                    print(f"  ❌ Failed to browse: {url}")
            except Exception as e:
                print(f"  ❌ Error browsing {url}: {e}")

        # Check memory for web content
        web_memories = [m for m in self.agent.memory.events if m.get('type') == 'web_page']

        self.test_results['web_browsing'] = {
            'pages_browsed': pages_browsed,
            'web_memories_stored': len(web_memories),
            'total_text_bytes': sum(len(m.get('text', '')) for m in web_memories)
        }

        print(f"✅ Web browsing test complete - {pages_browsed} pages, {len(web_memories)} memories")

    async def test_vision_learning(self):
        """Test learning through observation (vision)"""
        print("\n👁️  Testing Vision Learning...")

        pics_dir = Path(__file__).parent / "npc_applications" / "pics"
        image_files = list(pics_dir.glob("*.jpg")) + list(pics_dir.glob("*.png")) + list(pics_dir.glob("*.jpeg"))

        images_processed = 0
        for img_path in image_files[:5]:  # Test first 5 images
            try:
                # Load image
                from PIL import Image
                image = Image.open(img_path)

                # Process with vision system
                frame = np.array(image)
                if frame.shape[-1] == 4:  # RGBA
                    frame = frame[:, :, :3]  # RGB only

                # Simulate observation
                obs = self.agent.observe(frame, info={'source': 'image', 'filename': img_path.name})

                images_processed += 1
                print(f"  ✅ Processed: {img_path.name} -> obs shape: {obs.shape}")

            except Exception as e:
                print(f"  ❌ Error processing {img_path.name}: {e}")

        # Check vision memories
        vision_memories = [m for m in self.agent.memory.events if m.get('type') == 'observation']

        self.test_results['vision_learning'] = {
            'images_processed': images_processed,
            'vision_memories': len(vision_memories)
        }

        print(f"✅ Vision test complete - {images_processed} images processed")

    async def test_memory_system(self):
        """Test memory and training from memory"""
        print("\n🧠 Testing Memory System...")

        # Add some test memories
        test_memories = [
            {'type': 'experience', 'action': 'explore', 'reward': 1.0, 'text': 'Found interesting location'},
            {'type': 'chat', 'message': 'Hello world', 'sender': 'user'},
            {'type': 'observation', 'description': 'Saw a tree', 'tags': ['nature', 'visual']}
        ]

        for mem in test_memories:
            self.agent.memory.remember(mem, tags=mem.get('tags', []))

        # Test retrieval
        all_memories = self.agent.memory.recall(n=10)
        chat_memories = self.agent.memory.recall(event_type='chat')
        experience_memories = self.agent.memory.recall(tags=['experience'])

        self.test_results['memory_system'] = {
            'total_memories': len(self.agent.memory.events),
            'retrieved_all': len(all_memories),
            'chat_memories': len(chat_memories),
            'experience_memories': len(experience_memories)
        }

        print(f"✅ Memory test complete - {len(self.agent.memory.events)} total memories")

    async def test_emotional_tagging(self):
        """Test emotional tagging for memories"""
        print("\n😊 Testing Emotional Tagging...")

        # Simulate emotional experiences
        emotions_to_test = ['joy', 'sadness', 'fear', 'surprise']

        for emotion in emotions_to_test:
            # Add emotion
            self.agent.emotion.add(emotion, 0.8)

            # Create memory with emotion
            self.agent.memory.remember({
                'type': 'emotional_experience',
                'emotion': emotion,
                'intensity': 0.8,
                'description': f'Felt {emotion} intensely'
            }, tags=['emotion', emotion])

            # Decay emotion
            self.agent.emotion.decay()

        # Check emotional memories
        emotional_memories = [m for m in self.agent.memory.events if 'emotion' in m.get('tags', [])]

        # Test if emotions affect memory retrieval
        dominant_emotion = self.agent.emotion.dominant_emotion()

        self.test_results['emotional_tagging'] = {
            'emotional_memories': len(emotional_memories),
            'dominant_emotion': dominant_emotion,
            'emotion_snapshot': self.agent.emotion.snapshot()
        }

        print(f"✅ Emotional tagging test complete - Dominant: {dominant_emotion}")

    async def test_reward_system(self):
        """Test reward system updating policies and behaviors"""
        print("\n🎯 Testing Reward System...")

        # Initialize reward system if not already
        if self.agent.reward_system is None:
            self.agent.initialize_reward_system()

        # Simulate some experiences
        test_experiences = [
            {'obs': np.random.randn(50), 'action': np.random.randn(11), 'reward': 1.0, 'next_obs': np.random.randn(50)},
            {'obs': np.random.randn(50), 'action': np.random.randn(11), 'reward': -0.5, 'next_obs': np.random.randn(50)},
            {'obs': np.random.randn(50), 'action': np.random.randn(11), 'reward': 0.2, 'next_obs': np.random.randn(50)}
        ]

        total_reward = 0
        for exp in test_experiences:
            outcome = {'reward': exp['reward'], 'done': False}
            self.agent.learn(exp['obs'], exp['action'], exp['next_obs'], outcome)
            total_reward += exp['reward']

        # Check if memories include rewards
        reward_memories = [m for m in self.agent.memory.events if m.get('type') == 'experience']

        self.test_results['reward_system'] = {
            'experiences_processed': len(test_experiences),
            'total_reward': total_reward,
            'reward_memories': len(reward_memories),
            'reward_system_initialized': self.agent.reward_system is not None
        }

        print(f"✅ Reward system test complete - {len(reward_memories)} reward memories")

    async def test_world_model(self):
        """Test mental mind simulation (world model)"""
        print("\n🌍 Testing World Model Simulation...")

        # Check if world model is initialized
        world_model_active = hasattr(self.agent, 'world_model') and self.agent.world_model is not None

        if world_model_active:
            # Test prediction
            dummy_obs = {
                'vision': torch.randn(1, 3, 84, 84),
                'audio': torch.randn(1, 128),
                'proprioception': torch.randn(1, 32),
                'language': torch.randint(0, 1000, (1, 10)),
                'action': torch.randn(1, 11)
            }

            try:
                prediction = self.agent.world_model.predict(dummy_obs, steps=5)
                prediction_success = prediction is not None
            except Exception as e:
                prediction_success = False
                print(f"  ❌ Prediction failed: {e}")

            # Check replay buffer
            buffer_size = len(self.agent.world_model_trainer.replay_buffer) if hasattr(self.agent, 'world_model_trainer') else 0

            self.test_results['world_model'] = {
                'world_model_active': True,
                'prediction_success': prediction_success,
                'replay_buffer_size': buffer_size,
                'model_parameters': sum(p.numel() for p in self.agent.world_model.parameters())
            }

            print(f"✅ World model test complete - {buffer_size} buffer items, {self.test_results['world_model']['model_parameters']} params")
        else:
            self.test_results['world_model'] = {
                'world_model_active': False,
                'error': 'World model not initialized'
            }
            print("❌ World model not active")

    async def run_all_tests(self):
        """Run all tests"""
        print("🚀 Starting Comprehensive Agent Testing")
        print("=" * 50)

        await self.setup_agent()

        await self.test_transformer_speech()
        await self.test_web_browsing()
        await self.test_vision_learning()
        await self.test_memory_system()
        await self.test_emotional_tagging()
        await self.test_reward_system()
        await self.test_world_model()

        print("\n" + "=" * 50)
        print("📊 TEST RESULTS SUMMARY")
        print("=" * 50)

        for test_name, results in self.test_results.items():
            print(f"\n🔍 {test_name.upper()}:")
            for key, value in results.items():
                print(f"  {key}: {value}")

        print("\n✅ All tests completed!")

        # Save results
        results_file = Path(__file__).parent / "test_results.json"
        with open(results_file, 'w') as f:
            json.dump(self.test_results, f, indent=2, default=str)

        print(f"📄 Results saved to: {results_file}")

async def main():
    tester = AgentTester()
    await tester.run_all_tests()

if __name__ == "__main__":
    asyncio.run(main())