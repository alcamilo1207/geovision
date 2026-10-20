@echo off
chcp 65001 >nul
title Instalador de Dependencias — GeoVision U044
cd /d "%~dp0"

echo ======================================================================
echo    INSTALADOR DE DEPENDENCIAS — GEOVISION U044 (WINDOWS)
echo ======================================================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    where py >nul 2>&1
    if %errorlevel% neq 0 (
        echo [ERROR] No se encontro Python instalado.
        echo Descargue e instale Python desde https://www.python.org/downloads/
        echo (Asegurese de marcar la casilla "Add python.exe to PATH")
        echo.
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

echo Usando:
%PY_CMD% --version
echo.
echo Actualizando pip e instalando dependencias de requirements.txt...
echo.

%PY_CMD% -m pip install --upgrade pip
%PY_CMD% -m pip install -r requirements.txt

echo.
echo ======================================================================
echo    Instalacion completada con exito.
echo    Ya puede ejecutar 'INICIAR_GEOVISION.bat' para abrir la aplicacion.
echo ======================================================================
echo.
pause
