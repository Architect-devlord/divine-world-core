# py_backend/main.py 
## there is an admin endpoint to list queued files and processing status.
"""
Divine World Backend with:
- Binary WebSocket protocol for video/images
- Multi-agent port allocation
- Pattern recognition integration
- Avalanche continual learning hooks
- Request validation
- Health checks
- Atomic operations
"""

from contextlib import asynccontextmanager
import time
import asyncio
import sys
import os
from pathlib import Path
from io import BytesIO
import struct
from fastapi import FastAPI, WebSocket, Request, HTTPException, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Optional, Any
import numpy as np
import json
from auto_connect_system import integrate_with_backend
from ai_core.logger_setup import initialize_logging
initialize_logging()
from ai_core.web_browser import add_web_browsing_to_agent

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config first
from config import Config

# Initialize config
Config.ensure_dirs()
if not Config.validate():
    logging.critical("Configuration validation failed!")
    sys.exit(1)

from auto_packager import EnhancedAgentSpawner
from ai_core.agent import NPCAgent
from communication_protocol import (
    BinaryProtocol,
    HighPerformanceWebSocketHandler,
    decompress_jpeg_to_frame,
    compress_frame_to_jpeg,
    ActionFrame
)
from utils.validation import ChatRequest, FileUploadRequest

# Optional S3/MinIO support
try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except Exception:
    S3_AVAILABLE = False

log = logging.getLogger("dw_backend")
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(name)s - %(message)s'
)

