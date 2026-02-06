#!/bin/bash
# verify_standalone_setup.sh - Verify that all components for standalone agent building are in place

set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY_BACKEND="$BASE_DIR/py_backend"
AI_CORE="$PY_BACKEND/ai_core"

echo "=========================================="
echo "Standalone Agent Setup Verification"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ERRORS=0

# Check 1: Required files in ai_core
echo -e "${YELLOW}[1] Checking required modules in ai_core...${NC}"
REQUIRED_MODULES=(
    "agent.py"
    "agent_standalone.py"
    "config.py"
    "communication_protocol.py"
    "validation.py"
    "__init__.py"
)

for module in "${REQUIRED_MODULES[@]}"; do
    if [ -f "$AI_CORE/$module" ]; then
        echo -e "  ${GREEN}✓${NC} $module"
    else
        echo -e "  ${RED}✗${NC} $module - MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Check 2: Python compilation
echo -e "${YELLOW}[2] Verifying Python modules compile...${NC}"
cd "$PY_BACKEND"
MODULES_TO_CHECK=(
    "ai_core/config.py"
    "ai_core/communication_protocol.py"
    "ai_core/validation.py"
    "ai_core/agent.py"
    "ai_core/agent_standalone.py"
)

for module in "${MODULES_TO_CHECK[@]}"; do
    if python3 -m py_compile "$module" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $module compiles"
    else
        echo -e "  ${RED}✗${NC} $module - COMPILATION ERROR"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Check 3: Build scripts
echo -e "${YELLOW}[3] Checking build scripts...${NC}"
BUILD_SCRIPTS=(
    "$BASE_DIR/build_agents.sh"
    "$BASE_DIR/build_agent.spec"
)

for script in "${BUILD_SCRIPTS[@]}"; do
    if [ -f "$script" ]; then
        echo -e "  ${GREEN}✓${NC} $(basename $script)"
    else
        echo -e "  ${RED}✗${NC} $(basename $script) - MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done
echo ""

# Check 4: Import ai_core
echo -e "${YELLOW}[4] Testing ai_core import...${NC}"
cd "$PY_BACKEND"
if python3 -c "import ai_core; print('  ✓ ai_core imported'); from ai_core import Config, NPCAgent; print('  ✓ Config and NPCAgent available')" 2>/dev/null; then
    echo ""
else
    echo -e "  ${RED}✗${NC} Failed to import ai_core"
    ERRORS=$((ERRORS + 1))
    echo ""
fi

# Check 5: PyInstaller availability
echo -e "${YELLOW}[5] Checking PyInstaller...${NC}"
if command -v pyinstaller &> /dev/null; then
    VERSION=$(pyinstaller --version)
    echo -e "  ${GREEN}✓${NC} PyInstaller installed ($VERSION)"
else
    echo -e "  ${YELLOW}⚠${NC} PyInstaller not found - install with: pip install pyinstaller"
fi
echo ""

# Check 6: Required dependencies
echo -e "${YELLOW}[6] Checking required Python packages...${NC}"
PACKAGES=(
    "torch"
    "numpy"
    "fastapi"
    "uvicorn"
    "websockets"
    "aiohttp"
)

for package in "${PACKAGES[@]}"; do
    if python3 -c "import $package" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $package"
    else
        echo -e "  ${YELLOW}⚠${NC} $package - not installed (optional)"
    fi
done
echo ""

# Check 7: README exists
echo -e "${YELLOW}[7] Checking documentation...${NC}"
if [ -f "$BASE_DIR/README_STANDALONE_AGENTS.md" ]; then
    echo -e "  ${GREEN}✓${NC} README_STANDALONE_AGENTS.md"
else
    echo -e "  ${RED}✗${NC} README_STANDALONE_AGENTS.md - MISSING"
    ERRORS=$((ERRORS + 1))
fi
echo ""

# Summary
echo "=========================================="
if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}✅ All checks passed!${NC}"
    echo ""
    echo "Your setup is ready for standalone agent building."
    echo ""
    echo "Quick start:"
    echo "  1. ./build_agents.sh alice          # Build agent 'alice'"
    echo "  2. ./build/agents/dist/DW_Agent_Alice --agent-id alice --port 8001"
    echo ""
else
    echo -e "${RED}❌ $ERRORS issue(s) found${NC}"
    echo ""
    echo "Fix the issues above, then run:"
    echo "  $0"
fi
echo "=========================================="

exit $ERRORS
