@echo off
setlocal

REM Portable Windows build for accessslskd
REM - Produces dist\accessslskd.exe
REM - Config (config.json) is saved next to the EXE

REM Choose Python launcher
set "LAUNCHER="
where python >NUL 2>&1 && set "LAUNCHER=python"
if "%LAUNCHER%"=="" (
  where py >NUL 2>&1 && set "LAUNCHER=py -3"
)
if "%LAUNCHER%"=="" (
  echo Could not find Python. Install Python 3.10+ and try again.
  exit /b 1
)
echo Using: %LAUNCHER%

echo === Upgrading pip and installing deps ===
%LAUNCHER% -m pip install --upgrade pip
%LAUNCHER% -m pip install -r requirements.txt
%LAUNCHER% -m pip install pyinstaller

echo === Verifying slskd_api is importable ===
set "_TMPPY=%TEMP%\\verify_slskd_api_%RANDOM%.py"
> "%_TMPPY%" echo import sys
>>"%_TMPPY%" echo try:
>>"%_TMPPY%" echo ^    import slskd_api
>>"%_TMPPY%" echo ^    print("slskd_api:", slskd_api.__file__)
>>"%_TMPPY%" echo ^    try:
>>"%_TMPPY%" echo ^        import slskd_api.apis._types as _t
>>"%_TMPPY%" echo ^        print("slskd_api.apis._types import OK")
>>"%_TMPPY%" echo ^    except Exception as e:
>>"%_TMPPY%" echo ^        print("WARN: slskd_api.apis._types not present:", e)
>>"%_TMPPY%" echo except Exception as e:
>>"%_TMPPY%" echo ^    print("ERROR: cannot import slskd_api:", e)
>>"%_TMPPY%" echo ^    raise SystemExit(1)
%LAUNCHER% "%_TMPPY%"
set "_PYRC=%ERRORLEVEL%"
del /q "%_TMPPY%" >nul 2>nul
if not "%_PYRC%"=="0" exit /b %_PYRC%

echo === Building portable EXE (onefile) ===
%LAUNCHER% -m PyInstaller ^
  --noconfirm --clean ^
  --name accessslskd ^
  --windowed ^
  --onefile ^
  --collect-submodules slskd_api ^
  --hidden-import slskd_api ^
  --hidden-import slskd_api.apis ^
  --hidden-import slskd_api.apis._types ^
  accessslskd\__main__.py

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Build completed.
echo Portable EXE: dist\accessslskd.exe
echo Config file (config.json) will be created next to the EXE on first run.
echo.
endlocal
