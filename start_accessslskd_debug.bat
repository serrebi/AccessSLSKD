@echo off
setlocal EnableExtensions EnableDelayedExpansion
rem Launch accessslskd with verbose debug and tee output to a rotating log.
cd /d "%~dp0"

set "ACCESS_SLSKD_DEBUG=1"
rem Keep config next to this script so we don't touch your AppData while testing
set "ACCESS_SLSKD_PORTABLE=1"
set "PYTHONUNBUFFERED=1"
set "PYTHONWARNINGS=default"

rem Use PowerShell Tee-Object to avoid file locking conflicts.
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Continue';" ^
  "$dir = (Get-Location).Path;" ^
  "$logDir = Join-Path -Path $dir -ChildPath 'debug_logs';" ^
  "New-Item -Force -ItemType Directory -Path $logDir | Out-Null;" ^
  "$ts = Get-Date -Format yyyyMMdd-HHmmss;" ^
  "$log = Join-Path -Path $logDir -ChildPath ('accessslskd-debug-' + $ts + '.log');" ^
  "Write-Host ('Logging to: ' + $log);" ^
  "$py = (Get-Command python -ErrorAction SilentlyContinue); $launcher = if ($py) { 'python' } else { 'py' };" ^
  "Write-Host ('Using ' + $launcher);" ^
  "& $launcher '-m' 'accessslskd' $args 2>&1 | Tee-Object -FilePath $log -Append" -- %*

echo.
echo Debug session ended. A log was written under: "%~dp0debug_logs"
echo.
pause
