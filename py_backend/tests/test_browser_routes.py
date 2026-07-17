"""
Regression tests for agent.py's /browser/scroll and /browser/screenshot
routes.

Historical bugs: /browser/scroll took a {dx, dy} body and gated the real
scroll behind `hasattr(web_browser, "_page")`, which was always False
(WebBrowser never sets self._page - every interaction method opens its
own local `page`). /browser/screenshot called a screenshot_jpeg() method
that doesn't exist anywhere (the real method is screenshot(), and returns
PNG). Both routes now call the real scroll()/screenshot() methods with
the shapes those methods actually take.
"""
import pytest


class FakeInteractionResult:
    def __init__(self, success, message, screenshot_b64=None):
        self.success = success
        self.message = message
        self.screenshot_b64 = screenshot_b64


class FakeWebBrowser:
    """Matches WebBrowser's real scroll()/screenshot() signatures - if
    those signatures ever change, this fake (and these tests) should be
    updated to match, which is exactly the point: it keeps the route
    code's assumptions about the real API honest."""

    def __init__(self):
        self.scroll_calls = []
        self.screenshot_calls = []

    async def scroll(self, url, direction="down", amount=600):
        self.scroll_calls.append((url, direction, amount))
        return FakeInteractionResult(True, f"Scrolled {direction} {amount}px", "fake_b64_after_scroll")

    async def screenshot(self, url, full_page=False):
        self.screenshot_calls.append((url, full_page))
        return "fake_base64_png_data"


@pytest.fixture
def agent_mod():
    import importlib
    return importlib.import_module("ai_core.agent")


@pytest.fixture
def mock_agent_with_browser(agent_mod):
    class _Agent:
        web_browser = FakeWebBrowser()
    a = _Agent()
    agent_mod.global_agent = a
    yield a
    agent_mod.global_agent = None


@pytest.mark.asyncio
async def test_scroll_calls_real_method_with_correct_args(
    agent_mod, mock_agent_with_browser, fake_request
):
    req = fake_request({"url": "https://example.com", "direction": "up", "amount": 300})
    result = await agent_mod.browser_scroll(req)

    assert mock_agent_with_browser.web_browser.scroll_calls == [
        ("https://example.com", "up", 300)
    ]
    assert result == {
        "status": "ok", "message": "Scrolled up 300px", "screenshot": "fake_b64_after_scroll"
    }


@pytest.mark.asyncio
async def test_scroll_uses_sensible_defaults_when_fields_omitted(
    agent_mod, mock_agent_with_browser, fake_request
):
    req = fake_request({"url": "https://example.com"})
    await agent_mod.browser_scroll(req)
    url, direction, amount = mock_agent_with_browser.web_browser.scroll_calls[0]
    assert direction == "down"
    assert amount == 600


@pytest.mark.asyncio
async def test_scroll_without_browser_attached_raises_404(agent_mod, fake_request):
    class _AgentNoBrowser:
        pass
    agent_mod.global_agent = _AgentNoBrowser()
    try:
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await agent_mod.browser_scroll(fake_request({"url": "https://example.com"}))
        assert exc_info.value.status_code == 404
    finally:
        agent_mod.global_agent = None


@pytest.mark.asyncio
async def test_screenshot_calls_real_method_with_correct_args(
    agent_mod, mock_agent_with_browser
):
    result = await agent_mod.browser_screenshot(url="https://example.com", full_page=True)

    assert mock_agent_with_browser.web_browser.screenshot_calls == [
        ("https://example.com", True)
    ]
    assert result == {"status": "ok", "screenshot": "fake_base64_png_data"}


@pytest.mark.asyncio
async def test_screenshot_full_page_defaults_to_false(agent_mod, mock_agent_with_browser):
    await agent_mod.browser_screenshot(url="https://example.com")
    _, full_page = mock_agent_with_browser.web_browser.screenshot_calls[0]
    assert full_page is False


@pytest.mark.asyncio
async def test_screenshot_reports_error_status_when_browser_returns_none(
    agent_mod, mock_agent_with_browser
):
    """screenshot() returns None on failure/blocked URLs - the route must
    surface that as an error status, not silently claim success."""
    async def returns_none(url, full_page=False):
        return None
    mock_agent_with_browser.web_browser.screenshot = returns_none

    result = await agent_mod.browser_screenshot(url="https://blocked-site.example")
    assert result["status"] == "error"