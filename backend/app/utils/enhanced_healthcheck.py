#!/usr/bin/env python3
"""
US-005: Enhanced health check with intelligent failure detection.
Distinguishes between timeout (slow start) and connection refused (failed).
Exit codes: 0=ok, 1=slow, 2=failed
"""

import os
import subprocess
import sys
import time
from datetime import datetime

# Configuration from environment
MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 10))
RETRY_BASE_INTERVAL = int(os.environ.get('RETRY_BASE_INTERVAL', 2))  # seconds
TIMEOUT_SECONDS = int(os.environ.get('BACKEND_TIMEOUT', 10))
SLOW_THRESHOLD = float(os.environ.get('SLOW_THRESHOLD', 8))  # seconds

API_URL = os.environ.get('API_URL')
FRONTEND_URL = os.environ.get('FRONTEND_URL')
DB_PATH = os.environ.get('DB_PATH')


def make_curl_request(url: str, attempt: int) -> tuple[int, str, float]:
    """
    Make HTTP request with curl.
    Returns: (exit_code, message, response_time_seconds)
    """
    cmd = [
        'curl', '-s', '-o', '/dev/null', '-w', '%{http_code}:%{time_total}',
        '--max-time', str(TIMEOUT_SECONDS),
        url
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_SECONDS + 2)
        exit_code = result.returncode
        output = result.stdout.strip()
        
        # Parse curl output: http_code:time_total
        if ':' in output:
            http_code, time_str = output.rsplit(':', 1)
            response_time = float(time_str)
        else:
            http_code = 'unknown'
            response_time = 0.0
        
        # Check for specific curl errors
        if exit_code == 28:  # Timeout
            return exit_code, f"Timeout after {TIMEOUT_SECONDS}s", response_time
        elif exit_code == 7:  # Connection refused or host unreachable
            return exit_code, "Connection refused (服务实际失败)", response_time
        
        # HTTP errors that indicate service is running but responding poorly
        if http_code.startswith('5'):
            return 1, f"HTTP {http_code} (服务启动中但有问题)", response_time
            
        return 0, f"OK ({http_code})", response_time
        
    except subprocess.TimeoutExpired:
        return 28, "Request timed out", TIMEOUT_SECONDS
    except FileNotFoundError:
        return 2, "curl not found", 0.0
    except Exception as e:
        return 2, f"Unexpected error: {str(e)}", 0.0


def check_backend_health() -> tuple[bool, bool, str]:
    """
    Check backend API health with retry logic.
    Returns: (is_healthy, is_slow, reason)
    """
    print(f"\n{'='*60}")
    print("Checking backend API...")
    print(f"URL: {API_URL}, MAX_RETRIES={MAX_RETRIES}, BASE_INTERVAL={RETRY_BASE_INTERVAL}s")
    print(f"{'='*60}\n")
    
    for attempt in range(1, MAX_RETRIES + 1):
        interval = RETRY_BASE_INTERVAL * (1 << (attempt - 1))  # Exponential backoff: 1,2,4,8...
        
        if attempt > 1:
            sleep_msg = f"sleeping {interval:.0f}s"
        else:
            sleep_msg = ""
        
        print(f"Attempt {attempt}/{MAX_RETRIES}{sleep_msg}: checking {API_URL}")
        
        exit_code, message, response_time = make_curl_request(API_URL, attempt)
        
        # Exit code 0 = healthy
        if exit_code == 0:
            if response_time < SLOW_THRESHOLD:
                print(f"✅ Backend OK: {message}, response_time={response_time:.3f}s")
                return True, False, "Fast response"
            else:
                print(f"⚠️  Backend slow: {message}, response_time={response_time:.3f}s (>={SLOW_THRESHOLD}s)")
                return False, True, "Slow response"
        
        # Exit code 28 or 7 = failed
        if exit_code in [28, 7]:
            print(f"❌ Backend FAILED: {message}")
            if attempt == MAX_RETRIES:
                print(f"   After {MAX_RETRIES} attempts with exponential backoff")
            return False, False, "Failed after retries"
        
        # Other HTTP errors might mean service is starting
        print(f"🔄 Backend HTTP {exit_code}: {message}")
        
        if attempt < MAX_RETRIES:
            print(f"   Will retry in {interval:.0f}s\n")
            time.sleep(interval)
    
    # Max retries exceeded without success
    print(f"❌ Backend FAILED after {MAX_RETRIES} attempts")
    return False, False, "Max retries exceeded"


