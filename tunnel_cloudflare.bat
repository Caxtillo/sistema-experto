@echo off
cd /d "%~dp0"
title Cloudflare Tunnel

set LOG=%TEMP%\_tunnel.log
:loop
cloudflared tunnel --url http://localhost:8000 --no-autoupdate > "%LOG%" 2>&1
timeout /t 5 /nobreak >nul
goto loop
