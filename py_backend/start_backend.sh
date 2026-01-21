#!/bin/bash

# Divine World Backend Startup Script
# Usage: ./start_backend.sh [OPTIONS]

set -e

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Configuration
BACKEND_PORT=${DW_BACKEND_PORT:-11400}
CLIENT_MEMORY=${DW_CLIENT_MEMORY:-2048}
LOG_LEVEL=${DW_LOG_LEVEL:-INFO}

# Functions
print_header() {
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}🤖 Divine World Backend Launcher${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
}

print_config() {
    echo -e "${YELLOW}Configuration:${NC}"
    echo "  Backend Port: $BACKEND_PORT"
    echo "  Client Memory: ${CLIENT_MEMORY}MB"
    echo "  Log Level: $LOG_LEVEL"
    echo "  Python: $(which python3)"
    echo "  Virtual Env: dw_env"
}

check_venv() {
    if [ ! -f "dw_env/bin/activate" ]; then
        echo -e "${RED}❌ Virtual environment not found!${NC}"
        echo "Creating virtual environment..."
        python3 -m venv dw_env
        echo -e "${GREEN}✅ Virtual environment created${NC}"
    fi
}

activate_venv() {
    source dw_env/bin/activate
    echo -e "${GREEN}✅ Virtual environment activated${NC}"
}

check_dependencies() {
    echo -e "${YELLOW}Checking dependencies...${NC}"
    
    python3 -c "import fastapi" 2>/dev/null && echo -e "  ${GREEN}✅ FastAPI${NC}" || echo -e "  ${RED}❌ FastAPI${NC}"
    python3 -c "import torch" 2>/dev/null && echo -e "  ${GREEN}✅ PyTorch${NC}" || echo -e "  ${RED}❌ PyTorch${NC}"
    python3 -c "import websockets" 2>/dev/null && echo -e "  ${GREEN}✅ WebSockets${NC}" || echo -e "  ${RED}❌ WebSockets${NC}"
    python3 -c "import numpy" 2>/dev/null && echo -e "  ${GREEN}✅ NumPy${NC}" || echo -e "  ${RED}❌ NumPy${NC}"
}

verify_config() {
    echo -e "${YELLOW}Verifying configuration...${NC}"
    python3 << 'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

try:
    from config import Config
    print(f"  ✅ Backend Port: {Config.BASE_BACKEND_PORT}")
    print(f"  ✅ Data Directory: {Config.DATA_DIR}")
    print(f"  ✅ Brains Directory: {Config.BRAINS_DIR}")
    print(f"  ✅ Client JAR: {Config.CLIENT_JAR if Config.CLIENT_JAR else '(Chat-only mode)'}")
    print(f"  ✅ Server: {Config.DEFAULT_SERVER}")
except Exception as e:
    print(f"  ❌ Configuration Error: {e}")
    sys.exit(1)
EOF
}

print_startup_info() {
    echo -e ""
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}🚀 Divine World Backend Starting${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
    echo -e "${YELLOW}Access Points:${NC}"
    echo -e "  🌐 HTTP API: ${GREEN}http://127.0.0.1:${BACKEND_PORT}${NC}"
    echo -e "  📡 WebSocket: ${GREEN}ws://127.0.0.1:${BACKEND_PORT}/ws/agent${NC}"
    echo -e "  📚 API Docs: ${GREEN}http://127.0.0.1:${BACKEND_PORT}/docs${NC}"
    echo -e "  💬 Redoc: ${GREEN}http://127.0.0.1:${BACKEND_PORT}/redoc${NC}"
    echo ""
    echo -e "${YELLOW}Divine World Endpoints:${NC}"
    echo -e "  ✓ POST   /api/genesis/spawn"
    echo -e "  ✓ POST   /api/divineworld/divine_reset"
    echo -e "  ✓ POST   /api/agents/clear_memories"
    echo -e "  ✓ POST   /api/gods/spawn"
    echo -e "  ✓ POST   /api/divineworld/god_ability"
    echo -e "  ✓ POST   /api/divineworld/god_transform"
    echo -e "  ✓ GET    /api/divineworld/list_agents"
    echo -e "  ✓ POST   /api/divineworld/npc/spawn"
    echo -e "  ✓ POST   /api/divineworld/npc/remove"
    echo -e "  ✓ GET    /api/divineworld/npc/info/{agent_id}"
    echo ""
    echo -e "${YELLOW}Health Checks:${NC}"
    echo -e "  • ${GREEN}http://127.0.0.1:${BACKEND_PORT}/health${NC}"
    echo -e "  • ${GREEN}http://127.0.0.1:${BACKEND_PORT}/health/detailed${NC}"
    echo ""
    echo -e "${YELLOW}Documentation:${NC}"
    echo -e "  • See ${GREEN}DIVINE_WORLD_API.md${NC} for complete API reference"
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo -e "Press ${YELLOW}Ctrl+C${NC} to stop the server"
    echo -e "${BLUE}════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Main flow
print_header
print_config
check_venv
activate_venv
check_dependencies
verify_config
print_startup_info

# Start server
export DW_BACKEND_PORT=$BACKEND_PORT
export DW_CLIENT_MEMORY=$CLIENT_MEMORY
export DW_LOG_LEVEL=$LOG_LEVEL

exec python3 main.py
