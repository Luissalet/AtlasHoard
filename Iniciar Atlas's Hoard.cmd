@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
  py -3 -m venv --without-pip venv
  if errorlevel 1 exit /b 1
)
"venv\Scripts\python.exe" -m atlas_hoard
if errorlevel 1 pause
