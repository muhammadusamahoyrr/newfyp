@echo off
REM Stops the AttorneyAI demo: the backend gracefully (so its buffered data is
REM written), then the frontend on port 3001. Mongo is left running; it is
REM harmless and makes the next start faster (it stops when the laptop shuts down).

setlocal
set "ROOT=%~dp0"

echo Stopping the backend...
pushd "%ROOT%backend"
"%ROOT%backend\venv\Scripts\python.exe" scripts\serve.py stop < nul
popd

echo Stopping the frontend (port 3001)...
powershell -NoProfile -Command ^
  "Get-NetTCPConnection -State Listen -LocalPort 3001 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

echo Done.
endlocal
pause
