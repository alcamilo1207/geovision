@echo off
chcp 65001 >nul
title GeoVision U044 — Gemelo Digital & QRA
cd /d "%~dp0"

echo ======================================================================
echo    🏭 GEOVISION PLANT EXTRACTOR — GEMELO DIGITAL & QRA (U044)
echo ======================================================================
echo.

:: 1. Comprobar si Python está instalado
where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] No se encontro Python instalado en este sistema.
        echo.
        echo Por favor instale Python 3.10, 3.11 o 3.12 desde:
        echo https://www.python.org/downloads/
        echo.
        echo IMPORTANTE: Al instalar, marque la casilla "Add python.exe to PATH".
        echo.
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

echo [1/3] Python detectado correctamente:
%PY_CMD% --version
echo.

:: 2. Verificar dependencias principales (FastAPI, Uvicorn, Pandas)
echo [2/3] Verificando dependencias del sistema...
%PY_CMD% -c "import fastapi, uvicorn, pandas" >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo Dependencias faltantes detectadas. Instalando automaticamente...
    echo Esto solo tardara un momento en la primera ejecucion...
    echo.
    %PY_CMD% -m pip install --upgrade pip
    %PY_CMD% -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo.
        echo [ADVERTENCIA] Ocurrio un error al instalar algunas librerias.
        echo Intentando continuar con la ejecucion...
    )
) else (
    echo Dependencias verificadas con exito.
)
echo.

:: 3. Iniciar servidor y abrir aplicacion en el navegador
echo [3/3] Iniciando servidor y abriendo la aplicacion en su navegador...
echo URL Local: http://localhost:8080
echo.
echo Presione CTRL + C en esta ventana para detener la aplicacion cuando termine.
echo ======================================================================
echo.

%PY_CMD% run_server.py

pause
