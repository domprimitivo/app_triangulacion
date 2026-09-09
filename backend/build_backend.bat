@echo off
REM ============================================================================
REM  Mileforum - Compilacion del backend a ejecutable unico (PyInstaller)
REM  Ejecutar DENTRO de la carpeta backend\ en una maquina Windows con:
REM    pip install -r requirements.txt pyinstaller
REM
REM  ESTRATEGIA DE DATOS (importante):
REM  La app es LOCAL y PERSISTENTE. El Aprendiz REESCRIBE los modelos in-place y
REM  el operador EDITA los cucurucho_*.json. Por eso los datos NO se embeben en el
REM  .exe (--add-data queda en sys._MEIPASS, temporal y de solo-lectura, se borra al
REM  cerrar). En su lugar se COPIAN junto al .exe y runtime_paths.get_base_dir()
REM  los resuelve en disco (Path(sys.executable).parent cuando sys.frozen).
REM ============================================================================

echo Limpiando builds anteriores...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist mileforum_backend.spec del mileforum_backend.spec

echo.
echo Compilando Backend con PyInstaller...
pyinstaller --onefile --clean --noconfirm ^
  --name mileforum_backend ^
  --hidden-import runtime_paths ^
  --hidden-import flujo_kpis ^
  --hidden-import agora_conector ^
  --hidden-import cucurucho_embudo ^
  --hidden-import lazo_generico ^
  --hidden-import compresion_geometrica ^
  --hidden-import local_storage ^
  --collect-submodules aprendiz_motor ^
  --collect-submodules uvicorn ^
  --collect-submodules apscheduler ^
  --collect-all torch ^
  server.py

if not exist "dist\mileforum_backend.exe" (
  echo.
  echo [ERROR] La compilacion fallo: no se encontro dist\mileforum_backend.exe
  pause
  exit /b 1
)

echo.
echo Ensamblando el paquete final en dist\Mileforum ...
set "PKG=dist\Mileforum"
set "PKG_BACKEND=%PKG%\backend"
mkdir "%PKG_BACKEND%" 2>nul
mkdir "%PKG%\app" 2>nul

REM --- Ejecutable + config ---
copy /y "dist\mileforum_backend.exe" "%PKG_BACKEND%\" >nul
if exist "config.json" copy /y "config.json" "%PKG_BACKEND%\" >nul

REM --- Catalogos (config editable por el operador) junto al .exe ---
if exist "flujo"        xcopy /e /i /y "flujo"        "%PKG_BACKEND%\flujo"        >nul
if exist "aprendiz_data" xcopy /e /i /y "aprendiz_data" "%PKG_BACKEND%\aprendiz_data" >nul

REM --- Modelos (el Aprendiz los reescribe in-place) junto al .exe ---
if exist "bundles"              xcopy /e /i /y "bundles"              "%PKG_BACKEND%\bundles"              >nul
if exist "aprendiz_motor\modelos" xcopy /e /i /y "aprendiz_motor\modelos" "%PKG_BACKEND%\aprendiz_motor\modelos" >nul
if exist "data\modelos"         xcopy /e /i /y "data\modelos"         "%PKG_BACKEND%\data\modelos"         >nul

REM --- Cucurucho_*.json viven en backend.parent (get_base_dir().parent) ---
copy /y "..\cucurucho_*.json" "%PKG%\" >nul

REM --- Lanzador + carpeta para el ejecutable de Flutter ---
if exist "..\Iniciar_App.bat" copy /y "..\Iniciar_App.bat" "%PKG%\" >nul
echo Coloca aqui el ejecutable de la interfaz Flutter (mileforum_app.exe). > "%PKG%\app\_COLOCAR_FLUTTER_AQUI.txt"

echo.
echo ============================================================================
echo  Paquete listo en:  %CD%\%PKG%
echo   %PKG%\backend\mileforum_backend.exe   (+ flujo, bundles, modelos, aprendiz_data)
echo   %PKG%\cucurucho_*.json
echo   %PKG%\Iniciar_App.bat
echo   %PKG%\app\  (copia aqui mileforum_app.exe de Flutter)
echo ============================================================================
pause
