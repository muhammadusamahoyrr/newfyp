@echo off
REM Starts everything the AttorneyAI demo needs, in order:
REM   1. the local Mongo replica set (port 27018)
REM   2. the backend on the LOCAL demo overlay (port 8000) - never the hosted .env DB
REM   3. the frontend (port 3001) in its own window
REM then waits until both answer and opens the app in the browser.
REM Double-click it, or run it from any folder.

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%backend\venv\Scripts\python.exe"

echo.
echo [1/3] Starting Mongo (127.0.0.1:27018)...
pushd "%ROOT%backend"
"%PY%" scripts\dev_mongo_replset.py < nul
if errorlevel 1 (
    echo     Mongo did not start. See the message above.
    popd
    pause
    exit /b 1
)

echo.
echo [2/3] Backend (http://127.0.0.1:8000, demo overlay)...
call :listening 8000
if errorlevel 1 (
    "%PY%" scripts\serve.py start --env-overlay .env.analyzer-demo.local < nul
) else (
    echo     already running - left as it is.
)
popd

echo.
echo [3/3] Frontend (http://localhost:3001)...
call :listening 3001
if errorlevel 1 (
    start "AttorneyAI frontend" /D "%ROOT%frontend" cmd /k npm run dev
    echo     started in a new window.
) else (
    echo     already running - left as it is.
)

echo.
echo Waiting for the backend and the frontend to answer (first start can take a few minutes)...
powershell -NoProfile -Command ^
  "$ok=$false; for($i=0;$i -lt 120;$i++){" ^
  "  try{$b=(Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 'http://127.0.0.1:8000/health' -ErrorAction Stop).StatusCode}catch{$b=$_.Exception.Response.StatusCode.value__};" ^
  "  try{$f=(Invoke-WebRequest -UseBasicParsing -TimeoutSec 20 'http://localhost:3001/login' -ErrorAction Stop).StatusCode}catch{$f=0};" ^
  "  if($b -and $f -eq 200){$ok=$true;break}; Start-Sleep -Seconds 5 };" ^
  "if($ok){Write-Host 'Ready: http://localhost:3001'; exit 0}else{Write-Host 'Still starting - check backend\serve.log and the frontend window.'; exit 1}"

if errorlevel 1 goto :done_wait

REM Dev mode compiles each page the first time it is opened, which made the
REM first click on every page slow. Compile the main ones now, before the demo.
echo Warming up the main pages (one-time, about a minute)...
powershell -NoProfile -Command ^
  "$pages='/','/login','/dashboard','/chat','/intake','/appointments','/tracking','/documents','/lawyers','/lawyer','/lawyer/appointments','/lawyer/cases','/lawyer/clients','/lawyer/ai-assistant','/lawyer/doc-automation','/lawyer/documents','/lawyer/vault';" ^
  "foreach($p in $pages){ try{ Invoke-WebRequest -UseBasicParsing -TimeoutSec 300 ('http://localhost:3001'+$p) | Out-Null; Write-Host ('  ready '+$p) }catch{ Write-Host ('  skipped '+$p) } }"

start "" "http://localhost:3001/login"
:done_wait

echo.
echo Done. To stop everything, run stop-demo.bat.
endlocal
pause
exit /b 0

REM errorlevel 0 when something already listens on the port, 1 when free.
:listening
powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort %1 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
exit /b %errorlevel%
