@echo off
cd /d "%~dp0"
echo Abriendo panel de configuración...
start http://localhost:8080
python config_panel.py
pause
