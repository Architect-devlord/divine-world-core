"""
agent_stub_server.py — a lightweight stand-in for agent.py's `global_agent`,
for testing the React/Electron frontend without the real brain/policy/world-
model stack needing to initialize at all.

Same philosophy as human_controller_server.py, applied to the Electron
frontend instead of the Minecraft body: verify the pipeline (in this case,
the FRONTEND's rendering and request/response handling) without needing the
real AI stack to be correct or even running. This is a standalone, separate
tool — it doesn't import anything from agent.py's NPCAgent, brain_core, or
policy/world_model, on purpose, so it can never accidentally depend on (or
destabilize) the real agent implementation.

One deliberate exception: py_backend.ai_core.web_browser.WebBrowser. Checked
its constructor before importing it — it only touches `agent.agent_id` (for
logging and the browser's user-agent string), nothing from brain_core/
policy/world_model — so it's exactly as "standalone" as everything else
here, and using the REAL Playwright+Chromium browser means "surf the
allowed websites" is genuinely tested, not faked. Falls back to a no-op
stand-in automatically if Playwright/Chromium isn't installed, so this file
still runs with zero extra setup for people who only want to test chat/
controller-mode/status.

It exposes the EXACT SAME HTTP/WebSocket surface the React app's BACKEND_PORT
talks to (verified against agent.py route-by-route: /status, /thoughts,
/chat, /ws, /api/agents/{id}/web/allow, /api/controller/*, /api/upload) — so
`npm run dev` (with its Vite proxy to this port) needs zero changes to work
against this instead of a real agent.py process.

Unlike the real endpoints, /chat doesn't compute a response from a policy —
it waits (with a timeout fallback) for a HUMAN, on the companion /debug
control page, to type the agent's reply. That's the "communicate to the
frontend as the agent" part: a person stands in for what process_chat()
would normally return, so the actual React rendering/WS-handling code gets
exercised with real, human-timed interaction instead of canned data.

Run:
    python agent_stub_server.py --port 11400
Then, in the react-app folder:
    npm run dev
and open the Vite dev URL. Open http://localhost:11400/debug in a second
tab to drive the stub — reply to chat, fire test broadcasts, flip
controller-mode success/failure, edit the fake device/stats numbers, and
(if Playwright/Chromium is installed) browse a real allowed URL.
"""
import argparse
import asyncio
import json
import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, Query, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s - stub - %(message)s')
log = logging.getLogger("agent_stub")

# Real browsing, if available — see the module docstring for why importing
# this specifically doesn't compromise "no heavy AI stack needed."
sys.path.insert(0, str(Path(__file__).parent))
_REAL_BROWSER_IMPORT_ERROR = ""   # Python 3 deletes `as e` after the except block,
                                   # so anything that needs it later must be copied out.
try:
    from py_backend.ai_core.web_browser import WebBrowser as _RealWebBrowser
    _REAL_BROWSER_AVAILABLE = True
except Exception as _wb_import_err:
    _RealWebBrowser = None
    _REAL_BROWSER_AVAILABLE = False
    _REAL_BROWSER_IMPORT_ERROR = str(_wb_import_err)
    log.warning(f"Real WebBrowser unavailable ({_wb_import_err}) — falling back to a no-op "
                f"stand-in. Note this can fail for reasons OTHER than Playwright itself missing: "
                f"web_browser.py imports through the ai_core package's __init__.py, which pulls "
                f"in torch and the rest of the stack regardless of which submodule you wanted — "
                f"if you have Playwright installed and still see this, check the actual error "
                f"above before assuming it's a Playwright problem. Otherwise: "
                f"`pip install playwright beautifulsoup4 && playwright install chromium`.")


DEFAULT_TIMEOUT_S = 60.0   # how long /chat waits for a human reply before a canned fallback


# =============================================================================
# Stand-in objects — just enough surface for the real routes below to work
# =============================================================================