def check_frontend_health() -> tuple[bool, bool, str]:
    """Check frontend health similarly."""
    print(f"\n{'='*60}")
    print("Checking frontend...")
    print(f"URL: {FRONTEND_URL}")
    print(f"{'='*60}\n")
    
    exit_code, message, _ = make_curl_request(FRONTEND_URL, 1)
    
    if exit_code == 0:
        print(f"✅ Frontend OK: {message}")
        return True, False, "Fast response"
    elif exit_code in [28, 7]:
        print(f"❌ Frontend FAILED: {message}")
        return False, False, "Connection failed"
    else:
        print(f"⚠️  Frontend issue: {message}")
        return False, True, "Partial failure"


def check_database_existence() -> tuple[bool, str]:
    """Check database file exists."""
    print(f"\n{'='*60}")
    print("Checking database file...")
    print(f"Path: {DB_PATH}")
    print(f"{'='*60}\n")
    
    from pathlib import Path
    
    if Path(DB_PATH).exists():
        size = Path(DB_PATH).stat().st_size
        print(f"✅ Database exists: size={size:,} bytes")
        return True, f"Found ({size:,} bytes)"
    else:
        print(f"❌ Database missing: {DB_PATH}")
        return False, "File not found"


def check_disk_space(disk_path: str) -> tuple[bool, str]:
    """Check available disk space."""
    print(f"\n{'='*60}")
    print("Checking disk space...")
    print(f"Path: {disk_path}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(['df', '-h', disk_path], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split('\n')
        if len(lines) >= 2:
            parts = lines[1].split()
            if len(parts) >= 5:
                available = parts[4]
                print(f"✅ Available: {available}")
                return True, f"{available}"
    except Exception as e:
        print(f"⚠️  Could not check disk: {e}")
        return False, "Unknown"
    
    return False, "Could not determine"


def main() -> int:
    """Main health check orchestration."""
    checks_passed = 0
    total_checks = 4
    
    print("="*60)
    print("     玄穹文枢健康检查 (Enhanced Health Check)")
    print("="*60)
    print(f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"配置：MAX_RETRIES={MAX_RETRIES}, BASE_INTERVAL={RETRY_BASE_INTERVAL}s, TIMEOUT={TIMEOUT_SECONDS}s")
    print("="*60)
    
    # Check backend
    backend_ok, backend_slow, backend_reason = check_backend_health()
    if backend_ok:
        checks_passed += 1
    elif backend_slow:
        print(f"📊 Status: Service starting slowly (will be ready soon)\n")
        # Don't count as failed yet, give some grace
    else:
        print(f"📊 Status: Backend unreachable after retries\n")
    
    # Check frontend
    frontend_ok, frontend_slow, frontend_reason = check_frontend_health()
    if frontend_ok:
        checks_passed += 1
    
    # Check database
    db_exists, db_info = check_database_existence()
    if db_exists:
        checks_passed += 1
    
    # Check disk space
    disk_ok, disk_info = check_disk_space(DISK_PATH)
    if disk_ok:
        checks_passed += 1
    
    # Summary
    print(f"\n{'='*60}")
    print("Health Check Summary")
    print(f"{'='*60}")
    print(f"Passed: {checks_passed}/{total_checks} checks")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Determine exit code
    if checks_passed == total_checks:
        print("\n✅ All systems operational!\n")
        return 0
    elif backend_slow or frontend_slow:
        print("\n⚠️  Warning: Services starting slowly. Try again in a few minutes.\n")
        return 1
    else:
        print("\n❌ Error: Service(s) failed to respond. Check logs.\n")
        return 2


if __name__ == '__main__':
    import os
    sys.exit(main())
