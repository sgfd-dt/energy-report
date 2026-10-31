@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [1/3] local web server on port 8765 (minimized window)
start "" /min "%~dp0_serve.cmd"
timeout /t 2 >nul
:loop
echo.
echo [2/3] connecting public tunnel ... wait for a line like:
echo        Forwarding HTTP traffic from https://xxxx.serveousercontent.com
echo [3/3] the free tunnel dies about every hour; this window auto-reconnects
echo        and prints a NEW address each time. Keep this window open.
echo ------------------------------------------------------------
ssh -T -o StrictHostKeyChecking=no -o UserKnownHostsFile="%TEMP%\serveo_hosts" -R 80:127.0.0.1:8765 serveo.net
echo.
echo tunnel closed, reconnecting in 5 seconds ...
timeout /t 5 >nul
goto loop
