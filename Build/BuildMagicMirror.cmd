@echo off
setlocal
cd /d "%~dp0.."

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

%PYTHON% -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --icon "resources\icon.ico" ^
  --hidden-import "widget_manager" ^
  --name "MagicMirror" ^
  --add-data "resources;resources" ^
  "Main.py"

endlocal
