@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/2] starting web server on port 8765 ...
start "" /min "%~dp0_serve.cmd"
timeout /t 2 >nul
echo [2/2] open in browser ...
start "" http://127.0.0.1:8765/
echo.
echo Local :  http://127.0.0.1:8765/
for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /c:"IPv4"') do echo Phone :  http://%%i:8765/  ^(same WiFi^)
echo.
echo Keep this window open. Close it to stop, or press any key.
pause >nul
