#!/bin/bash
# production_ready_check.sh - Verify system is ready for production deployment

set +e  # Don't exit on errors, we want to show all issues

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BACKEND="$BASE_DIR/py_backend"
AI_CORE="$PY_BACKEND/ai_core"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

PASS=0
WARN=0
FAIL=0

# Test result functions
pass() { echo -e "${GREEN}✅${NC} $1"; ((PASS++)); }
warn() { echo -e "${YELLOW}⚠️${NC} $1"; ((WARN++)); }
fail() { echo -e "${RED}❌${NC} $1"; ((FAIL++)); }

echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║  Divine World Production Readiness Check v1.0         ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# === PYTHON ENVIRONMENT ===
echo -e "${BLUE}▶ Python Environment${NC}"

if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    pass "Python 3 found: v$PY_VERSION"
else
    fail "Python 3 not found - install with: sudo apt-get install python3"
fi

if [ -d "$BASE_DIR/py_backend/dw_env" ]; then
    pass "Virtual environment (dw_env) exists"
else
    warn "Virtual environment missing - create with: python3 -m venv dw_env"
fi

# === AI CORE MODULES ===
echo ""
echo -e "${BLUE}▶ AI Core Modules${NC}"

modules=("config.py" "communication_protocol.py" "validation.py" "agent.py" "agent_standalone.py" "world_model.py" "__init__.py")
for module in "${modules[@]}"; do
    if [ -f "$AI_CORE/$module" ]; then
        pass "ai_core/$module exists"
    else
        fail "ai_core/$module missing"
    fi
done

# === PYTHON COMPILATION ===
echo ""
echo -e "${BLUE}▶ Python Syntax Validation${NC}"

if python3 -m py_compile "$AI_CORE/agent_standalone.py" 2>/dev/null; then
    pass "agent_standalone.py compiles"
else
    fail "agent_standalone.py has syntax errors"
fi

if python3 -m py_compile "$PY_BACKEND/main.py" 2>/dev/null; then
    pass "main.py compiles"
else
    fail "main.py has syntax errors"
fi

if python3 -m py_compile "$AI_CORE/config.py" 2>/dev/null; then
    pass "config.py compiles"
else
    fail "config.py has syntax errors"
fi

# === BUILD SYSTEM ===
echo ""
echo -e "${BLUE}▶ Build System${NC}"

if [ -f "$BASE_DIR/build_agents.sh" ]; then
    pass "build_agents.sh exists"
    
    if bash -n "$BASE_DIR/build_agents.sh" 2>/dev/null; then
        pass "build_agents.sh syntax is valid"
    else
        fail "build_agents.sh has bash syntax errors"
    fi
else
    fail "build_agents.sh not found"
fi

if [ -f "$BASE_DIR/build_agent.spec" ]; then
    pass "build_agent.spec (PyInstaller config) exists"
else
    warn "build_agent.spec not found (needed for building)"
fi

# === BUILD DEPENDENCIES ===
echo ""
echo -e "${BLUE}▶ Build Dependencies${NC}"

if python3 -m pip show pyinstaller &>/dev/null; then
    pass "PyInstaller installed"
else
    warn "PyInstaller not installed - install with: pip install pyinstaller"
fi

if python3 -m pip show fastapi &>/dev/null; then
    pass "FastAPI installed"
else
    warn "FastAPI not installed"
fi

if python3 -m pip show uvicorn &>/dev/null; then
    pass "Uvicorn installed"
else
    warn "Uvicorn not installed"
fi

if python3 -m pip show torch &>/dev/null; then
    pass "PyTorch installed"
else
    warn "PyTorch not installed (large download, optional)"
fi

# === MINECRAFT SETUP ===
echo ""
echo -e "${BLUE}▶ Minecraft Integration${NC}"

ULTIMMC_FOUND=false
ULTIMMC_PATHS=(
    "$HOME/UltimMC/UltimMC-linux-x64.AppImage"
    "$HOME/UltimMC/ultimmc"
    "$HOME/.ultimmc/ultimmc"
    "$HOME/.local/share/ultimmc/ultimmc"
    "/opt/ultimmc/ultimmc"
    "/Applications/UltimMC.app/Contents/MacOS/UltimMC"
)

for ultimmc_path in "${ULTIMMC_PATHS[@]}"; do
    if [ -f "$ultimmc_path" ] || [ -d "$ultimmc_path" ]; then
        pass "UltimMC found at: $ultimmc_path"
        ULTIMMC_FOUND=true
        break
    fi
done

if [ "$ULTIMMC_FOUND" = false ]; then
    warn "UltimMC not found - download from: https://github.com/UltimMC/Launcher/releases"
fi

if command -v java &> /dev/null; then
    JAVA_VERSION=$(java -version 2>&1 | head -1)
    pass "Java installed: $JAVA_VERSION"
