@echo off
rem Compass Converter for PokiNative. Double-click it, or drop your Compass folder on it.
setlocal
if "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Convert-Compass.ps1"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Convert-Compass.ps1" -Compass "%~1"
)
echo.
pause
