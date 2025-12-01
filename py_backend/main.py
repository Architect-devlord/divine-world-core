# py_backend/main.py - PRODUCTION VERSION v2.1.0
"""
Production-ready Divine World Backend with:
- Binary WebSocket protocol for video/images
- Multi-agent port allocation
- Pattern recognition integration
- Avalanche continual learning hooks
- Request validation
- Health checks
- Atomic operations
"""

import time
import asyncio
import sys
from pathlib import Path
from fastapi import FastAPI, WebSocket, Request, HTTPException, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from typing import Dict, Optional, Any
import numpy as np
import json
from ai_core.logger_setup import initialize_logging
initialize_logging()


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

# ==================== BINARY WEBSOCKET ENDPOINT ====================

@app.websocket("/ws/agent")
async def agent_binary_websocket(websocket: WebSocket):
    """
    Binary WebSocket with protocol negotiation.
    Ensures client supports binary protocol before proceeding.
    """
    await websocket.accept()
    
    agent_id = None
    
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
        
        if client_protocol != "binary":
            await websocket.send_json({
                "type": "error",
                "message": "Binary protocol required. Please upgrade your client.",
                "required_protocol": "binary",
                "required_version": "2.1.0"
            })
            await websocket.close(code=1008, reason="Protocol mismatch")
            return
        
        log.info(f"🔌 Binary WebSocket connected: {agent_id} (v{client_version})")
        
        # Get or create agent
        agent = agent_manager.get_agent(agent_id)
        if not agent:
            agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        # Create high-performance handler
        handler = HighPerformanceWebSocketHandler(websocket, agent_id)
        agent_manager.websocket_handlers[agent_id] = handler
        
        # PHASE 3: Send acknowledgment (last JSON message)
        await websocket.send_json({
            "type": "connected",
            "agent_id": agent_id,
            "protocol": "binary",
            "version": "2.1.0",
            "capabilities": {
                "max_fps": Config.WEBSOCKET_MAX_FPS,
                "max_latency_ms": Config.WEBSOCKET_MAX_LATENCY_MS,
                "image_format": "jpeg",
                "audio_format": "pcm"
            }
        })
        
        # PHASE 4: Binary communication loop
        log.info(f"📡 Switching to binary protocol for {agent_id}")
        
        while True:
            try:
                # Receive perception frame (binary)
                perception = await handler.receive_perception()
                
                if perception is None:
                    break
                
                # Decompress image
                frame = decompress_jpeg_to_frame(perception.image_data)
                
                # Build observation dict
                obs_dict = {
                    'frame': frame,
                    'health': perception.health,
                    'hunger': perception.hunger,
                    'position': perception.position,
                    'rotation': perception.rotation,
                    'entities': perception.entities,
                    'timestamp': perception.timestamp
                }
                
                # Agent processes perception
                obs = agent.perceive(obs_dict)
                action_array = agent.decide(obs, deterministic=False)
                action_dict = agent.act(action_array)
                
                # Convert to binary action frame
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
                
                # Send action to client
                await handler.send_action(action_frame)
                
                # Learning
                if agent.last_obs is not None:
                    outcome = {
                        'health': perception.health,
                        'hunger': perception.hunger,
                        'is_dead': perception.health <= 0,
                        'task_reward': 0.0
                    }
                    
                    agent.learn(agent.last_obs, action_array, obs, outcome)
                
                agent.last_obs = obs
                
                # Log stats periodically
                if handler.frame_count % 100 == 0:
                    stats = handler.get_stats()
                    log.info(f"📊 {agent_id}: {stats['fps']:.1f} FPS, "
                            f"{stats['avg_latency_ms']:.1f}ms latency, "
                            f"{stats['bandwidth_in_mbps']:.2f} Mbps")
            
            except WebSocketDisconnect:
                break
            except Exception as e:
                log.error(f"Error in perception loop for {agent_id}: {e}")
                break
    
    except Exception as e:
        log.error(f"WebSocket error: {e}")
    
    finally:
        if agent_id and agent_id in agent_manager.websocket_handlers:
            del agent_manager.websocket_handlers[agent_id]
        
        log.info(f"🔌 Binary WebSocket disconnected: {agent_id}")

# ==================== CHAT ENDPOINT ====================

@app.post("/api/chat")
async def handle_chat(chat_request: ChatRequest):
    """Chat endpoint with validation"""
    try:
        message = chat_request.message
        agent_id = chat_request.agent_id
        
        log.info(f"[Chat] User message for {agent_id}: {message}")
        
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
        response = agent.brain.process_language_input(message, context)
        
        if not response:
            response = f"[Stage {agent.brain.language.language_stage}] Learning..."
        
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
async def upload_file(file: UploadFile = File(...), agent_id: str = "demo"):
    """Handle file uploads with validation"""
    try:
        # Validate using Pydantic
        file_request = FileUploadRequest(
            filename=file.filename,
            agent_id=agent_id,
            filetype=file.content_type or "application/octet-stream"
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
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        log.info(f"[Upload] Saved {file_request.filename} for {agent_id} ({len(content)} bytes)")
        
        agent = agent_manager.get_or_create_demo_agent(agent_id)
        
        # Use brain's language intelligence to learn from file
        summary = agent.brain.learn_from_file(str(file_path), file_request.filetype)
        
        return {
            "status": "success",
            "filename": file_request.filename,
            "path": str(file_path),
            "size": len(content),
            "summary": summary,
            "language_progress": {
                "stage": agent.brain.language.language_stage,
                "vocabulary": agent.brain.language.vocabulary_size
            }
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

@app.on_event("startup")
async def startup_event():
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

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    log.info("🛑 Shutting down Divine World Backend...")
    
    agent_manager.cleanup_all()
    
    log.info("✅ Shutdown complete")

# ==================== ERROR HANDLERS ====================

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