app = FastAPI(
    title="Divine World Backend",
    version="2.1.0",
    description="AI Backend with Binary WebSocket Protocol & Pattern Recognition"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== GLOBAL STATE ====================

class EnhancedAgentManager:
    """Enhanced manager with binary protocol support and language integration"""
    
    def __init__(self):
        self.spawner = EnhancedAgentSpawner(
            client_jar_path=str(Config.CLIENT_JAR) if Config.CLIENT_JAR else None,
            auto_package=True,
            package_output_dir=str(Config.NPC_APPLICATIONS_DIR)
        )
        
        # WebSocket handlers (upgraded to binary protocol)
        self.websocket_handlers: Dict[str, HighPerformanceWebSocketHandler] = {}
        
        # Demo agents (for testing without Minecraft)
        self.demo_agents: Dict[str, NPCAgent] = {}
        
        # Connected agents tracking
        self.connected_agents: Dict[str, Dict] = {}
        
        log.info("Enhanced Agent Manager initialized with binary protocol")
    
    def get_agent(self, agent_id: str) -> Optional[NPCAgent]:
        """Get agent runtime"""
        spawner_agent = self.spawner.get_agent(agent_id)
        if spawner_agent:
            return spawner_agent
        
        if agent_id in self.demo_agents:
            return self.demo_agents[agent_id]
        
        return None
    
    def get_or_create_demo_agent(self, agent_id: str) -> NPCAgent:
        """Get or create demo agent with GUARANTEED language capabilities"""
        if agent_id not in self.demo_agents:
            log.info(f"Creating demo agent: {agent_id}")
            
            # Create agent
            agent = NPCAgent(agent_id)
            agent.mode = 'chat'
            # Attach unified memory (Scylla-backed if available)
            try:
                from ai_core.unified_memory import UnifiedMemoryStore
                agent.memory = UnifiedMemoryStore(
                    agent_id=agent_id,
                    capacity=10000,
                    use_scylla=True,
                    scylla_hosts=['127.0.0.1']
                )
                log.info(f"✅ UnifiedMemory attached for {agent_id}")
            except Exception as e:
                log.debug(f"UnifiedMemory not available: {e}")
            
            # CRITICAL FIX: Ensure language capabilities are initialized
            if not hasattr(agent.brain, 'language') or agent.brain.language is None:
                from ai_core.brain_language import add_language_to_brain
                add_language_to_brain(agent.brain)
                log.info(f"✅ Language capabilities initialized for {agent_id}")
            else:
                log.info(f"✅ Language already initialized for {agent_id}")
            
            # Try to load existing brain if available
            brain_path = Config.get_agent_brain_path(agent_id)
            if brain_path.exists():
                try:
                    agent.load(str(brain_path))
                    log.info(f"✅ Loaded existing brain for {agent_id}")
                except Exception as e:
                    log.warning(f"⚠️ Failed to load brain, using fresh state: {e}")
            
            self.demo_agents[agent_id] = agent
            register_agent_with_chat_system(agent_id, agent)

        return self.demo_agents[agent_id]
    
    def mark_agent_connected(self, agent_id: str, player_uuid: str, agent_type: str):
        """Mark agent as connected"""
        self.connected_agents[agent_id] = {
            'player_uuid': player_uuid,
            'agent_type': agent_type,
            'connected_at': time.time()
        }
        log.info(f"✅ Agent {agent_id} connected (UUID: {player_uuid})")
    
    def mark_agent_disconnected(self, agent_id: str):
        """Mark agent as disconnected"""
        if agent_id in self.connected_agents:
            del self.connected_agents[agent_id]
            log.info(f"❌ Agent {agent_id} disconnected")
    
    def cleanup_all(self):
        """Cleanup all agents with atomic saves"""
        log.info("Cleaning up all agents...")
        
        # Save demo agents
        for agent_id, agent in self.demo_agents.items():
            try:
                save_path = Config.get_agent_brain_path(agent_id)
                save_path.parent.mkdir(parents=True, exist_ok=True)
                agent.save(str(save_path))
                log.info(f"Saved demo agent: {agent_id}")
            except Exception as e:
                log.error(f"Failed to save {agent_id}: {e}")
        
        self.spawner.cleanup_all()
        log.info("Cleanup complete")


agent_manager = EnhancedAgentManager()
integrate_with_backend(app, agent_manager)

try:
    from unified_chat_system import chat_system
    CHAT_SYSTEM_AVAILABLE = True
    log.info("✅ Chat system imported successfully")
except ImportError as e:
    CHAT_SYSTEM_AVAILABLE = False
    log.warning(f"⚠️ Chat system not available: {e}")


class WebSocketChatBridge:
    """
    Bridges unified_chat_system to main WebSocket handlers.
    Ensures cognitive loop speech reaches the frontend.
    """
    
    def __init__(self, agent_manager):
        self.agent_manager = agent_manager
        log.info("🌉 WebSocket Chat Bridge initialized")
    
    async def send_message_to_websocket(self, agent_id: str, message: str, 
                                       sender: str = "agent", msg_type: str = "agent_speech"):
        """
        Send message from chat system to WebSocket connection.
        This is the BRIDGE that was missing!
        """
        # Check if WebSocket handler exists
        if agent_id not in self.agent_manager.websocket_handlers:
            log.warning(f"[Bridge] ⚠️ No WebSocket handler for {agent_id}")
            log.warning(f"[Bridge] Available handlers: {list(self.agent_manager.websocket_handlers.keys())}")
            return False
        
        handler = self.agent_manager.websocket_handlers[agent_id]
        
        try:
            # Send via WebSocket using the SAME format as agent_speak endpoint
            await handler.websocket.send_json({
                "type": msg_type,
                "agent_id": agent_id,
                "text": message,
                "sender": sender,
                "timestamp": time.time()
            })
            
            log.info(f"[Bridge] ✅ Message sent to WebSocket: {agent_id}")
            log.debug(f"[Bridge] Message: {message[:60]}...")
            return True
            
        except Exception as e:
            log.error(f"[Bridge] ❌ Failed to send to WebSocket: {e}", exc_info=True)
            return False


# Create bridge instance
ws_bridge = WebSocketChatBridge(agent_manager)


# Monkey-patch chat_system to use our bridge
if CHAT_SYSTEM_AVAILABLE:
    # Store original _send_to_gui method
    _original_send_to_gui = chat_system._send_to_gui
    
    async def _bridged_send_to_gui(agent_id: str, msg):
        """
        Enhanced _send_to_gui that uses main WebSocket handlers.
        This replaces the original method in chat_system.
        """
        # Try to send via main WebSocket first
        success = await ws_bridge.send_message_to_websocket(
            agent_id=agent_id,
            message=msg.text,
            sender=msg.sender,
            msg_type="agent_speech" if msg.sender == "agent" else "chat"
        )
        
        if success:
            log.debug(f"[Bridge] Message routed via main WebSocket")
        else:
            # Fallback to original method (if chat_system has its own connections)
            log.debug(f"[Bridge] Falling back to original chat system method")
            try:
                await _original_send_to_gui(agent_id, msg)
            except Exception as e:
                log.error(f"[Bridge] Both methods failed: {e}")
    
    # Replace the method
    chat_system._send_to_gui = _bridged_send_to_gui
    log.info("✅ Chat system bridged to main WebSocket handlers")


# ==================== REGISTER AGENTS WITH CHAT SYSTEM ====================

def register_agent_with_chat_system(agent_id: str, agent):
    """Register agent with chat system when created"""
    if CHAT_SYSTEM_AVAILABLE:
        chat_system.register_agent(agent_id, agent)
        log.info(f"✅ Agent {agent_id} registered with chat system")


# Initialize S3/MinIO client if available
s3_client = None
if S3_AVAILABLE:
    try:
        s3_client = boto3.client(
            's3',
            endpoint_url=Config.MINIO_ENDPOINT,
            aws_access_key_id=Config.MINIO_ACCESS_KEY,
            aws_secret_access_key=Config.MINIO_SECRET_KEY,
            region_name=os.getenv('AWS_REGION', 'us-east-1')
        )
        # Ensure bucket exists
        try:
            s3_client.head_bucket(Bucket=Config.MINIO_BUCKET)
        except ClientError:
            try:
                s3_client.create_bucket(Bucket=Config.MINIO_BUCKET)
            except Exception as e:
                log.warning(f"Could not create bucket {Config.MINIO_BUCKET}: {e}")
    except Exception as e:
        log.warning(f"S3 client initialization failed: {e}")
        s3_client = None

#===================== AGENT SPEECH BROADCASTING ====================
async def broadcast_agent_speech(agent_id: str, message: str):
    """
    Standalone function to broadcast agent speech.
    Can be called from anywhere in the codebase.
    """
    return await ws_bridge.send_message_to_websocket(
        agent_id=agent_id,
        message=message,
        sender="agent",
        msg_type="agent_speech"
    )


async def broadcast_agent_thought(agent_id: str, thought: str):
    """
    Broadcast internal thought (shown in thoughts panel, not chat)
    """
    if agent_id not in agent_manager.websocket_handlers:
        return False
    
    handler = agent_manager.websocket_handlers[agent_id]
    
    try:
        await handler.websocket.send_json({
            "type": "agent_thought",
            "agent_id": agent_id,
            "internal_thought": thought,
            "timestamp": time.time()
        })
        return True
    except Exception as e:
        log.error(f"Failed to broadcast thought: {e}")
        return False

# ==================== BINARY WEBSOCKET ENDPOINT ====================

@app.websocket("/ws/agent")
async def agent_binary_websocket(websocket: WebSocket):
    """
    Enhanced WebSocket with proper message transport fallback chain.
    Supports: Binary → JSON → REST API fallback
    """
    await websocket.accept()
    
    agent_id = None
    protocol_mode = "json"  # Start with JSON, upgrade to binary if supported
    

    try:
        # PHASE 1: JSON Handshake
        handshake = await websocket.receive_json()
        agent_id = handshake.get("agent_id")
        
        if not agent_id:
            await websocket.send_json({
                "type": "error",
                "message": "Missing agent_id in handshake"
            })
            await websocket.close(code=1008, reason="Missing agent_id")
            return
        
        # PHASE 2: Protocol Negotiation
        client_protocol = handshake.get("protocol", "json")
        client_version = handshake.get("version", "1.0.0")
        
        # Determine protocol mode
        if client_protocol == "binary":
            protocol_mode = "binary"
            log.info(f"🔌 Binary WebSocket connected: {agent_id} (v{client_version})")
        else:
            protocol_mode = "json"
            log.info(f"🔌 JSON WebSocket connected: {agent_id}")
        
        # Get or create agent
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        # Create handler
        handler = HighPerformanceWebSocketHandler(websocket, agent_id)
        agent_manager.websocket_handlers[agent_id] = handler
        log.info(f"✅ WebSocket handler registered for {agent_id} (before acknowledgment)")
        
        if CHAT_SYSTEM_AVAILABLE:
            chat_system.register_gui(agent_id, websocket)
            log.info(f"✅ {agent_id} registered with chat system via WebSocket")

        # PHASE 3: Send acknowledgment
        await websocket.send_json({
            "type": "connected",
            "agent_id": agent_id,
            "protocol": protocol_mode,
            "version": "2.1.0",
            "capabilities": {
                "binary": protocol_mode == "binary",
                "json": True,
                "rest_fallback": True,
                "max_fps": Config.WEBSOCKET_MAX_FPS if protocol_mode == "binary" else 10,
                "max_latency_ms": Config.WEBSOCKET_MAX_LATENCY_MS
            }
        })
        
        log.info(f"✅ Acknowledgment sent to {agent_id} (mode: {protocol_mode})")
        
        # PHASE 4: Communication loop with proper fallback handling
        while True:
            try:
                message = await websocket.receive()
                
                # Handle binary frames (PERCEPTION or CHAT)
                if "bytes" in message and protocol_mode == "binary":
                    data = message["bytes"]
                    
                    if len(data) < 8:
                        continue
                    
                    magic = struct.unpack('!I', data[0:4])[0]
                    frame_type = struct.unpack('!I', data[4:8])[0]
                    
                    if magic != BinaryProtocol.MAGIC:
                        log.warning(f"Invalid binary frame magic: {hex(magic)}, falling back to JSON")
                        protocol_mode = "json"
                        continue
                    
                    # Handle PERCEPTION frame
                    if frame_type == BinaryProtocol.FRAME_PERCEPTION:
                        try:
                            perception = BinaryProtocol.unpack_perception(data)
                            frame = decompress_jpeg_to_frame(perception.image_data)
                            
                            obs_dict = {
                                'frame': frame,
                                'health': perception.health,
                                'hunger': perception.hunger,
                                'position': perception.position,
                                'rotation': perception.rotation,
                                'entities': perception.entities,
                                'timestamp': perception.timestamp
                            }
                            
                            obs = agent.perceive(obs_dict)
                            action_array = agent.decide(obs, deterministic=False)
                            action_dict = agent.act(action_array)
                            
                            action_frame = ActionFrame(
                                agent_id=agent_id,
                                timestamp=time.time(),
                                move_forward=action_dict['move_forward'],
                                move_strafe=action_dict['move_strafe'],
                                yaw_delta=action_dict['yaw_delta'],
                                pitch_delta=action_dict['pitch_delta'],
                                action_flags=BinaryProtocol.dict_to_action_flags(action_dict),
                                hotbar_slot=action_dict.get('hotbar_slot')
                            )
                            
                            await handler.send_action(action_frame)
                            
                            if agent.last_obs is not None:
                                outcome = {
                                    'health': perception.health,
                                    'hunger': perception.hunger,
                                    'is_dead': perception.health <= 0,
                                    'task_reward': 0.0
                                }
                                agent.learn(agent.last_obs, action_array, obs, outcome)
                            
                            agent.last_obs = obs
                            
                        except Exception as e:
                            log.error(f"Binary perception processing failed: {e}")
                            continue
                    
                    # Handle CHAT frame (binary)
                    elif frame_type == BinaryProtocol.FRAME_CHAT:
                        try:
                            buffer = BytesIO(data)
                            buffer.read(8)  # Skip magic and type
                            
                            agent_id_len = struct.unpack('!I', buffer.read(4))[0]
                            msg_agent_id = buffer.read(agent_id_len).decode('utf-8')
                            msg_timestamp = struct.unpack('!d', buffer.read(8))[0]
                            msg_len = struct.unpack('!I', buffer.read(4))[0]
                            user_message = buffer.read(msg_len).decode('utf-8')
                            
                            log.info(f"[Chat Binary] {msg_agent_id}: {user_message}")
                            
                            # Process message
                            response = await process_chat_message(agent, user_message)
                            
                            # Send response as binary
                            response_bytes = encode_chat_binary(agent_id, response)
                            await websocket.send_bytes(response_bytes)
                            
                        except Exception as e:
                            log.error(f"Binary chat processing failed: {e}, falling back to JSON")
                            protocol_mode = "json"
                
                # Handle JSON messages (fallback or primary for non-binary clients)
                elif "text" in message:
                    message_data = message["text"]
                    
                    try:
                        message_data = json.loads(message_data)
                    except:
                        log.warning("Received non-JSON text message")
                        continue
                    
                    msg_type = message_data.get("type")
                    
                    # Handle chat message (JSON)
                    if msg_type == "chat":
                        user_message = message_data.get("message", "")
                        
                        if user_message:
                            log.info(f"[Chat JSON] {agent_id}: {user_message}")
                            
                            # Process message
                            response = await process_chat_message(agent, user_message)
                            
                            # Send response as JSON
                            await websocket.send_json({
                                "type": "chat",
                                "from": agent_id,
                                "text": response,
                                "timestamp": time.time()
                            })
                    
                    # Handle re-registration
                    elif msg_type == "register":
                        await websocket.send_json({
                            "type": "registered",
                            "agent_id": agent_id,
                            "protocol": protocol_mode
                        })
                    
                    # Handle protocol upgrade request
                    elif msg_type == "upgrade_protocol":
                        requested_protocol = message_data.get("protocol", "json")
                        if requested_protocol == "binary":
                            protocol_mode = "binary"
                            await websocket.send_json({
                                "type": "protocol_upgraded",
                                "protocol": "binary",
                                "message": "Switched to binary protocol"
                            })
                            log.info(f"✅ Protocol upgraded to binary for {agent_id}")
            
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error(f"Error in websocket loop for {agent_id}: {e}", exc_info=True)
                # Try to send error notification
                try:
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e),
                        "fallback_to": "rest_api"
                    })
                except:
                    pass
                break
    
    except Exception as e:
        log.error(f"WebSocket error: {e}", exc_info=True)
    
    finally:
        if agent_id and agent_id in agent_manager.websocket_handlers:
            del agent_manager.websocket_handlers[agent_id]
            log.info(f"🔌 WebSocket handler unregistered: {agent_id}")

        log.info(f"🔌 WebSocket disconnected: {agent_id}")


