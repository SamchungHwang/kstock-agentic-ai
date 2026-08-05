@echo off
setlocal
cd /d %~dp0
chcp 65001 >nul
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
set PYTHONUNBUFFERED=1
python run_cli.py %*
