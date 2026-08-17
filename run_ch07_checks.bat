@echo off
setlocal
python -m pytest -q tests\ch07
if errorlevel 1 exit /b %errorlevel%
python tools\validate_ch7_policy.py
if errorlevel 1 exit /b %errorlevel%
echo Chapter 7 checks: PASS
