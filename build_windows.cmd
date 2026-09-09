@echo off
setlocal
cd /d "%~dp0"

set "MM_PYTHON=%CD%\.venv\Scripts\python.exe"
rem Keep build discovery and caches independent of global Python installations.
set "PYTHONNOUSERSITE=1"
set "PYTHONUSERBASE=%CD%\.cache\python-user"
set "PYINSTALLER_CONFIG_DIR=%CD%\.cache\pyinstaller\cache"
if exist "%MM_PYTHON%" goto dependencies

echo Creating the project Python environment...
where py >nul 2>&1
if errorlevel 1 (
  python -m venv ".venv"
) else (
  py -3 -m venv ".venv"
)
if errorlevel 1 goto failed

:dependencies
echo Checking application and build dependencies...
"%MM_PYTHON%" -m pip install --disable-pip-version-check -r "requirements-build.txt"
if errorlevel 1 goto failed

echo Building MagicMirror. This may take a few minutes...
"%MM_PYTHON%" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --onedir ^
  --windowed ^
  --workpath ".cache\pyinstaller\work" ^
  --specpath ".cache\pyinstaller" ^
  --distpath ".cache\pyinstaller\dist" ^
  --icon "%CD%\resources\icon.ico" ^
  --hidden-import "widget_manager" ^
  --name "MagicMirror" ^
  --add-data "%CD%\resources\icon.png;resources" ^
  --add-data "%CD%\resources\icon.ico;resources" ^
  --add-data "%CD%\resources\ui;resources\ui" ^
  "Main.py"
if errorlevel 1 goto failed

rem Copy from staging without deleting existing config, profiles, or templates.
robocopy ".cache\pyinstaller\dist\MagicMirror" "dist\MagicMirror" /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto failed

echo.
echo Build complete: "%CD%\dist\MagicMirror\MagicMirror.exe"
if /i "%~1"=="--run" (
  echo Opening MagicMirror with the project configuration...
  rem Robocopy returns 1 for a successful copy; clear it before START.
  "%ComSpec%" /c exit 0
  start "" /D "%CD%" "%CD%\dist\MagicMirror\MagicMirror.exe"
  if errorlevel 1 goto failed
)
exit /b 0

:failed
echo.
echo Build failed. See the error above. Close any running MagicMirror app before rebuilding.
exit /b 1