class _StubMemory:
    """Mirrors NPCAgent.memory's public surface the real routes touch."""
    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def remember(self, event: Dict[str, Any], tags: Optional[List[str]] = None):
        event = dict(event)
        event['_tags'] = tags or []
        event['_at']   = time.time()
        self.events.append(event)

    def get_stats(self) -> Dict[str, Any]:
        return {"total_events": len(self.events)}


class _StubWebBrowser:
    """Fallback only, used when the real WebBrowser (Playwright/Chromium)
    isn't installed — mirrors just enough of its public surface (the
    allow-list) so /api/agents/{id}/web/allow and the frontend's
    WebAccessManager still work, without being able to actually browse."""
    def __init__(self):
        self.allowed_websites: List[Dict[str, Any]] = []
        self.is_real = False

    def update_allowed_websites(self, websites: List[Any]):
        self.allowed_websites = websites
        # Defensive: the real /chat endpoint normalizes bare strings to
        # {'url':..} before calling this, but /api/agents/{id}/web/allow
        # passes whatever it received straight through — accept either so
        # a slightly-off test payload doesn't crash the whole debug server.
        labels = [w.get('url', w) if isinstance(w, dict) else w for w in websites]
        log.info(f"Allowed websites updated: {labels}")


class _StubControllerRuntime:
    """Stands in for py_backend.utils.dw_controller.ControllerRuntime.
    Driven entirely from the /debug page — nothing here touches a real
    camera, microphone, filesystem, or network device."""
    def __init__(self):
        self.running             = False
        self.enabled_permissions: Dict[str, bool] = {}
        self.fail_next_activate  = False   # /debug toggle: test the frontend's error path
        self._stats = {
            "camera_active": False, "microphone_active": False,
            "frames_processed": 0, "audio_chunks_processed": 0,
            "learning_events": 0, "files_processed": 0,
        }

    def grant_permissions(self, granted: List[str]):
        if self.fail_next_activate:
            self.fail_next_activate = False
            raise RuntimeError("Simulated failure (toggled from /debug)")
        self.enabled_permissions = {p: True for p in granted}

    def start_multimodal_learning(self, vision: bool = False, audio: bool = False):
        self.running = True
        self._stats["camera_active"]     = bool(vision)
        self._stats["microphone_active"] = bool(audio)

    def stop(self):
        self.running = False
        self._stats["camera_active"] = self._stats["microphone_active"] = False

    def get_stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def bump(self, key: str, by: int = 1):
        """Lets the /debug page manually tick frames/audio/learning/file
        counters, so the frontend's live stats display has something to show
        moving without needing real camera/mic capture running."""
        if key in self._stats:
            self._stats[key] += by


