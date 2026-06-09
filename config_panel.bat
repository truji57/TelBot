@echo off
cd /d "%~dp0"
echo Abriendo panel de configuración...
start http://localhost:8765
python config_panel.py
pause
