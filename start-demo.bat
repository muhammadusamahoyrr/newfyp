@echo off
REM Starts everything the AttorneyAI demo needs, in order:
REM   1. the local Mongo replica set (port 27018)
REM   2. the backend on the LOCAL demo overlay (port 8000) - never the hosted .env DB
REM   3. the frontend (port 3001) in its own window
REM then waits until both answer and opens the app in the browser.
REM Double-click it, or run it from any folder.
REM
REM   start-demo.bat        PRODUCTION frontend (the default, for the demo)
REM   start-demo.bat dev    DEV frontend (npm run dev, for writing code)
REM
REM Why production: dev mode compiles each page on its first visit and runs
REM React's development build, which renders everything twice. Measured on
REM 2026-11-22 over 8 section switches: the page froze 2184 ms in dev and
REM 0 ms in production. The production build goes to frontend\.next-build
REM (NEXT_DIST_DIR, see next.config.js), so it never clashes with a dev
REM server's .next folder. It is rebuilt only when code or config is newer
REM than the last build.

setlocal
set "ROOT=%~dp0"
set "PY=%ROOT%backend\venv\Scripts\python.exe"
set "MODE=prod"
if /i "%~1"=="dev" set "MODE=dev"
set "NEXT_TELEMETRY_DISABLED=1"
if /i not "%MODE%"=="dev" set "NEXT_DIST_DIR=.next-build"

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
echo [3/3] Frontend (http://localhost:3001, %MODE% mode)...
call :listening 3001
if not errorlevel 1 (
    echo     already running - left as it is.
    echo     To switch between dev and production, run stop-demo.bat first.
    goto :frontend_done
)
if /i "%MODE%"=="dev" goto :frontend_dev
call :build_if_needed
if errorlevel 1 (
    echo     The production build failed - see the messages above.
    echo     The dev version still works:  start-demo.bat dev
    endlocal
    pause
    exit /b 1
)
start "AttorneyAI frontend" /D "%ROOT%frontend" cmd /k npx next start -p 3001
echo     started in a new window (production build).
goto :frontend_done
:frontend_dev
start "AttorneyAI frontend (dev)" /D "%ROOT%frontend" cmd /k npm run dev
echo     started in a new window (dev mode).
:frontend_done

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
REM first click on every page slow, so the main ones are opened once now. In
REM production they are already built and this takes a few seconds.
echo Warming up the main pages...
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

REM errorlevel 0 when the production build in frontend\.next-build is current
REM (or was just rebuilt), 1 when the build failed. "Current" means nothing the
REM build reads - src, public, next.config.js, package.json, package-lock.json,
REM .env.local (NEXT_PUBLIC_* values are fixed at build time) - is newer.
:build_if_needed
pushd "%ROOT%frontend"
powershell -NoProfile -Command "$b='.next-build\BUILD_ID'; if (-not (Test-Path $b)) { exit 1 }; $t=(Get-Item $b).LastWriteTimeUtc; $f=@(Get-ChildItem src,public -Recurse -File -ErrorAction SilentlyContinue) + @(Get-Item next.config.js,package.json,package-lock.json,.env.local -ErrorAction SilentlyContinue); if ($f | Where-Object { $_.LastWriteTimeUtc -gt $t } | Select-Object -First 1) { exit 1 }; exit 0"
if not errorlevel 1 (
    echo     production build is up to date.
    popd
    exit /b 0
)
echo     building the production version - about 1-2 minutes, only after code changes...
call npx next build
set "BUILD_RC=%errorlevel%"
popd
exit /b %BUILD_RC%

REM errorlevel 0 when something already listens on the port, 1 when free.
:listening
powershell -NoProfile -Command "if (Get-NetTCPConnection -State Listen -LocalPort %1 -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
exit /b %errorlevel%
