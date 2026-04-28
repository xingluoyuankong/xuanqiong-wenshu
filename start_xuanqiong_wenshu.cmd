@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

set "BACKEND_HOST=%XUANQIONG_WENSHU_BACKEND_HOST%"
if not defined BACKEND_HOST set "BACKEND_HOST=127.0.0.1"

set "BACKEND_PORT=%XUANQIONG_WENSHU_BACKEND_PORT%"
if not defined BACKEND_PORT set "BACKEND_PORT=8013"

set "FRONTEND_HOST=%XUANQIONG_WENSHU_FRONTEND_HOST%"
if not defined FRONTEND_HOST set "FRONTEND_HOST=127.0.0.1"

set "FRONTEND_PORT=%XUANQIONG_WENSHU_FRONTEND_PORT%"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5174"

set "XUANQIONG_WENSHU_BACKEND_HOST=%BACKEND_HOST%"
set "XUANQIONG_WENSHU_BACKEND_PORT=%BACKEND_PORT%"
set "XUANQIONG_WENSHU_FRONTEND_HOST=%FRONTEND_HOST%"
set "XUANQIONG_WENSHU_FRONTEND_PORT=%FRONTEND_PORT%"

echo ========================================
echo Xuanqiong Wenshu - Starter
echo ========================================
echo Backend:  http://%BACKEND_HOST%:%BACKEND_PORT%
echo Frontend: http://%FRONTEND_HOST%:%FRONTEND_PORT%
echo.

echo [1/4] Cleaning old processes (%BACKEND_PORT%, %FRONTEND_PORT%)...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort %BACKEND_PORT%,%FRONTEND_PORT% -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }" 2>nul

set "BACKEND=%ROOT%\backend"
set "FRONTEND=%ROOT%\frontend"

if not exist "%BACKEND%\start_backend.cmd" (
  echo [ERROR] Missing backend\start_backend.cmd
  pause
  exit /b 1
)

if not exist "%FRONTEND%\start_frontend_dev.cmd" (
  echo [ERROR] Missing frontend\start_frontend_dev.cmd
  pause
  exit /b 1
)

echo [2/5] Starting local MySQL...
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\tools\start_local_mysql.ps1"
if errorlevel 1 (
  echo [ERROR] Local MySQL startup failed
  pause
  exit /b 1
)

echo [3/5] Starting backend...
start "XuanqiongWenshu_Backend" cmd /d /c call "%BACKEND%\start_backend.cmd"

echo [4/5] Starting frontend...
start "XuanqiongWenshu_Frontend" cmd /d /c call "%FRONTEND%\start_frontend_dev.cmd"

echo [5/5] Waiting for services...
set /a MAX_WAIT=60
set /a COUNT=0
:wait_loop
powershell -NoProfile -Command "try { $r = Invoke-RestMethod 'http://%BACKEND_HOST%:%BACKEND_PORT%/api/health' -TimeoutSec 1; if($r.status -eq 'healthy'){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  set /a COUNT+=1
  if %COUNT% geq %MAX_WAIT% goto timeout
  powershell -NoProfile -Command "Start-Sleep -Seconds 1" >nul 2>&1
  goto wait_loop
)

echo.
echo ========================================
echo Services started successfully.
echo ========================================
echo URL: http://%FRONTEND_HOST%:%FRONTEND_PORT%/
echo API: http://%BACKEND_HOST%:%BACKEND_PORT%
echo.
start "" "http://%FRONTEND_HOST%:%FRONTEND_PORT%/"
goto end

:timeout
echo.
echo [WARN] Services may still be starting. Check logs manually.
echo.
pause

:end
exit /b 0
