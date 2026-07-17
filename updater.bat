@echo off
cd /d "%~dp0"
echo Comprobando actualizaciones...
python updater.py
if errorlevel 1 (
    echo.
    echo No se pudo actualizar.
) else (
    echo.
    echo Listo.
)
pause
