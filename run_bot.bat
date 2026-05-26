@echo off
  cd /d "%~dp0"

  REM === AUTO-UPDATE via GitHub ===
  if exist updater.py (
      python updater.py
      if errorlevel 1 (
          echo.
          echo [run_bot] Error en actualizacion, continuando de todas formas...
          echo.
      )
  )

  REM === Ejecutar bot principal ===
  python telegram_listener.py

  echo.
  echo ******* Bot detenido *******
  pause