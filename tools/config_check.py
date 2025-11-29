# tools/config_check.py
"""
Command-line tool to print Divine World configuration summary
and test environment variable overrides.
"""

import os
from ai_core.config_loader import summary, get_device

if __name__ == "__main__":
    print("🌍 Divine World Configuration Inspector")
    print(f"Detected device: {get_device()}")
    summary()

    print("Environment Overrides (DW_*):")
    for k, v in os.environ.items():
        if k.startswith("DW_"):
            print(f"  {k} = {v}")
    print("\n✅ Configuration loaded successfully.\n")
