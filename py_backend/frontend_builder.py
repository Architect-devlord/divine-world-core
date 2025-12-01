"""
Frontend build helper for DW Agent
"""

import os
import sys
import logging
import subprocess
import shutil
from pathlib import Path

log = logging.getLogger("frontend_builder")

# Find npm in PATH
NPM_CMD = shutil.which("npm") or "npm"

class FrontendBuilder:
    """Handles building the React frontend"""
    
    def __init__(self):
        # Use npm found in PATH
        self.npm_cmd = NPM_CMD
        log.info(f"Using npm at: {self.npm_cmd}")
    
    def build_frontend(self, frontend_dir: Path, output_dir: Path) -> bool:
        """
        Build the React frontend
        
        Args:
            frontend_dir: Path to the React app directory
            output_dir: Where to copy the built frontend
        
        Returns:
            bool: True if build successful
        """
        try:
            log.info(f"🔨 Building frontend from: {frontend_dir}")
            
            # Verify frontend directory
            if not frontend_dir.exists():
                log.error(f"Frontend directory not found: {frontend_dir}")
                return False
            
            if not (frontend_dir / "package.json").exists():
                log.error(f"No package.json found in: {frontend_dir}")
                return False
            
            # Install dependencies if needed
            if not (frontend_dir / "node_modules").exists():
                log.info("📦 Installing dependencies...")
                try:
                    result = subprocess.run(
                        [self.npm_cmd, "install"],
                        cwd=str(frontend_dir),
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    if result.stderr:
                        log.warning(f"npm install stderr: {result.stderr}")
                except subprocess.CalledProcessError as e:
                    log.error(f"npm install failed: {e.stderr}")
                    return False
            
            # Run build
            log.info("🗝️ Building frontend...")
            try:
                result = subprocess.run(
                    [self.npm_cmd, "run", "build"],
                    cwd=str(frontend_dir),
                    check=True,
                    capture_output=True,
                    text=True
                )
                if result.stderr:
                    log.warning(f"Build stderr: {result.stderr}")
            except subprocess.CalledProcessError as e:
                log.error(f"Build failed: {e.stderr}")
                return False
            
            # Find build output
            possible_build_dirs = [
                frontend_dir / "dist",
                frontend_dir / "build",
                frontend_dir / "out"
            ]
            
            build_dir = None
            for d in possible_build_dirs:
                if d.exists():
                    build_dir = d
                    break
            
            if not build_dir:
                log.error("No build output found")
                return False
            
            # Copy to output directory
            if output_dir.exists():
                shutil.rmtree(output_dir)
            
            shutil.copytree(build_dir, output_dir)
            log.info(f"✅ Frontend built and copied to: {output_dir}")
            return True
            
        except Exception as e:
            log.error(f"Frontend build failed: {e}")
            import traceback
            log.error(traceback.format_exc())
            return False

# Test the builder
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    builder = FrontendBuilder()
    frontend_dir = Path("dw_agent/electron/react-app")
    output_dir = Path("test_build")
    
    success = builder.build_frontend(frontend_dir, output_dir)
    print(f"Build {'succeeded' if success else 'failed'}")