async def process_chat_message(agent, user_message: str) -> str:
    """
    Process chat message and generate response.
    Returns the response text.
    """
    agent_id = getattr(agent, 'agent_id', 'unknown')
    # Log incoming message
    log.info(f"[Chat] 📩 User → {agent_id}: {user_message}")

    # Store user message
    agent.memory.remember({
        'type': 'user_message',
        'text': user_message,
        'tags': ['chat'],
        'timestamp': time.time()
    })
    
    # Build context
    context = {
        'health': agent.health,
        'hunger': agent.hunger,
        'emotions': agent.emotion.snapshot(),
        'dominant_emotion': agent.emotion.dominant_emotion(),
        'memory_size': len(agent.memory.events)
    }
    
    # Generate response
    log.debug(f"[Chat] 🧠 Generating response for {agent_id}...")
    response = agent.brain.process_language_input(user_message, context)
    if not response:
        response = f"[Stage {agent.brain.language.language_stage}] Learning..."
        log.debug(f"[Chat] ⚠️ No response generated, using fallback or learning")
    
    # Store agent response
    agent.memory.remember({
        'type': 'agent_response',
        'text': response,
        'tags': ['chat'],
        'timestamp': time.time()
    })
    
    return response


def encode_chat_binary(agent_id: str, message: str) -> bytes:
    """Encode chat message as binary frame"""
    buffer = BytesIO()
    
    # Header
    buffer.write(struct.pack('!I', BinaryProtocol.MAGIC))
    buffer.write(struct.pack('!I', BinaryProtocol.FRAME_CHAT))
    
    # Agent ID
    agent_id_bytes = agent_id.encode('utf-8')
    buffer.write(struct.pack('!I', len(agent_id_bytes)))
    buffer.write(agent_id_bytes)
    
    # Timestamp
    buffer.write(struct.pack('!d', time.time()))
    
    # Message
    message_bytes = message.encode('utf-8')
    buffer.write(struct.pack('!I', len(message_bytes)))
    buffer.write(message_bytes)
    
    return buffer.getvalue()