class StubAgent:
    """
    Stand-in for NPCAgent — implements exactly the interface the routes
    below call (get_info, thoughts, process_chat, memory, web_browser),
    nothing else. No brain_core, no policy, no world_model, no torch.
    """
    def __init__(self, agent_id: str = "stub-agent", custom_name: str = "Stub Test Agent"):
        self.agent_id    = agent_id
        self.custom_name = custom_name
        self.agent_type  = "npc"
        self.mode        = "stub"
        self.thoughts: List[Dict[str, Any]] = []
        self.memory      = _StubMemory()
        self.controller  = _StubControllerRuntime()

        if _REAL_BROWSER_AVAILABLE:
            try:
                self.web_browser = _RealWebBrowser(self)   # only needs self.agent_id
                self.web_browser.is_real = True
                log.info("Real WebBrowser (Playwright/Chromium) attached — "
                          "allowed websites will actually be browsed.")
            except Exception as e:
                log.warning(f"Real WebBrowser failed to construct ({e}) — falling back to stand-in.")
                self.web_browser = _StubWebBrowser()
        else:
            self.web_browser = _StubWebBrowser()

        self.auto_reply       = False
        self.canned_reply     = "(stub agent — no one answered on /debug in time)"
        self.reply_timeout_s  = DEFAULT_TIMEOUT_S

        self._pending: Dict[str, "asyncio.Future[str]"] = {}
        self._debug_ws_clients: List[WebSocket] = []

    def get_info(self) -> Dict[str, Any]:
        """Deliberately mirrors NPCAgent.get_info()'s real key set (see
        agent.py) so /status exercises the exact same frontend code path,
        just with fake/static values instead of a real running brain."""
        return {
            'agent_id':         self.agent_id,
            'custom_name':      self.custom_name,
            'agent_type':       self.agent_type,
            'mode':             self.mode,
            'gender':           'dual',
            'is_alive':         True,
            'step_count':       0,
            'health':           20.0,
            'hunger':           20.0,
            'personality':      {'gender': 'dual'},
            'emotions':         {},
            'memory_size':      len(self.memory.events),
            'dominant_emotion': 'neutral',
            'autonomous':       False,
            'tcp_port':         0,
            'backend_port':     0,
            'memory_stats':     self.memory.get_stats(),
            'metadata':         {'stub': True, 'note': 'agent_stub_server.py — not a real agent'},
        }

    async def _broadcast_debug(self, message: Dict[str, Any]):
        dead = []
        for ws in self._debug_ws_clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._debug_ws_clients:
                self._debug_ws_clients.remove(ws)

    async def process_chat(self, message: str, speaker_id: str = "web_user") -> str:
        """
        The interactive core: broadcasts the incoming message to every
        connected /debug page and waits for a human to type a reply there.
        Falls back to a canned line after reply_timeout_s so the real
        frontend's /chat call never hangs indefinitely if nobody's watching.
        """
        self.memory.remember({'type': 'chat_message', 'sender': 'user', 'message': message},
                              tags=['chat'])

        if self.auto_reply:
            return self.canned_reply

        if not self._debug_ws_clients:
            log.info("[chat] no /debug clients attached — using canned fallback immediately")
            return self.canned_reply

        req_id = uuid.uuid4().hex[:10]
        fut: "asyncio.Future[str]" = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        await self._broadcast_debug({
            "type": "incoming_chat", "req_id": req_id,
            "message": message, "speaker_id": speaker_id, "timestamp": time.time(),
        })
        log.info(f"[chat] waiting up to {self.reply_timeout_s:.0f}s for a human reply "
                 f"on /debug (req_id={req_id})")

        try:
            reply = await asyncio.wait_for(fut, timeout=self.reply_timeout_s)
        except asyncio.TimeoutError:
            reply = self.canned_reply
            log.info(f"[chat] {req_id} timed out — using canned fallback")
        finally:
            self._pending.pop(req_id, None)

        self.thoughts.append({"timestamp": time.time(), "thought": f"Replied to: {message[:60]}"})
        return reply

    def resolve_chat(self, req_id: str, reply_text: str) -> bool:
        fut = self._pending.get(req_id)
        if fut is None or fut.done():
            return False
        fut.set_result(reply_text)
        return True


# =============================================================================
# FastAPI app — route surface matches agent.py exactly (verified route by
# route against py_backend/ai_core/agent.py before writing this file)
# =============================================================================

agent = StubAgent()
active_websockets: List[WebSocket] = []   # the REAL /ws clients (the React app)


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    yield
    # Shutdown: close the real browser cleanly if one was launched
    # (browse() starts Chromium lazily on first use) — otherwise a headless
    # Chromium process would be left orphaned when this server exits.
    if getattr(agent.web_browser, 'is_real', False):
        try:
            await agent.web_browser.close()
        except Exception as e:
            log.debug(f"Browser shutdown: {e}")


