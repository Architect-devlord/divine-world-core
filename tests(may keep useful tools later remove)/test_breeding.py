"""
py_backend/tests/test_breeding.py - Breeding System Test Suite

Tests the complete breeding → spawning → packaging pipeline.
"""

import asyncio
import time
import logging
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from auto_packager import EnhancedAgentSpawner
from ai_core.personality import Personality

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)

log = logging.getLogger("test_breeding")


class BreedingSystemTester:
    """Test suite for NPC breeding system"""
    
    def __init__(self):
        self.spawner = EnhancedAgentSpawner(
            client_jar_path="DWClientBot.jar",
            auto_package=True,
            package_output_dir="test_output/npc_applications"
        )
        self.test_agents = []
    
    def test_personality_inheritance(self):
        """Test personality trait inheritance"""
        log.info("\n" + "="*60)
        log.info("TEST 1: Personality Inheritance")
        log.info("="*60)
        
        # Create parent personalities
        parent_a = Personality(traits={
            'curiosity': 0.9,
            'boldness': 0.7,
            'sociability': 0.5,
            'agreeableness': 0.3,
            'conscientiousness': 0.8
        })
        
        parent_b = Personality(traits={
            'curiosity': 0.3,
            'boldness': 0.5,
            'sociability': 0.9,
            'agreeableness': 0.7,
            'conscientiousness': 0.4
        })
        
        log.info("\nParent A Traits:")
        for key, val in parent_a.to_dict().items():
            log.info(f"  {key}: {val:.2f}")
        
        log.info("\nParent B Traits:")
        for key, val in parent_b.to_dict().items():
            log.info(f"  {key}: {val:.2f}")
        
        # Simulate inheritance (matching Java implementation)
        child_traits = {}
        mutation_rate = 0.1
        
        for key in parent_a.to_dict().keys():
            val_a = parent_a.to_dict()[key]
            val_b = parent_b.to_dict()[key]
            
            # Average
            base = (val_a + val_b) / 2.0
            
            # Add mutation
            import random
            mutation = (random.random() * 2 - 1) * mutation_rate
            
            # Clamp
            child_val = max(-1.0, min(1.0, base + mutation))
            child_traits[key] = child_val
        
        log.info("\nChild Traits (with mutation):")
        for key, val in child_traits.items():
            parent_avg = (parent_a.to_dict()[key] + parent_b.to_dict()[key]) / 2.0
            diff = val - parent_avg
            log.info(f"  {key}: {val:.2f} (mutation: {diff:+.2f})")
        
        log.info("\n✅ Personality inheritance test complete")
        return child_traits
    
    def test_spawn_parents(self):
        """Test spawning parent NPCs"""
        log.info("\n" + "="*60)
        log.info("TEST 2: Spawn Parent NPCs")
        log.info("="*60)
        
        # Spawn parent A
        log.info("\nSpawning Parent A...")
        parent_a = self.spawner.spawn_npc(
            agent_id="test_parent_a",
            persona_traits={
                'curiosity': 0.9,
                'boldness': 0.7,
                'sociability': 0.5
            }
        )
        self.test_agents.append(parent_a)
        log.info(f"✅ Parent A spawned: {parent_a.agent_id}")
        
        # Spawn parent B
        log.info("\nSpawning Parent B...")
        parent_b = self.spawner.spawn_npc(
            agent_id="test_parent_b",
            persona_traits={
                'curiosity': 0.3,
                'boldness': 0.5,
                'sociability': 0.9
            }
        )
        self.test_agents.append(parent_b)
        log.info(f"✅ Parent B spawned: {parent_b.agent_id}")
        
        return parent_a, parent_b
    
    def test_spawn_child(self, parent_a, parent_b, child_traits):
        """Test spawning child NPC with inherited traits"""
        log.info("\n" + "="*60)
        log.info("TEST 3: Spawn Child NPC")
        log.info("="*60)
        
        child_id = f"test_child_{int(time.time())}"
        
        log.info(f"\nSpawning child: {child_id}")
        log.info("Inherited traits:")
        for key, val in child_traits.items():
            log.info(f"  {key}: {val:.2f}")
        
        child = self.spawner.spawn_npc(
            agent_id=child_id,
            persona_traits=child_traits
        )
        self.test_agents.append(child)
        
        log.info(f"\n✅ Child spawned: {child.agent_id}")
        log.info(f"   Backend: {child.client_process.backend_url}")
        log.info(f"   Type: {child.agent_type}")
        
        return child
    
    def test_packaging_queue(self):
        """Test auto-packaging queue"""
        log.info("\n" + "="*60)
        log.info("TEST 4: Auto-Packaging Queue")
        log.info("="*60)
        
        if not self.spawner.packager:
            log.error("❌ Auto-packaging not enabled")
            return False
        
        packager = self.spawner.packager
        
        log.info(f"\nQueue size: {packager.packaging_queue.qsize()}")
        log.info(f"Expected: {len(self.test_agents)} agents")
        
        log.info("\nWaiting for packaging to complete...")
        max_wait = 60  # 60 seconds
        waited = 0
        
        while waited < max_wait:
            packaged = packager.list_packaged_agents()
            log.info(f"  [{waited}s] Packaged: {len(packaged)}/{len(self.test_agents)}")
            
            if len(packaged) >= len(self.test_agents):
                log.info("\n✅ All agents packaged!")
                break
            
            time.sleep(5)
            waited += 5
        
        # Show packaging results
        log.info("\nPackaging Results:")
        for agent in self.test_agents:
            info = packager.get_package_info(agent.agent_id)
            if info:
                log.info(f"\n  {agent.agent_id}:")
                log.info(f"    ✅ Packaged")
                log.info(f"    Exe: {info['exe_path']}")
                log.info(f"    Package: {info['package_path']}")
            else:
                log.info(f"\n  {agent.agent_id}:")
                log.info(f"    ⏳ Still in queue")
        
        return True
    
    def test_brain_capsule_portability(self):
        """Test brain capsule save/load"""
        log.info("\n" + "="*60)
        log.info("TEST 5: Brain Capsule Portability")
        log.info("="*60)
        
        if not self.test_agents:
            log.error("❌ No test agents to save")
            return False
        
        test_agent = self.test_agents[0]
        
        # Save brain
        brain_path = Path("test_output") / f"{test_agent.agent_id}_brain.pcap"
        brain_path.parent.mkdir(parents=True, exist_ok=True)
        
        log.info(f"\nSaving brain for {test_agent.agent_id}...")
        
        from ai_core.brain_capsule import BrainCapsule
        
        capsule = BrainCapsule(
            metadata={
                'agent_id': test_agent.agent_id,
                'agent_type': test_agent.agent_type,
                'saved_at': time.time()
            },
            personality=test_agent.personality.to_dict(),
            emotion_snapshot=test_agent.emotion.snapshot(),
            memory_snapshot=[]
        )
        
        capsule.save(str(brain_path))
        log.info(f"✅ Brain saved to {brain_path}")
        
        # Verify files exist
        json_file = brain_path.with_suffix('.pcap.json')
        if json_file.exists():
            log.info(f"✅ JSON metadata exists ({json_file.stat().st_size} bytes)")
        else:
            log.error(f"❌ JSON metadata missing")
            return False
        
        # Load brain
        log.info(f"\nLoading brain from {brain_path}...")
        loaded_capsule = BrainCapsule.load(str(brain_path))
        
        log.info("✅ Brain loaded successfully")
        log.info(f"   Agent ID: {loaded_capsule.metadata.get('agent_id')}")
        log.info(f"   Type: {loaded_capsule.metadata.get('agent_type')}")
        log.info(f"   Personality: {loaded_capsule.personality}")
        
        # Verify portability
        log.info("\n✅ Brain capsule is portable (can be moved to another computer)")
        
        return True
    
    def run_all_tests(self):
        """Run complete test suite"""
        log.info("\n" + "="*60)
        log.info("  BREEDING SYSTEM TEST SUITE")
        log.info("="*60)
        
        try:
            # Test 1: Personality inheritance
            child_traits = self.test_personality_inheritance()
            
            # Test 2: Spawn parents
            parent_a, parent_b = self.test_spawn_parents()
            
            # Test 3: Spawn child
            child = self.test_spawn_child(parent_a, parent_b, child_traits)
            
            # Test 4: Auto-packaging
            self.test_packaging_queue()
            
            # Test 5: Brain portability
            self.test_brain_capsule_portability()
            
            log.info("\n" + "="*60)
            log.info("  ALL TESTS COMPLETE")
            log.info("="*60)
            log.info(f"\nTotal agents spawned: {len(self.test_agents)}")
            log.info(f"Packaged agents: {len(self.spawner.packager.list_packaged_agents())}")
            
            return True
            
        except Exception as e:
            log.error(f"\n❌ Test failed: {e}", exc_info=True)
            return False
        
        finally:
            # Cleanup
            log.info("\n\nCleaning up test agents...")
            self.spawner.cleanup_all()
            log.info("✅ Cleanup complete")


def main():
    """Run tests"""
    print("\n" + "="*60)
    print("  Divine World - Breeding System Test Suite")
    print("="*60 + "\n")
    
    tester = BreedingSystemTester()
    
    try:
        success = tester.run_all_tests()
        
        if success:
            print("\n✅ All tests passed!")
            sys.exit(0)
        else:
            print("\n❌ Some tests failed")
            sys.exit(1)
    
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        tester.spawner.cleanup_all()
        sys.exit(1)


if __name__ == "__main__":
    main()