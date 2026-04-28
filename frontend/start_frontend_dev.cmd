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

if not defined VITE_API_PROXY_TARGET set "VITE_API_PROXY_TARGET=http://%BACKEND_HOST%:%BACKEND_PORT%"
if not defined VITE_API_BASE_URL set "VITE_API_BASE_URL="
if not defined BROWSER set "BROWSER=none"
set "NO_COLOR=1"

set "NPM_CMD="
for /f "delims=" %%I in ('where npm.cmd 2^>nul') do (
  if not defined NPM_CMD set "NPM_CMD=%%I"
)
if not defined NPM_CMD if exist "C:\Program Files\nodejs\npm.cmd" set "NPM_CMD=C:\Program Files\nodejs\npm.cmd"
if not defined NPM_CMD if exist "D:\download\node\npm.cmd" set "NPM_CMD=D:\download\node\npm.cmd"
if not defined NPM_CMD (
  echo [ERROR] npm.cmd not found in PATH.
  exit /b 1
)

echo [Frontend] npm: %NPM_CMD%
echo [Frontend] URL: http://%FRONTEND_HOST%:%FRONTEND_PORT%
echo [Frontend] API proxy: %VITE_API_PROXY_TARGET%

call "%NPM_CMD%" run dev -- --host %FRONTEND_HOST% --port %FRONTEND_PORT%
exit /b %ERRORLEVEL%
