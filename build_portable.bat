@echo off
setlocal

REM Portable Windows build for accessslskd
REM - Produces dist\accessslskd.exe
REM - Config (config.json) is saved next to the EXE

where py >NUL 2>&1
if errorlevel 1 (
  echo Python launcher 'py' not found. Install Python 3.10+ and try again.
  exit /b 1
)

echo === Upgrading pip and installing deps ===
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 -m pip install pyinstaller

echo === Verifying slskd_api is importable ===
py -3 - <<PY
import sys
try:
    import slskd_api
    print("slskd_api:", slskd_api.__file__)
    try:
        import slskd_api.apis._types as _t
        print("slskd_api.apis._types import OK")
    except Exception as e:
        print("WARN: slskd_api.apis._types not present:", e)
except Exception as e:
    print("ERROR: cannot import slskd_api:", e)
    raise SystemExit(1)
PY
if errorlevel 1 exit /b 1

echo === Building portable EXE (onefile) ===
py -3 -m pyinstaller ^
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
