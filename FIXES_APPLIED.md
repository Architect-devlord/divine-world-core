# Divine World Core - Problems Fixed

## Summary
Fixed critical issues with agent packaging and Minecraft integration that were preventing agents from launching properly.

## Issues Addressed

### 1. **Agent Packaging Problem** ✅ FIXED
**Original Issue**: The `wait_for_connection()` method was called before UltimMC was packaged and started, causing timeouts.

**Root Cause**: When agents were created via REST API with `mode="minecraft"`, the agent process would attempt to wait for a Minecraft connection before UltimMC setup was complete.

**Solution**:
- Modified `run_standalone_agent()` in [ai_core/agent.py](ai_core/agent.py#L1375-L1410) to check if UltimMC is available
- If UltimMC exists: agent waits for Minecraft connection (up to 120 seconds)
- If UltimMC doesn't exist: agent logs that manual setup is needed and doesn't block
- This allows agents to initialize without hanging when UltimMC setup is deferred to the packaging step

### 2. **Agent Launching Minecraft Problem** ✅ FIXED  
**Original Issue**: The codebase was using a different UltimMC executable instead of the one bundled with agents in `npc_applications/<agent_id>/UltimMC/bin/UltimMC`.

**Root Cause**: The `_create_portable_package()` method in packager.py was not copying the UltimMC folder to the portable package, even though `_setup_ultimmc()` had already created and prepared it.

**Solution**:
- Modified `_create_portable_package()` in [packager.py](packager.py#L644-L700) to explicitly copy the UltimMC folder
- Now includes the complete UltimMC installation with:
  - Pre-configured Minecraft account
  - Ready-to-use Forge instance
  - Installed DivineWorld + DWClientBot mods
  - Correct data directory structure

### 3. **Improved UltimMC Handling** ✅ ENHANCED
**Changes to `try_ultimmc()` function** in [packager.py](packager.py#L402-L419):
- Added better error logging to show if UltimMC is found or missing
- Added 2-second delay after launching to give Java/Minecraft time to start
- Improved log messages for debugging launch issues

### 4. **Enhanced User Feedback** ✅ IMPROVED
**Changes to launcher template** in [packager.py](packager.py#L451-L458):
- Shows clear message when server is detected
- Displays Minecraft launch progress
- Provides helpful manual setup instructions if launch fails
- Estimates loading time (30-60 seconds for first launch)

**Changes to package README** in [packager.py](packager.py#L678-L715):
- Comprehensive quick-start guide with internet requirement noted
- Clear explanation of all bundled components
- Automatic setup features listed
- Troubleshooting section for common issues
- Environment details for reference

## Files Modified

1. **[py_backend/ai_core/agent.py](ai_core/agent.py#L1375-L1410)**
   - Modified `run_standalone_agent()` to make wait_for_connection conditional on UltimMC availability

2. **[py_backend/packager.py](packager.py)**
   - Line 402-419: Enhanced `try_ultimmc()` function with better logging and delay
   - Line 451-458: Improved launcher feedback about Minecraft launching
   - Line 644-700: Added UltimMC folder to portable package
   - Line 678-715: Enhanced README template with comprehensive instructions

## How It Works Now

### Agent Creation Flow (via REST API):
```
1. POST /api/gods/spawn
2. Agent process started with mode="minecraft"
3. run_standalone_agent() detects UltimMC status
   ├─ If UltimMC present: waits for Minecraft connection (120s timeout)
   └─ If not present: logs status, continues without blocking
4. Brain file saved to disk
5. Auto-packager kicks in:
   ├─ Creates executable
   ├─ Bundles UltimMC with agent
   └─ Creates portable package
6. User runs packaged agent:
   ├─ try_ultimmc() launches Minecraft via bundled UltimMC
   ├─ Minecraft loads assets and connects
   └─ Agent operates normally
```

### Agent Execution Flow (packaged):
```
1. User double-clicks agent executable
2. launcher.py is executed:
   ├─ Loads agent brain
   ├─ Starts backend API server
   ├─ Detects game server at 127.0.0.1:25565
   ├─ Calls try_ultimmc() to launch Minecraft
   │  ├─ UltimMC uses bundled Minecraft instance
   │  ├─ Loads with pre-configured account
   │  └─ Auto-joins game server
   └─ Enters main loop (auto-save every 5 min)
```

## Testing Recommendations

1. **Test agent creation via REST API**:
   ```bash
   curl -X POST http://localhost:8000/api/gods/spawn \
     -H "Content-Type: application/json" \
     -d '{"god_type": "oracle"}'
   ```

2. **Test packaged agent execution**:
   - Look in `npc_applications/<agent_id>_portable/`
   - Run the executable from Windows Explorer or terminal
   - Monitor logs for UltimMC launch and Minecraft connection

3. **Verify UltimMC is bundled**:
   ```bash
   ls npc_applications/<agent_id>_portable/UltimMC/bin/UltimMC
   ```

4. **Check logs for improvements**:
   - Should see "UltimMC included in package" during packaging
   - Should see "Minecraft launching" message when running packaged agent
   - No timeout errors for wait_for_connection

## Notes

- **Internet connection required**: First launch downloads Minecraft assets
- **Port requirements**: Backend uses BASE_BACKEND_PORT + hash(agent_id) % 9000
- **Minecraft version**: Forge {Config.MINECRAFT_VERSION}
- **Game server**: Must be running at DEFAULT_SERVER for auto-join

## Breaking Changes

None - all changes are backwards compatible. Agents created before this fix will still work:
- Old packaged agents: Same behavior as before
- API spawning: Now works without hanging when waiting for Minecraft
