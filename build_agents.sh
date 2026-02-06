#!/bin/bash
# build_agents.sh - Build standalone agent executables using PyInstaller
# Includes frontend assets, Minecraft mod jars, and UltimMC integration
# 
# Usage:
#   ./build_agents.sh alice         # Build agent named 'alice'
#   ./build_agents.sh alice bob eve # Build multiple agents
#   ./build_agents.sh all           # Build all known agents

set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BACKEND="$BASE_DIR/py_backend"
AI_CORE="$PY_BACKEND/ai_core"
BUILD_DIR="$BASE_DIR/build/agents"
DIST_DIR="$BUILD_DIR/dist"
DATA_DIR="$BUILD_DIR/data"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Known agents
KNOWN_AGENTS=("alice" "bob" "eve" "adam" "sophia" "jack")

echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Divine World Agent Builder - with Minecraft & Frontend Support${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════${NC}"
echo ""

# Prepare data bundle (frontend, mods, etc.)
prepare_data_bundle() {
    echo -e "${YELLOW}Preparing data bundle...${NC}"
    
    mkdir -p "$DATA_DIR"
    
    # Copy frontend dist if available
    FRONTEND_DIST="$BASE_DIR/dw_agent/electron/react-app/dist"
    if [ -d "$FRONTEND_DIST" ]; then
        echo -e "  ${GREEN}✓${NC} Including frontend assets"
        cp -r "$FRONTEND_DIST" "$DATA_DIR/frontend" 2>/dev/null || true
    else
        echo -e "  ${YELLOW}⚠${NC} Frontend not built (optional)"
    fi
    
    # Copy mod jars
    MODS_DIR="$DATA_DIR/mods"
    mkdir -p "$MODS_DIR"
    
    # DivineWorld mod
    if [ -f "$BASE_DIR/DivineWorld/build/libs/divineworld-1.0.0-all.jar" ]; then
        cp "$BASE_DIR/DivineWorld/build/libs/divineworld-1.0.0-all.jar" "$MODS_DIR/"
        echo -e "  ${GREEN}✓${NC} Included DivineWorld mod"
    else
        echo -e "  ${YELLOW}⚠${NC} DivineWorld mod not found (build with: cd DivineWorld && gradle build)"
    fi
    
    # DWClientBot mod
    if [ -f "$BASE_DIR/DWClientBot/build/libs/dwclient-1.0.0.jar" ]; then
        cp "$BASE_DIR/DWClientBot/build/libs/dwclient-1.0.0.jar" "$MODS_DIR/"
        echo -e "  ${GREEN}✓${NC} Included DWClientBot mod"
    else
        echo -e "  ${YELLOW}⚠${NC} DWClientBot mod not found (build with: cd DWClientBot && gradle build)"
    fi
    
    # Create UltimMC setup guide
    cat > "$DATA_DIR/ULTIMMC_SETUP.txt" << 'EOF'
═══════════════════════════════════════════════════════════════════
ULTIMMC SETUP GUIDE FOR DIVINE WORLD AGENTS
═══════════════════════════════════════════════════════════════════

To use Minecraft integration with these Divine World agents, you need
to install UltimMC (an open-source Minecraft launcher).

QUICK SETUP:
────────────
1. Download UltimMC from:
   • https://github.com/UltimMC/Launcher/releases
   • OR https://github.com/Architect-devlord/Launcher/releases

2. Extract to one of these locations:
   • ~/UltimMC (recommended)
   • ~/.ultimmc
   • ~/.local/share/ultimmc
   • Or in the same directory as this agent

3. Run agent with Minecraft:
   ./DW_Agent_Alice --agent-id alice --minecraft --ultimmc-path ~/UltimMC

RUNNING WITHOUT MINECRAFT:
──────────────────────────
The agent runs fine without UltimMC - it will just run in API mode.
You can still connect to the WebSocket endpoint directly:

   ./DW_Agent_Alice --agent-id alice --port 8001
   # Connect to: ws://127.0.0.1:8001/ws

AUTOMATIC DETECTION:
────────────────────
The agent will automatically detect UltimMC if installed in:
   • ~/UltimMC
   • ~/.ultimmc
   • ~/.local/share/ultimmc
   • Same directory as the agent executable

Just run:
   ./DW_Agent_Alice --agent-id alice --minecraft

═══════════════════════════════════════════════════════════════════
EOF
    
    echo -e "  ${GREEN}✓${NC} Created UltimMC setup guide"
}

# Function to build single agent
build_agent() {
    local AGENT_ID=$1
    local AGENT_UPPER=$(echo "$AGENT_ID" | tr 'a-z' 'A-Z')
    local OUTPUT_NAME="DW_Agent_${AGENT_UPPER}"
    
    echo -e "${YELLOW}Building agent: $AGENT_ID${NC}"
    echo "  Output: $OUTPUT_NAME"
    
    # Create build directory
    mkdir -p "$BUILD_DIR"
    
    # Run PyInstaller with data files
    cd "$BASE_DIR"
    
    # Build PyInstaller command with data files
    PYINSTALLER_ARGS=(
        "--onefile"
        "--name=$OUTPUT_NAME"
        "--distpath=$DIST_DIR"
        "--buildpath=$BUILD_DIR/build"
        "--specpath=$BUILD_DIR"
        "--hidden-import=torch"
        "--hidden-import=numpy"
        "--hidden-import=fastapi"
        "--hidden-import=uvicorn"
        "--hidden-import=websockets"
        "--hidden-import=aiohttp"
        "--hidden-import=msgpack"
        "--hidden-import=ai_core"
        "--collect-all=ai_core"
        "--collect-all=torch"
    )
    
    # Add data files if available
    if [ -d "$DATA_DIR/mods" ] && [ -n "$(ls -A $DATA_DIR/mods 2>/dev/null)" ]; then
        PYINSTALLER_ARGS+=("--add-data=$DATA_DIR/mods:mods")
    fi
    
    if [ -d "$DATA_DIR/frontend" ]; then
        PYINSTALLER_ARGS+=("--add-data=$DATA_DIR/frontend:frontend")
    fi
    
    if [ -f "$DATA_DIR/ULTIMMC_SETUP.txt" ]; then
        PYINSTALLER_ARGS+=("--add-data=$DATA_DIR/ULTIMMC_SETUP.txt:.")
    fi
    
    PYINSTALLER_ARGS+=("$AI_CORE/agent_standalone.py")
    
    python3 -m PyInstaller "${PYINSTALLER_ARGS[@]}"
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ Built: $OUTPUT_NAME${NC}"
        echo "   Location: $DIST_DIR/$OUTPUT_NAME"
        
        # Create wrapper script for easy launching
        WRAPPER="$BUILD_DIR/run_${AGENT_ID}.sh"
        AGENT_UPPER_VAR=$(echo "$AGENT_ID" | tr 'a-z' 'A-Z')
        cat > "$WRAPPER" << 'LAUNCHER_EOF'
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ID="${1:-alice}"
PORT="${2:-8001}"
"$SCRIPT_DIR/dist/DW_Agent_AGENT_UPPER" --agent-id "$AGENT_ID" --port "$PORT" "${@:3}"
LAUNCHER_EOF
        sed -i "s/AGENT_UPPER/$AGENT_UPPER_VAR/g" "$WRAPPER"
        chmod +x "$WRAPPER"
        echo "   Launcher: $WRAPPER"
        
        # Copy UltimMC setup guide
        if [ -f "$DATA_DIR/ULTIMMC_SETUP.txt" ]; then
            cp "$DATA_DIR/ULTIMMC_SETUP.txt" "$DIST_DIR/ULTIMMC_SETUP_${AGENT_UPPER}.txt"
            echo "   Guide: $DIST_DIR/ULTIMMC_SETUP_${AGENT_UPPER}.txt"
        fi
    else
        echo -e "${RED}❌ Failed to build: $AGENT_ID${NC}"
        return 1
    fi
}

main() {
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  Divine World Agent Builder v1.0     ║${NC}"
    echo -e "${CYAN}║  Build Standalone PyInstaller Agents ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo ""
    
    # Check if Python 3 is available
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}❌ Error: Python 3 is not installed${NC}"
        exit 1
    fi
    
    # Check if PyInstaller is installed
    if ! python3 -m pip show pyinstaller &> /dev/null; then
        echo -e "${YELLOW}⚠️  PyInstaller not found. Installing...${NC}"
        python3 -m pip install pyinstaller -q
    fi
    
    # Build data directory with assets (once per build session)
    prepare_data_bundle
    
    # Determine which agents to build
    if [ $# -eq 0 ]; then
        # Build all agents
        AGENTS_TO_BUILD=("${KNOWN_AGENTS[@]}")
        echo -e "${CYAN}Building all agents: ${KNOWN_AGENTS[*]}${NC}"
    else
        # Build specified agents
        AGENTS_TO_BUILD=("$@")
        echo -e "${CYAN}Building specified agents: $*${NC}"
    fi
    
    echo ""
    SUCCESSFUL=0
    FAILED=0
    
    # Build each agent
    for AGENT_ID in "${AGENTS_TO_BUILD[@]}"; do
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        echo "Building agent: $AGENT_ID"
        echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
        
        if build_agent "$AGENT_ID"; then
            ((SUCCESSFUL++))
        else
            ((FAILED++))
        fi
        
        echo ""
    done
    
    # Display summary
    echo -e "${CYAN}╔══════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║           BUILD SUMMARY              ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════╝${NC}"
    echo "Successful: $SUCCESSFUL"
    echo "Failed: $FAILED"
    
    if [ $FAILED -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ All agents built successfully!${NC}"
        echo ""
        echo "📦 Executables location: $DIST_DIR/"
        echo "📦 Data bundled:"
        echo "   - Frontend assets"
        echo "   - DivineWorld & DWClientBot mods"
        echo "   - UltimMC setup guide"
        echo ""
        echo "🚀 To run an agent:"
        echo "   $DIST_DIR/DW_Agent_alice --agent-id alice --port 8001"
        echo ""
        echo "🎮 To launch with Minecraft:"
        echo "   $DIST_DIR/DW_Agent_alice --agent-id alice --minecraft"
        echo ""
        echo "❓ For Minecraft setup help:"
        echo "   cat $DIST_DIR/ULTIMMC_SETUP_ALICE.txt"
        echo ""
    else
        echo -e "${RED}❌ Some agents failed to build${NC}"
        exit 1
    fi
}

# Handle script arguments
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi
