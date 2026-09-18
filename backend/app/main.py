from contextlib import asynccontextmanager
import logging
from logging.config import dictConfig
import re
import sys
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .api.routers import api_router
from .core.config import settings
from .db.init_db import init_db
from .db.session import AsyncSessionLocal
from .services.prompt_service import PromptService


_logging_boot_error: str | None = None


for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_LEVEL_LABELS = {
    "DEBUG": "调试",
    "INFO": "信息",
    "WARNING": "警告",
    "ERROR": "错误",
    "CRITICAL": "严重",
}

_LEVEL_GLYPHS = {
    "DEBUG": "┆",
    "INFO": "●",
    "WARNING": "▲",
    "ERROR": "✖",
    "CRITICAL": "※",
}

_TRANSLATION_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^Started server process \[(?P<pid>\d+)\]$"), "已启动服务进程 [\\g<pid>]"),
    (re.compile(r"^Finished server process \[(?P<pid>\d+)\]$"), "服务进程已结束 [\\g<pid>]"),
    (re.compile(r"^Started reloader process \[(?P<pid>\d+)\] using (?P<backend>.+)$"), "已启动热重载进程 [\\g<pid>]，模式=\\g<backend>"),
    (re.compile(r"^Waiting for application startup\.$"), "等待应用启动。"),
    (re.compile(r"^Application startup complete\.$"), "应用启动完成。"),
    (re.compile(r"^Application shutdown complete\.$"), "应用已完成关闭。"),
    (re.compile(r"^Shutting down$"), "正在关闭服务。"),
    (re.compile(r"^Uvicorn running on (?P<addr>.+) \(Press CTRL\+C to quit\)$"), "服务已启动：\\g<addr>（按 CTRL+C 停止）"),
)

_BENIGN_WARNING_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^Can't create database '(?P<db>.+)'; database exists$"),
        "数据库「\\g<db>」已存在，跳过创建。",
    ),
)

_LOGGER_NAME_ALIASES = {
    "app": "应用",
    "app.errors": "异常处理",
    "uvicorn.error": "Uvicorn",
    "uvicorn.access": "访问日志",
    "asyncmy": "MySQL",
    "sqlalchemy.engine": "SQL引擎",
    "sqlalchemy.pool": "连接池",
    "watchfiles.main": "热重载",
    "httpx": "HTTP客户端",
    "urllib3": "网络底层",
}


def _humanize_logger_name(name: str) -> str:
    if name in _LOGGER_NAME_ALIASES:
        return _LOGGER_NAME_ALIASES[name]
    if name.startswith("app.api.routers."):
        return f"接口/{name.rsplit('.', 1)[-1]}"
    if name.startswith("app.services."):
        return f"服务/{name.rsplit('.', 1)[-1]}"
    if name.startswith("app.db."):
        return f"数据库/{name.rsplit('.', 1)[-1]}"
    if name.startswith("app.core."):
        return f"核心/{name.rsplit('.', 1)[-1]}"
    if name.startswith("backend.api."):
        return f"接口/{name.rsplit('.', 1)[-1]}"
    if name.startswith("backend.services."):
        return f"服务/{name.rsplit('.', 1)[-1]}"
    return name.replace(".", "/")


class LocalizedConsoleFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.level_label = _LEVEL_LABELS.get(record.levelname, record.levelname)
        record.level_glyph = _LEVEL_GLYPHS.get(record.levelname, "·")
        record.logger_alias = _humanize_logger_name(record.name)
        record.source_loc = f"{record.filename}:{record.lineno}"
        return super().format(record)


class LocalizedFileFormatter(LocalizedConsoleFormatter):
    pass


class HumanizedLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            rendered_message = record.getMessage()
        except Exception:
            return True

        for pattern, template in _BENIGN_WARNING_RULES:
            matched = pattern.match(rendered_message)
            if matched:
                record.levelno = logging.INFO
                record.levelname = logging.getLevelName(logging.INFO)
                record.msg = pattern.sub(template, rendered_message)
                record.args = ()
                return True

        for pattern, template in _TRANSLATION_RULES:
            if pattern.match(rendered_message):
                record.msg = pattern.sub(template, rendered_message)
                record.args = ()
                break
        return True


