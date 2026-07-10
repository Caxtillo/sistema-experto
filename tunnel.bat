@echo off
:loop
echo [%date% %time%] Iniciando tunnel...
node "%APPDATA%\npm\node_modules\localtunnel\bin\lt.js" --port 8000 --subdomain experto-cond-2026
echo [%date% %time%] Tunnel caido, reiniciando en 3 segundos...
timeout /t 3 >nul
goto loop
