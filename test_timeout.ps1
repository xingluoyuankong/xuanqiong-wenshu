# Test script to verify timeout mechanism works
# This will start backend with a 2-second timeout to quickly verify the feature

$ErrorActionPreference = 'Continue'

Write-Host "=== Testing Timeout Mechanism ===" -ForegroundColor Cyan

$TIMEOUT_SECONDS = 2  # Very short for quick test
$CHECK_INTERVAL_MS = 200

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $scriptPath
$backendWd = Join-Path $repo 'backend'
$backendPy = Join-Path $backendWd '.venv\python.exe'
$backendPortValue = '9999'  # Use port 9999 which should be free
$backendBaseUrl = "http://127.0.0.1:$backendPortValue"

Write-Host "Testing with ${TIMEOUT_SECONDS}s timeout on port ${backendPortValue}..." -ForegroundColor Gray
Write-Host "(This should fail quickly since no service runs on this port)" -ForegroundColor DarkGray

$startTimeBackend = Get-Date
$backendJob = Start-Process -FilePath $backendPy `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$backendPortValue", '--log-level', 'info', '--no-access-log') `
    -WorkingDirectory $backendWd `
    -RedirectStandardOutput "${repo}\logs\test-backend.log" `
    -RedirectStandardError "${repo}\logs\test-backend-error.log" `
    -PassThru

Write-Host "Backend PID: $($backendJob.Id)" -ForegroundColor Gray
Write-Host "Waiting for health check (timeout: ${TIMEOUT_SECONDS}s)..." -ForegroundColor Gray

$elapsedSeconds = 0
$timedOut = $false

while ((Get-Date).Subtract($startTimeBackend).TotalSeconds -lt $TIMEOUT_SECONDS) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing "$backendBaseUrl/api/health" -TimeoutSec 1
        if ($resp.StatusCode -eq 200) {
            Write-Host "✓ Backend healthy after ${elapsedSeconds}s" -ForegroundColor Green
            $timedOut = $false
            break
        }
    } catch {
        Write-Host "  Health check failed: $($_.Exception.Message)" -ForegroundColor Yellow
    }
    
    Start-Sleep -Milliseconds $CHECK_INTERVAL_MS
    $elapsedSeconds += ($CHECK_INTERVAL_MS / 1000)
    
    if ([math]::Floor($elapsedSeconds) % 1 -eq 0 -and $elapsedSeconds -gt 0) {
        $remaining = [math]::Floor($TIMEOUT_SECONDS - $elapsedSeconds)
        Write-Host "  ⏱ Elapsed: ${elapsedSeconds}s, Remaining: ${remaining}s" -ForegroundColor DarkGray
    }
}

if ($elapsedSeconds -ge $TIMEOUT_SECONDS) {
    Write-Host "❌ TIMEOUT CONFIRMED: No response within ${TIMEOUT_SECONDS}s" -ForegroundColor Red
    $timedOut = $true
    
    # Clean up
    Stop-Process -Id $backendJob.Id -Force -ErrorAction SilentlyContinue
}

# Verify cleanup happened
Start-Sleep -Seconds 1
try {
    $process = Get-Process -Id $backendJob.Id -ErrorAction SilentlyContinue
    if ($process) {
        Write-Host "⚠ WARNING: Process still running!" -ForegroundColor Yellow
        Stop-Process -Id $backendJob.Id -Force
        $timedOut = $false
    } else {
        Write-Host "✓ Cleanup successful: Process terminated" -ForegroundColor Green
    }
} catch {
    Write-Host "✓ Process already terminated" -ForegroundColor Green
}

# Summary
Write-Host "`n=== Test Result ===" -ForegroundColor Cyan
if ($timedOut) {
    Write-Host "PASS: Timeout mechanism works correctly" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAIL: Backend started successfully (unexpected)" -ForegroundColor Red
    exit 1
}
