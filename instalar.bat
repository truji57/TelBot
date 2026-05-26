@echo off
chcp 65001 >nul
echo ============================================
echo  Instalacion del Bot de Trading TelBot
echo ============================================
echo.

REM --- Verificar que Git existe ---
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git no esta instalado.
    echo Descargalo desde: https://git-scm.com
    pause
    exit /b 1
)

REM --- Clonar repositorio ---
echo Clonando repositorio...
git clone https://github.com/truji57/TelBot.git
if errorlevel 1 (
    echo.
    echo [ERROR] No se pudo clonar el repositorio.
    echo Comprueba tu conexion a internet.
    pause
    exit /b 1
)

cd TelBot

REM --- Crear .env a partir de la plantilla ---
copy .env.example .env >nul

REM --- Instalar dependencias ---
echo Instalando dependencias Python...
pip install -r requirements.txt 2>nul

echo.
echo ============================================
echo  Instalacion completada con exito
echo ============================================
echo.
echo   SIGUIENTES PASOS:
echo   1. Edita el archivo .env con TUS credenciales
echo      (Telegram API, canal de senales, etc.)
echo.
echo   2. Ejecuta:  run_bot.bat
echo.
pause
