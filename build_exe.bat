@echo off
rem Build single-file exe: dist\spyglass.exe
rem Usage is identical to: python -m spyglass
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [ERROR] .venv not found. Run: python -m venv .venv
    exit /b 1
)

set "ICONFLAG=--icon icon.ico"
if not exist "%~dp0icon.ico" (
    echo [WARN] icon.ico not found, building without custom icon
    set "ICONFLAG="
)

"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    "%PY%" -m pip install pyinstaller
    if errorlevel 1 exit /b 1
)

"%PY%" -m PyInstaller ^
    --onefile ^
    --console ^
    --name spyglass ^
    --optimize 2 ^
    --clean ^
    --noconfirm ^
    %ICONFLAG% ^
    --hidden-import truststore ^
    --hidden-import winotify ^
    --exclude-module pytest ^
    --exclude-module _pytest ^
    -p . ^
    build_exe_entry.py
if errorlevel 1 exit /b 1

echo.
echo Done: dist\spyglass.exe
for %%A in (dist\spyglass.exe) do echo Size: %%~zA bytes
endlocal
