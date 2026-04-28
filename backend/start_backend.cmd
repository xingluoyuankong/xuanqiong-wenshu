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

set "PYTHON_EXE="
if exist "%ROOT%\.venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%ROOT%\venv\Scripts\python.exe" set "PYTHON_EXE=%ROOT%\venv\Scripts\python.exe"
if not defined PYTHON_EXE (
  echo [ERROR] Missing backend virtualenv: %ROOT%\.venv\Scripts\python.exe
  exit /b 1
)

set "RUN_LOG_DIR=%XUANQIONG_WENSHU_LOG_DIR%"
if not defined RUN_LOG_DIR set "RUN_LOG_DIR=%LOG_DIR%"
if not defined RUN_LOG_DIR set "RUN_LOG_DIR=%ROOT%\logs"

if not defined LOGGING_LEVEL set "LOGGING_LEVEL=INFO"
if not defined CONSOLE_LOGGING_LEVEL set "CONSOLE_LOGGING_LEVEL=WARNING"

set "UVICORN_LOG_LEVEL=%XUANQIONG_WENSHU_UVICORN_LOG_LEVEL%"
if not defined UVICORN_LOG_LEVEL set "UVICORN_LOG_LEVEL=warning"

set "UVICORN_ACCESS_LOG=%XUANQIONG_WENSHU_UVICORN_ACCESS_LOG%"
if not defined UVICORN_ACCESS_LOG set "UVICORN_ACCESS_LOG=0"

set "BACKEND_RELOAD=%XUANQIONG_WENSHU_BACKEND_RELOAD%"
if not defined BACKEND_RELOAD set "BACKEND_RELOAD=0"

set "XUANQIONG_WENSHU_BACKEND_HOST=%BACKEND_HOST%"
set "XUANQIONG_WENSHU_BACKEND_PORT=%BACKEND_PORT%"
set "XUANQIONG_WENSHU_LOG_DIR=%RUN_LOG_DIR%"
set "LOG_DIR=%RUN_LOG_DIR%"
set "XUANQIONG_WENSHU_UVICORN_LOG_LEVEL=%UVICORN_LOG_LEVEL%"
set "XUANQIONG_WENSHU_UVICORN_ACCESS_LOG=%UVICORN_ACCESS_LOG%"
set "XUANQIONG_WENSHU_BACKEND_RELOAD=%BACKEND_RELOAD%"

set "PYTHONUNBUFFERED=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "NO_COLOR=1"

if not exist "%RUN_LOG_DIR%" mkdir "%RUN_LOG_DIR%" >nul 2>nul

set "UVICORN_ARGS=--host %BACKEND_HOST% --port %BACKEND_PORT% --log-level %UVICORN_LOG_LEVEL%"
if /I not "%UVICORN_ACCESS_LOG%"=="1" set "UVICORN_ARGS=%UVICORN_ARGS% --no-access-log"
if /I "%BACKEND_RELOAD%"=="1" set "UVICORN_ARGS=%UVICORN_ARGS% --reload"

echo [Backend] Python: %PYTHON_EXE%
echo [Backend] Log dir: %RUN_LOG_DIR%
echo [Backend] Uvicorn args: %UVICORN_ARGS%

call "%PYTHON_EXE%" -m uvicorn app.main:app %UVICORN_ARGS%
exit /b %ERRORLEVEL%