app = FastAPI(title="Divine World — Frontend Debug Stub", lifespan=_lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


async def broadcast_to_clients(message: Dict[str, Any]):
    dead = []
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in active_websockets:
            active_websockets.remove(ws)


# ── Real surface (matches agent.py) ─────────────────────────────────────────

@app.websocket("/ws")
@app.websocket("/agent-ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.append(websocket)
    try:
        await websocket.send_json({
            "type": "connected", "agent_id": agent.agent_id,
            "protocol": "json", "version": "1.0.0-stub",
        })
        log.info(f"[WS] Frontend connected. Active: {len(active_websockets)}")
        while True:
            data    = await websocket.receive_text()
            message = json.loads(data)
            if message.get("type") == "chat":
                user_message = message.get("message", "")
                if user_message:
                    # FIX ("can't send a message after a few"): this used to
                    # `await agent.process_chat(...)` directly inline, which
                    # blocks THIS while-loop from reaching the next
                    # receive_text() until a human replies on /debug (or the
                    # timeout elapses) — so every message after the first
                    # just sat unread in the browser's send buffer for as
                    # long as process_chat() was waiting. Spawning it as its
                    # own task lets the loop go straight back to listening,
                    # so multiple messages can be in flight (each with its
                    # own req_id) at once, exactly like a real chat.
                    asyncio.create_task(_handle_ws_chat(websocket, user_message))
    except WebSocketDisconnect:
        log.info("[WS] Frontend disconnected")
    except Exception as e:
        log.error(f"[WS] Error: {e}")
    finally:
        if websocket in active_websockets:
            active_websockets.remove(websocket)


async def _handle_ws_chat(websocket: WebSocket, user_message: str):
    """Split out of websocket_endpoint so a slow/human-timed reply for one
    message can never block the receive loop from handling the next one."""
    try:
        response = await agent.process_chat(user_message)
        await websocket.send_json({
            "type": "chat", "from": "agent",
            "text": response, "timestamp": time.time(),
        })
    except Exception as e:
        log.error(f"[WS chat] {e}")


@app.get("/status")
async def get_status():
    return agent.get_info()


@app.get("/thoughts")
async def get_thoughts():
    return {"thoughts": agent.thoughts[-20:]}


@app.post("/chat")
async def chat(message: str = Form(...),
               agent_id: str = Form(None),
               speaker_id: str = Form(None),
               allowed_websites: str = Form(None)):
    if allowed_websites:
        try:
            websites_data = json.loads(allowed_websites)
            formatted = [
                {'url': w, 'enabled': True, 'type': 'url'} if isinstance(w, str) else w
                for w in websites_data
            ]
            agent.web_browser.update_allowed_websites(formatted)
        except Exception as e:
            log.error(f"Error updating allowed websites: {e}")

    response = await agent.process_chat(message, speaker_id=speaker_id or "web_user")
    await broadcast_to_clients({
        "type": "chat", "from": "agent", "text": response, "timestamp": time.time(),
    })
    return {"response": response}


@app.post("/api/agents/{agent_id_path}/web/allow")
async def allow_websites(agent_id_path: str, data: Dict[str, Any]):
    agent.web_browser.update_allowed_websites(data.get('websites', []))
    return {"status": "success"}


@app.get("/api/controller/detect-devices")
async def detect_devices(agent_id: str = "demo"):
    return {
        "status": "success",
        "devices": {
            "cameras":     ["Stub Webcam 0 (fake)"],
            "microphones": ["Stub Microphone 0 (fake)"],
        },
    }


@app.post("/api/controller/activate")
async def activate_controller(data: Dict[str, Any]):
    perm_settings = data.get("permissionSettings", {})
    granted = [k for k, v in perm_settings.items() if v]
    try:
        agent.controller.grant_permissions(granted)
        agent.controller.start_multimodal_learning(
            vision=perm_settings.get("camera", False),
            audio= perm_settings.get("microphone", False),
        )
        log.info(f"[controller] activated — permissions: {granted}")
        return {"status": "success", "permissions": granted}
    except Exception as e:
        log.info(f"[controller] activate failed (as configured): {e}")
        return {"status": "error", "message": str(e)}


@app.post("/api/controller/deactivate")
async def deactivate_controller(agent_id: str = Query(default="demo")):
    agent.controller.stop()
    return {"status": "success"}


@app.get("/api/controller/status")
async def controller_status(agent_id: str = "demo"):
    stats = agent.controller.get_stats()
    return {
        "active":            agent.controller.running,
        "camera_active":     stats.get("camera_active", False),
        "microphone_active": stats.get("microphone_active", False),
        "permissions":       agent.controller.enabled_permissions,
        "stats": {
            "frames_processed":       stats.get("frames_processed", 0),
            "audio_chunks_processed": stats.get("audio_chunks_processed", 0),
            "learning_events":        stats.get("learning_events", 0),
            "files_processed":        stats.get("files_processed", 0),
        },
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...),
                       agent_id: str    = Form(...),
                       filetype: str    = Form(...),
                       sync:     bool   = Form(False)):
    try:
        content      = await file.read()
        text_content = content.decode('utf-8', errors='replace')
        agent.memory.remember({
            'type': 'file_upload', 'filename': file.filename,
            'filetype': filetype, 'content': text_content, 'size': len(content),
        }, tags=['file', 'upload'])
        if sync:
            agent.thoughts.append({
                "timestamp": time.time(),
                "thought": f"Processed file: {file.filename} ({filetype})",
            })
        return {"success": True, "filename": file.filename, "size": len(content)}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# /debug — the human control panel (this stub's version of dw_controller.html)
# =============================================================================

@app.get("/debug")
async def debug_page():
    html_path = Path(__file__).parent / "agent_stub_debug.html"
    return FileResponse(html_path)


@app.websocket("/debug/ws")
async def debug_ws(websocket: WebSocket):
    """Separate from /ws on purpose: /ws is the REAL app's channel (matches
    agent.py exactly); this is only the control panel's own live feed, so
    the two can never be confused with each other."""
    await websocket.accept()
    agent._debug_ws_clients.append(websocket)
    try:
        await websocket.send_json({
            "type": "debug_connected",
            "frontend_clients": len(active_websockets),
        })
        while True:
            await websocket.receive_text()   # panel doesn't push anything over this socket
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in agent._debug_ws_clients:
            agent._debug_ws_clients.remove(websocket)


def _describe_allowed_websites(web_browser) -> List[str]:
    """
    The real WebBrowser normalizes update_allowed_websites() input into
    allowed_domains / allowed_urls sets and doesn't keep the original raw
    list around; the fallback _StubWebBrowser keeps it as-is. Handle both
    without needing to modify the real (unmodified, imported-as-is) class.
    """
    if getattr(web_browser, 'is_real', False):
        return sorted(web_browser.allowed_domains) + sorted(web_browser.allowed_urls)
    return [w.get('url', w) if isinstance(w, dict) else w for w in web_browser.allowed_websites]


@app.get("/debug/api/state")
async def debug_state():
    """Everything the control panel needs to render its current view."""
    return {
        "frontend_clients":  len(active_websockets),
        "pending_chats":     list(agent._pending.keys()),
        "auto_reply":        agent.auto_reply,
        "canned_reply":      agent.canned_reply,
        "reply_timeout_s":   agent.reply_timeout_s,
        "allowed_websites":  _describe_allowed_websites(agent.web_browser),
        "web_browser_real":  getattr(agent.web_browser, 'is_real', False),
        "controller": {
            "running":              agent.controller.running,
            "enabled_permissions":  agent.controller.enabled_permissions,
            "fail_next_activate":   agent.controller.fail_next_activate,
            "stats":                agent.controller.get_stats(),
        },
        "thoughts": agent.thoughts[-10:],
    }


@app.post("/debug/api/reply")
async def debug_reply(data: Dict[str, Any]):
    """Answer a specific pending /chat call as the agent."""
    req_id = data.get("req_id", "")
    text   = data.get("text", "")
    ok     = agent.resolve_chat(req_id, text)
    return {"ok": ok}


@app.post("/debug/api/settings")
async def debug_settings(data: Dict[str, Any]):
    """Toggle auto-reply mode / canned reply text / reply timeout."""
    if "auto_reply" in data:
        agent.auto_reply = bool(data["auto_reply"])
    if "canned_reply" in data:
        agent.canned_reply = str(data["canned_reply"])
    if "reply_timeout_s" in data:
        agent.reply_timeout_s = float(data["reply_timeout_s"])
    return {"ok": True}


@app.post("/debug/api/controller-config")
async def debug_controller_config(data: Dict[str, Any]):
    """Configure the fake ControllerRuntime from the panel: force the next
    /api/controller/activate call to fail (test the frontend's error path),
    or bump a stat counter so a 'live stats' display has something to show."""
    if "fail_next_activate" in data:
        agent.controller.fail_next_activate = bool(data["fail_next_activate"])
    if "bump" in data:
        agent.controller.bump(data["bump"], int(data.get("by", 1)))
    return {"ok": True, "controller": agent.controller.get_stats()}


@app.post("/debug/api/broadcast")
async def debug_broadcast(data: Dict[str, Any]):
    """
    Send an arbitrary WS message, in the exact shape App.jsx's switch
    statement expects, straight to the REAL frontend clients on /ws — lets
    /debug trigger agent_thought / agent_speech / activity_update /
    world_model_update / visualization_update without any of those needing
    a real brain to produce them. 'type' is required; everything else is
    passed through as-is, so the panel can send any shape App.jsx handles.
    """
    if "type" not in data:
        return JSONResponse({"error": "missing 'type'"}, status_code=400)
    data.setdefault("timestamp", time.time())
    await broadcast_to_clients(data)
    return {"ok": True, "sent_to": len(active_websockets)}


@app.post("/debug/api/browse")
async def debug_browse(data: Dict[str, Any]):
    """
    Manually trigger a real browse — the stand-in for what
    brain_core.should_browse() would normally decide autonomously. Only
    does something real if the real WebBrowser attached (Playwright/
    Chromium installed); otherwise reports that plainly rather than
    pretending to have browsed.
    """
    url = data.get("url", "")
    if not url:
        return JSONResponse({"error": "missing 'url'"}, status_code=400)

    if not getattr(agent.web_browser, 'is_real', False):
        return {
            "ok": False,
            "reason": "no_real_browser",
            "message": f"Real WebBrowser isn't attached. Import error was: "
                       f"{_REAL_BROWSER_IMPORT_ERROR or 'unknown'!r} — note this can be a "
                       f"transitive dependency (e.g. torch, via ai_core's package __init__.py) "
                       f"rather than Playwright itself; check the message above before assuming "
                       f"`playwright install chromium` is what's missing. Allow-list state can "
                       f"still be tested, but nothing will actually be fetched.",
        }

    if not agent.web_browser._is_url_allowed(url):
        return {"ok": False, "reason": "not_allowed",
                "message": f"{url} isn't in the current allow-list — set it from the "
                           f"React app's Web Access panel first."}

    try:
        snapshot = await agent.web_browser.browse(url)
        if snapshot is None:
            return {"ok": False, "reason": "not_allowed", "message": f"{url} was rejected by the allow-list check."}
        agent.thoughts.append({"timestamp": time.time(), "thought": f"Browsed: {url}"})
        return {"ok": True, "summary": snapshot.get_summary(800), "url": snapshot.url,
                "title": snapshot.title, "load_time_ms": snapshot.load_time_ms}
    except Exception as e:
        log.error(f"[browse] {url} failed: {e}")
        return {"ok": False, "reason": "error", "message": str(e)}


# =============================================================================
# Entry point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=11400,
                         help="Port to serve on — 11400 matches react-app/vite.config.js's "
                              "dev-server proxy target, so `npm run dev` needs no changes.")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    import uvicorn
    log.info(f"Frontend debug stub on http://{args.host}:{args.port}  "
             f"(control panel: http://localhost:{args.port}/debug)")
    log.info("This is NOT a real agent — no brain, no policy, no world model. "
              "For testing the React frontend only.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()