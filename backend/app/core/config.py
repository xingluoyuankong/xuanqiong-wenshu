from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, AnyUrl, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
ENV_FILES = (
    str(BACKEND_ROOT / ".env"),
    str(REPO_ROOT / ".env"),
)


class Settings(BaseSettings):
    """应用全局配置。"""

    # -------------------- 基础应用配置 --------------------
    app_name: str = Field(default="玄穹文枢 API", description="FastAPI 文档标题")
    environment: str = Field(default="development", description="当前环境标识")
    debug: bool = Field(default=False, description="是否开启调试模式")
    allow_registration: bool = Field(
        default=False,
        validation_alias=AliasChoices("ALLOW_USER_REGISTRATION", "ALLOW_REGISTRATION"),
        description="是否允许用户自助注册",
    )
    logging_level: str = Field(default="INFO", description="文件日志级别")
    console_logging_level: str = Field(default="WARNING", description="控制台日志级别")
    sqlalchemy_echo: bool = Field(default=False, description="是否输出 SQLAlchemy 原始 SQL")
    log_dir: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("XUANQIONG_WENSHU_LOG_DIR", "LOG_DIR"),
        description="日志目录，未配置时默认 backend/logs",
    )
    file_logging_enabled: bool = Field(default=True, description="是否启用文件日志")
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024 * 256, description="单个日志文件最大字节数")
    log_file_backup_count: int = Field(default=5, ge=1, description="日志滚动备份份数")
    uvicorn_access_log_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("XUANQIONG_WENSHU_UVICORN_ACCESS_LOG", "UVICORN_ACCESS_LOG_ENABLED"),
        description="是否启用 uvicorn access log",
    )
    enable_linuxdo_login: bool = Field(default=False, description="是否启用 Linux.do OAuth 登录")
    cors_allow_origins: str = Field(
        default="http://127.0.0.1:5174,http://localhost:5174",
        description="允许跨域访问的来源",
    )
    cors_allow_credentials: bool = Field(default=True, description="是否允许跨域请求携带凭证")

    # -------------------- 安全配置 --------------------
    secret_key: str = Field(..., description="JWT 密钥")
    jwt_algorithm: str = Field(default="HS256", description="JWT 算法")
    access_token_expire_minutes: int = Field(default=60 * 24 * 7, description="访问令牌过期时间（分钟）")

    # -------------------- 数据库配置 --------------------
    database_url: Optional[str] = Field(default=None, description="完整数据库连接串")
    db_provider: str = Field(default="sqlite", description="数据库类型，仅支持 mysql / sqlite")
    mysql_host: str = Field(default="localhost", description="MySQL 主机")
    mysql_port: int = Field(default=3306, description="MySQL 端口")
    mysql_user: str = Field(default="root", description="MySQL 用户名")
    mysql_password: str = Field(default="", description="MySQL 密码")
    mysql_database: str = Field(default="xuanqiong_wenshu", description="MySQL 数据库名称")
    mysql_pool_size: int = Field(default=15, ge=1, description="MySQL 连接池基础大小")
    mysql_max_overflow: int = Field(default=25, ge=0, description="MySQL 连接池最大溢出连接数")
    mysql_pool_timeout: int = Field(default=30, ge=1, description="MySQL 获取连接超时时间（秒）")
    mysql_pool_recycle: int = Field(default=1800, ge=1, description="MySQL 连接回收时间（秒）")
    mysql_pool_use_lifo: bool = Field(default=True, description="MySQL 连接池是否优先复用最近归还的连接")
    sqlite_db_path: Optional[str] = Field(default=None, description="SQLite 数据库文件路径")

    # -------------------- 管理员初始化 --------------------
    admin_default_username: str = Field(default="admin", description="默认管理员用户名")
    admin_default_password: str = Field(default="ChangeMe123!", description="默认管理员密码")
    admin_default_email: Optional[str] = Field(default=None, description="默认管理员邮箱")

    # -------------------- LLM 配置 --------------------
    openai_api_key: Optional[str] = Field(default=None, description="默认 LLM API Key")
    openai_base_url: Optional[HttpUrl] = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_BASE_URL", "OPENAI_BASE_URL"),
        description="LLM API Base URL",
    )
    openai_model_name: str = Field(default="gpt-4o-mini", description="默认 LLM 模型名称")
    writer_chapter_versions: int = Field(
        default=2,
        ge=1,
        validation_alias=AliasChoices("WRITER_CHAPTER_VERSION_COUNT", "WRITER_CHAPTER_VERSIONS"),
        description="每次生成章节的候选版本数量",
    )
    embedding_provider: str = Field(default="openai", description="嵌入模型提供方，支持 openai / ollama")
    embedding_base_url: Optional[AnyUrl] = Field(default=None, description="嵌入模型 Base URL")
    embedding_api_key: Optional[str] = Field(default=None, description="嵌入模型 API Key")
    embedding_model: str = Field(
        default="text-embedding-3-large",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "VECTOR_EMBEDDING_MODEL"),
        description="默认嵌入模型名称",
    )
    embedding_model_vector_size: Optional[int] = Field(default=None, description="嵌入向量维度")
    ollama_embedding_base_url: Optional[AnyUrl] = Field(default=None, description="Ollama 嵌入服务地址")
    ollama_embedding_model: str = Field(default="nomic-embed-text:latest", description="Ollama 嵌入模型名称")
    vector_db_url: Optional[str] = Field(default=None, description="向量库连接地址")
    vector_db_auth_token: Optional[str] = Field(default=None, description="向量库访问令牌")
    vector_top_k_chunks: int = Field(default=5, ge=0, description="剧情 chunk 检索条数")
    vector_top_k_summaries: int = Field(default=3, ge=0, description="章节摘要检索条数")
    vector_chunk_size: int = Field(default=480, ge=128, description="章节分块目标字数")
    vector_chunk_overlap: int = Field(default=120, ge=0, description="章节分块重叠字数")

    # -------------------- Linux.do OAuth --------------------
    linuxdo_client_id: Optional[str] = Field(default=None, description="Linux.do OAuth Client ID")
    linuxdo_client_secret: Optional[str] = Field(default=None, description="Linux.do OAuth Client Secret")
    linuxdo_redirect_uri: Optional[HttpUrl] = Field(default=None, description="Linux.do OAuth 回调地址")
    linuxdo_auth_url: Optional[HttpUrl] = Field(default=None, description="Linux.do OAuth 授权地址")
    linuxdo_token_url: Optional[HttpUrl] = Field(default=None, description="Linux.do OAuth Token 地址")
    linuxdo_user_info_url: Optional[HttpUrl] = Field(default=None, description="Linux.do 用户信息地址")

    # -------------------- 邮件配置 --------------------
    smtp_server: Optional[str] = Field(default=None, description="SMTP 服务地址")
    smtp_port: int = Field(default=587, description="SMTP 服务端口")
    smtp_username: Optional[str] = Field(default=None, description="SMTP 登录用户名")
    smtp_password: Optional[str] = Field(default=None, description="SMTP 登录密码")
    email_from: Optional[str] = Field(default=None, description="邮件发送方显示名称或邮箱")

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if isinstance(value, str) and value.strip() else value

    @field_validator("db_provider", mode="before")
    @classmethod
    def _normalize_db_provider(cls, value: Optional[str]) -> str:
        candidate = (value or "sqlite").strip().lower()
        if candidate not in {"mysql", "sqlite"}:
            raise ValueError("DB_PROVIDER 仅支持 mysql 或 sqlite")
        return candidate

    @field_validator("embedding_provider", mode="before")
    @classmethod
    def _normalize_embedding_provider(cls, value: Optional[str]) -> str:
        candidate = (value or "openai").strip().lower()
        if candidate not in {"openai", "ollama"}:
            raise ValueError("EMBEDDING_PROVIDER 仅支持 openai 或 ollama")
        return candidate

    @field_validator("logging_level", "console_logging_level", mode="before")
    @classmethod
    def _normalize_logging_level(cls, value: Optional[str]) -> str:
        candidate = (value or "INFO").strip().upper()
        valid_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
        if candidate not in valid_levels:
            raise ValueError("日志级别仅支持 CRITICAL/ERROR/WARNING/INFO/DEBUG/NOTSET")
        return candidate

    @property
    def cors_allow_origins_list(self) -> list[str]:
        raw_value = (self.cors_allow_origins or "").strip()
        if not raw_value:
            return []
        if raw_value == "*":
            return ["*"]
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                import json

                parsed = json.loads(raw_value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        return [item.strip() for item in raw_value.split(",") if item.strip()]

    @property
    def cors_allow_credentials_effective(self) -> bool:
        return bool(self.cors_allow_credentials and self.cors_allow_origins_list != ["*"])

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() == "production"

    @property
    def project_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    @property
    def resolved_log_dir(self) -> Path:
        raw_log_dir = (self.log_dir or "").strip()
        if raw_log_dir:
            candidate = Path(raw_log_dir).expanduser()
            if not candidate.is_absolute():
                candidate = (self.project_root / candidate).resolve()
            return candidate
        return (self.project_root / "logs").resolve()

    @property
    def app_log_file(self) -> Path:
        return self.resolved_log_dir / "backend.log"

    @property
    def error_log_file(self) -> Path:
        return self.resolved_log_dir / "backend-error.log"

    @property
    def admin_password_uses_default(self) -> bool:
        normalized = (self.admin_default_password or "").strip().lower()
        return normalized in {"changeme123!", "请替换为管理员密码", "admin", "password", "123456"}

    @property
    def secret_key_looks_placeholder(self) -> bool:
        normalized = (self.secret_key or "").strip().lower()
        placeholder_tokens = {
            "",
            "changeme",
            "replace-me",
            "replace_this_secret",
            "your-secret-key",
            "your_secret_key",
        }
        return (
            normalized in placeholder_tokens
            or "请替换" in normalized
            or "random-string" in normalized
            or len((self.secret_key or "").strip()) < 32
        )

    @property
    def startup_security_issues(self) -> list[str]:
        issues: list[str] = []
        if self.debug:
            issues.append("DEBUG 必须在生产环境关闭")
        if self.admin_password_uses_default:
            issues.append("ADMIN_DEFAULT_PASSWORD 仍是默认值")
        if self.secret_key_looks_placeholder:
            issues.append("SECRET_KEY 看起来仍是占位值或长度过短")
        return issues

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            url = make_url(self.database_url)
            database = (url.database or "").strip("/")
            normalized = URL.create(
                drivername=url.drivername,
                username=url.username,
                password=url.password,
                host=url.host,
                port=url.port,
                database=database or None,
                query=url.query,
            )
            return normalized.render_as_string(hide_password=False)

        if self.db_provider == "sqlite":
            sqlite_path = (self.sqlite_db_path or "").strip()
            if sqlite_path:
                db_path = Path(sqlite_path).expanduser()
                if not db_path.is_absolute():
                    db_path = (self.project_root / db_path).resolve()
            else:
                db_path = (self.project_root / "storage" / "xuanqiong_wenshu.db").resolve()
            return f"sqlite+aiosqlite:///{db_path}"

        from urllib.parse import quote_plus

        encoded_password = quote_plus(self.mysql_password)
        database = (self.mysql_database or "").strip("/")
        return (
            f"mysql+asyncmy://{self.mysql_user}:{encoded_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{database}"
        )

    @property
    def is_sqlite_backend(self) -> bool:
        return make_url(self.sqlalchemy_database_uri).get_backend_name() == "sqlite"

    @property
    def vector_store_enabled(self) -> bool:
        return bool(self.vector_db_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
