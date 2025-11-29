#!/bin/bash
# Example environment variable overrides for Divine World AI runtime
export DW_DEVICE=cuda
export DW_PRECISION=bfloat16
export DW_LM=gpt2-medium
export DW_WM=divine_world_dreamer_v1
export DW_LOG_LEVEL=DEBUG
export DW_LOG_DIR=data/logs
export DW_SAFE_MODE=false
python tools/config_check.py
