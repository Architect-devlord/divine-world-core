#!/usr/bin/env python3
# py_backend/start_production.py - Production Startup Script
"""
Production startup script with health checks and validation.
"""

import sys
import os
from pathlib import Path
import logging

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(message)s'
)
log = logging.getLogger("startup")

def validate_environment():
    """Validate environment before starting"""
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        issues.append(f"Python 3.8+ required (current: {sys.version_info.major}.{sys.version_info.minor})")
    
    # Check critical directories
    required_dirs = ['ai_core', 'py_backend', 'data']
    for dir_name in required_dirs:
        if not Path(dir_name).exists():
            issues.append(f"Missing directory: {dir_name}")
    
    # Check critical files
    required_files = [
        'C:/Users/user/Desktop/divineworld/py_backend/main.py',
        'C:/Users/user/Desktop/divineworld/py_backend/config.py',
        'C:/Users/user/Desktop/divineworld/py_backend/ai_core/agent.py',
        'C:/Users/user/Desktop/divineworld/py_backend/ai_core/brain_core.py',
    ]
    for file_path in required_files:
        if not Path(file_path).exists():
            issues.append(f"Missing file: {file_path}")
    
    return issues

def check_dependencies():
    """Check if required packages are installed"""
    required = [
        'fastapi',
        'uvicorn',
        'numpy',
        'torch',
        'pydantic',
        'websockets',
    ]
    
    missing = []
    for package in required:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    return missing

def main():
    """Main startup sequence"""
    print("\n" + "="*70)
    print("  🤖 DIVINE WORLD BACKEND - PRODUCTION STARTUP")
    print("="*70 + "\n")
    
    # Step 1: Validate environment
    log.info("Step 1: Validating environment...")
    issues = validate_environment()
    if issues:
        log.error("Environment validation failed:")
        for issue in issues:
            log.error(f"  ❌ {issue}")
        print("\n" + "="*70)
        print("  ❌ STARTUP FAILED - Fix issues above")
        print("="*70 + "\n")
        sys.exit(1)
    log.info("✅ Environment valid")
    
    # Step 2: Check dependencies
    log.info("Step 2: Checking dependencies...")
    missing = check_dependencies()
    if missing:
        log.error("Missing dependencies:")
        for package in missing:
            log.error(f"  ❌ {package}")
        log.error("\nInstall with: pip install " + " ".join(missing))
        print("\n" + "="*70)
        print("  ❌ STARTUP FAILED - Install missing packages")
        print("="*70 + "\n")
        sys.exit(1)
    log.info("✅ Dependencies installed")
    
    # Step 3: Validate configuration
    log.info("Step 3: Validating configuration...")
    try:
        from config import Config
        if not Config.validate():
            log.error("Configuration validation failed")
            sys.exit(1)
        log.info("✅ Configuration valid")
    except Exception as e:
        log.error(f"Configuration error: {e}")
        sys.exit(1)
    
    # Step 4: Start server
    log.info("Step 4: Starting server...")
    print("\n" + "="*70)
    print("  ✅ ALL CHECKS PASSED")
    print("="*70 + "\n")
    
    try:
        import uvicorn
        from main import app
        
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=Config.BASE_BACKEND_PORT,
            log_level="info",
            access_log=True
        )
    except KeyboardInterrupt:
        print("\n\n" + "="*70)
        print("  🛑 Server stopped by user")
        print("="*70 + "\n")
    except Exception as e:
        log.error(f"Server error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()