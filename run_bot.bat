@echo off
cd /d "%~dp0"

REM Comprobar si hay actualizaciones disponibles
python updater.py --check
if %ERRORLEVEL% EQU 1 (
    echo.
    echo ========================================
    echo   Hay actualizaciones disponibles
    echo ========================================
    echo.
    python updater.py
    if errorlevel 1 (
        echo.
        echo Error al actualizar, continuando de todas formas...
        echo.
    )
)

python telegram_listener.py

echo.
echo ******* Bot detenido *******
pause