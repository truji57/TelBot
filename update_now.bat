@echo off
cd /d "%~dp0"
echo Comprobando actualizaciones...
if exist .update_cache del .update_cache
python updater.py
if errorlevel 1 (
    echo.
    echo [update_now] Error en la actualizacion.
    pause
    exit /b 1
)
echo.
echo [update_now] Proceso completado.
pause
