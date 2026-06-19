#!/usr/bin/env python3
"""
DivineWorld Human Controller Server
=====================================
Run this INSTEAD of the regular Python AI agent for the selected agent.
It bridges your browser-based controller to the Minecraft DWClientBot.

Quick start:
    pip install fastapi "uvicorn[standard]" websockets
    python human_controller_server.py
    Open: http://localhost:8888

Architecture:
    Browser ←──WS /ws/human──→ [This Server] ←──WS (agent port) ←── DWClientBot
                                              └──TCP (action port) ──→ DWClientBot

Port mapping (from agents.json, same as AgentsJsonReader.java):
    tcp_port = agents.json value  (e.g. 11401)
    ws_port  = tcp_port + 10000   (e.g. 21401)

NOTE:
    Make sure NO Python AI agent process is running for the selected agent —
    its ports will conflict with this server.
    Start Minecraft AFTER selecting an agent here (TCP connect retries automatically).
"""

import asyncio
import base64
import json
import logging
import socket
import struct
import time
from pathlib import Path
from typing import Optional, Set, Any

import uvicorn
import websockets
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("dw_hc")

BROWSER_PORT   = 8888
WS_PORT_OFFSET = 10000  # matches AgentsJsonReader.WS_PORT_OFFSET


# ─────────────────────────────────────────────────────────────────────────────
# Global state  (single-controller: one browser operator, one agent at a time)
# ─────────────────────────────────────────────────────────────────────────────
class _St:
    agent_name: str           = ""
    agent_type: str           = "npc"
    god_type:   Optional[str] = None
    tcp_port:   int           = 0
    ws_port:    int           = 0

    tcp_sock: Optional[socket.socket] = None
    mc_ws:    Optional[Any]           = None
    browser_clients: Set[WebSocket]   = set()

    mc_connected:  bool = False
    tcp_connected: bool = False

    _agent_ws_server: Optional[Any]            = None
    _tcp_retry_task:  Optional[asyncio.Task]   = None

st = _St()


# ─────────────────────────────────────────────────────────────────────────────
# agents.json reader  (mirrors AgentsJsonReader.java + AgentConfigLoader.java)
# ─────────────────────────────────────────────────────────────────────────────
def _find_agents_json() -> Optional[Path]:
    home = Path.home()
    for p in [
        home / "Documents"              / "agents.json",
        home / "Desktop"                / "agents.json",
        home / "OneDrive" / "Documents" / "agents.json",
        home / "OneDrive" / "Desktop"   / "agents.json",
    ]:
        if p.exists():
            return p
    return None


def _load_agents() -> list:
    path = _find_agents_json()
    if not path:
        log.warning("agents.json not found — check ~/Documents or ~/Desktop")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.error(f"Cannot read agents.json: {exc}")
        return []

    agents = []

    # NPCs  →  root.NPCs.{gender}.{name: port}
    for gender, entries in data.get("NPCs", {}).items():
        if isinstance(entries, dict):
            for name, port in entries.items():
                agents.append({
                    "name": name, "type": "npc", "gender": gender,
                    "god_type": None,
                    "tcp_port": int(port), "ws_port": int(port) + WS_PORT_OFFSET,
                })

    # GODs  →  root.GODs.dual.{god_type}.{name: port}
    for god_type, entries in data.get("GODs", {}).get("dual", {}).items():
        if isinstance(entries, dict):
            for name, port in entries.items():
                agents.append({
                    "name": name, "type": "god", "gender": "dual",
                    "god_type": god_type,
                    "tcp_port": int(port), "ws_port": int(port) + WS_PORT_OFFSET,
                })

    return agents


# ─────────────────────────────────────────────────────────────────────────────
# TCP action packing  (TCPServer.java wire format, big-endian)
# ─────────────────────────────────────────────────────────────────────────────
def _encode_flags(f: dict) -> int:
    b = 0
    if f.get("jump"):      b |= 0b10000000
    if f.get("sneak"):     b |= 0b01000000
    if f.get("attack"):    b |= 0b00100000
    if f.get("use"):       b |= 0b00010000
    if f.get("drop"):      b |= 0b00001000
    if f.get("open_inv"):  b |= 0b00000100
    if f.get("swap_hand"): b |= 0b00000010
    if f.get("sprint"):    b |= 0b00000001
    return b