else
    warn "Java not found - install with: sudo apt-get install default-jre"
fi

# === MOD COMPILATION ===
echo ""
echo -e "${BLUE}▶ Minecraft Mods${NC}"

if [ -f "$BASE_DIR/DivineWorld/build/libs/divineworld-1.0.0-all.jar" ]; then
    pass "DivineWorld mod JAR built"
else
    warn "DivineWorld mod needs build: cd DivineWorld && gradle build"
fi

if [ -f "$BASE_DIR/DWClientBot/build/libs/DWClientBot.jar" ]; then
    pass "DWClientBot mod JAR built"
else
    warn "DWClientBot mod needs build: cd DWClientBot && gradle build"
fi

# === FRONTEND ===
echo ""
echo -e "${BLUE}▶ Frontend Build${NC}"

if [ -d "$BASE_DIR/dw_agent/electron/react-app/dist" ]; then
    pass "Frontend (React) built at dw_agent/electron/react-app/dist"
    DIST_SIZE=$(du -sh "$BASE_DIR/dw_agent/electron/react-app/dist" 2>/dev/null | awk '{print $1}')
    echo -e "   Size: $DIST_SIZE"
else
    warn "Frontend not built - build with: cd dw_agent/electron/react-app && npm run build"
fi

# === FILE STRUCTURE ===
echo ""
echo -e "${BLUE}▶ Directory Structure${NC}"

dirs=("$BASE_DIR/data/brains" "$BASE_DIR/data/logs" "$BASE_DIR/build/agents" "$PY_BACKEND/npc_applications")
for dir in "${dirs[@]}"; do
    if [ -d "$dir" ]; then
        pass "Directory exists: ${dir#$BASE_DIR/}"
    else
        warn "Directory missing: ${dir#$BASE_DIR/} (will be created on first run)"
    fi
done

# === DOCUMENTATION ===
echo ""
echo -e "${BLUE}▶ Documentation${NC}"

docs=("README.md" "DEPLOYMENT_GUIDE.md" "QUICK_START.md" "README_STANDALONE_AGENTS.md")
for doc in "${docs[@]}"; do
    if [ -f "$BASE_DIR/$doc" ]; then
        pass "$doc exists"
    else
        warn "$doc not found"
    fi
done

# === PERMISSIONS ===
echo ""
echo -e "${BLUE}▶ Script Permissions${NC}"

scripts=("build_agents.sh" "verify_standalone_setup.sh")
for script in "${scripts[@]}"; do
    if [ -f "$BASE_DIR/$script" ]; then
        if [ -x "$BASE_DIR/$script" ]; then
            pass "$script is executable"
        else
            warn "$script needs execute permission: chmod +x $BASE_DIR/$script"
        fi
    fi
done

# === PORT AVAILABILITY ===
echo ""
echo -e "${BLUE}▶ Port Availability${NC}"

ports=(8001 8002 8003 25565)
for port in "${ports[@]}"; do
    if ! netstat -tuln 2>/dev/null | grep -q ":$port "; then
        pass "Port $port is available"
    else
        warn "Port $port is in use"
    fi
done

# === OPTIONAL ENHANCEMENTS ===
echo ""
echo -e "${BLUE}▶ Optional Enhancements${NC}"

if [ -f "$BASE_DIR/docker-compose.yml" ]; then
    pass "Docker Compose config found"
else
    warn "Docker not configured (optional)"
fi

if command -v git &> /dev/null; then
    pass "Git installed (for version control)"
else
    warn "Git not installed (optional)"
fi

# === SUMMARY ===
echo ""
echo -e "${CYAN}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              READINESS REPORT SUMMARY                  ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════╝${NC}"
echo -e "${GREEN}✅ Passed${NC}: $PASS"
echo -e "${YELLOW}⚠️ Warnings${NC}: $WARN"
echo -e "${RED}❌ Failed${NC}: $FAIL"
echo ""

if [ $FAIL -eq 0 ] && [ $WARN -le 2 ]; then
    echo -e "${GREEN}🚀 System is ${BOLD}PRODUCTION READY${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. cd /home/devlord/divine-world-core"
    echo "  2. chmod +x build_agents.sh"
    echo "  3. ./build_agents.sh all"
    echo "  4. ./build/agents/dist/DW_Agent_alice --agent-id alice --minecraft"
    echo ""
elif [ $FAIL -eq 0 ]; then
    echo -e "${YELLOW}⚠️  System is ${BOLD}MOSTLY READY${NC} (some optional items missing)"
    echo ""
    echo "You can still run agents, but consider fixing warnings for full functionality."
    echo ""
else
    echo -e "${RED}❌ System has ${BOLD}CRITICAL ISSUES${NC}"
    echo ""
    echo "Please fix the failed items above before deploying."
    echo ""
fi

# Return appropriate exit code
[ $FAIL -eq 0 ] && exit 0 || exit 1
