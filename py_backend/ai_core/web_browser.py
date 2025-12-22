# ai_core/web_browser.py - AUTONOMOUS WEB BROWSING FOR AI
"""
Web Browser Module for Autonomous AI Learning
==============================================
Allows AI agents to browse websites permitted by the frontend.
The AI just surfs and stores raw content - the existing brain/memory
systems handle all learning naturally.

Features:
- Respects frontend's allowed websites
- Extracts and stores web content
- Brain/memory systems handle learning automatically
- Rate limiting and safety checks
"""

import asyncio
import time
import logging
from typing import Dict, Any, List, Optional, Set
from urllib.parse import urlparse, urljoin
from collections import deque

# Web scraping imports
try:
    import aiohttp
    from bs4 import BeautifulSoup
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logging.warning("aiohttp not available - install with: pip install aiohttp beautifulsoup4")

log = logging.getLogger("web_browser")


class WebPage:
    """Represents a scraped web page"""
    
    def __init__(self, url: str, html: str, timestamp: float):
        self.url = url
        self.html = html
        self.timestamp = timestamp
        self.soup = BeautifulSoup(html, 'html.parser') if html else None
        
        # Extracted content
        self.title = self._extract_title()
        self.text = self._extract_text()
        self.links = self._extract_links()
        self.images = self._extract_images()
        self.metadata = self._extract_metadata()
    
    def _extract_title(self) -> str:
        """Extract page title"""
        if not self.soup:
            return ""
        title_tag = self.soup.find('title')
        return title_tag.get_text(strip=True) if title_tag else ""
    
    def _extract_text(self) -> str:
        """Extract main text content"""
        if not self.soup:
            return ""
        
        # Remove script and style elements
        for script in self.soup(["script", "style", "nav", "footer", "header"]):
            script.decompose()
        
        # Get text from main content areas
        main_content = self.soup.find('main') or self.soup.find('article') or self.soup.find('body')
        
        if main_content:
            text = main_content.get_text(separator='\n', strip=True)
        else:
            text = self.soup.get_text(separator='\n', strip=True)
        
        # Clean up whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return '\n'.join(lines)
    
    def _extract_links(self) -> List[str]:
        """Extract all links"""
        if not self.soup:
            return []
        
        links = []
        for a_tag in self.soup.find_all('a', href=True):
            href = a_tag['href']
            # Convert relative URLs to absolute
            full_url = urljoin(self.url, href)
            links.append(full_url)
        
        return list(set(links))  # Remove duplicates
    
    def _extract_images(self) -> List[str]:
        """Extract image URLs"""
        if not self.soup:
            return []
        
        images = []
        for img_tag in self.soup.find_all('img', src=True):
            src = img_tag['src']
            full_url = urljoin(self.url, src)
            images.append(full_url)
        
        return images
    
    def _extract_metadata(self) -> Dict[str, Any]:
        """Extract page metadata"""
        if not self.soup:
            return {}
        
        metadata = {}
        
        # Meta tags
        for meta in self.soup.find_all('meta'):
            name = meta.get('name') or meta.get('property')
            content = meta.get('content')
            if name and content:
                metadata[name] = content
        
        # Headings
        headings = []
        for i in range(1, 4):  # h1, h2, h3
            for heading in self.soup.find_all(f'h{i}'):
                headings.append({
                    'level': i,
                    'text': heading.get_text(strip=True)
                })
        metadata['headings'] = headings
        
        return metadata
    
    def get_summary(self, max_length: int = 500) -> str:
        """Get page summary"""
        summary = f"Title: {self.title}\n\n"
        
        if len(self.text) <= max_length:
            summary += self.text
        else:
            summary += self.text[:max_length] + "..."
        
        return summary


class WebBrowser:
    """
    Autonomous web browser for AI agents.
    Just fetches and stores content - brain/memory handle learning.
    """
    
    def __init__(self, agent):
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp required: pip install aiohttp beautifulsoup4")
        
        self.agent = agent
        
        # Allowed domains (set by frontend)
        self.allowed_domains: Set[str] = set()
        
        # Browsing history
        self.visited_urls: Set[str] = set()
        self.page_cache: Dict[str, WebPage] = {}
        
        # Browse queue (URLs to visit)
        self.browse_queue: deque = deque(maxlen=100)
        
        # Rate limiting
        self.last_request_time: Dict[str, float] = {}
        self.min_request_interval = 2.0  # seconds between requests to same domain
        
        # Statistics
        self.stats = {
            'pages_visited': 0,
            'total_text_bytes': 0,
            'links_discovered': 0,
            'last_browse_time': 0
        }
        
        # Session
        self.session: Optional[aiohttp.ClientSession] = None
        
        log.info(f"WebBrowser initialized for {agent.agent_id}")
    
    async def _ensure_session(self):
        """Ensure aiohttp session exists"""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': f'DivineWorldAI/{self.agent.agent_id}'
                }
            )
    
    def update_allowed_websites(self, websites: List[Dict[str, Any]]):
        """Update allowed websites from frontend"""
        self.allowed_domains.clear()
        
        for site in websites:
            if site.get('enabled', True):
                url = site.get('url', '')
                domain = self._extract_domain(url)
                if domain:
                    self.allowed_domains.add(domain)
                    log.info(f"Allowed domain: {domain}")
        
        log.info(f"Updated allowed domains: {len(self.allowed_domains)} domains")
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path
            # Remove www.
            domain = domain.replace('www.', '')
            return domain.lower()
        except Exception:
            return ""
    
    def _is_url_allowed(self, url: str) -> bool:
        """Check if URL is from allowed domain"""
        domain = self._extract_domain(url)
        
        # Check if domain matches any allowed domain
        for allowed in self.allowed_domains:
            if domain == allowed or domain.endswith('.' + allowed):
                return True
        
        return False
    
    def _can_request_now(self, url: str) -> bool:
        """Check rate limiting"""
        domain = self._extract_domain(url)
        
        last_time = self.last_request_time.get(domain, 0)
        current_time = time.time()
        
        return (current_time - last_time) >= self.min_request_interval
    
    async def browse(self, url: str) -> Optional[WebPage]:
        """
        Browse a URL and store the content.
        Brain/memory systems will handle learning from stored content.
        
        Args:
            url: URL to visit
        
        Returns:
            WebPage object or None if failed
        """
        # Security checks
        if not self._is_url_allowed(url):
            log.warning(f"URL not allowed: {url}")
            return None
        
        if url in self.visited_urls:
            # Return cached if available
            if url in self.page_cache:
                log.debug(f"Using cached page: {url}")
                return self.page_cache[url]
        
        # Rate limiting
        if not self._can_request_now(url):
            wait_time = self.min_request_interval - (time.time() - self.last_request_time.get(self._extract_domain(url), 0))
            log.debug(f"Rate limited, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
        
        try:
            await self._ensure_session()
            
            log.info(f"🌐 Browsing: {url}")
            
            # Fetch page
            async with self.session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    log.warning(f"HTTP {response.status} for {url}")
                    return None
                
                html = await response.text()
            
            # Update rate limiting
            domain = self._extract_domain(url)
            self.last_request_time[domain] = time.time()
            
            # Create WebPage object
            page = WebPage(url, html, time.time())
            
            # Cache page
            self.page_cache[url] = page
            self.visited_urls.add(url)
            
            # Update stats
            self.stats['pages_visited'] += 1
            self.stats['total_text_bytes'] += len(page.text)
            self.stats['links_discovered'] += len(page.links)
            self.stats['last_browse_time'] = time.time()
            
            # Just store in memory - let brain/memory handle learning
            # This is the KEY CHANGE - we're not forcing learning
            self.agent.memory.remember({
                'type': 'web_page',
                'url': url,
                'title': page.title,
                'text': page.text,  # Raw text for brain to process naturally
                'summary': page.get_summary(500),
                'links': page.links[:10],  # First 10 links
                'metadata': page.metadata,
                'timestamp': time.time()
            }, tags=['web', 'browsing', 'content'])
            
            # Discover new links to explore
            self._discover_links(page)
            
            log.info(f"✅ Browsed: {page.title} ({len(page.text)} chars)")
            
            return page
            
        except asyncio.TimeoutError:
            log.error(f"Timeout browsing {url}")
            return None
        except Exception as e:
            log.error(f"Error browsing {url}: {e}")
            return None
    
    def _discover_links(self, page: WebPage):
        """Discover and queue interesting links"""
        for link in page.links:
            # Check if allowed
            if not self._is_url_allowed(link):
                continue
            
            # Skip if already visited
            if link in self.visited_urls:
                continue
            
            # Skip common non-content pages
            if any(pattern in link.lower() for pattern in ['login', 'signin', 'register', 'cart', 'checkout']):
                continue
            
            # Add to queue
            if link not in self.browse_queue:
                self.browse_queue.append(link)
    
    async def autonomous_browse(self, max_pages: int = 3):
        """
        Autonomously browse queued URLs.
        Called by cognitive loop when agent is curious.
        """
        if not self.browse_queue:
            log.debug("No URLs in browse queue")
            return
        
        pages_browsed = 0
        
        while self.browse_queue and pages_browsed < max_pages:
            url = self.browse_queue.popleft()
            
            page = await self.browse(url)
            
            if page:
                pages_browsed += 1
                
                # Small delay between pages
                await asyncio.sleep(1.0)
        
        if pages_browsed > 0:
            log.info(f"🌐 Autonomous browsing completed: {pages_browsed} pages")
    
    def add_url_to_queue(self, url: str):
        """Add URL to browse queue"""
        if self._is_url_allowed(url) and url not in self.visited_urls:
            self.browse_queue.append(url)
            log.info(f"Queued URL: {url}")
    
    def search_cached_pages(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search cached pages for query"""
        query_lower = query.lower()
        results = []
        
        for url, page in self.page_cache.items():
            # Search in title and text
            relevance = 0
            
            if query_lower in page.title.lower():
                relevance += 10
            
            if query_lower in page.text.lower():
                relevance += page.text.lower().count(query_lower)
            
            if relevance > 0:
                results.append({
                    'url': url,
                    'title': page.title,
                    'relevance': relevance,
                    'summary': page.get_summary(200)
                })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        
        return results[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get browsing statistics"""
        return {
            **self.stats,
            'allowed_domains': len(self.allowed_domains),
            'cached_pages': len(self.page_cache),
            'queue_size': len(self.browse_queue),
            'visited_urls': len(self.visited_urls)
        }
    
    async def close(self):
        """Close browser session"""
        if self.session and not self.session.closed:
            await self.session.close()
            log.info("WebBrowser session closed")


# Integration function
def add_web_browsing_to_agent(agent):
    """
    Add web browsing capability to agent.
    
    Usage:
        from ai_core.web_browser import add_web_browsing_to_agent
        add_web_browsing_to_agent(agent)
    """
    if not AIOHTTP_AVAILABLE:
        log.warning("Web browsing not available - install aiohttp and beautifulsoup4")
        return None
    
    browser = WebBrowser(agent)
    agent.web_browser = browser
    
    log.info(f"✅ Web browsing added to {agent.agent_id}")
    return browser


# Simple helper for cognitive loop integration
async def browse_if_curious(agent, max_pages: int = 2):
    """
    Simple function for cognitive loop to call.
    Just browses if the agent has queued URLs.
    """
    if not hasattr(agent, 'web_browser'):
        return
    
    browser = agent.web_browser
    
    # Browse queued URLs if available
    if browser.browse_queue:
        await browser.autonomous_browse(max_pages=max_pages)