#!/usr/bin/env python3
"""Test script to verify websocket communication is working"""

import asyncio
import json
import sys

async def test_websocket():
    try:
        import websockets
    except:
        print("Installing websockets...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    async with websockets.connect("ws://localhost:11400/ws/agent") as ws:
        print("✅ WebSocket connected to backend")

        # Send binary protocol handshake (as frontend does)
        await ws.send(json.dumps({"agent_id": "demo", "protocol": "binary", "version": "2.1.0"}))
        response = await ws.recv()
        print(f"✅ Registered: {response}")

        # Trigger speak endpoint via HTTP to make the backend broadcast agent_speech
        try:
            import aiohttp
        except:
            print("Installing aiohttp...")
            import subprocess
            subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp", "-q"])
            import aiohttp

        async with aiohttp.ClientSession() as sess:
            resp = await sess.post('http://127.0.0.1:11400/api/agents/demo/audio/speak', json={'text': 'Hello from backend test'})
            print('Speak POST status:', resp.status)

        # Wait for response
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=5.0)
            print(f"✅ Received response: {response}")
        except asyncio.TimeoutError:
            print("⏱️ No response within 5 seconds")

if __name__ == "__main__":
    asyncio.run(test_websocket())
