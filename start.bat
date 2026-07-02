@echo off
title Sistema Experto - Activos Criticos
echo ============================================
echo  SISTEMA EXPERTO - GESTION DE ACTIVOS
echo  IIoT + Logica Difusa
echo ============================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado.
    echo Instalelo desde https://www.python.org/
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Instalando dependencias...
pip install -r requirements.txt >nul 2>&1

echo Iniciando servidor...
echo.
echo Abra su navegador en: http://localhost:8000
echo.
echo Presione CTRL+C para detener el servidor.
echo ============================================
python app.py

pause