def _pack_action(
    agent_id: str = "", move_forward: float = 0.0, move_strafe: float = 0.0,
    yaw_delta: float = 0.0, pitch_delta: float = 0.0, action_flags: int = 0,
    hotbar_slot: int = -1,
    ability: Optional[str] = None, p1: float = 0.0, p2: float = 0.0, p3: float = 0.0,
) -> bytes:
    """
    Wire format:
      [4] agent_id_len  [N] agent_id  [8] tick_ms
      [4] move_forward  [4] move_strafe  [4] yaw_delta  [4] pitch_delta
      [1] action_flags  [1] hotbar_slot (0xFF = no change)
      [2] ability_len   [M] ability  [4]p1 [4]p2 [4]p3  (omitted when len=0)
    """
    aid  = agent_id.encode("utf-8")
    hb   = 0xFF if hotbar_slot < 0 else max(0, min(8, hotbar_slot))
    buf  = struct.pack(">I", len(aid)) + aid
    buf += struct.pack(">q", int(time.time() * 1000))
    buf += struct.pack(">ffff", move_forward, move_strafe, yaw_delta, pitch_delta)
    buf += struct.pack(">BB", action_flags & 0xFF, hb)
    if ability:
        ab   = ability.encode("utf-8")
        buf += struct.pack(">H", len(ab)) + ab
        buf += struct.pack(">fff", p1, p2, p3)
    else:
        buf += struct.pack(">H", 0)
    return buf


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _broadcast(msg: dict):
    text = json.dumps(msg)
    dead: Set[WebSocket] = set()
    for ws in st.browser_clients:
        try:
            await ws.send_text(text)
        except Exception:
            dead.add(ws)
    st.browser_clients -= dead


async def _tcp_send(data: bytes) -> bool:
    if not st.tcp_sock:
        return False
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, st.tcp_sock.sendall, data)
        return True
    except Exception as exc:
        log.warning(f"TCP send failed: {exc}")
        st.tcp_sock = None
        st.tcp_connected = False
        asyncio.create_task(_broadcast({"type": "tcp_status", "connected": False,
                                        "msg": "Disconnected — Minecraft closed?"}))
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Minecraft WS frame classification  (DWClientBot → browser)
# ─────────────────────────────────────────────────────────────────────────────
async def _handle_mc_frame(frame: Any):
    # ── JSON text frames (chat observations, game state) ────────────────────
    if isinstance(frame, str):
        try:
            await _broadcast(json.loads(frame))
        except Exception:
            await _broadcast({"type": "raw_text", "data": frame[:500]})
        return

    if not isinstance(frame, (bytes, bytearray)) or len(frame) < 2:
        return

    # ── JPEG magic  FF D8 FF ────────────────────────────────────────────────
    if frame[0] == 0xFF and frame[1] == 0xD8:
        await _broadcast({"type": "vision", "data": base64.b64encode(frame).decode()})
        return

    # ── DWAI binary envelope ────────────────────────────────────────────────
    #    DWAI (4 bytes) + frame_type (1 byte) + payload
    if len(frame) > 5 and frame[:4] == b"DWAI":
        ft      = frame[4]
        payload = frame[5:]
        if ft == 0x01:
            await _broadcast({"type": "vision", "data": base64.b64encode(payload).decode()})
        elif ft == 0x02:
            await _broadcast({"type": "audio",  "data": base64.b64encode(payload).decode()})
        elif ft == 0x03:
            try:
                await _broadcast(json.loads(payload.decode()))
            except Exception:
                pass
        return

    # ── Default: raw PCM audio (16-bit mono 22 050 Hz) ──────────────────────
    await _broadcast({"type": "audio", "data": base64.b64encode(frame).decode()})


# ─────────────────────────────────────────────────────────────────────────────
# Agent WebSocket server  (DWClientBot connects here on agent's WS port)
# ─────────────────────────────────────────────────────────────────────────────
async def _agent_ws_handler(websocket, *_):
    remote = getattr(websocket, "remote_address", "unknown")
    log.info(f"✅ DWClientBot connected from {remote}")
    st.mc_ws        = websocket
    st.mc_connected = True
    await _broadcast({"type": "mc_status", "connected": True})

    try:
        async for frame in websocket:
            await _handle_mc_frame(frame)
    except (websockets.exceptions.ConnectionClosed, Exception):
        pass
    finally:
        st.mc_ws        = None
        st.mc_connected = False
        log.info("DWClientBot disconnected")
        await _broadcast({"type": "mc_status", "connected": False})


async def _start_agent_ws_server(ws_port: int):
    if st._agent_ws_server is not None:
        try:
            st._agent_ws_server.close()
            await st._agent_ws_server.wait_closed()
        except Exception:
            pass
        st._agent_ws_server = None

    try:
        server = await websockets.serve(_agent_ws_handler, "0.0.0.0", ws_port)
        st._agent_ws_server = server
        log.info(f"Agent WS server → ws://0.0.0.0:{ws_port}/ws/agent")
        await _broadcast({"type": "agent_ws_status", "listening": True, "port": ws_port})
    except OSError as exc:
        msg = (f"Cannot bind WS port {ws_port}: {exc}. "
               "Stop any running Python agent for this agent first.")
        log.error(msg)
        await _broadcast({"type": "error", "msg": msg})


