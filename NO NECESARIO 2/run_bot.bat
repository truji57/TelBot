@echo off
  cd /d "C:\Users\danit\Desktop\PROYECTOS\TelBot"

  REM --- ejecuta el listener ---
  python telegram_listener.py

  echo.
  echo ******* Bot detenido *******
  pause