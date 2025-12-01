@echo off
rem Example environment variable overrides for Divine World AI runtime
set DW_DEVICE=cuda
set DW_PRECISION=bfloat16
set DW_LM=gpt2-medium
set DW_WM=divine_world_dreamer_v1
set DW_LOG_LEVEL=DEBUG
set DW_LOG_DIR=data\logs
set DW_SAFE_MODE=false
python tools\config_check.py
pause
