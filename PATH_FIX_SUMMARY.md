# Path Fix Summary

## Issue
The configuration was calculating paths incorrectly, resulting in nested `ai_core/ai_core` path lookups:
```
Config validation failed: ai_core directory not found: /home/devlord/divine-world-core/py_backend/ai_core/ai_core
```

## Root Cause
Both `py_backend/config.py` and `py_backend/ai_core/config.py` were calculating paths relative to `__file__` incorrectly:
```python
# WRONG:
HOME = Path(__file__).parent.parent.parent
BASE_DIR = Path(__file__).parent.parent
PY_BACKEND_DIR = Path(__file__).parent
AI_CORE_DIR = PY_BACKEND_DIR / "ai_core"
```

For `py_backend/ai_core/config.py`:
- `__file__` = `/home/devlord/divine-world-core/py_backend/ai_core/config.py`
- `.parent` = `/home/devlord/divine-world-core/py_backend/ai_core/`
- `.parent.parent` = `/home/devlord/divine-world-core/py_backend/`
- `.parent.parent.parent` = `/home/devlord/divine-world-core/`

Then `PY_BACKEND_DIR / "ai_core"` would be:
- `/home/devlord/divine-world-core/py_backend/` ← WRONG, should be ai_core dir directly

## Solution
Fixed path calculations in both config files to properly reflect the file hierarchy:

### py_backend/ai_core/config.py
```python
# CORRECT:
AI_CORE_DIR = Path(__file__).parent              # .../py_backend/ai_core/
PY_BACKEND_DIR = Path(__file__).parent.parent    # .../py_backend/
BASE_DIR = PY_BACKEND_DIR.parent                 # .../divine-world-core/
HOME = BASE_DIR                                   # .../divine-world-core/
```

### py_backend/config.py
```python
# CORRECT:
PY_BACKEND_DIR = Path(__file__).parent            # .../py_backend/
BASE_DIR = PY_BACKEND_DIR.parent                  # .../divine-world-core/
HOME = BASE_DIR                                    # .../divine-world-core/
AI_CORE_DIR = PY_BACKEND_DIR / "ai_core"         # .../py_backend/ai_core/
```

## Files Updated
1. ✅ `py_backend/ai_core/config.py` - Fixed path calculations
2. ✅ `py_backend/config.py` - Fixed path calculations
3. ✅ `build_agent.spec` - Updated to use correct paths and `agent.py` instead of `agent_standalone.py`
4. ✅ `DEPLOYMENT_CHECKLIST.md` - Updated Python version to 3.13
5. ✅ `DEPLOYMENT_GUIDE.md` - Updated Python version to 3.13

## Verification Results
```
✅ Config validation PASSED
✅ AI_CORE_DIR: /home/devlord/divine-world-core/py_backend/ai_core
✅ PY_BACKEND_DIR: /home/devlord/divine-world-core/py_backend
✅ BASE_DIR: /home/devlord/divine-world-core
✅ All core classes imported successfully
✅ Personality system working correctly
✅ Executable generator ready
✅ All Python files compile successfully
```

## Status
**✅ PATH ISSUE FIXED - SYSTEM OPERATIONAL**

The nested path lookup error is resolved. Config validation now passes without errors, and all modules import correctly.
