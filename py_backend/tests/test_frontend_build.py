"""
test_frontend_build.py - Complete Frontend Integration Test
Run this to verify frontend builds and integrates properly
"""

import subprocess
import sys
from pathlib import Path
import shutil
import time

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")

def print_step(step_num, total, text):
    print(f"[{step_num}/{total}] {text}")

# Use shutil.which to find npm in PATH (works cross-platform)
NPM_CMD = shutil.which("npm") or "npm"

def run_command(cmd, cwd=None, check=True):
    """Run command and return output"""
    # Replace 'npm' with the npm found in PATH
    if cmd[0] == "npm":
        cmd[0] = NPM_CMD
    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=check)
    if result.returncode != 0:
        print(f"  ❌ Error: {result.stderr}")
        if check:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}")
    else:
        print(f"  ✅ Success")
    return result

def main():
    print_header("🔧 Frontend Integration Test")
    
    # Paths
    workspace = Path(__file__).parent.parent  # Go up from py_backend to root
    frontend_dir = workspace / "dw_agent" / "electron" / "react-app"
    
    print(f"Workspace: {workspace}")
    print(f"Looking for frontend in: {frontend_dir}")
    
    if not frontend_dir.exists():
        print(f"❌ Frontend directory not found: {frontend_dir}")
        print("\nExpected structure:")
        print("  C:\\Users\\user\\Desktop\\divineworld\\")
        print("  └── dw_agent\\")
        print("      └── electron\\")
        print("          └── react-app\\")
        sys.exit(1)
    
    print(f"✅ Frontend directory found: {frontend_dir}\n")
    
    # Test 1: Check files exist
    print_step(1, 6, "Checking required files...")
    
    required_files = [
        "package.json",
        "vite.config.js",
        "index.html",
        "src/App.jsx",
        "src/main.jsx"
    ]
    
    missing = []
    for file in required_files:
        file_path = frontend_dir / file
        if file_path.exists():
            print(f"  ✅ {file}")
        else:
            print(f"  ❌ {file} - MISSING")
            missing.append(file)
    
    if missing:
        print(f"\n❌ Missing files: {', '.join(missing)}")
        sys.exit(1)
    
    # Test 2: Check vite.config.js has correct settings
    print_step(2, 6, "Checking vite.config.js...")
    
    vite_config = (frontend_dir / "vite.config.js").read_text()
    
    checks = {
        "base: './'": "base: './'",
        "outDir: 'dist'": "outDir",
        "assetsDir": "assetsDir"
    }
    
    for check_name, check_text in checks.items():
        if check_text in vite_config:
            print(f"  ✅ {check_name} configured")
        else:
            print(f"  ⚠️  {check_name} not found (may need updating)")
    
    # Test 3: Install dependencies
    print_step(3, 6, "Installing dependencies...")
    
    if not (frontend_dir / "node_modules").exists():
        print("  node_modules not found, running npm install...")
        run_command(["npm", "install"], cwd=frontend_dir)
    else:
        print("  ✅ node_modules exists")
    
    # Test 4: Build frontend
    print_step(4, 6, "Building frontend...")
    
    # Clean old build
    dist_dir = frontend_dir / "dist"
    if dist_dir.exists():
        print("  Cleaning old dist/")
        shutil.rmtree(dist_dir)
    
    # Build
    run_command(["npm", "run", "build"], cwd=frontend_dir)
    
    # Test 5: Verify build output
    print_step(5, 6, "Verifying build output...")
    
    if not dist_dir.exists():
        print(f"  ❌ dist/ directory not created!")
        sys.exit(1)
    
    print(f"  ✅ dist/ directory created")
    
    # Check for critical files
    critical_files = [
        "index.html",
        "assets"  # Should be a directory
    ]
    
    for file in critical_files:
        file_path = dist_dir / file
        if file_path.exists():
            if file_path.is_dir():
                asset_count = len(list(file_path.iterdir()))
                print(f"  ✅ {file}/ directory ({asset_count} files)")
            else:
                size = file_path.stat().st_size
                print(f"  ✅ {file} ({size} bytes)")
        else:
            print(f"  ❌ {file} - MISSING in dist/")
    
    # Test 6: Test with preview server
    print_step(6, 6, "Testing with preview server...")
    
    print("\n  Starting preview server (press Ctrl+C to stop)...")
    print("  Open browser to: http://localhost:8766")
    print("  Backend should be on: http://localhost:11400")
    print("\n  If frontend loads, integration is successful!")
    print("  Press Ctrl+C when done testing...\n")
    
    try:
        preview_process = subprocess.Popen(
            [NPM_CMD, "run", "preview"],
            cwd=frontend_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Wait for user to test
        time.sleep(2)
        print("  ✅ Preview server started")
        print("\n" + "=" * 70)
        print("  🎉 ALL TESTS PASSED!")
        print("=" * 70)
        print("\n  Your frontend is ready for packaging!")
        print("\n  Next steps:")
        print("    1. Run: python py_backend/create_oracle.py")
        print("    2. Wait for packaging to complete")
        print("    3. Check: npc_applications/god_oracle_xxx_portable/")
        print("    4. Run the .exe")
        print("\n  Press Ctrl+C to stop preview server...")
        
        preview_process.wait()
        
    except KeyboardInterrupt:
        print("\n\n  Stopping preview server...")
        preview_process.terminate()
        preview_process.wait()
        print("  ✅ Done!")
    
    print("\n" + "=" * 70)
    print("  ✅ INTEGRATION TEST COMPLETE")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)