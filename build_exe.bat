@echo off
cd /d "%~dp0"
echo Instalando PyInstaller...
pip install pyinstaller -q

echo.
echo Compilando sflow.exe...
pyinstaller --noconfirm ^
  --onefile ^
  --windowed ^
  --icon=assets/icon.ico ^
  --name=sflow ^
  --add-data "assets;assets" ^
  --add-data "dashboard/templates;dashboard/templates" ^
  --hidden-import=win32timezone ^
  --hidden-import=pywintypes ^
  app.py

echo.
if exist dist\sflow.exe (
    echo Listo! El ejecutable esta en:  dist\sflow.exe
    echo Puedes copiar dist\sflow.exe a cualquier lugar y ejecutarlo.
) else (
    echo Error durante la compilacion.
)
pause
