@echo off
setlocal
call "%~dp0..\build_windows.cmd" --run
set "MM_BUILD_EXIT=%ERRORLEVEL%"
if /i not "%~1"=="--no-pause" pause
exit /b %MM_BUILD_EXIT%
