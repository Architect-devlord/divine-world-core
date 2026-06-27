# ai_core/web_browser.py - AUTONOMOUS WEB BROWSING FOR AI
"""
Web Browser Module for Autonomous AI Learning
==============================================
Inspired by VS Code 1.110's native browser integration (Feb 2026):
  - DOM element interaction (click, type, scroll, hover)
  - Visual page snapshots / screenshots
  - Real-time console log capture (JS errors, network events)
  - Accessibility tree snapshots for token-efficient page understanding
  - JavaScript execution in a live browser context
  - Playwright-backed automation (not raw HTTP scraping)

The AI can now truly *see and interact* with pages rather than just
scraping raw HTML. Brain/memory systems still handle all learning.

Design rules
------------
- WebBrowser is a TOOL only. It browses when told to.
- brain_core.should_browse() owns the decision of WHEN to browse.
- cognitive_loop._think() calls brain.should_browse() each cycle and
  sets thoughts['should_browse'] = True when the agent wants to look
  something up. _execute_web_browsing() then calls browser.browse()
  directly — no intermediate helper needed.
- agent.process_chat() stores mentioned URLs as memory events.
  Only explicit user requests ("check", "look at", etc.) queue a URL
  immediately. The agent decides autonomously the rest of the time.

Dependencies:
    pip install playwright beautifulsoup4
    playwright install chromium
"""

import asyncio
import base64
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

log = logging.getLogger("web_browser")

# ---------------------------------------------------------------------------
# Optional dependency guards
# ---------------------------------------------------------------------------
try:
    from playwright.async_api import (
        Browser,
        BrowserContext,
        ConsoleMessage,
        Page,
        Playwright,
        async_playwright,
    )
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    log.warning(
        "Playwright not available. Install with:\n"
        "  pip install playwright\n"
        "  playwright install chromium"
    )

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ConsoleEntry:
    """A single browser console message."""
    level: str          # 'log' | 'warn' | 'error' | 'info' | 'debug'
    text: str
    timestamp: float
    url: str = ""       # source URL if available


