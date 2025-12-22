# test_vision.py
import asyncio
import websockets
import struct

async def monitor_websocket():
    uri = "ws://localhost:11400/ws/agent"
    
    async with websockets.connect(uri) as ws:
        # Send handshake
        await ws.send(json.dumps({
            "agent_id": "AI_Test_001",
            "protocol": "binary"
        }))
        
        # Wait for acknowledgment
        ack = await ws.recv()
        print(f"Connected: {ack}")
        
        # Monitor incoming data
        while True:
            data = await ws.recv()
            
            # Check for binary frame
            if isinstance(data, bytes):
                magic = struct.unpack('!I', data[0:4])[0]
                frame_type = struct.unpack('!I', data[4:8])[0]
                
                if magic == 0x44574149:  # 'DWAI'
                    if frame_type == 0x01:
                        print("📷 PERCEPTION frame received!")
                    elif frame_type == 0x02:
                        print("🎮 ACTION frame received!")

asyncio.run(monitor_websocket())