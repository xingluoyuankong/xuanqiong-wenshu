# AIMETA P=根因诊断服务_日志分析与故障定位|R=日志扫描_根因提取_事件排序|NR=不含业务写操作|E=RootCauseDiagnosticsService|X=internal|A=日志诊断|D=pathlib,regex|S=fs|RD=./README.ai
from __future__ import annotations

from datetime import datetime, timedelta
import re
from pathlib import Path
from typing import Any, Optional

from ..core.config import settings


_LOG_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) "
    r"\[(?P<level>[A-Z]+)\] (?P<logger>\S+) (?P<source>[^|]+)\| (?P<message>.*)$"
)
_REQUEST_FAILED_RE = re.compile(
    r"Request failed:\s*request_id=(?P<request_id>\S+)\s+method=(?P<method>\S+)\s+"
    r"path=(?P<path>\S+)\s+status=(?P<status>\d+)\s+code=(?P<code>\S+)\s+"
    r"message=(?P<message>.*?)\s+root_cause=(?P<root_cause>.*)$"
)
_EXCEPTION_TOKEN_RE = re.compile(
    r"(?P<etype>[A-Za-z_][\w\.]*(?:Error|Exception|Warning|MissingGreenlet))"
)


def _normalize_nullable_token(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    if not cleaned:
        return None
    lowered = cleaned.lower()
    if cleaned == "-" or lowered in {"none", "null", "n/a", "na"}:
        return None
    return cleaned


class RootCauseDiagnosticsService:
    """从后端日志中提取最主要根因事件，优先结构化错误，回退 traceback。"""

    def __init__(
        self,
        *,
        logs_root: Optional[Path] = None,
        latest_run_file: Optional[Path] = None,
        max_runs: int = 8,
        max_incidents: int = 20,
    ) -> None:
        self._logs_root = logs_root or (settings.project_root.parent / "logs")
        self._latest_run_file = latest_run_file or (self._logs_root / "latest-run.txt")
        self._max_runs = max_runs
        self._max_incidents = max_incidents

    def diagnose_root_cause(self) -> dict[str, Any]:
        run_dirs = self._resolve_run_dirs()
        incidents: list[dict[str, Any]] = []
        scanned_logs: list[str] = []

        for run_rank, run_dir in enumerate(run_dirs):
            for log_name in ("backend-error.log", "backend.log"):
                log_path = run_dir / log_name
                if not log_path.is_file():
                    continue
                scanned_logs.append(self._display_log_path(log_path))
                incidents.extend(self._parse_log_file(log_path, run_rank=run_rank))

        incidents = self._dedupe_incidents(incidents)
        incidents.sort(key=self._incident_sort_key, reverse=True)
        incidents = incidents[: self._max_incidents]
        primary = self._pick_primary_incident(incidents)

        if not primary:
            return {
                "generated_at": datetime.now(),
                "scanned_logs": scanned_logs,
                "primary_error_type": "NO_ERROR_FOUND",
                "primary_error_message": "未在最近日志中发现可解析错误事件",
                "root_cause": None,
                "request_id": None,
                "path": None,
                "status_code": None,
                "occurred_at": None,
                "source_log": None,
                "stack_excerpt": None,
                "hint": "建议先复现一次问题，然后刷新诊断面板。",
                "confidence": 0.0,
                "incidents": [],
            }

        return {
            "generated_at": datetime.now(),
            "scanned_logs": scanned_logs,
            "primary_error_type": primary["error_type"],
            "primary_error_message": primary["error_message"],
            "root_cause": primary.get("root_cause"),
            "request_id": primary.get("request_id"),
            "path": primary.get("path"),
            "status_code": primary.get("status_code"),
            "occurred_at": primary.get("occurred_at"),
            "source_log": primary.get("source_log"),
            "stack_excerpt": primary.get("stack_excerpt"),
            "hint": primary.get("hint"),
            "confidence": primary.get("confidence", 0.0),
            "incidents": incidents,
        }

    def _resolve_run_dirs(self) -> list[Path]:
        run_dirs: list[Path] = []
        seen: set[str] = set()

        latest = self._read_latest_run_dir()
        if latest and latest.is_dir():
            resolved = str(latest.resolve())
            seen.add(resolved)
            run_dirs.append(latest)

        if self._logs_root.is_dir():
            history_runs = sorted(
                [item for item in self._logs_root.iterdir() if item.is_dir() and item.name.startswith("run-")],
                key=lambda item: item.name,
                reverse=True,
            )
            for run_dir in history_runs:
                resolved = str(run_dir.resolve())
                if resolved in seen:
                    continue
                run_dirs.append(run_dir)
                seen.add(resolved)
                if len(run_dirs) >= self._max_runs:
                    break

        if not run_dirs and settings.resolved_log_dir.is_dir():
            run_dirs.append(settings.resolved_log_dir)
        return run_dirs

    def _pick_primary_incident(self, incidents: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if not incidents:
            return None

        now = datetime.now()
        recent_cutoff = now - timedelta(hours=2)
        recent = []
        for incident in incidents:
            occurred_at = incident.get("occurred_at")
            if isinstance(occurred_at, datetime) and occurred_at >= recent_cutoff:
                recent.append(incident)

        search_pool = recent or incidents
        for incident in search_pool:
            if self._is_actionable_incident(incident):
                return incident

        return None

    @staticmethod
    def _is_actionable_incident(incident: dict[str, Any]) -> bool:
        status_code = incident.get("status_code")
        if isinstance(status_code, int):
            if status_code >= 500:
                return True
            if status_code in {401, 403, 404}:
                return False
        error_type = str(incident.get("error_type") or "")
        if "MissingGreenlet" in error_type:
            return True
        message = str(incident.get("error_message") or "")
        lowered = message.lower()
        if "not found" in lowered or "not authenticated" in lowered or "用户名或密码错误" in lowered:
            return False
        return bool(message.strip())

    def _read_latest_run_dir(self) -> Optional[Path]:
        if not self._latest_run_file.is_file():
            return None
        try:
            raw = self._latest_run_file.read_text(encoding="utf-8", errors="replace").strip()
            if not raw:
                return None
            return Path(raw)
        except Exception:
            return None

    def _parse_log_file(self, log_path: Path, *, run_rank: int) -> list[dict[str, Any]]:
        incidents: list[dict[str, Any]] = []
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return incidents

        file_mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
        idx = 0
        while idx < len(lines):
            line = lines[idx].rstrip()
            prefix_match = _LOG_PREFIX_RE.match(line)
            if not prefix_match:
                if self._is_traceback_start(line):
                    block, next_idx = self._collect_traceback_block(lines, idx)
                    incidents.append(self._incident_from_traceback(block, log_path, file_mtime, run_rank=run_rank))
                    idx = next_idx
                    continue
                idx += 1
                continue

            message = prefix_match.group("message").strip()
            level = prefix_match.group("level")
            occurred_at = datetime.strptime(prefix_match.group("ts"), "%Y-%m-%d %H:%M:%S")

            trace_block: list[str] = []
            if idx + 1 < len(lines) and self._is_traceback_start(lines[idx + 1]):
                trace_block, next_idx = self._collect_traceback_block(lines, idx + 1)
                idx = next_idx
            else:
                idx += 1

            if "Request failed:" in message:
                incidents.append(
                    self._incident_from_structured_failure(
                        message,
                        occurred_at,
                        log_path,
                        trace_block,
                        run_rank=run_rank,
                    )
                )
                continue
            if level not in {"ERROR", "CRITICAL"}:
                continue
            incidents.append(
                self._incident_from_error_line(
                    message,
                    occurred_at,
                    log_path,
                    trace_block,
                    run_rank=run_rank,
                )
            )
        return incidents

    def _incident_from_structured_failure(
        self,
        message: str,
        occurred_at: datetime,
        log_path: Path,
        trace_block: list[str],
        *,
        run_rank: int,
    ) -> dict[str, Any]:
        matched = _REQUEST_FAILED_RE.search(message)
        if not matched:
            return self._incident_from_error_line(message, occurred_at, log_path, trace_block)

        raw_message = matched.group("message").strip()
        root_cause = _normalize_nullable_token(matched.group("root_cause"))
        normalized_message = _normalize_nullable_token(raw_message) or "请求失败（缺少详细错误信息）"
        error_type, error_message = self._split_exception(root_cause or normalized_message)
        status_code = int(matched.group("status"))
        confidence = 0.98 if status_code >= 500 else 0.72
        return {
            "occurred_at": occurred_at,
            "source_log": self._display_log_path(log_path),
            "error_type": error_type,
            "error_message": error_message,
            "root_cause": root_cause or None,
            "request_id": matched.group("request_id").strip(),
            "path": matched.group("path").strip(),
            "status_code": status_code,
            "stack_excerpt": self._format_stack_excerpt(trace_block),
            "hint": self._build_hint(error_type, root_cause or normalized_message),
            "confidence": confidence,
            "run_rank": run_rank,
        }

    def _incident_from_error_line(
        self,
        message: str,
        occurred_at: datetime,
        log_path: Path,
        trace_block: list[str],
        *,
        run_rank: int,
    ) -> dict[str, Any]:
        root_cause = self._extract_traceback_root_cause(trace_block)
        source_text = root_cause or message
        error_type, error_message = self._split_exception(source_text)
        return {
            "occurred_at": occurred_at,
            "source_log": self._display_log_path(log_path),
            "error_type": error_type,
            "error_message": error_message,
            "root_cause": root_cause,
            "request_id": None,
            "path": None,
            "status_code": None,
            "stack_excerpt": self._format_stack_excerpt(trace_block),
            "hint": self._build_hint(error_type, source_text),
            "confidence": 0.9 if root_cause else 0.8,
            "run_rank": run_rank,
        }

    def _incident_from_traceback(
        self,
        trace_block: list[str],
        log_path: Path,
        occurred_at: datetime,
        *,
        run_rank: int,
    ) -> dict[str, Any]:
        root_cause = self._extract_traceback_root_cause(trace_block) or "未识别的 traceback 错误"
        error_type, error_message = self._split_exception(root_cause)
        return {
            "occurred_at": occurred_at,
            "source_log": self._display_log_path(log_path),
            "error_type": error_type,
            "error_message": error_message,
            "root_cause": root_cause,
            "request_id": None,
            "path": None,
            "status_code": None,
            "stack_excerpt": self._format_stack_excerpt(trace_block),
            "hint": self._build_hint(error_type, root_cause),
            "confidence": 0.86,
            "run_rank": run_rank,
        }

    @staticmethod
    def _is_traceback_start(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("Traceback (most recent call last):") or "Exception Group Traceback" in stripped

    def _collect_traceback_block(self, lines: list[str], start: int) -> tuple[list[str], int]:
        block: list[str] = []
        idx = start
        while idx < len(lines):
            line = lines[idx].rstrip()
            if idx > start and _LOG_PREFIX_RE.match(line):
                break
            block.append(line)
            idx += 1
            if len(block) >= 120:
                break
        return block, idx

    @staticmethod
    def _extract_traceback_root_cause(trace_block: list[str]) -> Optional[str]:
        if not trace_block:
            return None
        ignored_tokens = (
            "Exception Group Traceback",
            "BaseExceptionGroup(",
            "raise BaseExceptionGroup(",
            "collapse_excgroups",
        )
        for line in reversed(trace_block):
            stripped = line.strip()
            if not stripped:
                continue
            if any(token in stripped for token in ignored_tokens):
                continue
            if stripped.startswith("| File ") or stripped.startswith('File "'):
                continue
            if _EXCEPTION_TOKEN_RE.search(stripped):
                return stripped
        return None

    @staticmethod
    def _format_stack_excerpt(trace_block: list[str], max_lines: int = 24) -> Optional[str]:
        if not trace_block:
            return None
        excerpt = trace_block[:max_lines]
        text = "\n".join(excerpt).strip()
        return text or None

    def _split_exception(self, text: str) -> tuple[str, str]:
        cleaned = (text or "").strip()
        if not cleaned:
            return "UNKNOWN_ERROR", "未知错误"
        if "baseexceptiongroup" in cleaned.lower():
            return "ExceptionGroupError", cleaned

        left, sep, right = cleaned.partition(":")
        left = left.strip()
        right = right.strip()
        if sep and self._looks_like_exception_name(left):
            return left, right or cleaned

        token = _EXCEPTION_TOKEN_RE.search(cleaned)
        if token:
            etype = token.group("etype")
            return etype, cleaned

        lowered = cleaned.lower()
        if "missing 1 required keyword-only argument" in lowered or "required positional argument" in lowered:
            return "TypeError", cleaned
        if "timeout" in lowered:
            return "TimeoutError", cleaned
        return "RuntimeError", cleaned

    @staticmethod
    def _looks_like_exception_name(candidate: str) -> bool:
        if not candidate:
            return False
        if candidate.endswith(("Error", "Exception", "Warning", "MissingGreenlet")):
            return True
        return bool(_EXCEPTION_TOKEN_RE.fullmatch(candidate))

    def _build_hint(self, error_type: str, text: str) -> str:
        payload = f"{error_type} {text}".lower()
        if "missinggreenlet" in payload:
            return "检测到 SQLAlchemy 异步懒加载问题：请确保关系字段在查询阶段使用 selectinload 预加载。"
        if "missing 1 required keyword-only argument" in payload or "required positional argument" in payload:
            return "检测到函数参数缺失：请检查调用方是否传递了必需参数（例如 user_id）。"
        if "apiconnectionerror" in payload or "httpx.readerror" in payload or "connecterror" in payload:
            return "检测到上游连接异常：建议检查模型网关可用性，并启用重试/降级策略。"
        if "timeout" in payload:
            return "请求超时：建议降低单次任务复杂度并增加超时与重试策略。"
        if "401" in payload or "unauthorized" in payload:
            return "认证失败：请检查 token 有效期与后端鉴权配置。"
        return "建议结合 request_id 检索详细日志，并优先修复最先出现的高频异常。"

    def _dedupe_incidents(self, incidents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for incident in incidents:
            key = "|".join(
                [
                    str(incident.get("source_log") or ""),
                    str(incident.get("occurred_at") or ""),
                    str(incident.get("error_type") or ""),
                    str(incident.get("error_message") or ""),
                    str(incident.get("path") or ""),
                    str(incident.get("status_code") or ""),
                    str(incident.get("request_id") or ""),
                ]
            )
            existing = deduped.get(key)
            if not existing or float(incident.get("confidence") or 0.0) > float(existing.get("confidence") or 0.0):
                deduped[key] = incident
        return list(deduped.values())

    @staticmethod
    def _incident_sort_key(incident: dict[str, Any]) -> tuple[int, float, datetime]:
        priority = 0
        raw_rank = incident.get("run_rank")
        run_rank = int(raw_rank) if raw_rank is not None else 999
        if run_rank == 0:
            priority += 6
        elif run_rank == 1:
            priority += 2
        else:
            priority -= min(run_rank, 6)

        status_code = incident.get("status_code")
        if isinstance(status_code, int):
            if status_code >= 500:
                priority += 5
            elif status_code >= 400:
                priority += 0
            if status_code == 429:
                priority += 1
            if status_code in {401, 403}:
                # 认证错误通常是噪声，不应压过真实 5xx 故障
                priority -= 4
        error_type = str(incident.get("error_type") or "")
        if "MissingGreenlet" in error_type:
            priority += 5
        root_cause = _normalize_nullable_token(str(incident.get("root_cause") or ""))
        if root_cause:
            priority += 2
        error_message = _normalize_nullable_token(str(incident.get("error_message") or ""))
        if not error_message:
            priority -= 2
        if incident.get("request_id") and incident.get("path"):
            priority += 1
        confidence = float(incident.get("confidence") or 0.0)
        occurred_at = incident.get("occurred_at") or datetime.min
        if not isinstance(occurred_at, datetime):
            occurred_at = datetime.min
        return priority, confidence, occurred_at

    def _display_log_path(self, path: Path) -> str:
        try:
            if path.parent.name.startswith("run-"):
                return f"{path.parent.name}/{path.name}"
            return str(path.relative_to(self._logs_root))
        except Exception:
            return str(path)