# ==================== AUDIO CONTROL ENDPOINTS ====================

@app.post("/api/agents/{agent_id}/audio/start")
async def start_audio_listening(agent_id: str):
    """Start audio listening for agent"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        if not hasattr(agent, 'audio_processor'):
            raise HTTPException(
                status_code=400,
                detail="Audio processing not available for this agent"
            )
        
        success = agent.audio_processor.start_listening()
        
        if success:
            return {
                "status": "success",
                "message": f"Agent {agent_id} started listening",
                "is_listening": True
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to start audio listening"
            )
    
    except Exception as e:
        log.error(f"[Audio] Start listening error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/audio/stop")
async def stop_audio_listening(agent_id: str):
    """Stop audio listening for agent"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        if not hasattr(agent, 'audio_processor'):
            raise HTTPException(
                status_code=400,
                detail="Audio processing not available"
            )
        
        agent.audio_processor.stop_listening()
        
        return {
            "status": "success",
            "message": f"Agent {agent_id} stopped listening",
            "is_listening": False
        }
    
    except Exception as e:
        log.error(f"[Audio] Stop listening error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/{agent_id}/audio/status")
async def get_audio_status(agent_id: str):
    """Get audio processing status"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        if not hasattr(agent, 'audio_processor'):
            return {
                "available": False,
                "message": "Audio processing not available"
            }
        
        stats = agent.audio_processor.get_stats()
        
        return {
            "available": True,
            "status": stats,
            "agent_id": agent_id
        }
    
    except Exception as e:
        log.error(f"[Audio] Status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/agents/{agent_id}/audio/speak")
async def agent_speak(agent_id: str, request: Request):
    """Make agent speak text (text-to-speech)"""
    try:
        data = await request.json()
        text = data.get('text', '')
        
        log.info(f"[Speak] Received speak request for {agent_id}: {text}")
        
        if not text:
            raise HTTPException(status_code=400, detail="No text provided")
        
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        # Store as spoken message
        agent.memory.remember({
            'type': 'agent_speech',
            'text': text,
            'timestamp': time.time()
        }, tags=['language', 'output', 'speech'])
        
        log.info(f"[Speak] 📡 Checking for WebSocket handler...")
        log.info(f"[Speak] 📡 Available handlers: {list(agent_manager.websocket_handlers.keys())}")
        log.info(f"[Speak] 📡 Looking for: {agent_id}")
        
        # Broadcast via WebSocket
        if agent_id in agent_manager.websocket_handlers:
            handler = agent_manager.websocket_handlers[agent_id]
            log.info(f"[Speak] ✅ Found WebSocket handler for {agent_id}, broadcasting...")
            try:
                await handler.websocket.send_json({
                    "type": "agent_speech",
                    "agent_id": agent_id,
                    "text": text,
                    "timestamp": time.time()
                })
                log.info(f"[Speak] Successfully sent agent_speech JSON to client")
            except Exception as ws_err:
                log.error(f"[Speak] Failed to send via WebSocket: {ws_err}",exc_info=True)
        else:
            log.warning(f"[Speak] No WebSocket handler for {agent_id}. Available: {list(agent_manager.websocket_handlers.keys())}")
            log.warning(f"[Speak] ⚠️ WebSocket might not be connected yet")

        return {
            "status": "success",
            "text": text,
            "agent_id": agent_id,
            "websocket_available": agent_id in agent_manager.websocket_handlers
        }
    
    except Exception as e:
        log.error(f"[Audio] Speak error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== AUDIO STREAMING (Advanced) ====================

@app.websocket("/ws/audio/{agent_id}")
async def audio_stream_websocket(websocket: WebSocket, agent_id: str):
    """
    WebSocket for real-time audio streaming.
    Allows frontend to send audio chunks for processing.
    """
    await websocket.accept()
    
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        if not hasattr(agent, 'audio_processor'):
            await websocket.send_json({
                "type": "error",
                "message": "Audio processing not available"
            })
            await websocket.close()
            return
        
        await websocket.send_json({
            "type": "connected",
            "agent_id": agent_id,
            "message": "Audio stream connected"
        })
        
        while True:
            # Receive audio data from frontend
            data = await websocket.receive_bytes()
            
            # Convert to numpy array (assumes 16-bit PCM)
            audio_array = np.frombuffer(data, dtype=np.int16)
            
            # Process audio chunk
            if len(audio_array) > 0:
                # Feed to agent's audio processor
                if agent and hasattr(agent, 'audio_processor') and agent.audio_processor:
                    try:
                        # Process audio through the agent's audio processor
                        agent.audio_processor.capture.add_audio_data(audio_array)
                    except Exception as e:
                        log.warning(f"Error processing audio chunk: {e}")
                
                await websocket.send_json({
                    "type": "audio_received",
                    "samples": len(audio_array),
                    "timestamp": time.time()
                })
    
    except WebSocketDisconnect:
        log.info(f"Audio stream disconnected: {agent_id}")
    except Exception as e:
        log.error(f"Audio stream error: {e}")
    finally:
        log.info(f"Audio stream closed: {agent_id}")

# ==================== CHAT ENDPOINT ====================

@app.post("/api/chat")
async def handle_chat(chat_request: ChatRequest):
    """Chat endpoint with validation"""
    try:
        message = chat_request.message
        agent_id = chat_request.agent_id
        
        log.info(f"[Chat/REST] 📩 User → {agent_id}: {message}")        

        agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        # Build context
        context = {
            'health': agent.health,
            'hunger': agent.hunger,
            'emotions': agent.emotion.snapshot(),
            'dominant_emotion': agent.emotion.dominant_emotion(),
            'memory_size': len(agent.memory.events)
        }
        
        # Store user message
        agent.memory.remember({
            'type': 'user_message',
            'text': message,
            'tags': ['chat', 'frontend'],
            'timestamp': time.time()
        })
        
        # Generate response using brain's language intelligence
        log.debug(f"[Chat/REST] 🧠 Generating response for {agent_id}...")
        response = agent.brain.process_language_input(message, context)
        
        if not response:
            response = f"[Stage {agent.brain.language.language_stage}] Learning..."
            log.debug(f"[Chat/REST] ⚠️ No response generated, using fallback or learning")

        log.info(f"[Chat/REST] 💬 {agent_id} → User: {response[:100]}{'...' if len(response) > 100 else ''}")
        
        # Store agent response
        agent.memory.remember({
            'type': 'agent_response',
            'text': response,
            'tags': ['chat', 'frontend'],
            'timestamp': time.time()
        })
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "response": response,
            "language_stage": agent.brain.language.language_stage,
            "vocabulary_size": agent.brain.language.vocabulary_size,
            "emotion": agent.emotion.dominant_emotion()
        }
        
    except Exception as e:
        log.error(f"[Chat] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== FILE UPLOAD ENDPOINT ====================

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), agent_id: str = "demo", filetype: str = None, sync: bool = False):
    """Handle file uploads with validation and cognitive loop integration"""
    try:
        # Validate using Pydantic
        file_request = FileUploadRequest(
            filename=file.filename,
            agent_id=agent_id,
            filetype=filetype or file.content_type or "application/octet-stream"
        )
        
        upload_dir = Config.get_agent_upload_dir(file_request.agent_id)
        file_path = upload_dir / file_request.filename
        
        content = await file.read()
        
        # Check size limit
        if len(content) > Config.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=413,
                detail=f"File too large (max {Config.MAX_UPLOAD_SIZE_MB}MB)"
            )
        
        # Schedule background processing: write to disk, upload to S3 (optional), record memory, and queue for cognitive loop
        async def _background_handle_upload(agent_id_inner, file_request_inner, content_inner, file_path_inner, sync_inner):
            try:
                agent_inner = agent_manager.get_or_create_demo_agent(agent_id_inner)

                # Ensure upload directory exists
                Path(file_path_inner).parent.mkdir(parents=True, exist_ok=True)

                # Write file to disk in thread to avoid blocking event loop
                try:
                    await asyncio.to_thread(lambda: open(file_path_inner, 'wb').write(content_inner))
                    log.info(f"[Upload][BG] Saved {file_request_inner.filename} for {agent_id_inner} ({len(content_inner)} bytes)")
                except Exception as e:
                    log.error(f"[Upload][BG] Failed to write file {file_path_inner}: {e}")

                # Upload to S3/MinIO if available
                s3_url_inner = None
                if s3_client:
                    try:
                        key = f"uploads/{agent_id_inner}/{file_request_inner.filename}"
                        s3_client.put_object(Bucket=Config.MINIO_BUCKET, Key=key, Body=content_inner)
                        s3_url_inner = f"{Config.MINIO_ENDPOINT.rstrip('/')}/{Config.MINIO_BUCKET}/{key}"
                        log.info(f"[Upload][BG] Uploaded {file_request_inner.filename} to object storage: {s3_url_inner}")
                    except Exception as e:
                        log.warning(f"[Upload][BG] S3 upload failed for {file_request_inner.filename}: {e}")

                # Record upload in memory
                try:
                    agent_inner.memory.remember({
                        'type': 'file_uploaded',
                        'filename': file_request_inner.filename,
                        'path': str(file_path_inner),
                        'filetype': file_request_inner.filetype,
                        'size': len(content_inner),
                        'timestamp': time.time(),
                        'agent_id': agent_id_inner,
                        's3_url': s3_url_inner
                    })
                except Exception:
                    log.debug("[Upload][BG] Agent memory not available to record upload")

                file_meta_inner = {
                    'path': str(file_path_inner),
                    'filename': file_request_inner.filename,
                    'filetype': file_request_inner.filetype,
                    'size': len(content_inner),
                    'timestamp': time.time(),
                    's3_url': s3_url_inner
                }

                # If client did not request sync processing, queue for cognitive loop
                if not sync_inner:
                    try:
                        if not hasattr(agent_inner, 'cognitive_loop') or agent_inner.cognitive_loop is None:
                            if hasattr(agent_inner, '_init_cognitive_loop'):
                                agent_inner._init_cognitive_loop()

                        if hasattr(agent_inner, 'cognitive_loop') and agent_inner.cognitive_loop:
                            agent_inner.cognitive_loop.receive_file(file_meta_inner)
                            log.info(f"[Upload][BG] Queued {file_request_inner.filename} for cognitive processing")

                            if not getattr(agent_inner.cognitive_loop, 'running', False):
                                if hasattr(agent_inner, 'start_autonomous_mode'):
                                    try:
                                        await agent_inner.start_autonomous_mode()
                                    except Exception as e:
                                        log.debug(f"[Upload][BG] Failed to start cognitive loop for {agent_id_inner}: {e}")
                    except Exception as e:
                        log.error(f"[Upload][BG] Failed to queue file for cognitive loop: {e}")
                else:
                    # If sync requested, perform learning in a thread so even learning doesn't block the request-response cycle
                    try:
                        if hasattr(agent_inner.brain, 'learn_from_file'):
                            summary_inner = await asyncio.to_thread(agent_inner.brain.learn_from_file, str(file_path_inner), file_request_inner.filetype)
                            try:
                                agent_inner.memory.remember({
                                    'type': 'file_processed',
                                    'filename': file_request_inner.filename,
                                    'path': str(file_path_inner),
                                    'filetype': file_request_inner.filetype,
                                    'size': len(content_inner),
                                    'timestamp': time.time(),
                                    'agent_id': agent_id_inner,
                                    'summary': summary_inner,
                                    's3_url': s3_url_inner
                                })
                            except Exception:
                                log.debug("[Upload][BG] Failed to record file_processed in agent memory")
                    except Exception as e:
                        log.debug(f"[Upload][BG] Synchronous (background) learn_from_file failed: {e}")

            except Exception as e:
                log.error(f"[Upload][BG] Unexpected error handling upload: {e}", exc_info=True)

        # Schedule the background task and return immediately
        try:
            asyncio.create_task(_background_handle_upload(agent_id, file_request, content, str(file_path), sync))
        except Exception as e:
            log.error(f"Failed to schedule background upload task: {e}")

        return {
            "status": "accepted",
            "message": "Upload scheduled for background processing",
            "filename": file_request.filename,
            "path": str(file_path),
            "size": len(content)
        }
        
    except Exception as e:
        log.error(f"[Upload] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PATTERN RECOGNITION ENDPOINT ====================

@app.get("/api/agents/{agent_id}/patterns")
async def get_pattern_recognition(agent_id: str):
    """Get pattern recognition summary"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        pattern_summary = agent.brain.get_pattern_summary()
        
        return {
            "agent_id": agent_id,
            "patterns": pattern_summary,
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"[Patterns] Error getting patterns for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== AGENT STATUS ENDPOINT ====================

@app.get("/api/agents/{agent_id}/status")
async def get_agent_status(agent_id: str):
    """Get complete agent status"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        status = {
            "agent_id": agent_id,
            "mode": getattr(agent, 'mode', 'unknown'),
            "is_alive": agent.is_alive(),
            "health": agent.health,
            "hunger": agent.hunger,
            "step_count": agent.step_count,
            "emotions": agent.emotion.snapshot(),
            "dominant_emotion": agent.emotion.dominant_emotion(),
            "personality": agent.personality.to_dict(),
            "memory_size": len(agent.memory.events),
            "timestamp": time.time()
        }
        
        # Add language progress
        if hasattr(agent.brain, 'language'):
            status["language"] = agent.brain.get_language_progress()
        
        # Add pattern recognition stats
        status["patterns"] = agent.brain.get_pattern_summary()
        
        # Add connection info
        if agent_id in agent_manager.connected_agents:
            status["connected_to_server"] = True
            status["server_info"] = agent_manager.connected_agents[agent_id]
        else:
            status["connected_to_server"] = False
        
        # Add WebSocket stats if connected
        if agent_id in agent_manager.websocket_handlers:
            handler = agent_manager.websocket_handlers[agent_id]
            status["websocket_stats"] = handler.get_stats()
        
        return status
    
    except Exception as e:
        log.error(f"[Status] Error for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== HEALTH CHECK ENDPOINTS ====================

@app.get("/health")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "uptime": time.time() - startup_time,
        "agents_active": len(agent_manager.websocket_handlers),
        "demo_agents": len(agent_manager.demo_agents),
        "protocol": "binary_websocket_v2.1"
    }

@app.get("/health/detailed")
async def health_check_detailed():
    """Comprehensive health check with component status"""
    checks = {
        "status": "healthy",
        "timestamp": time.time(),
        "uptime": time.time() - startup_time,
        "version": "2.1.0",
        "components": {}
    }
    
    # Component 1: Agents
    try:
        spawned = len(agent_manager.spawner.list_agents())
        connected = len(agent_manager.connected_agents)
        websockets = len(agent_manager.websocket_handlers)
        demos = len(agent_manager.demo_agents)
        
        checks["components"]["agents"] = {
            "status": "ok",
            "spawned": spawned,
            "connected": connected,
            "websockets": websockets,
            "demo_agents": demos,
            "total": spawned + demos
        }
    except Exception as e:
        checks["components"]["agents"] = {
            "status": "error",
            "error": str(e)
        }
        checks["status"] = "degraded"
    
    # Component 2: Filesystem
    try:
        brains_count = len(list(Config.BRAINS_DIR.glob("*/brain.pcap")))
        uploads_count = len(list(Config.UPLOADS_DIR.glob("*/*")))
        
        checks["components"]["filesystem"] = {
            "status": "ok",
            "brains_dir": str(Config.BRAINS_DIR),
            "brains_count": brains_count,
            "uploads_count": uploads_count,
            "disk_writable": Config.DATA_DIR.exists() and os.access(Config.DATA_DIR, os.W_OK)
        }
    except Exception as e:
        checks["components"]["filesystem"] = {
            "status": "error",
            "error": str(e)
        }
        checks["status"] = "degraded"
    
    # Component 3: Configuration
    try:
        checks["components"]["configuration"] = {
            "status": "ok",
            "backend_port": Config.BASE_BACKEND_PORT,
            "minecraft_mode": agent_manager.spawner.client_manager.minecraft_mode,
            "client_jar": str(Config.CLIENT_JAR) if Config.CLIENT_JAR else None,
            "max_fps": Config.WEBSOCKET_MAX_FPS,
            "max_latency_ms": Config.WEBSOCKET_MAX_LATENCY_MS
        }
    except Exception as e:
        checks["components"]["configuration"] = {
            "status": "error",
            "error": str(e)
        }
    
    # Overall status determination
    component_statuses = [
        c.get("status", "unknown") 
        for c in checks["components"].values()
    ]
    
    if "error" in component_statuses:
        checks["status"] = "unhealthy"
    elif "warning" in component_statuses:
        checks["status"] = "degraded"
    
    return checks


# ==================== ADMIN: QUEUED FILES ====================
@app.get("/admin/files")
async def list_queued_files():
    """Return queued files and processing status across demo agents"""
    data = {}
    for agent_id, agent in agent_manager.demo_agents.items():
        try:
            qlen = 0
            peek = []
            if hasattr(agent, 'cognitive_loop') and agent.cognitive_loop:
                qlen = len(agent.cognitive_loop.file_buffer)
                peek = list(agent.cognitive_loop.file_buffer)[:10]
            # Also check memory for file_uploaded events
            recent = []
            try:
                recent = agent.memory.recall(10)
            except Exception:
                recent = []

            uploads = [e for e in recent if e.get('type') == 'file_uploaded']

            data[agent_id] = {
                'queue_length': qlen,
                'queue_peek': peek,
                'recent_uploads': uploads
            }
        except Exception as e:
            data[agent_id] = {'error': str(e)}

    return {'agents': data}

# ==================== CONTINUAL LEARNING ENDPOINTS ====================

@app.post("/api/agents/{agent_id}/continual_learning/switch_task")
async def switch_task(agent_id: str, request: Request):
    """Switch agent to new task"""
    try:
        data = await request.json()
        new_task = data.get("task_id", 0)
        
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent.brain.switch_task(new_task)
        
        log.info(f"[CL] {agent_id} switched to task {new_task}")
        
        return {
            "success": True,
            "agent_id": agent_id,
            "current_task": agent.brain.current_task,
            "message": f"Switched to task {new_task}"
        }
    
    except Exception as e:
        log.error(f"[CL] Error switching task for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/agents/{agent_id}/continual_learning/buffer")
async def get_continual_buffer(agent_id: str, task: Optional[int] = None, limit: int = 100):
    """Get continual learning buffer"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        experiences = agent.brain.get_continual_buffer(task=task, limit=limit)
        
        return {
            "agent_id": agent_id,
            "task_filter": task,
            "experience_count": len(experiences),
            "experiences": experiences[:10],
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"[CL] Error getting buffer for {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== PLAYER EVENT ENDPOINT ====================

@app.post("/api/player_event")
async def handle_player_event(request: Request):
    """Receive player connection/disconnection events"""
    try:
        data = await request.json()
        
        agent_id = data.get("agent_id")
        player_uuid = data.get("player_uuid")
        agent_type = data.get("agent_type", "npc")
        event = data.get("event")
        
        if not agent_id or not event:
            raise HTTPException(status_code=400, detail="Missing agent_id or event")
        
        if event == "connected":
            agent_manager.mark_agent_connected(agent_id, player_uuid, agent_type)
            
            # ADDED: Mark in auto-connect system
            if hasattr(app.state, 'auto_connect'):
                app.state.auto_connect.mark_connected(agent_id)
            
            return {
                "status": "success",
                "message": f"Agent {agent_id} registered as connected",
                "player_uuid": player_uuid
            }
        
        elif event == "disconnected":
            agent_manager.mark_agent_disconnected(agent_id)
            
            return {
                "status": "success",
                "message": f"Agent {agent_id} marked as disconnected"
            }
        
        else:
            raise HTTPException(status_code=400, detail=f"Unknown event: {event}")
        
    except Exception as e:
        log.error(f"[PlayerEvent] Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
        
# ==================== WEB ACCESS ENDPOINTS ====================

@app.post("/api/agents/{agent_id}/web/allow")
async def update_allowed_websites(agent_id: str, request: Request):
    """Update allowed websites from frontend"""
    try:
        data = await request.json()
        websites = data.get('websites', [])
        
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        if not hasattr(agent, 'web_browser'):
            add_web_browsing_to_agent(agent)
        
        agent.web_browser.update_allowed_websites(websites)
        
        return {
            "status": "success",
            "allowed_domains": len(agent.web_browser.allowed_domains)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/agents/{agent_id}/web/stats")
async def get_web_stats(agent_id: str):
    """Get browsing statistics"""
    agent = agent_manager.get_or_create_demo_agent(agent_id)
    
    if not hasattr(agent, 'web_browser'):
        return {"status": "not_initialized"}
    
    return agent.web_browser.get_stats()

# ==================== AGENT MANAGEMENT ENDPOINTS ====================

@app.get("/api/agents/connected")
async def list_connected_agents():
    """List agents currently connected"""
    return {
        "agents": list(agent_manager.connected_agents.keys()),
        "count": len(agent_manager.connected_agents),
        "details": agent_manager.connected_agents
    }

@app.get("/api/agents/spawned")
async def list_spawned_agents():
    """List all spawned agents"""
    spawned = agent_manager.spawner.list_agents()
    
    agents_info = {}
    for agent_id in spawned:
        agent = agent_manager.get_agent(agent_id)
        if agent:
            agents_info[agent_id] = {
                "agent_id": agent_id,
                "mode": getattr(agent, 'mode', 'unknown'),
                "health": agent.health,
                "hunger": agent.hunger,
                "memory_events": len(agent.memory.events),
                "dominant_emotion": agent.emotion.dominant_emotion(),
                "is_alive": agent.is_alive(),
                "language_stage": agent.brain.language.language_stage if hasattr(agent.brain, 'language') else 0,
                "vocabulary": agent.brain.language.vocabulary_size if hasattr(agent.brain, 'language') else 0
            }
    
    return {
        "count": len(spawned),
        "agents": agents_info
    }

@app.post("/api/agents/{agent_id}/save")
async def save_agent(agent_id: str):
    """Save agent state with atomic write"""
    try:
        agent = agent_manager.get_agent(agent_id)
        
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        save_path = Config.get_agent_brain_path(agent_id)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        
        agent.save(str(save_path))
        
        return {
            "status": "success",
            "agent_id": agent_id,
            "saved_to": str(save_path),
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"[Save] Error saving {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== ROOT ENDPOINT ====================

@app.get("/")
async def root():
    """Root endpoint with API documentation"""
    return {
        "status": "online",
        "service": "Divine World Backend",
        "version": "2.1.0",
        "description": "Production-Ready AI Backend with Binary WebSocket Protocol",
        "agents": {
            "spawned": len(agent_manager.spawner.list_agents()),
            "connected": len(agent_manager.connected_agents),
            "demo": len(agent_manager.demo_agents),
            "websockets": len(agent_manager.websocket_handlers)
        },
        "endpoints": {
            "websocket": {
                "WS /ws/agent": "Binary WebSocket for high-performance video/action streaming"
            },
            "chat": {
                "POST /api/chat": "Send chat message",
                "POST /api/upload": "Upload file for learning",
                "GET /api/agents/{agent_id}/status": "Get agent status",
                "GET /api/agents/{agent_id}/patterns": "Get pattern recognition"
            },
            "health": {
                "GET /health": "Basic health check",
                "GET /health/detailed": "Detailed health check"
            },
            "management": {
                "GET /api/agents/connected": "List connected agents",
                "GET /api/agents/spawned": "List spawned agents",
                "POST /api/agents/{agent_id}/save": "Save agent state"
            }
        },
        "features": {
            "binary_websocket": True,
            "pattern_recognition": True,
            "language_intelligence": True,
            "multimodal_learning": True,
            "continual_learning": True,
            "request_validation": True,
            "atomic_saves": True,
            "protocol_negotiation": True
        },
        "timestamp": time.time()
    }

# ==================== STARTUP/SHUTDOWN EVENTS ====================

startup_time = time.time()

@asynccontextmanager
async def lifespan():
    """Initialize services"""
    global startup_time
    startup_time = time.time()
    
    log.info("=" * 60)
    log.info("  🤖 Divine World Backend Starting")
    log.info("=" * 60)
    log.info(f"  Version: 2.1.0 (Production)")
    log.info(f"  Binary WebSocket: ENABLED")
    log.info(f"  Pattern Recognition: ENABLED")
    log.info(f"  Language Intelligence: ENABLED")
    log.info(f"  Request Validation: ENABLED")
    log.info(f"  Atomic Operations: ENABLED")
    log.info("=" * 60)
    
    log.info("✅ Backend initialized successfully")
    
    yield

    """Cleanup on shutdown"""
    log.info("🛑 Shutting down Divine World Backend...")
    
    agent_manager.cleanup_all()
    
    log.info("✅ Shutdown complete")




# ==================== CONTROLLER ENDPOINTS ====================

agent_runtimes: Dict[str, Any] = {}  # Store active controller runtimes

@app.post("/api/controller/detect-devices")
async def detect_devices(agent_id: str = "demo"):
    """Detect available camera and microphone devices"""
    try:
        from utils.dw_controller import ControllerRuntime
        from ai_core.agent import NPCAgent
        
        # Create temporary runtime for device detection
        temp_agent = NPCAgent(agent_id)
        runtime = ControllerRuntime(temp_agent)
        
        # Detect devices
        cameras = runtime.list_cameras()
        microphones = runtime.list_microphones()
        
        return {
            "status": "success",
            "devices": {
                "cameras": cameras,
                "microphones": microphones,
                "camera_count": len(cameras),
                "microphone_count": len(microphones)
            },
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"Device detection failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "devices": {
                "cameras": [],
                "microphones": [],
                "camera_count": 0,
                "microphone_count": 0
            },
            "timestamp": time.time()
        }

@app.post("/api/controller/activate")
async def activate_controller(request: Request):
    """Activate controller mode for an agent with specific permissions"""
    try:
        data = await request.json()
        agent_id = data.get("agent_id", "demo")
        permissions = data.get("permissions", [])
        permission_settings = data.get("permissionSettings", {})  # New: individual permission toggles
        
        log.info(f"🎮 Activating controller mode for {agent_id}")
        log.info(f"   Permissions: {permissions}")
        log.info(f"   Settings: {permission_settings}")
        
        # Get or create agent
        agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        # Import controller runtime
        from utils.dw_controller import ControllerRuntime
        
        # Create runtime
        if agent_id in agent_runtimes:
            log.warning(f"Controller already active for {agent_id}, stopping existing")
            agent_runtimes[agent_id].stop()
        
        def stats_callback(stats):
            """Callback for runtime stats"""
            log.debug(f"Controller stats for {agent_id}: {stats}")
        
        runtime = ControllerRuntime(agent, callback=stats_callback)
        
        # Store permission settings on runtime
        runtime.permission_settings = permission_settings
        runtime.enabled_permissions = {
            'camera': permission_settings.get('camera', False),
            'microphone': permission_settings.get('microphone', False),
            'filesystem': permission_settings.get('filesystem', False),
            'network': permission_settings.get('network', False)
        }
        
        agent_runtimes[agent_id] = runtime
        
        # Start multimodal learning based on permissions
        vision_enabled = permission_settings.get('camera', False)
        audio_enabled = permission_settings.get('microphone', False)
        
        if vision_enabled or audio_enabled:
            runtime.start_multimodal_learning(vision=vision_enabled, audio=audio_enabled)
            log.info(f"✅ Multimodal learning started: vision={vision_enabled}, audio={audio_enabled}")
        else:
            log.info(f"⚠️  No multimodal input enabled (camera={vision_enabled}, microphone={audio_enabled})")
        
        # Log filesystem and network restrictions
        if not permission_settings.get('filesystem', False):
            log.info(f"🔒 File system access DISABLED for {agent_id}")
        if not permission_settings.get('network', False):
            log.info(f"🔒 Network access DISABLED for {agent_id}")
        
        return {
            "status": "success",
            "message": f"Controller mode activated for {agent_id}",
            "permissions": permissions,
            "settings": runtime.enabled_permissions,
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"Controller activation failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

@app.post("/api/controller/deactivate")
async def deactivate_controller(agent_id: str = "demo"):
    """Deactivate controller mode for an agent"""
    try:
        log.info(f"🛑 Deactivating controller mode for {agent_id}")
        
        if agent_id in agent_runtimes:
            runtime = agent_runtimes[agent_id]
            runtime.stop()
            del agent_runtimes[agent_id]
            log.info(f"✅ Controller mode deactivated for {agent_id}")
        
        return {
            "status": "success",
            "message": f"Controller mode deactivated for {agent_id}",
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"Controller deactivation failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

@app.get("/api/controller/status")
async def get_controller_status(agent_id: str = "demo"):
    """Get controller mode status for an agent"""
    try:
        is_active = agent_id in agent_runtimes
        
        status_data = {
            "agent_id": agent_id,
            "active": is_active,
            "timestamp": time.time()
        }
        
        if is_active:
            runtime = agent_runtimes[agent_id]
            status_data["stats"] = runtime.stats
            status_data["camera_active"] = runtime.camera is not None and runtime.camera.running
            status_data["microphone_active"] = runtime.microphone is not None and runtime.microphone.running
            
            # Include current permission settings
            status_data["permissions"] = runtime.enabled_permissions
            status_data["permissions_count"] = sum(1 for v in runtime.enabled_permissions.values() if v)
        
        return status_data
    
    except Exception as e:
        log.error(f"Status check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": time.time()
        }

@app.get("/api/controller/devices")
async def get_controller_devices(agent_id: str = "demo"):
    """Get device list for controller mode"""
    try:
        if agent_id in agent_runtimes:
            runtime = agent_runtimes[agent_id]
            cameras = runtime.list_cameras()
            microphones = runtime.list_microphones()
        else:
            # Use temp runtime for detection
            from utils.dw_controller import ControllerRuntime
            from ai_core.agent import NPCAgent
            
            temp_agent = NPCAgent(agent_id)
            runtime = ControllerRuntime(temp_agent)
            cameras = runtime.list_cameras()
            microphones = runtime.list_microphones()
        
        return {
            "status": "success",
            "devices": {
                "cameras": cameras,
                "microphones": microphones
            },
            "timestamp": time.time()
        }
    
    except Exception as e:
        log.error(f"Device listing failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "devices": {"cameras": [], "microphones": []},
            "timestamp": time.time()
        }

# ==================== EXCEPTION HANDLERS ====================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": time.time()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle general exceptions"""
    log.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "timestamp": time.time()
        }
    )

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn
    import os
    
    print("\n" + "=" * 60)
    print("  🤖 Divine World Backend (Production v2.1.0)")
    print("=" * 60)
    print("  Starting server...")
    print("  Binary WebSocket: ws://localhost:11400/ws/agent")
    print("  API Documentation: http://localhost:11400/")
    print("  Health Check: http://localhost:11400/health")
    print("=" * 60 + "\n")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=11400,
        log_level="info",
        reload=False,
        access_log=True
    )