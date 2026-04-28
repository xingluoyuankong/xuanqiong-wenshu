from contextlib import asynccontextmanager
import logging
from logging.config import dictConfig
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


def _configure_logging() -> None:
    global _logging_boot_error

    handlers: dict[str, dict[str, object]] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": settings.console_logging_level,
            "formatter": "console",
            "stream": "ext://sys.stdout",
        }
    }
    shared_handlers = ["console"]

    if settings.file_logging_enabled:
        try:
            settings.resolved_log_dir.mkdir(parents=True, exist_ok=True)
            handlers["app_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": settings.logging_level,
                "formatter": "file",
                "filename": str(settings.app_log_file),
                "maxBytes": settings.log_file_max_bytes,
                "backupCount": settings.log_file_backup_count,
                "encoding": "utf-8",
            }
            handlers["error_file"] = {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "file",
                "filename": str(settings.error_log_file),
                "maxBytes": settings.log_file_max_bytes,
                "backupCount": settings.log_file_backup_count,
                "encoding": "utf-8",
            }
            shared_handlers.extend(["app_file", "error_file"])
        except Exception as exc:  # pragma: no cover - depends on host filesystem
            _logging_boot_error = f"{type(exc).__name__}: {exc}"

    access_log_level = settings.logging_level if settings.uvicorn_access_log_enabled else "WARNING"
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s %(levelname).1s %(name)s | %(message)s",
                "datefmt": "%H:%M:%S",
            },
            "file": {
                "format": "%(asctime)s [%(levelname)s] %(name)s %(filename)s:%(lineno)d | %(message)s",
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
        "日志初始化完成: log_dir=%s console_level=%s access_log=%s",
        settings.resolved_log_dir,
        settings.console_logging_level,
        settings.uvicorn_access_log_enabled,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _enforce_startup_security()
    await init_db()
    async with AsyncSessionLocal() as session:
        prompt_service = PromptService(session)
        await prompt_service.preload()

    app_logger.info("应用启动完成")
    yield
    app_logger.info("应用已关闭")


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
        "Request failed: request_id=%s method=%s path=%s status=%s code=%s message=%s root_cause=%s",
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