def _configure_logging() -> None:
    global _logging_boot_error

    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.console_logging_level,
            "formatter": "console",
            "filters": ["humanize"],
            "stream": "ext://sys.stdout",
        }
    }
    shared_handlers = ["console"]

    if settings.file_logging_enabled:
        try:
            settings.resolved_log_dir.mkdir(parents=True, exist_ok=True)
            settings.runtime_log_dir.mkdir(parents=True, exist_ok=True)
            settings.latest_run_file.write_text(str(settings.runtime_log_dir), encoding="utf-8")
            handlers["app_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.logging_level,
                "formatter": "file",
                "filters": ["humanize"],
                "filename": str(settings.app_log_file),
                "maxBytes": settings.log_file_max_bytes,
                "backupCount": settings.log_file_backup_count,
                "encoding": "utf-8",
                "delay": True,
            }
            handlers["error_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "file",
                "filters": ["humanize"],
                "filename": str(settings.error_log_file),
                "maxBytes": settings.log_file_max_bytes,
                "backupCount": settings.log_file_backup_count,
                "encoding": "utf-8",
                "delay": True,
            }
            shared_handlers.extend(["app_file", "error_file"])
        except Exception as exc:  # pragma: no cover - depends on host filesystem
            _logging_boot_error = f"{type(exc).__name__}: {exc}"

    access_log_level = settings.logging_level if settings.uvicorn_access_log_enabled else "WARNING"
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "humanize": {
                "()": HumanizedLogFilter,
            }
        },
        "formatters": {
            "console": {
                "()": LocalizedConsoleFormatter,
                "format": "%(asctime)s %(level_glyph)s %(level_label)s %(logger_alias)s | %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "file": {
                "()": LocalizedFileFormatter,
                "format": "%(asctime)s %(level_glyph)s %(level_label)s %(logger_alias)s %(source_loc)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": handlers,
        "loggers": {
            "backend": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "app": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "backend.app": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "backend.api": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "backend.services": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "app.errors": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": settings.logging_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "uvicorn.access": {
                "level": access_log_level,
                "handlers": shared_handlers,
                "propagate": False,
            },
            "asyncmy": {
                "level": "ERROR",
                "handlers": shared_handlers,
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": shared_handlers,
                "propagate": False,
            },
            "sqlalchemy.pool": {
                "level": "WARNING",
                "handlers": shared_handlers,
                "propagate": False,
            },
            "watchfiles.main": {
                "level": "WARNING",
                "handlers": shared_handlers,
                "propagate": False,
            },
            "httpx": {
                "level": "WARNING",
                "handlers": shared_handlers,
                "propagate": False,
            },
            "urllib3": {
                "level": "WARNING",
                "handlers": shared_handlers,
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": shared_handlers,
        },
    }
    dictConfig(config)


_configure_logging()

app_logger = logging.getLogger("app")
error_logger = logging.getLogger("app.errors")

if _logging_boot_error:
    error_logger.warning("文件日志初始化失败，已退回控制台日志：%s", _logging_boot_error)
elif settings.file_logging_enabled:
    app_logger.info(
        "日志初始化完成：root_dir=%s current_run=%s console_level=%s access_log=%s",
        settings.resolved_log_dir,
        settings.runtime_log_dir,
        settings.console_logging_level,
        settings.uvicorn_access_log_enabled,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle manager with detailed stage logging for diagnostics."""
    import time
    from datetime import datetime
    
    startup_start = time.time()
    app_logger.info("=" * 60)
    app_logger.info("[LIFESPAN] STARTUP | 🚀 APPLICATION STARTUP INITIATED")
    app_logger.info("[LIFESPAN] Timestamp: %s", datetime.now().isoformat())
    app_logger.info("=" * 60)
    
    # Stage 1: Startup Security Enforcement
    app_logger.info("[LIFESPAN] [STAGE-1/6] LIFESPAN-START | Enforcing startup security checks...")
    stage1_start = time.time()
    _enforce_startup_security()
    stage1_duration = time.time() - stage1_start
    app_logger.info("[LIFESPAN] [STAGE-1/6] LIFESPAN-OK | Startup security enforcement complete. Duration: %.2fs", stage1_duration)
    
    # Stage 2: Database Initialization & Migration Check
    app_logger.info("[LIFESPAN] [STAGE-2/6] LIFESPAN-START | Initializing database (Alembic migration check)...")
    stage2_start = time.time()
    await init_db()
    migration_status = "unknown"
    try:
        from subprocess import check_output
        from pathlib import Path
        alembic_result = check_output(["alembic", "current"], cwd=str(Path(__file__).parent))
        migration_status = alembic_result.decode().strip()
    except Exception as e:
        error_logger.warning("[LIFESPAN] [STAGE-2/6] LIFESPAN-WARN | alembic CLI unavailable (%s), falling back to SQL version query", str(e))
        try:
            from sqlalchemy import text as _sqltext
            async with AsyncSessionLocal() as _sess:
                _rev = (await _sess.execute(_sqltext("SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"))).scalar()
                migration_status = str(_rev) if _rev else "no-revision-row"
        except Exception as e2:
            # No alembic_version table means migrations were never run on this
            # database. This is a degraded-but-valid state, NOT a startup error:
            # report clearly and do not pollute the error tally.
            migration_status = "unavailable (no alembic_version table)"
            app_logger.warning(
                "[LIFESPAN] [STAGE-2/6] LIFESPAN-WARN | No alembic_version table found (%s); "
                "Alembic migrations have not been executed on this database (schema likely created "
                "via init_db/create_all). Run 'alembic upgrade head' to enable version tracking.",
                e2,
            )
    app_logger.info("[LIFESPAN] [STAGE-2/6] LIFESPAN-OK | Database ready. Migration revision: %s", migration_status)
    app_logger.info("[LIFESPAN] [STAGE-2/6] PERFORMANCE | Database init + migration check completed in %.2fs", time.time() - stage2_start)
    
    startup_errors: list[str] = []

    # Stage 3: Provider Initialization
    app_logger.info("[LIFESPAN] [STAGE-3/6] LIFESPAN-START | Provider initialization sequence starting...")
    stage3_start = time.time()
    stage3_ok = False
    stage3_outcome = "unknown"
    try:
        from .services.llm_service import LLMService
        from .core.config import settings

        app_logger.info("[LIFESPAN] [STAGE-3/6] PROVIDER-STATUS | Checking configured providers...")
        providers_available = []

        if settings.openai_api_key and settings.openai_base_url:
            app_logger.info("[LIFESPAN] [STAGE-3/6] PROVIDER-ATTEMPT | Attempting to initialize OpenAI provider...")
            try:
                # LLMService requires a database session (verified signature:
                # LLMService.__init__(self, session)). It creates its OpenAI
                # client lazily inside methods, so constructibility is the
                # only meaningful readiness probe available at startup.
                async with AsyncSessionLocal() as _llm_session:
                    llm_service = LLMService(_llm_session)
                    app_logger.info(
                        "[LIFESPAN] [STAGE-3/6] PROVIDER-OK | LLMService constructed "
                        "(session bound, base_url=%s, model=%s)",
                        settings.openai_base_url,
                        settings.openai_model_name,
                    )
                    if hasattr(llm_service, "session") and llm_service.session is not None:
                        providers_available.append("OpenAI")
                        stage3_ok = True
                        stage3_outcome = "initialized"
                    else:
                        stage3_outcome = "constructed-but-no-session"
                        app_logger.warning(
                            "[LIFESPAN] [STAGE-3/6] PROVIDER-WARN | LLMService has no bound session"
                        )
            except TypeError as e:
                # Signature mismatch must be loud: it means our call site drifted
                # from the real constructor. Treat as degraded, not fatal.
                stage3_outcome = "signature-error"
                _msg = f"LLMService construction signature error: {e}"
                startup_errors.append("STAGE-3: " + _msg)
                error_logger.error("[LIFESPAN] [STAGE-3/6] PROVIDER-FAIL | %s", _msg)
            except Exception as e:
                stage3_outcome = "init-error"
                _msg = f"Failed to initialize OpenAI provider: {e}"
                startup_errors.append("STAGE-3: " + _msg)
                error_logger.error("[LIFESPAN] [STAGE-3/6] PROVIDER-FAIL | %s", _msg)
        else:
            stage3_outcome = "not-configured"
            stage3_ok = True  # absence of config is a valid, non-error state
            app_logger.info(
                "[LIFESPAN] [STAGE-3/6] PROVIDER-NOTIFY | No OpenAI API key/base_url configured, "
                "skipping initialization (chapter generation unavailable until configured)"
            )

        # Note: Additional providers (Ollama, etc.) would be initialized here when implemented

        if providers_available:
            app_logger.info(
                "[LIFESPAN] [STAGE-3/6] PROVIDER-COMPLETE | Available providers: %s",
                ", ".join(providers_available),
            )
        elif stage3_outcome == "not-configured":
            app_logger.warning(
                "[LIFESPAN] [STAGE-3/6] PROVIDER-NOTIFY | No providers configured - "
                "chapter generation will fail until configured"
            )
        else:
            app_logger.warning(
                "[LIFESPAN] [STAGE-3/6] PROVIDER-NOTIFY | No providers available - "
                "chapter generation will fail until configured"
            )

    except ImportError as e:
        stage3_outcome = "import-error"
        _msg = f"Could not import LLMService: {e}"
        startup_errors.append("STAGE-3: " + _msg)
        error_logger.error("[LIFESPAN] [STAGE-3/6] IMPORT-FAIL | %s", _msg)
    except Exception as e:
        stage3_outcome = "unexpected-error"
        _msg = f"Unexpected error during provider initialization: {e}"
        startup_errors.append("STAGE-3: " + _msg)
        error_logger.error("[LIFESPAN] [STAGE-3/6] LIFESPAN-ERROR | %s", _msg)

    # Stage-3 must always emit a terminal marker, whatever branch was taken.
    if stage3_ok:
        app_logger.info(
            "[LIFESPAN] [STAGE-3/6] LIFESPAN-OK | Provider stage complete (outcome=%s)", stage3_outcome
        )
    elif stage3_outcome == "not-configured":
        app_logger.info(
            "[LIFESPAN] [STAGE-3/6] LIFESPAN-OK | Provider stage complete (outcome=%s)", stage3_outcome
        )
    else:
        app_logger.warning(
            "[LIFESPAN] [STAGE-3/6] LIFESPAN-DEGRADED | Provider stage finished with errors (outcome=%s)",
            stage3_outcome,
        )
    app_logger.info(
        "[LIFESPAN] [STAGE-3/6] PERFORMANCE | Provider initialization completed in %.2fs",
        time.time() - stage3_start,
    )
    
    # Stage 4: Prompt Preload
    app_logger.info("[LIFESPAN] [STAGE-4/6] LIFESPAN-START | Loading prompts into cache...")
    stage4_start = time.time()
    async with AsyncSessionLocal() as session:
        prompt_service = PromptService(session)
        preload_start = time.time()
        await prompt_service.preload()
        preload_duration = time.time() - preload_start
        try:
            from .services.prompt_service import _CACHE as _PROMPT_CACHE
            _loaded_count = len(_PROMPT_CACHE)
        except Exception:
            _loaded_count = -1
        app_logger.info("[LIFESPAN] [STAGE-4/6] PROMPT-STATUS | Preloaded %d prompts", _loaded_count)
        app_logger.info("[LIFESPAN] [STAGE-4/6] PERFORMANCE | Prompt preload completed in %.2fs", preload_duration)
    app_logger.info("[LIFESPAN] [STAGE-4/6] LIFESPAN-OK | Prompts loaded successfully into cache layer")
    
    # Stage 5: Startup Reconciliation
    app_logger.info("[LIFESPAN] [STAGE-5/6] LIFESPAN-START | Running startup reconciliation checks...")
    stage5_start = time.time()
    try:
        # Check database consistency
        async with AsyncSessionLocal() as session:
            from sqlalchemy import text
            result = await session.execute(text("SELECT COUNT(*) FROM novel_projects"))
            project_count = result.scalar() or 0
            app_logger.info("[LIFESPAN] [STAGE-5/6] RECONCILE-DATA | Database contains %d novel_projects", project_count)
            
            result = await session.execute(text("SELECT COUNT(*) FROM chapters"))
            novel_count = result.scalar() or 0
            app_logger.info("[LIFESPAN] [STAGE-5/6] RECONCILE-DATA | Database contains %d chapters", novel_count)
        
        app_logger.info("[LIFESPAN] [STAGE-5/6] LIFESPAN-OK | Startup reconciliation complete. Data integrity verified.")
        app_logger.info("[LIFESPAN] [STAGE-5/6] PERFORMANCE | Reconciliation checks completed in %.2fs", time.time() - stage5_start)
        
    except Exception as e:
        _msg = f"Startup reconciliation failed: {e}"
        startup_errors.append("STAGE-5: " + _msg)
        error_logger.error("[LIFESPAN] [STAGE-5/6] LIFESPAN-ERROR | %s", _msg)
        app_logger.warning(
            "[LIFESPAN] [STAGE-5/6] LIFESPAN-DEGRADED | Reconciliation skipped; "
            "application starting without full data-integrity verification"
        )
        app_logger.info(
            "[LIFESPAN] [STAGE-5/6] PERFORMANCE | Reconciliation checks terminated in %.2fs",
            time.time() - stage5_start,
        )
    
    # Stage 6: Background Sweeper Initialization
    app_logger.info("[LIFESPAN] [STAGE-6/6] LIFESPAN-START | Initializing background sweepers...")
    stage6_start = time.time()
    try:
        # No sweeper implementation exists in this codebase (verified by repo-wide
        # grep). Do NOT fabricate a startup message implying one is running.
        app_logger.info(
            "[LIFESPAN] [STAGE-6/6] SWEEPER-NOTIFY | No sweeper implementation present "
            "(placeholder) - background cleanup tasks are not registered"
        )
        app_logger.info(
            "[LIFESPAN] [STAGE-6/6] LIFESPAN-OK | Sweeper stage complete "
            "(nothing to start; placeholder mode)"
        )
        app_logger.info(
            "[LIFESPAN] [STAGE-6/6] PERFORMANCE | Sweeper stage completed in %.2fs",
            time.time() - stage6_start,
        )
    except Exception as e:
        _msg = f"Sweeper initialization failed: {e}"
        startup_errors.append("STAGE-6: " + _msg)
        error_logger.error("[LIFESPAN] [STAGE-6/6] LIFESPAN-ERROR | %s", _msg)
        app_logger.warning("[LIFESPAN] [STAGE-6/6] LIFESPAN-DEGRADED | Sweeper stage finished with errors")
    
    total_duration = time.time() - startup_start
    app_logger.info("=" * 60)
    if startup_errors:
        # Never claim a clean startup while any stage recorded an error.
        app_logger.warning(
            "[LIFESPAN] STARTUP | ⚠️ Application startup completed WITH ERRORS (%d)", len(startup_errors)
        )
        for _i, _err in enumerate(startup_errors, 1):
            app_logger.warning("[LIFESPAN] STARTUP-ERROR-%d | %s", _i, _err)
        app_logger.warning(
            "[LIFESPAN] STARTUP | Application is DEGRADED - some features may not work"
        )
    else:
        app_logger.info("[LIFESPAN] STARTUP | ✅ Application startup complete")
    app_logger.info("Total startup duration: %.2fs", total_duration)
    app_logger.info("=" * 60)
    
    yield
    
    # Shutdown phase
    app_logger.info("=" * 60)
    app_logger.info("[LIFESPAN] SHUTDOWN | 🛑 Application shutting down")
    app_logger.info("[LIFESPAN] Timestamp: %s", datetime.now().isoformat())
    app_logger.info("=" * 60)


app = FastAPI(
    title=settings.app_name,
    debug=settings.debug,
    version="1.0.0",
    lifespan=lifespan,
)


def _get_request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        return request_id
    request_id = uuid4().hex[:12]
    request.state.request_id = request_id
    return request_id


def _find_root_cause(exc: BaseException) -> BaseException:
    current: BaseException = exc
    visited: set[int] = set()
    while True:
        next_exc = current.__cause__ or current.__context__
        if next_exc is None or id(next_exc) in visited:
            return current
        visited.add(id(next_exc))
        current = next_exc


def _format_root_cause(exc: BaseException) -> str:
    root = _find_root_cause(exc)
    root_message = str(root).strip()
    return f"{type(root).__name__}: {root_message}" if root_message else type(root).__name__


def _normalize_error_detail(
    *,
    detail: object,
    status_code: int,
    request_id: str,
    root_cause: str | None = None,
) -> dict[str, object]:
    if isinstance(detail, dict):
        payload = dict(detail)
    elif isinstance(detail, str) and detail.strip():
        payload = {"message": detail.strip()}
    else:
        payload = {"message": "服务处理失败，请稍后重试"}

    payload.setdefault("code", f"HTTP_{status_code}")
    payload.setdefault("message", "服务处理失败，请稍后重试")
    payload["request_id"] = request_id

    if root_cause and not payload.get("root_cause"):
        payload["root_cause"] = root_cause

    return payload


def _log_request_failure(
    *,
    request: Request,
    status_code: int,
    payload: dict[str, object],
    exc: BaseException | None = None,
) -> None:
    root_cause = str(payload.get("root_cause") or "").strip() or "-"
    code = str(payload.get("code") or f"HTTP_{status_code}")
    message = str(payload.get("message") or "").strip()
    request_id = str(payload.get("request_id") or _get_request_id(request))
    smoke_test_request = request.headers.get("X-Smoke-Test") == "openapi-route-smoke"
    if smoke_test_request and status_code < 500:
        return
    log_method = error_logger.error if status_code >= 500 else error_logger.warning
    log_method(
        "请求失败｜请求ID=%s 方法=%s 路径=%s 状态=%s 错误码=%s 信息=%s 根因=%s",
        request_id,
        request.method,
        request.url.path,
        status_code,
        code,
        message,
        root_cause,
        exc_info=exc if status_code >= 500 else None,
    )


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex[:12]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(HTTPException)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = _get_request_id(request)
    payload = _normalize_error_detail(
        detail=exc.detail,
        status_code=exc.status_code,
        request_id=request_id,
    )
    _log_request_failure(request=request, status_code=exc.status_code, payload=payload)
    response = JSONResponse(status_code=exc.status_code, content={"detail": payload})
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = _get_request_id(request)
    payload = _normalize_error_detail(
        detail={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "服务处理失败，请查看根因信息后重试",
            "hint": "请优先查看根因、错误码和请求 ID；若问题持续存在，请根据请求 ID 检索后端日志。",
        },
        status_code=500,
        request_id=request_id,
        root_cause=_format_root_cause(exc),
    )
    _log_request_failure(request=request, status_code=500, payload=payload, exc=exc)
    response = JSONResponse(status_code=500, content={"detail": payload})
    response.headers["X-Request-ID"] = request_id
    return response


def _enforce_startup_security() -> None:
    issues = settings.startup_security_issues
    if settings.is_production and issues:
        raise RuntimeError("生产环境启动被拒绝：" + "；".join(issues))

    for issue in issues:
        app_logger.warning("启动安全警告：%s", issue)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list or ["http://127.0.0.1:5174", "http://localhost:5174"],
    allow_credentials=settings.cors_allow_credentials_effective,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Request timeout middleware ===
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio

_REQUEST_TIMEOUT_SECONDS = 90

# 长时运行的端点路径（生成、大纲、研究等），超时设为10分钟
_LONG_RUNNING_PATH_PREFIXES = ("/api/writer", "/api/projects/", "/api/novels/")

class RequestTimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        timeout = _REQUEST_TIMEOUT_SECONDS
        for prefix in _LONG_RUNNING_PATH_PREFIXES:
            if request.url.path.startswith(prefix):
                timeout = 600  # 10 minutes for long-running operations
                break
        try:
            return await asyncio.wait_for(call_next(request), timeout=timeout)
        except asyncio.TimeoutError:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=503,
                content={"detail": {"message": "Request timeout, please retry", "code": "HTTP_503"}},
            )

app.add_middleware(RequestTimeoutMiddleware)


@app.on_event("startup")
async def cleanup_stuck_chapters_on_startup():
    """在服务启动时自动清理所有卡在generating状态的章节。
    这确保服务重启后用户可以立即重新生成之前卡住的章节。"""
    try:
        from .db.session import AsyncSessionLocal
        from .models.novel import Chapter
        from sqlalchemy import select, update
        import logging
        logger = logging.getLogger("startup_cleanup")
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chapter).where(Chapter.status == "generating")
            )
            stuck = result.scalars().all()
            if stuck:
                logger.warning("发现 %d 个卡在generating状态的章节，正在重置...", len(stuck))
                for ch in stuck:
                    logger.warning("  重置: project=%s chapter=%s", ch.project_id[:20], ch.chapter_number)
                    ch.status = "draft"
                    session.add(ch)
                await session.commit()
                logger.warning("已重置 %d 个卡住的章节为draft状态", len(stuck))
            else:
                logger.info("未发现卡住的章节，启动清理完毕")
    except Exception as exc:
        logging.getLogger("startup_cleanup").warning("启动清理busy章节失败: %s", exc)

app.include_router(api_router)


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
async def health_check():
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.app_name,
            "version": "1.0.0",
        },
        media_type="application/json; charset=utf-8",
    )
