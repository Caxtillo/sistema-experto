@echo off
cd /d "%~dp0"
title Sistema Experto

echo Matando procesos anteriores...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000"') do taskkill /F /PID %%a 2>nul
taskkill /F /IM "cloudflared.exe" 2>nul
timeout /t 2 /nobreak >nul

:: Limpia log del tunnel anterior
del "%TEMP%\_tunnel.log" 2>nul

:: Tunnel en background (minimizado)
start /min "tunnel" cmd /c tunnel_cloudflare.bat

:: Espera a que cloudflared genere la URL
echo Esperando tunnel...
set TUNNEL_URL=
for /l %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    for /f "usebackq tokens=*" %%a in (`powershell -Command "if(Test-Path \"$env:TEMP\_tunnel.log\"){$c=Get-Content \"$env:TEMP\_tunnel.log\" -ErrorAction SilentlyContinue;foreach($l in $c){if($l -match 'https://([a-z0-9-]+)\.trycloudflare\.com'){$matches[0];break}}}"`) do set TUNNEL_URL=%%a
    if defined TUNNEL_URL goto :show
)

:show
cls
echo ========================================
echo  Servidor local: http://localhost:8000
if defined TUNNEL_URL (
    echo  Tunnel URL:    %TUNNEL_URL%
) else (
    echo  Tunnel:        (revisa %%TEMP%%\_tunnel.log)
)
echo ----------------------------------------
echo  Para salir: CTRL+C en esta ventana
echo ========================================
echo.

:: Uvicorn en primer plano (misma ventana)
python3.13 -m uvicorn app:app --host 0.0.0.0 --port 8000 --log-level warning

:: Al cerrar uvicorn, mata el tunnel
taskkill /F /IM "cloudflared.exe" 2>nul 1>nul
