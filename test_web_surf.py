
import asyncio
import sys
import os
from unittest.mock import MagicMock, AsyncMock

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

# Add to path
sys.path.insert(0, os.path.join(os.getcwd(), 'py_backend'))

from ai_core.web_browser import WebBrowser

# Mock agent
class MockAgent:
    def __init__(self):
        self.agent_id = "test_agent"
        self.memory = MagicMock()

async def test_web_browsing():
    agent = MockAgent()
    browser = WebBrowser(agent)

    # Authorize a domain
    browser.update_allowed_websites([
        {'url': 'https://example.com', 'type': 'domain', 'enabled': True}
    ])

    # Test browsing allowed URL (REAL browsing if possible)
    print("Browsing allowed URL: https://example.com")
    try:
        page = await browser.browse("https://example.com")

        if page is not None:
            print(f"✅ Successfully browsed and parsed page: '{page.title}'")
            assert "Example" in page.title

            # Verify it was remembered
            agent.memory.remember.assert_called()
            print("✅ Page content was stored in memory")

            # Verify link discovery
            if len(page.links) > 0:
                print(f"✅ {len(page.links)} links were discovered")
        else:
            print("❌ Page is None (maybe no internet or request failed)")

    except Exception as e:
        print(f"❌ Browsing error: {e}")

    # Test browsing unauthorized URL
    print("\nBrowsing unauthorized URL: https://blocked.com")
    blocked_page = await browser.browse("https://blocked.com")
    assert blocked_page is None
    print("✅ Unauthorized URL was blocked")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(test_web_browsing())
