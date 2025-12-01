# utils/chat_backend.py (finalized)
import os, sys, base64
from flask import Flask
from flask_socketio import SocketIO, emit, join_room

# Add the parent directory to Python path so we can import ai_core
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_core.agent import NPCAgent

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# Live agents
AGENTS = {}

def get_agent(agent_id: str):
    if agent_id not in AGENTS:
        agent = NPCAgent(agent_id)
        agent.mode = "chat"  # default
        AGENTS[agent_id] = agent
    return AGENTS[agent_id]

@socketio.on("connect")
def connect():
    emit("hello", {"msg": "connected"})

@socketio.on("join_agent")
def join_agent(data):
    agent_id = data.get("agent_id", "demo")
    agent = get_agent(agent_id)
    join_room(agent_id)
    emit("joined", {"agent_id": agent_id, "mode": agent.mode})

@socketio.on("switch_mode")
def switch_mode(data):
    agent_id = data.get("agent_id")
    new_mode = data.get("mode", "chat")  # "chat" or "controller"
    agent = get_agent(agent_id)
    agent.mode = new_mode
    emit("mode_switched", {"agent_id": agent_id, "mode": agent.mode}, room=agent_id)

@socketio.on("user_message")
def handle_user_message(data):
    try:
        agent_id = data.get("agent_id", "demo")
        text = data.get("text", "")
        if not text.strip():
            emit("error", {"message": "Empty message"}, room=agent_id)
            return
            
        agent = get_agent(agent_id)
        ev = {"type": "chat_input", "tags": ["human_chat"], "payload": {"text": text}}
        agent.memory.remember(ev, tags=["chat"])
    except Exception as e:
        emit("error", {"message": f"Error processing message: {str(e)}"}, room=agent_id)
        return

    # (Replace with planner/LLM later)
    reply = f"I heard: {text}"
    agent.memory.remember({"type": "chat_reply", "payload": {"text": reply}}, tags=["chat"])

    emit("agent_reply", {"text": reply}, room=agent_id)

@socketio.on("upload_file")
def handle_upload_file(data):
    agent_id = data.get("agent_id", "demo")
    agent = get_agent(agent_id)

    filename = data.get("filename", "file.unknown")
    filetype = data.get("filetype", "application/octet-stream")
    filedata = data.get("data", "")

    # Save under agent folder
    agent_dir = os.path.join(UPLOAD_DIR, agent_id)
    os.makedirs(agent_dir, exist_ok=True)
    filepath = os.path.join(agent_dir, filename)

    # Decode if base64
    if filedata.startswith("data:"):
        filedata = filedata.split(",", 1)[1]
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(filedata))

    ev = {
        "type": "file_input",
        "tags": ["file_upload"],
        "payload": {"filename": filename, "path": filepath, "filetype": filetype},
    }
    agent.memory.remember(ev, tags=["file"])

    emit("file_received", {"message": f"📂 File '{filename}' stored."}, room=agent_id)

# Agent-initiated push
def agent_send_message(agent_id: str, text: str):
    """Emit a conversational reply from agent to chat window."""
    socketio.emit("agent_reply", {"text": text}, room=agent_id)

def agent_send_thought(agent_id: str, text: str):
    """Emit unsolicited thought to the thoughts window."""
    socketio.emit("agent_thought", {"text": text}, room=agent_id)

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=8765, allow_unsafe_werkzeug=True)  # Match frontend port