async def _connect_tcp():
    if not st.tcp_port:
        return
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect(("127.0.0.1", st.tcp_port))
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        st.tcp_sock      = sock
        st.tcp_connected = True
        log.info(f"✅ TCP connected to port {st.tcp_port}")
        await _broadcast({"type": "tcp_status", "connected": True})
    except Exception as exc:
        msg = (f"TCP connect to :{st.tcp_port} failed: {exc}. "
               "Start Minecraft first, then click Retry TCP.")
        log.warning(msg)
        await _broadcast({"type": "tcp_status", "connected": False, "msg": msg})


# ─────────────────────────────────────────────────────────────────────────────
# Browser message dispatcher
# ─────────────────────────────────────────────────────────────────────────────
async def _dispatch(msg: dict):
    t = msg.get("type")

    if t == "action":
        flags = _encode_flags(msg.get("flags", {}))
        await _tcp_send(_pack_action(
            agent_id     = st.agent_name,
            move_forward = float(msg.get("moveForward", 0)),
            move_strafe  = float(msg.get("moveStrafe",  0)),
            yaw_delta    = float(msg.get("yawDelta",    0)),
            pitch_delta  = float(msg.get("pitchDelta",  0)),
            action_flags = flags,
            hotbar_slot  = int(msg.get("hotbarSlot", -1)),
        ))

    elif t == "ability":
        await _tcp_send(_pack_action(
            agent_id = st.agent_name,
            ability  = str(msg["name"]),
            p1       = float(msg.get("param1", 0)),
            p2       = float(msg.get("param2", 0)),
            p3       = float(msg.get("param3", 0)),
        ))

    elif t == "inventory":
        ab = f"inv:{msg['slot']},{msg.get('button',0)},{msg.get('clickType',0)}"
        await _tcp_send(_pack_action(agent_id=st.agent_name, ability=ab))

    elif t == "screen":
        await _tcp_send(_pack_action(agent_id=st.agent_name, ability=f"screen:{msg['command']}"))

    elif t == "tcp_retry":
        await _connect_tcp()

    elif t == "ping":
        await _broadcast({"type": "pong", "server_ts": time.time()})


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(title="DW Human Controller", docs_url=None, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/")
async def root():
    """Serve the HTML controller file"""
    html_file = Path(__file__).parent / "dw_controller.html"
    if not html_file.exists():
        raise HTTPException(404, "dw_controller.html not found")
    return FileResponse(html_file, media_type="text/html")


@app.get("/api/agents")
async def api_agents():
    return _load_agents()


@app.post("/api/connect")
async def api_connect(body: dict):
    name   = body.get("name", "")
    agents = _load_agents()
    agent  = next((a for a in agents if a["name"] == name), None)
    if not agent:
        raise HTTPException(404, f"Agent '{name}' not found in agents.json")

    st.agent_name = agent["name"]
    st.agent_type = agent["type"]
    st.god_type   = agent.get("god_type")
    st.tcp_port   = agent["tcp_port"]
    st.ws_port    = agent["ws_port"]

    await _start_agent_ws_server(st.ws_port)
    asyncio.create_task(_connect_tcp())

    return {
        "status":   "connecting",
        "agent":    st.agent_name,
        "type":     st.agent_type,
        "god_type": st.god_type,
        "tcp_port": st.tcp_port,
        "ws_port":  st.ws_port,
    }


@app.post("/api/tcp-retry")
async def api_tcp_retry():
    await _connect_tcp()
    return {"status": "retrying", "port": st.tcp_port}


@app.get("/api/status")
async def api_status():
    return {
        "agent": st.agent_name, "agent_type": st.agent_type, "god_type": st.god_type,
        "mc_connected": st.mc_connected, "tcp_connected": st.tcp_connected,
        "browsers": len(st.browser_clients),
        "ws_port": st.ws_port, "tcp_port": st.tcp_port,
    }


@app.websocket("/ws/human")
async def ws_human(ws: WebSocket):
    await ws.accept()
    st.browser_clients.add(ws)
    log.info(f"Browser connected ({len(st.browser_clients)} total)")

    await ws.send_text(json.dumps({
        "type": "hello",
        "agent": st.agent_name, "agent_type": st.agent_type, "god_type": st.god_type,
        "mc_connected": st.mc_connected, "tcp_connected": st.tcp_connected,
        "ws_port": st.ws_port, "tcp_port": st.tcp_port,
    }))

    try:
        while True:
            raw = await ws.receive_text()
            try:
                await _dispatch(json.loads(raw))
            except Exception as exc:
                log.debug(f"Dispatch error: {exc}")
    except WebSocketDisconnect:
        pass
    finally:
        st.browser_clients.discard(ws)
        log.info(f"Browser disconnected ({len(st.browser_clients)} remaining)")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
async def _main():
    log.info("=" * 56)
    log.info("  DivineWorld Human Controller Server")
    log.info(f"  → http://localhost:{BROWSER_PORT}")
    log.info("=" * 56)
    cfg    = uvicorn.Config(app, host="0.0.0.0", port=BROWSER_PORT, log_level="warning")
    server = uvicorn.Server(cfg)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(_main())
