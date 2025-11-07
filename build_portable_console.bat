@echo off
setlocal

REM Portable Windows build with console (for troubleshooting)
REM Produces dist\accessslskd-console.exe

where py >NUL 2>&1 || (echo Python launcher 'py' not found.& exit /b 1)

echo === Ensure deps ===
py -3 -m pip install --upgrade pip
py -3 -m pip install -r requirements.txt
py -3 -m pip install pyinstaller

echo === Verify slskd_api import ===
py -3 - <<PY
try:
    import slskd_api
    print("slskd_api:", slskd_api.__file__)
    try:
        import slskd_api.apis._types
        print("slskd_api.apis._types OK")
    except Exception as e:
        print("WARN: _types missing:", e)
except Exception as e:
    print("ERROR: cannot import slskd_api:", e)
    raise SystemExit(1)
PY
if errorlevel 1 exit /b 1

echo === Build (console) ===
py -3 -m pyinstaller ^
  --noconfirm --clean ^
  --name accessslskd-console ^
  --onefile --console ^
  --collect-submodules slskd_api ^
  --hidden-import slskd_api ^
  --hidden-import slskd_api.apis ^
  --hidden-import slskd_api.apis._types ^
  accessslskd\__main__.py

if errorlevel 1 (echo Build failed.& exit /b 1)

echo Built: dist\accessslskd-console.exe
echo Run it from a writable folder; config.json will be created next to the EXE.
endlocal
