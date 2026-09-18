#!/usr/bin/env python3
"""
US-005: Health check classifier using raw TCP connect.

Distinguishes three states precisely:
  OK    (0) - TCP connect succeeded within SLOW_THRESHOLD
  SLOW  (1) - TCP connect timed out (service starting slowly / unreachable silently)
  FAILED(2) - TCP connect refused (nothing listening, service actually failed)

Usage:
  python3 healthcheck_classifier.py                 # uses default local targets
  HEALTH_TARGETS=127.0.0.1:8013,127.0.0.1:5174 python3 healthcheck_classifier.py

Env vars:
  HEALTH_TARGETS       - comma list host:port (default 127.0.0.1:8013,127.0.0.1:5174)
  HEALTH_MAX_RETRIES   - max attempts per target (default 3)
  HEALTH_RETRY_INTERVAL- base backoff seconds (default 2, exponential 1x,2x,4x)
  HEALTH_CONNECT_TIMEOUT - per-attempt connect timeout seconds (default 3)
  HEALTH_SLOW_THRESHOLD- seconds above which a successful connect counts slow (default 8)
"""

import os
import socket
import sys
import time
from datetime import datetime

OK, SLOW, FAILED = 0, 1, 2

DEFAULT_TARGETS = "127.0.0.1:8013,127.0.0.1:5174"


def parse_targets(raw: str):
    targets = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            host, port = item.rsplit(":", 1)
        else:
            host, port = "127.0.0.1", item
        targets.append((host.strip() or "127.0.0.1", int(port)))
    return targets


def probe_once(host: str, port: int, timeout: float):
    """
    Single TCP probe.
    Returns (state, detail, elapsed_seconds)
      state: OK / SLOW / FAILED
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    start = time.time()
    try:
        sock.connect((host, port))
        elapsed = time.time() - start
        return OK, f"connect ok in {elapsed:.3f}s", elapsed
    except ConnectionRefusedError:
        elapsed = time.time() - start
        return FAILED, f"ConnectionRefused after {elapsed:.3f}s", elapsed
    except socket.timeout:
        elapsed = time.time() - start
        return SLOW, f"timeout after {elapsed:.3f}s", elapsed
    except OSError as exc:
        # e.g. EHOSTUNREACH / ENETUNREACH are closer to "failed" than "slow"
        elapsed = time.time() - start
        return FAILED, f"{exc.__class__.__name__}: {exc} after {elapsed:.3f}s", elapsed
    finally:
        try:
            sock.close()
        except Exception:
            pass


def classify_target(host: str, port: int):
    max_retries = int(os.environ.get("HEALTH_MAX_RETRIES", "3"))
    base_interval = float(os.environ.get("HEALTH_RETRY_INTERVAL", "2"))
    connect_timeout = float(os.environ.get("HEALTH_CONNECT_TIMEOUT", "3"))
    slow_threshold = float(os.environ.get("HEALTH_SLOW_THRESHOLD", "8"))

    print(f"\n{'=' * 62}")
    print(f"Target: {host}:{port}")
    print(
        f"Config: retries={max_retries} interval={base_interval}s "
        f"timeout={connect_timeout}s slow>={slow_threshold}s"
    )
    print(f"{'=' * 62}")

    attempt = 1
    while attempt <= max_retries:
        state, detail, elapsed = probe_once(host, port, connect_timeout)

        if state == FAILED:
            # Explicit refusal is conclusive -> no retry, immediate FAILED
            print(f"  attempt {attempt}/{max_retries}: [FAILED] {detail}")
            print(f"  -> 连接被拒绝 (ECONNREFUSED)，服务实际失败，无需重试")
            return FAILED, detail

        if state == SLOW:
            if attempt < max_retries:
                wait = base_interval * (2 ** (attempt - 1))
                print(f"  attempt {attempt}/{max_retries}: [SLOW] {detail}")
                print(f"  -> 超时判定为“启动慢/无响应”，退避 {wait:.0f}s 后重试")
                time.sleep(wait)
                attempt += 1
                continue
            print(f"  attempt {attempt}/{max_retries}: [SLOW] {detail}")
            print(f"  -> 重试 {max_retries} 次仍超时，最终判定 SLOW(1)")
            return SLOW, detail

        # OK
        if elapsed >= slow_threshold:
            print(f"  attempt {attempt}/{max_retries}: [SLOW] {detail} (>= {slow_threshold}s)")
            return SLOW, detail
        print(f"  attempt {attempt}/{max_retries}: [OK] {detail}")
        return OK, detail

    return FAILED, "exhausted retries"


def main():
    raw = os.environ.get("HEALTH_TARGETS", DEFAULT_TARGETS)
    targets = parse_targets(raw)

    print("=" * 62)
    print("     玄穹文枢健康检查 (US-005 TCP 分类版)")
    print("=" * 62)
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标: {raw}")
    print("=" * 62)

    worst = OK
    results = []
    for host, port in targets:
        state, detail = classify_target(host, port)
        results.append((host, port, state, detail))
        if state == FAILED:
            worst = FAILED
        elif state == SLOW and worst != FAILED:
            worst = SLOW

    print(f"\n{'=' * 62}")
    print("汇总 Summary")
    print(f"{'=' * 62}")
    for host, port, state, detail in results:
        label = {OK: "OK    ", SLOW: "SLOW  ", FAILED: "FAILED"}[state]
        print(f"  {host}:{port}  ->  {label}  | {detail}")
    print(f"{'=' * 62}")

    if worst == OK:
        print("\n[结果] 所有目标正常 → exit 0")
    elif worst == SLOW:
        print("\n[结果] 存在超时（慢/启动中） → exit 1")
    else:
        print("\n[结果] 存在连接拒绝（服务失败） → exit 2")

    return worst


if __name__ == "__main__":
    sys.exit(main())
