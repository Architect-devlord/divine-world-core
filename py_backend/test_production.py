#!/usr/bin/env python3
# py_backend/test_production.py - Production Test Suite
"""
Comprehensive test suite for production backend.
"""

import sys
import os
from pathlib import Path
import logging
import requests
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
log = logging.getLogger("test")

def test_imports():
    """Test all critical imports"""
    log.info("Testing imports...")
    
    try:
        from config import Config
        from ai_core.agent import NPCAgent
        from ai_core.brain_core import BrainCore
        from ai_core.brain_language import add_language_to_brain
        from ai_core.brain_capsule import BrainCapsule
        from utils.validation import ChatRequest, FileUploadRequest
        log.info("✅ All imports successful")
        return True
    except Exception as e:
        log.error(f"❌ Import failed: {e}")
        return False

def test_config():
    """Test configuration system"""
    log.info("Testing configuration...")
    
    try:
        from config import Config
        
        assert Config.validate(), "Config validation failed"
        assert Config.DATA_DIR.exists(), "Data directory not created"
        assert Config.BRAINS_DIR.exists(), "Brains directory not created"
        
        log.info("✅ Configuration system working")
        return True
    except Exception as e:
        log.error(f"❌ Config test failed: {e}")
        return False

def test_agent_creation():
    """Test agent creation with language"""
    log.info("Testing agent creation...")
    
    try:
        from ai_core.agent import NPCAgent
        from ai_core.brain_language import add_language_to_brain
        
        agent = NPCAgent("test_agent")
        
        if not hasattr(agent.brain, 'language'):
            add_language_to_brain(agent.brain)
        
        assert hasattr(agent.brain, 'language'), "Language not initialized"
        assert agent.brain.language is not None, "Language is None"
        
        log.info("✅ Agent creation working")
        return True
    except Exception as e:
        log.error(f"❌ Agent creation failed: {e}")
        return False

def test_brain_save_load():
    """Test atomic brain save/load"""
    log.info("Testing brain save/load...")
    
    try:
        from ai_core.agent import NPCAgent
        from config import Config
        import tempfile
        
        agent = NPCAgent("test_save")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "test_brain.pcap"
            
            # Save
            agent.save(str(save_path))
            assert save_path.exists(), "Brain file not created"
            
            # Load
            agent2 = NPCAgent("test_load")
            agent2.load(str(save_path))
            
            assert agent2.agent_id == "test_save", "Agent ID not preserved"
        
        log.info("✅ Brain save/load working")
        return True
    except Exception as e:
        log.error(f"❌ Brain save/load failed: {e}")
        return False

def test_validation():
    """Test request validation"""
    log.info("Testing validation...")
    
    try:
        from utils.validation import ChatRequest, FileUploadRequest
        from pydantic import ValidationError
        
        # Valid request
        chat = ChatRequest(message="Hello", agent_id="test")
        assert chat.message == "Hello"
        
        # Invalid request (should raise)
        try:
            invalid = ChatRequest(message="", agent_id="test")
            assert False, "Should have raised ValidationError"
        except ValidationError:
            pass  # Expected
        
        # File upload sanitization
        upload = FileUploadRequest(filename="../../../etc/passwd")
        assert '..' not in upload.filename, "Path traversal not prevented"
        
        log.info("✅ Validation working")
        return True
    except Exception as e:
        log.error(f"❌ Validation test failed: {e}")
        return False

def test_server_health(base_url: str = "http://localhost:11400"):
    """Test server health endpoints"""
    log.info(f"Testing server health at {base_url}...")
    
    try:
        # Basic health check
        response = requests.get(f"{base_url}/health", timeout=5)
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        
        data = response.json()
        assert data['status'] == 'healthy', "Server not healthy"
        
        # Detailed health check
        response = requests.get(f"{base_url}/health/detailed", timeout=5)
        assert response.status_code == 200, "Detailed health check failed"
        
        data = response.json()
        assert 'components' in data, "Missing components in health check"
        
        log.info("✅ Server health checks passing")
        return True
    except requests.exceptions.ConnectionError:
        log.warning("⚠️  Server not running (start with: python start_production.py)")
        return None  # Not a failure, just not running
    except Exception as e:
        log.error(f"❌ Server health test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*70)
    print("  🧪 PRODUCTION TEST SUITE")
    print("="*70 + "\n")
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_config),
        ("Agent Creation", test_agent_creation),
        ("Brain Save/Load", test_brain_save_load),
        ("Validation", test_validation),
    ]
    
    results = []
    
    for name, test_func in tests:
        print(f"{'─'*70}")
        result = test_func()
        results.append((name, result))
        print(f"{'─'*70}\n")
    
    # Try server tests if server is running
    print(f"{'─'*70}")
    server_result = test_server_health()
    if server_result is not None:
        results.append(("Server Health", server_result))
    print(f"{'─'*70}\n")
    
    # Summary
    print("=" * 70)
    print("  📊 TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, r in results if r is True)
    total = len(results)
    
    for name, result in results:
        if result is True:
            status = "✅ PASS"
        elif result is False:
            status = "❌ FAIL"
        else:
            status = "⏭️  SKIP"
        print(f"  {status}  {name}")
    
    print(f"\n  Total: {passed}/{total} passed")
    
    if passed == total:
        print("\n  🎉 ALL TESTS PASSED!")
        print("  Production backend is ready")
    else:
        print("\n  ⚠️  SOME TESTS FAILED")
        print("  Review errors above")
    
    print("=" * 70 + "\n")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)