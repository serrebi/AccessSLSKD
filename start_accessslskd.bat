@echo off
setlocal
cd /d "%~dp0"

REM Prefer 'python' (pythoncore install) to avoid MS Store isolation issues
where python >nul 2>nul
if %errorlevel%==0 (
  python -m accessslskd %*
  goto :eof
)

REM Fallback to 'py' launcher
where py >nul 2>nul
if %errorlevel%==0 (
  echo Using 'py' launcher. If you see import errors for slskd_api.apis._types, install slskd-api into this interpreter:
  echo   py -m pip install --upgrade slskd-api
  py -m accessslskd %*
  goto :eof
)

echo Could not find Python on PATH. Please install Python 3 and try again.
pause
