@echo off
chcp 65001 >nul
cd /d "%~dp0"
python signal.py
echo.
pause
