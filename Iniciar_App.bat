@echo off
title Mileforum - Lanzador (Aprendiz Engine)
setlocal

REM ============================================================================
REM  Orquesta el arranque y cierre de:
REM    1) backend\mileforum_backend.exe  (FastAPI/Uvicorn en 127.0.0.1:8001)
REM    2) app\mileforum_app.exe          (interfaz Flutter)
REM  Al cerrar la interfaz, mata el proceso del backend.
REM  Colocar este .bat en la raiz del paquete, junto a backend\ , app\ y los
REM  cucurucho_*.json (que viven en backend.parent = esta carpeta).
REM ============================================================================

set "BACKEND_EXE=%~dp0backend\mileforum_backend.exe"
set "FLUTTER_EXE=%~dp0app\mileforum_app.exe"
set "BACKEND_NAME=mileforum_backend.exe"
set "HEALTH_URL=http://127.0.0.1:8001/api/"

if not exist "%BACKEND_EXE%" (
  echo [ERROR] No se encontro el backend: %BACKEND_EXE%
  pause
  exit /b 1
)

echo Iniciando servicios del backend...
start /min "" "%BACKEND_EXE%"

echo Esperando a que el backend levante (127.0.0.1:8001)...
set /a INTENTOS=0
:ESPERAR
set /a INTENTOS+=1
powershell -NoProfile -Command "try{(Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%HEALTH_URL%')|Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if %errorlevel%==0 goto LISTO
if %INTENTOS% GEQ 30 goto TIMEOUT
timeout /t 1 /nobreak >nul
goto ESPERAR

:TIMEOUT
echo [AVISO] El backend no respondio a tiempo; se intenta abrir la interfaz igualmente.

:LISTO
echo Backend listo. Iniciando interfaz...
if not exist "%FLUTTER_EXE%" (
  echo [ERROR] No se encontro la interfaz Flutter: %FLUTTER_EXE%
  echo Cerrando backend...
  taskkill /IM "%BACKEND_NAME%" /F >nul 2>&1
  pause
  exit /b 1
)

REM /wait: el script se bloquea aqui hasta que el operador cierra la interfaz
start /wait "" "%FLUTTER_EXE%"

echo Interfaz cerrada. Deteniendo backend...
taskkill /IM "%BACKEND_NAME%" /F >nul 2>&1

endlocal
exit
