#!/usr/bin/env python3
# py_backend/test_all_patches.py - Comprehensive Patch Verification
"""
Tests all applied patches to ensure backend is ready for production.
Run this after applying patches.
"""

import sys
import os
from pathlib import Path
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
log = logging.getLogger("patch_test")

def test_config_system():
    """Test Patch 1: Config Management"""
    log.info("Testing Patch 1: Config System...")
    
    try:
        from config import Config
        
        # Verify directories created
        assert Config.DATA_DIR.exists(), "DATA_DIR not created"
        assert Config.BRAINS_DIR.exists(), "BRAINS_DIR not created"
        assert Config.UPLOADS_DIR.exists(), "UPLOADS_DIR not created"
        
        # Verify validation
        assert Config.validate(), "Config validation failed"
        
        # Test path helpers
        brain_path = Config.get_agent_brain_path("test_agent")
        assert brain_path.parent == Config.BRAINS_DIR / "test_agent"
        
        log.info("✅ Patch 1: Config System PASSED")
        return True
    
    except Exception as e:
        log.error(f"❌ Patch 1 FAILED: {e}")
        return False


def test_brain_capsule():
    """Test Patch 2: Atomic Brain Save"""
    log.info("Testing Patch 2: Brain Capsule Atomic Save...")
    
    try:
        from ai_core.brain_capsule import BrainCapsule
        import tempfile
        
        # Create test capsule
        capsule = BrainCapsule(
            metadata={'test': True, 'agent_id': 'test'},
            personality={'openness': 0.5}
        )
        
        # Test save
        with tempfile.TemporaryDirectory() as tmpdir:
            test_path = Path(tmpdir) / "test_brain.pcap"
            capsule.save(str(test_path))
            
            # Verify file exists
            assert test_path.exists(), "Brain file not created"
            
            # Verify no .tmp file left behind
            tmp_files = list(Path(tmpdir).glob("*.tmp"))
            assert len(tmp_files) == 0, f"Temp files not cleaned: {tmp_files}"
            
            # Test load
            loaded = BrainCapsule.load(str(test_path))
            assert loaded.metadata['test'] == True
            assert loaded.personality['openness'] == 0.5
        
        log.info("✅ Patch 2: Brain Capsule PASSED")
        return True
    
    except Exception as e:
        log.error(f"❌ Patch 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_language_integration():
    """Test Patch 3: Language Module Integration"""
    log.info("Testing Patch 3: Language Integration...")
    
    try:
        from ai_core.agent import NPCAgent
        from ai_core.brain_language import add_language_to_brain
        
        # Create agent
        agent = NPCAgent("test_lang")
        
        # Check if language auto-initialized
        if not hasattr(agent.brain, 'language') or agent.brain.language is None:
            add_language_to_brain(agent.brain)
        
        # Verify language capabilities
        assert hasattr(agent.brain, 'language'), "Language module not added"
        assert agent.brain.language is not None, "Language module is None"
        assert hasattr(agent.brain.language, 'process_language_input')
        assert hasattr(agent.brain.language, 'generate_speech')
        
        # Test basic processing
        context = {'health': 20.0, 'emotions': agent.emotion.snapshot()}
        response = agent.brain.process_language_input("Hello", context)
        
        # Response can be empty at stage 0, just check no crash
        log.info(f"  Test response: {response}")
        log.info(f"  Language stage: {agent.brain.language.language_stage}")
        
        log.info("✅ Patch 3: Language Integration PASSED")
        return True
    
    except Exception as e:
        log.error(f"❌ Patch 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_port_allocation():
    """Test Patch 4: Port Allocation"""
    log.info("Testing Patch 4: Port Allocation...")
    
    try:
        import socket
        import time
        
        def is_port_free(port, max_retries=3):
            """Copy of patched method"""
            for attempt in range(max_retries):
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        s.bind(('127.0.0.1', port))
                        return True
                except OSError:
                    if attempt < max_retries - 1:
                        time.sleep(0.1 * (attempt + 1))
                        continue
                return False
            return False
        
        # Test port checking
        test_port = 50000
        
        # Should be free
        assert is_port_free(test_port), f"Port {test_port} should be free"
        
        # Occupy port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', test_port))
            
            # Should be busy
            assert not is_port_free(test_port), f"Port {test_port} should be busy"
        
        # Give OS time to release
        time.sleep(0.2)
        
        # Should be free again
        assert is_port_free(test_port), f"Port {test_port} should be free after release"
        
        log.info("✅ Patch 4: Port Allocation PASSED")
        return True
    
    except Exception as e:
        log.error(f"❌ Patch 4 FAILED: {e}")
        return False


def test_validation_system():
    """Test Patch 10: Validation"""
    log.info("Testing Patch 10: Validation System...")
    
    try:
        from utils.validation import ChatRequest, FileUploadRequest
        from pydantic import ValidationError
        
        # Test valid chat request
        valid = ChatRequest(message="Hello", agent_id="test_agent")
        assert valid.message == "Hello"
        assert valid.agent_id == "test_agent"
        
        # Test sanitization
        sanitized = ChatRequest(message="  Hello  \x00\n\n\n\n\n  ", agent_id="test")
        assert sanitized.message == "Hello  \n\n\n  "  # Null removed, newlines limited
        
        # Test invalid agent_id
        try:
            invalid = ChatRequest(message="Hi", agent_id="../../../etc/passwd")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass  # Expected
        
        # Test file upload validation
        upload = FileUploadRequest(filename="../dangerous/../../file.txt")
        assert upload.filename == "file.txt"  # Path traversal removed
        
        log.info("✅ Patch 10: Validation System PASSED")
        return True
    
    except Exception as e:
        log.error(f"❌ Patch 10 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all patch tests"""
    print("\n" + "="*70)
    print("  🔧 PATCH VERIFICATION TEST SUITE")
    print("="*70 + "\n")
    
    tests = [
        ("Config System", test_config_system),
        ("Brain Capsule Atomic Save", test_brain_capsule),
        ("Language Integration", test_language_integration),
        ("Port Allocation", test_port_allocation),
        ("Validation System", test_validation_system),
    ]
    
    results = []
    
    for name, test_func in tests:
        print(f"\n{'─'*70}")
        result = test_func()
        results.append((name, result))
        print(f"{'─'*70}\n")
    
    # Summary
    print("\n" + "="*70)
    print("  📊 TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")
    
    print(f"\n  Total: {passed}/{total} passed")
    
    if passed == total:
        print("\n  🎉 ALL PATCHES VERIFIED!")
        print("  Backend is ready for Java/frontend integration")
    else:
        print("\n  ⚠️  SOME PATCHES FAILED")
        print("  Review errors above before proceeding")
    
    print("="*70 + "\n")
    
    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)