@dataclass
class DOMElement:
    """A simplified accessibility-tree node (mirrors Playwright's aria snapshot)."""
    role: str
    name: str
    tag: str = ""
    selector: str = ""
    attributes: Dict[str, str] = field(default_factory=dict)
    children: List["DOMElement"] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "name": self.name,
            "tag": self.tag,
            "selector": self.selector,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class PageSnapshot:
    """
    A rich snapshot of a web page — what the agent *sees*.

    Captures:
      • Rendered visible text (post-JS)
      • Accessibility tree (structured, token-efficient element map)
      • Screenshot as base64 PNG
      • Console log buffer
      • All outgoing links (discovered from the live DOM)
      • Page metadata (title, description, headings)
    """
    url: str
    timestamp: float

    # Text / structure
    title: str = ""
    visible_text: str = ""
    accessibility_tree: List[Dict[str, Any]] = field(default_factory=list)

    # Visual
    screenshot_b64: Optional[str] = None   # base64-encoded PNG

    # Debug
    console_logs: List[ConsoleEntry] = field(default_factory=list)
    js_errors: List[ConsoleEntry] = field(default_factory=list)

    # Navigation
    links: List[str] = field(default_factory=list)

    # Meta
    metadata: Dict[str, str] = field(default_factory=dict)
    headings: List[Dict[str, Any]] = field(default_factory=list)

    # HTTP
    status_code: int = 200
    load_time_ms: float = 0.0

    def get_summary(self, max_length: int = 600) -> str:
        text_preview = (
            self.visible_text[:max_length] + "…"
            if len(self.visible_text) > max_length
            else self.visible_text
        )
        errors = [e.text for e in self.js_errors[:3]]
        return (
            f"Title: {self.title}\n"
            f"URL: {self.url}\n"
            f"Load: {self.load_time_ms:.0f}ms  |  Status: {self.status_code}\n"
            f"JS Errors: {errors or 'none'}\n\n"
            f"{text_preview}"
        )

    def to_memory_dict(self) -> Dict[str, Any]:
        """Serialise to the dict stored in agent memory."""
        return {
            "type": "web_page",
            "url": self.url,
            "title": self.title,
            "text": self.visible_text,
            "summary": self.get_summary(500),
            "accessibility_tree": self.accessibility_tree[:50],
            "has_screenshot": self.screenshot_b64 is not None,
            "console_logs": [
                {"level": e.level, "text": e.text} for e in self.console_logs[:20]
            ],
            "js_errors": [
                {"text": e.text} for e in self.js_errors[:10]
            ],
            "links": self.links[:15],
            "metadata": self.metadata,
            "headings": self.headings,
            "status_code": self.status_code,
            "load_time_ms": self.load_time_ms,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Browser interaction result
# ---------------------------------------------------------------------------

@dataclass
class InteractionResult:
    """Result of a DOM interaction (click / type / scroll / hover)."""
    success: bool
    action: str
    selector: str
    message: str = ""
    screenshot_b64: Optional[str] = None
    console_after: List[ConsoleEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core WebBrowser class
# ---------------------------------------------------------------------------

class WebBrowser:
    """
    Playwright-backed browser for AI agents.

    Capabilities (VS Code 1.110-style):
      1. DOM interaction  → click(), type_into(), hover(), scroll()
      2. Visual snapshots → screenshot() returns base64 PNG
      3. Console capture  → JS errors, warnings, network events streamed live
      4. Accessibility tree → structured element map (role/name/selector)
      5. JS execution     → evaluate() runs arbitrary JS in page context
      6. Dynamic content  → waits for JS to settle before capture

    This class is a pure tool. It does not decide when to browse.
    brain_core.should_browse() owns that decision.
    """

    def __init__(self, agent):
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright required:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )

        self.agent = agent

        # Permission model (set by frontend via update_allowed_websites)
        self.allowed_domains: Set[str] = set()
        self.allowed_urls: Set[str] = set()

        # State
        self.visited_urls: Set[str] = set()
        self.page_cache: Dict[str, PageSnapshot] = {}
        self.browse_queue: deque = deque(maxlen=200)

        # FIX (Chat & Web GRPO plan §3.6b): rolling window of recently visited
        # distinct domains, for introspection/debugging (exposed via
        # get_stats() below). Note: the actual evidence_r diversity SCORING
        # in reward_system.py maintains its own separate _recent_domains —
        # RewardSystem has no live reference to this WebBrowser instance, so
        # it tracks domains straight from each web event's own payload
        # instead. This deque is for visibility into this object directly
        # (e.g. the human-controller debug panel), not the reward path.
        self._recent_domains: deque = deque(maxlen=20)

        # Rate limiting
        self.last_request_time: Dict[str, float] = {}
        self.min_request_interval: float = 2.0   # seconds per domain

        # Stats (last_browse_time read by brain_core.should_browse())
        self.stats: Dict[str, Any] = {
            "pages_visited": 0,
            "total_text_bytes": 0,
            "links_discovered": 0,
            "js_errors_caught": 0,
            "screenshots_taken": 0,
            "interactions_performed": 0,
            "last_browse_time": 0.0,
        }

        # Playwright objects (lazy-initialised on first browse)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

        log.info("WebBrowser (Playwright) initialised for %s", agent.agent_id)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def _ensure_browser(self):
        """Start Playwright + Chromium if not already running."""
        if self._browser is not None:
            return
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=f"DivineWorldAI/{self.agent.agent_id}",
            java_script_enabled=True,
        )
        log.info("Chromium browser started")

    async def close(self):
        """Gracefully shut down the browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        log.info("WebBrowser session closed")

    # ------------------------------------------------------------------
    # Permission helpers
    # ------------------------------------------------------------------

    def update_allowed_websites(self, websites: List[Dict[str, Any]]):
        """Sync allowed sites from frontend config."""
        self.allowed_domains.clear()
        self.allowed_urls.clear()

        for site in websites:
            if not site.get("enabled", True):
                continue
            url = site.get("url", "")
            if site.get("type", "domain") == "domain":
                domain = self._extract_domain(url)
                if domain:
                    self.allowed_domains.add(domain)
                    log.info("Allowed domain: %s", domain)
            else:
                self.allowed_urls.add(url)
                log.info("Allowed URL: %s", url)

        log.info(
            "Permissions updated: %d domains, %d URLs",
            len(self.allowed_domains), len(self.allowed_urls),
        )

    @staticmethod
    def _extract_domain(url: str) -> str:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            return domain.replace("www.", "").lower()
        except Exception:
            return ""

    def _is_url_allowed(self, url: str) -> bool:
        if url in self.allowed_urls:
            return True
        for allowed in self.allowed_urls:
            if url.startswith(allowed):
                return True
        domain = self._extract_domain(url)
        for allowed in self.allowed_domains:
            if domain == allowed or domain.endswith("." + allowed):
                return True
        return False

    async def _rate_limit(self, url: str):
        domain = self._extract_domain(url)
        last = self.last_request_time.get(domain, 0.0)
        wait = self.min_request_interval - (time.time() - last)
        if wait > 0:
            log.debug("Rate limiting: sleeping %.1fs for %s", wait, domain)
            await asyncio.sleep(wait)
        self.last_request_time[domain] = time.time()

    # ------------------------------------------------------------------
    # Core: browse a URL
    # ------------------------------------------------------------------

    async def browse(
        self,
        url: str,
        take_screenshot: bool = True,
        wait_for: str = "networkidle",
    ) -> Optional[PageSnapshot]:
        """
        Navigate to *url* and return a rich PageSnapshot.

        Called directly by cognitive_loop._execute_web_browsing() —
        no intermediate helper. The brain decided to browse; this executes it.
        """
        if not self._is_url_allowed(url):
            log.warning("URL not allowed: %s", url)
            return None

        if url in self.page_cache:
            log.debug("Cache hit: %s", url)
            return self.page_cache[url]

        await self._rate_limit(url)
        await self._ensure_browser()

        console_logs: List[ConsoleEntry] = []
        js_errors: List[ConsoleEntry] = []
        page: Page = await self._context.new_page()

        def _on_console(msg: "ConsoleMessage"):
            entry = ConsoleEntry(level=msg.type, text=msg.text, timestamp=time.time())
            console_logs.append(entry)
            if msg.type == "error":
                js_errors.append(entry)

        def _on_pageerror(exc):
            js_errors.append(ConsoleEntry(level="error", text=str(exc), timestamp=time.time()))

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)

        try:
            t0 = time.time()
            log.info("🌐 Navigating to: %s", url)

            response = await page.goto(url, wait_until=wait_for, timeout=30_000)
            status_code = response.status if response else 0
            load_time_ms = (time.time() - t0) * 1000

            await asyncio.sleep(0.5)   # allow late JS to settle

            title              = await page.title()
            visible_text       = await self._extract_visible_text(page)
            accessibility_tree = await self._extract_accessibility_tree(page)
            links              = await self._extract_links(page, url)
            metadata, headings = await self._extract_metadata_and_headings(page)

            screenshot_b64: Optional[str] = None
            if take_screenshot:
                raw = await page.screenshot(type="png", full_page=False)
                screenshot_b64 = base64.b64encode(raw).decode()
                self.stats["screenshots_taken"] += 1

            snapshot = PageSnapshot(
                url=url, timestamp=time.time(),
                title=title, visible_text=visible_text,
                accessibility_tree=accessibility_tree,
                screenshot_b64=screenshot_b64,
                console_logs=console_logs, js_errors=js_errors,
                links=links, metadata=metadata, headings=headings,
                status_code=status_code, load_time_ms=load_time_ms,
            )

            self.page_cache[url]  = snapshot
            self.visited_urls.add(url)
            self._recent_domains.append(self._extract_domain(url))
            self.stats["pages_visited"]     += 1
            self.stats["total_text_bytes"]  += len(visible_text)
            self.stats["links_discovered"]  += len(links)
            self.stats["js_errors_caught"]  += len(js_errors)
            self.stats["last_browse_time"]   = time.time()

            # Store in agent memory — language learning picks up the text
            self.agent.memory.remember(
                snapshot.to_memory_dict(),
                tags=["web", "browsing", "content"],
            )

            self._enqueue_links(links)

            log.info(
                "✅ %s | %d chars | %d JS errors | %.0fms",
                title, len(visible_text), len(js_errors), load_time_ms,
            )
            return snapshot

        except asyncio.TimeoutError:
            log.error("Timeout navigating to %s", url)
            return None
        except Exception as exc:
            log.error("Error browsing %s: %s", url, exc)
            return None
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # DOM interactions
    # ------------------------------------------------------------------

    async def click(
        self, url: str, selector: str, take_screenshot: bool = True,
    ) -> InteractionResult:
        """Click an element on a page."""
        if not self._is_url_allowed(url):
            return InteractionResult(False, "click", selector, "URL not allowed")

        await self._ensure_browser()
        console_after: List[ConsoleEntry] = []
        page: Page = await self._context.new_page()
        page.on("console", lambda m: console_after.append(
            ConsoleEntry(m.type, m.text, time.time())
        ))

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.click(selector, timeout=10_000)
            await asyncio.sleep(0.5)

            screenshot_b64: Optional[str] = None
            if take_screenshot:
                raw = await page.screenshot(type="png")
                screenshot_b64 = base64.b64encode(raw).decode()
                self.stats["screenshots_taken"] += 1

            self.stats["interactions_performed"] += 1
            log.info("🖱️  Clicked '%s' on %s", selector, url)
            return InteractionResult(
                success=True, action="click", selector=selector,
                message=f"Clicked '{selector}'",
                screenshot_b64=screenshot_b64, console_after=console_after,
            )
        except Exception as exc:
            log.error("Click failed on %s [%s]: %s", url, selector, exc)
            return InteractionResult(False, "click", selector, str(exc))
        finally:
            await page.close()

    async def type_into(
        self, url: str, selector: str, text: str,
        submit: bool = False, take_screenshot: bool = True,
    ) -> InteractionResult:
        """Focus an input element and type *text* into it."""
        if not self._is_url_allowed(url):
            return InteractionResult(False, "type", selector, "URL not allowed")

        await self._ensure_browser()
        page: Page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.fill(selector, text)
            if submit:
                await page.press(selector, "Enter")
                await page.wait_for_load_state("networkidle", timeout=10_000)

            screenshot_b64: Optional[str] = None
            if take_screenshot:
                raw = await page.screenshot(type="png")
                screenshot_b64 = base64.b64encode(raw).decode()
                self.stats["screenshots_taken"] += 1

            self.stats["interactions_performed"] += 1
            log.info("⌨️  Typed into '%s' on %s", selector, url)
            return InteractionResult(
                success=True, action="type", selector=selector,
                message=f"Typed '{text[:30]}…' into '{selector}'",
                screenshot_b64=screenshot_b64,
            )
        except Exception as exc:
            log.error("Type failed on %s [%s]: %s", url, selector, exc)
            return InteractionResult(False, "type", selector, str(exc))
        finally:
            await page.close()

    async def scroll(
        self, url: str, direction: str = "down",
        amount: int = 600, take_screenshot: bool = True,
    ) -> InteractionResult:
        """Scroll the page up or down by *amount* pixels."""
        if not self._is_url_allowed(url):
            return InteractionResult(False, "scroll", "", "URL not allowed")

        await self._ensure_browser()
        page: Page = await self._context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            delta = amount if direction == "down" else -amount
            await page.evaluate(f"window.scrollBy(0, {delta})")
            await asyncio.sleep(0.4)

            screenshot_b64: Optional[str] = None
            if take_screenshot:
                raw = await page.screenshot(type="png")
                screenshot_b64 = base64.b64encode(raw).decode()
                self.stats["screenshots_taken"] += 1

            self.stats["interactions_performed"] += 1
            return InteractionResult(
                success=True, action="scroll", selector="",
                message=f"Scrolled {direction} {amount}px",
                screenshot_b64=screenshot_b64,
            )
        except Exception as exc:
            log.error("Scroll failed on %s: %s", url, exc)
            return InteractionResult(False, "scroll", "", str(exc))
        finally:
            await page.close()

    async def evaluate(self, url: str, js_code: str) -> Any:
        """Execute arbitrary JavaScript in the page context and return the result."""
        if not self._is_url_allowed(url):
            log.warning("evaluate() blocked — URL not allowed: %s", url)
            return None

        await self._ensure_browser()
        page: Page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            result = await page.evaluate(js_code)
            log.info("🔧 JS evaluated on %s", url)
            return result
        except Exception as exc:
            log.error("evaluate() failed on %s: %s", url, exc)
            return None
        finally:
            await page.close()

    async def screenshot(self, url: str, full_page: bool = False) -> Optional[str]:
        """Take a screenshot and return it as a base64-encoded PNG string."""
        if not self._is_url_allowed(url):
            return None

        await self._ensure_browser()
        page: Page = await self._context.new_page()
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            raw = await page.screenshot(type="png", full_page=full_page)
            self.stats["screenshots_taken"] += 1
            return base64.b64encode(raw).decode()
        except Exception as exc:
            log.error("screenshot() failed on %s: %s", url, exc)
            return None
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Page analysis helpers
    # ------------------------------------------------------------------

    async def _extract_visible_text(self, page: "Page") -> str:
        try:
            text = await page.evaluate(
                """() => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: (node) => {
                                const el = node.parentElement;
                                if (!el) return NodeFilter.FILTER_REJECT;
                                const style = window.getComputedStyle(el);
                                if (style.display === 'none' || style.visibility === 'hidden')
                                    return NodeFilter.FILTER_REJECT;
                                const tag = el.tagName.toLowerCase();
                                if (['script','style','noscript'].includes(tag))
                                    return NodeFilter.FILTER_REJECT;
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    const chunks = [];
                    let node;
                    while ((node = walker.nextNode())) {
                        const t = node.textContent.trim();
                        if (t) chunks.push(t);
                    }
                    return chunks.join('\\n');
                }"""
            )
            return text or ""
        except Exception:
            try:
                return await page.inner_text("body")
            except Exception:
                return ""

    async def _extract_accessibility_tree(self, page: "Page") -> List[Dict[str, Any]]:
        try:
            snapshot = await page.accessibility.snapshot(interesting_only=True)
            if not snapshot:
                return []
            return self._flatten_a11y(snapshot)
        except Exception as exc:
            log.debug("Accessibility snapshot failed: %s", exc)
            return []

    def _flatten_a11y(
        self, node: Dict[str, Any], depth: int = 0, max_depth: int = 6,
    ) -> List[Dict[str, Any]]:
        if depth > max_depth:
            return []
        result: List[Dict[str, Any]] = []
        entry = {
            "role":    node.get("role", ""),
            "name":    node.get("name", ""),
            "value":   node.get("value", ""),
            "checked": node.get("checked"),
            "depth":   depth,
        }
        entry = {k: v for k, v in entry.items() if v is not None and v != ""}
        if entry:
            result.append(entry)
        for child in node.get("children", []):
            result.extend(self._flatten_a11y(child, depth + 1, max_depth))
        return result

    async def _extract_links(self, page: "Page", base_url: str) -> List[str]:
        try:
            hrefs: List[str] = await page.evaluate(
                "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
            )
            seen: Set[str] = set()
            links: List[str] = []
            for href in hrefs:
                full = urljoin(base_url, href).split("#")[0]
                if full not in seen and full.startswith("http"):
                    seen.add(full)
                    links.append(full)
            return links
        except Exception:
            return []

    async def _extract_metadata_and_headings(
        self, page: "Page"
    ) -> tuple[Dict[str, str], List[Dict[str, Any]]]:
        try:
            data = await page.evaluate(
                """() => {
                    const meta = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        const val = m.getAttribute('content');
                        if (key && val) meta[key] = val;
                    });
                    const headings = [];
                    document.querySelectorAll('h1,h2,h3').forEach(h => {
                        headings.push({ level: parseInt(h.tagName[1]), text: h.innerText.trim() });
                    });
                    return { meta, headings };
                }"""
            )
            return data.get("meta", {}), data.get("headings", [])
        except Exception:
            return {}, []

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def _enqueue_links(self, links: List[str]):
        skip = {"login", "signin", "register", "cart", "checkout", "logout"}
        for link in links:
            if not self._is_url_allowed(link):
                continue
            if link in self.visited_urls:
                continue
            if any(p in link.lower() for p in skip):
                continue
            if link not in self.browse_queue:
                self.browse_queue.append(link)

    def add_url_to_queue(self, url: str):
        """
        Explicitly queue a URL for browsing.

        Called by agent.process_chat() only when the user uses an explicit
        action word ("check", "look at", "browse", etc.) alongside a URL.
        Autonomous browsing decisions go through brain.should_browse() instead.
        """
        if self._is_url_allowed(url) and url not in self.visited_urls:
            self.browse_queue.append(url)
            log.info("Queued: %s", url)

    async def autonomous_browse(
        self,
        max_pages: int = 3,
        take_screenshots: bool = True,
    ):
        """
        Browse queued URLs up to *max_pages*.

        Kept for external callers that want to drive the browser directly.
        The cognitive loop calls browser.browse() individually instead,
        so it can interleave memory storage and speech between pages.
        """
        if not self.browse_queue:
            return
        browsed = 0
        while self.browse_queue and browsed < max_pages:
            url = self.browse_queue.popleft()
            snapshot = await self.browse(url, take_screenshot=take_screenshots)
            if snapshot:
                browsed += 1
                await asyncio.sleep(1.0)
        if browsed:
            log.info("🌐 Autonomous browse complete: %d pages", browsed)

    # ------------------------------------------------------------------
    # Memory search
    # ------------------------------------------------------------------

    def search_cached_pages(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Full-text search over cached page snapshots."""
        q = query.lower()
        results = []
        for url, snap in self.page_cache.items():
            score = snap.title.lower().count(q) * 10
            score += snap.visible_text.lower().count(q)
            if score:
                results.append({
                    "url": url,
                    "title": snap.title,
                    "relevance": score,
                    "summary": snap.get_summary(200),
                    "js_errors": len(snap.js_errors),
                    "has_screenshot": snap.screenshot_b64 is not None,
                })
        results.sort(key=lambda x: x["relevance"], reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self.stats,
            "allowed_domains": len(self.allowed_domains),
            "cached_pages":    len(self.page_cache),
            "queue_size":      len(self.browse_queue),
            "visited_urls":    len(self.visited_urls),
            # FIX (Chat & Web GRPO plan §3.6b): was previously not exposed —
            # get_stats() reported counts only, never the recent distinct set.
            "recent_domains":  list(self._recent_domains),
        }


# ---------------------------------------------------------------------------
# Integration helper
# ---------------------------------------------------------------------------

def add_web_browsing_to_agent(agent) -> Optional["WebBrowser"]:
    """
    Attach a WebBrowser instance to *agent*.

    After this call:
      - agent.web_browser is a WebBrowser ready to browse allowed domains
      - brain_core.should_browse() controls WHEN the agent decides to browse
      - cognitive_loop._think() checks should_browse() each cycle and calls
        browser.browse() directly in _execute_web_browsing()
      - Users can explicitly trigger browsing by using action words
        ("check", "look at", "browse", "visit") when mentioning a URL in chat

    Usage
    -----
        from ai_core.web_browser import add_web_browsing_to_agent
        add_web_browsing_to_agent(agent)
    """
    if not PLAYWRIGHT_AVAILABLE:
        log.warning(
            "Web browsing unavailable. Install:\n"
            "  pip install playwright && playwright install chromium"
        )
        return None

    browser = WebBrowser(agent)
    agent.web_browser = browser
    log.info("✅ Playwright web browser attached to %s", agent.agent_id)
    return browser