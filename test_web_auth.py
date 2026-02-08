
import sys
import os
from unittest.mock import MagicMock

# Robust mocking of problematic modules
def mock_module(name):
    mock = MagicMock()
    sys.modules[name] = mock
    return mock

mock_torch = mock_module('torch')
mock_torch.nn = mock_module('torch.nn')
mock_module('msgpack')
mock_module('cassandra')
mock_module('cassandra.cluster')
mock_module('pyaudio')
mock_module('speech_recognition')
mock_module('librosa')
mock_module('cv2')

# Mock agent
class MockAgent:
    def __init__(self):
        self.agent_id = "test_agent"
        self.memory = MagicMock()

# Add to path
sys.path.insert(0, os.path.join(os.getcwd(), 'py_backend'))

from ai_core.web_browser import WebBrowser

def test_web_authorization_updated():
    agent = MockAgent()
    browser = WebBrowser(agent)

    # Test 1: Authorize a domain
    print("Setting allowed websites: domain:google.com")
    browser.update_allowed_websites([
        {'url': 'https://google.com', 'type': 'domain', 'enabled': True}
    ])

    assert browser._is_url_allowed('https://google.com') == True
    assert browser._is_url_allowed('https://www.google.com') == True
    assert browser._is_url_allowed('https://google.com/search') == True
    assert browser._is_url_allowed('https://bing.com') == False

    print("✅ Test 1 (Domain authorization) passed")

    # Test 2: Authorize a specific URL
    print("\nSetting allowed websites: url:example.com/specific-path")
    browser.update_allowed_websites([
        {'url': 'https://example.com/specific-path', 'type': 'url', 'enabled': True}
    ])

    assert browser._is_url_allowed('https://example.com/specific-path') == True
    assert browser._is_url_allowed('https://example.com/specific-path/sub') == True
    assert browser._is_url_allowed('https://example.com/other-path') == False
    assert browser._is_url_allowed('https://google.com') == False

    print("✅ Test 2 (Specific URL authorization) passed")

    # Test 3: Mixed authorization
    print("\nSetting mixed allowed websites")
    browser.update_allowed_websites([
        {'url': 'https://google.com', 'type': 'domain', 'enabled': True},
        {'url': 'https://example.com/only-this', 'type': 'url', 'enabled': True}
    ])

    assert browser._is_url_allowed('https://google.com/search') == True
    assert browser._is_url_allowed('https://example.com/only-this') == True
    assert browser._is_url_allowed('https://example.com/something-else') == False

    print("✅ Test 3 (Mixed authorization) passed")

if __name__ == "__main__":
    try:
        test_web_authorization_updated()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
