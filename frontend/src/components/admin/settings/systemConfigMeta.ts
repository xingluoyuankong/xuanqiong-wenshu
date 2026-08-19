import type { SelectOption } from 'naive-ui'
import { pick } from '@/composables/useLocale'

export type SystemConfigValueType = 'text' | 'number' | 'boolean' | 'select' | 'password' | 'multiline'

/**
 * 参数元数据。key / type / order 是内部真源；
 * label / category / description / options 是展示文案，统一用函数惰性求值，
 * 保证切换界面语言后重新取到对应语言，而不是停在首次求值时的语言。
 */
export interface SystemConfigMeta {
  key: string
  label: () => string
  category: () => string
  description: () => string
  type: SystemConfigValueType
  placeholder?: string
  options?: () => SelectOption[]
  order: number
}

const CATEGORY = {
  app: () => pick('基础应用', 'Application'),
  logging: () => pick('日志', 'Logging'),
  network: () => pick('网络', 'Network'),
  database: () => pick('数据库', 'Database'),
  email: () => pick('邮件', 'Email'),
  writing: () => pick('写作生成', 'Writing'),
  embedding: () => pick('向量检索', 'Embedding'),
}

const boolOptions = (): SelectOption[] => [
  { label: pick('开启 / true', 'On / true'), value: 'true' },
  { label: pick('关闭 / false', 'Off / false'), value: 'false' },
]

const loggingOptions = (): SelectOption[] =>
  ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'].map(item => ({ label: item, value: item }))

const embeddingProviderOptions = (): SelectOption[] => [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Ollama', value: 'ollama' },
]

const dbProviderOptions = (): SelectOption[] => [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'MySQL', value: 'mysql' },
]

const environmentOptions = (): SelectOption[] => [
  { label: pick('开发 / development', 'Development'), value: 'development' },
  { label: pick('生产 / production', 'Production'), value: 'production' },
  { label: pick('测试 / test', 'Test'), value: 'test' },
]

const createMeta = (meta: SystemConfigMeta) => meta

export const SYSTEM_CONFIG_META: SystemConfigMeta[] = [
  createMeta({ key: 'app_name', label: () => pick('应用名称', 'App name'), category: CATEGORY.app, description: () => pick('软件后台显示的应用名，影响管理台、接口文档等展示标题。', 'Application name shown in backend surfaces.'), type: 'text', order: 10 }),
  createMeta({ key: 'environment', label: () => pick('运行环境', 'Environment'), category: CATEGORY.app, description: () => pick('当前运行环境标识，建议明确区分开发、测试、生产。', 'Runtime environment identifier.'), type: 'select', options: environmentOptions, order: 20 }),
  createMeta({ key: 'debug', label: () => pick('调试模式', 'Debug mode'), category: CATEGORY.app, description: () => pick('是否开启调试模式。生产环境必须关闭。', 'Whether debug mode is enabled.'), type: 'boolean', options: boolOptions, order: 30 }),
  createMeta({ key: 'allow_registration', label: () => pick('允许用户注册', 'Allow registration'), category: CATEGORY.app, description: () => pick('是否允许普通用户自行注册账号。', 'Whether self-registration is allowed.'), type: 'boolean', options: boolOptions, order: 40 }),
  createMeta({ key: 'access_token_expire_minutes', label: () => pick('访问令牌有效期（分钟）', 'Access token lifetime (minutes)'), category: CATEGORY.app, description: () => pick('用户登录后访问令牌的有效时长，单位为分钟。', 'Access token lifetime in minutes.'), type: 'number', order: 50 }),

  createMeta({ key: 'logging_level', label: () => pick('文件日志级别', 'File log level'), category: CATEGORY.logging, description: () => pick('写入文件日志的等级。', 'Logging level for file logs.'), type: 'select', options: loggingOptions, order: 60 }),
  createMeta({ key: 'console_logging_level', label: () => pick('控制台日志级别', 'Console log level'), category: CATEGORY.logging, description: () => pick('终端输出日志的等级。', 'Logging level for console output.'), type: 'select', options: loggingOptions, order: 70 }),
  createMeta({ key: 'sqlalchemy_echo', label: () => pick('输出 SQL 调试日志', 'SQL echo'), category: CATEGORY.logging, description: () => pick('是否打印原始 SQL 语句。开发排查时可开启。', 'Whether raw SQL statements are printed.'), type: 'boolean', options: boolOptions, order: 80 }),
  createMeta({ key: 'log_dir', label: () => pick('日志目录', 'Log directory'), category: CATEGORY.logging, description: () => pick('日志文件保存目录。留空时默认写入 backend/logs。', 'Directory used for log files.'), type: 'text', order: 90 }),
  createMeta({ key: 'file_logging_enabled', label: () => pick('启用文件日志', 'File logging enabled'), category: CATEGORY.logging, description: () => pick('是否将日志写入文件。', 'Whether logs are written to files.'), type: 'boolean', options: boolOptions, order: 100 }),
  createMeta({ key: 'log_file_max_bytes', label: () => pick('单日志文件最大大小', 'Max log file size'), category: CATEGORY.logging, description: () => pick('单个日志文件允许的最大字节数，超过后触发轮转。', 'Maximum bytes of a single log file.'), type: 'number', order: 110 }),
  createMeta({ key: 'log_file_backup_count', label: () => pick('日志备份数量', 'Log backup count'), category: CATEGORY.logging, description: () => pick('日志轮转后保留多少份旧文件。', 'How many rotated log files to keep.'), type: 'number', order: 120 }),
  createMeta({ key: 'uvicorn_access_log_enabled', label: () => pick('启用访问日志', 'Access log enabled'), category: CATEGORY.logging, description: () => pick('是否启用 uvicorn access log。', 'Whether uvicorn access log is enabled.'), type: 'boolean', options: boolOptions, order: 130 }),

  createMeta({ key: 'cors_allow_origins', label: () => pick('允许跨域来源', 'CORS allowed origins'), category: CATEGORY.network, description: () => pick('允许访问后台的前端来源地址，多个地址用逗号分隔。', 'Allowed origins for CORS.'), type: 'multiline', order: 140 }),
  createMeta({ key: 'cors_allow_credentials', label: () => pick('跨域允许携带凭证', 'CORS allow credentials'), category: CATEGORY.network, description: () => pick('跨域请求是否允许携带 Cookie / 凭证。', 'Whether credentials are allowed in CORS requests.'), type: 'boolean', options: boolOptions, order: 150 }),
  createMeta({ key: 'db_provider', label: () => pick('数据库类型', 'Database provider'), category: CATEGORY.database, description: () => pick('后台实际使用的数据库类型，目前代码中支持 sqlite / mysql。', 'Database provider used by backend.'), type: 'select', options: dbProviderOptions, order: 160 }),
  createMeta({ key: 'mysql_host', label: () => pick('MySQL 主机', 'MySQL host'), category: CATEGORY.database, description: () => pick('MySQL 数据库主机地址。', 'MySQL host.'), type: 'text', order: 170 }),
  createMeta({ key: 'mysql_port', label: () => pick('MySQL 端口', 'MySQL port'), category: CATEGORY.database, description: () => pick('MySQL 服务端口。', 'MySQL port.'), type: 'number', order: 180 }),
  createMeta({ key: 'mysql_user', label: () => pick('MySQL 用户名', 'MySQL user'), category: CATEGORY.database, description: () => pick('MySQL 登录用户名。', 'MySQL username.'), type: 'text', order: 190 }),
  createMeta({ key: 'mysql_password', label: () => pick('MySQL 密码', 'MySQL password'), category: CATEGORY.database, description: () => pick('MySQL 登录密码。', 'MySQL password.'), type: 'password', order: 200 }),
  createMeta({ key: 'mysql_database', label: () => pick('MySQL 数据库名', 'MySQL database'), category: CATEGORY.database, description: () => pick('MySQL 使用的数据库名称。', 'MySQL database name.'), type: 'text', order: 210 }),
  createMeta({ key: 'mysql_pool_size', label: () => pick('MySQL 连接池基础大小', 'MySQL pool size'), category: CATEGORY.database, description: () => pick('SQLAlchemy MySQL 连接池基础大小。', 'Base size of MySQL connection pool.'), type: 'number', order: 220 }),
  createMeta({ key: 'mysql_max_overflow', label: () => pick('MySQL 最大溢出连接数', 'MySQL max overflow'), category: CATEGORY.database, description: () => pick('连接池满后允许额外创建的连接数量。', 'Maximum overflow connections for MySQL pool.'), type: 'number', order: 230 }),
  createMeta({ key: 'mysql_pool_timeout', label: () => pick('MySQL 取连接超时（秒）', 'MySQL pool timeout (seconds)'), category: CATEGORY.database, description: () => pick('从连接池获取连接的超时时间。', 'Timeout for acquiring a MySQL connection.'), type: 'number', order: 240 }),
  createMeta({ key: 'mysql_pool_recycle', label: () => pick('MySQL 连接回收时间（秒）', 'MySQL pool recycle (seconds)'), category: CATEGORY.database, description: () => pick('连接被强制回收重建前允许存在的秒数。', 'MySQL connection recycle time in seconds.'), type: 'number', order: 250 }),
  createMeta({ key: 'mysql_pool_use_lifo', label: () => pick('MySQL 连接池优先复用最近连接', 'MySQL pool use LIFO'), category: CATEGORY.database, description: () => pick('是否优先复用最近归还的连接。', 'Whether MySQL pool reuses the latest returned connection first.'), type: 'boolean', options: boolOptions, order: 260 }),
  createMeta({ key: 'sqlite_db_path', label: () => pick('SQLite 数据库路径', 'SQLite DB path'), category: CATEGORY.database, description: () => pick('当数据库类型为 sqlite 时实际使用的数据库文件路径。', 'SQLite database file path.'), type: 'text', order: 270 }),

  createMeta({ key: 'smtp.server', label: () => pick('SMTP 服务器', 'SMTP server'), category: CATEGORY.email, description: () => pick('发送邮件验证码所用的 SMTP 服务器地址。', 'SMTP server used for sending emails.'), type: 'text', order: 280 }),
  createMeta({ key: 'smtp.port', label: () => pick('SMTP 端口', 'SMTP port'), category: CATEGORY.email, description: () => pick('SMTP 服务端口。', 'SMTP server port.'), type: 'number', order: 290 }),
  createMeta({ key: 'smtp.username', label: () => pick('SMTP 用户名', 'SMTP username'), category: CATEGORY.email, description: () => pick('SMTP 登录用户名。', 'SMTP login username.'), type: 'text', order: 300 }),
  createMeta({ key: 'smtp.password', label: () => pick('SMTP 密码', 'SMTP password'), category: CATEGORY.email, description: () => pick('SMTP 登录密码。', 'SMTP login password.'), type: 'password', order: 310 }),
  createMeta({ key: 'smtp.from', label: () => pick('发件人显示名', 'Mail from'), category: CATEGORY.email, description: () => pick('邮件显示的发件人名称或邮箱。', 'Display name or sender email.'), type: 'text', order: 320 }),

  createMeta({ key: 'writer_chapter_versions', label: () => pick('候选版本数量（代码主键）', 'Writer chapter versions'), category: CATEGORY.writing, description: () => pick('代码中的章节候选版本数量字段，控制一次生成给出多少版。', 'Code-level chapter version count field.'), type: 'number', order: 330 }),
  createMeta({ key: 'writer.chapter_versions', label: () => pick('候选版本数量', 'Chapter variant count'), category: CATEGORY.writing, description: () => pick('系统配置表中使用的章节候选版本数量键。', 'System config table key for chapter version count.'), type: 'number', order: 340 }),
  createMeta({ key: 'embedding_provider', label: () => pick('嵌入模型提供方（代码主键）', 'Embedding provider'), category: CATEGORY.embedding, description: () => pick('代码中的嵌入模型提供方字段，支持 openai / ollama。', 'Embedding provider used in code.'), type: 'select', options: embeddingProviderOptions, order: 350 }),
  createMeta({ key: 'embedding.provider', label: () => pick('嵌入模型提供方', 'Embedding provider (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的嵌入模型提供方键。', 'System config key for embedding provider.'), type: 'select', options: embeddingProviderOptions, order: 360 }),
  createMeta({ key: 'embedding_api_key', label: () => pick('嵌入模型 API Key（代码主键）', 'Embedding API key'), category: CATEGORY.embedding, description: () => pick('代码中的嵌入模型专用 API Key。', 'Code-level embedding API key.'), type: 'password', order: 370 }),
  createMeta({ key: 'embedding.api_key', label: () => pick('嵌入模型 API Key', 'Embedding API key (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的嵌入模型专用 API Key。', 'System config key for embedding API key.'), type: 'password', order: 380 }),
  createMeta({ key: 'embedding_base_url', label: () => pick('嵌入模型地址（代码主键）', 'Embedding base URL'), category: CATEGORY.embedding, description: () => pick('代码中的嵌入模型 Base URL。', 'Code-level embedding base URL.'), type: 'text', order: 390 }),
  createMeta({ key: 'embedding.base_url', label: () => pick('嵌入模型地址', 'Embedding base URL (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的嵌入模型地址。', 'System config key for embedding base URL.'), type: 'text', order: 400 }),
  createMeta({ key: 'embedding_model', label: () => pick('嵌入模型名称（代码主键）', 'Embedding model'), category: CATEGORY.embedding, description: () => pick('代码中的嵌入模型名称。', 'Code-level embedding model.'), type: 'text', order: 410 }),
  createMeta({ key: 'embedding.model', label: () => pick('嵌入模型名称', 'Embedding model (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的嵌入模型名称。', 'System config key for embedding model.'), type: 'text', order: 420 }),
  createMeta({ key: 'embedding_model_vector_size', label: () => pick('嵌入维度（代码主键）', 'Embedding vector size'), category: CATEGORY.embedding, description: () => pick('代码中的嵌入向量维度。留空时由模型或后端自动判断。', 'Code-level embedding vector size.'), type: 'number', order: 430 }),
  createMeta({ key: 'embedding.model_vector_size', label: () => pick('嵌入维度', 'Embedding dimension'), category: CATEGORY.embedding, description: () => pick('系统配置表中的嵌入向量维度。', 'System config key for embedding dimension.'), type: 'number', order: 440 }),
  createMeta({ key: 'ollama_embedding_base_url', label: () => pick('Ollama 嵌入服务地址（代码主键）', 'Ollama embedding URL'), category: CATEGORY.embedding, description: () => pick('代码中的 Ollama 嵌入服务地址。', 'Code-level Ollama embedding URL.'), type: 'text', order: 450 }),
  createMeta({ key: 'ollama.embedding_base_url', label: () => pick('Ollama 嵌入服务地址', 'Ollama embedding URL (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的 Ollama 嵌入服务地址。', 'System config key for Ollama embedding URL.'), type: 'text', order: 460 }),
  createMeta({ key: 'ollama_embedding_model', label: () => pick('Ollama 嵌入模型（代码主键）', 'Ollama embedding model'), category: CATEGORY.embedding, description: () => pick('代码中的 Ollama 嵌入模型名称。', 'Code-level Ollama embedding model.'), type: 'text', order: 470 }),
  createMeta({ key: 'ollama.embedding_model', label: () => pick('Ollama 嵌入模型', 'Ollama embedding model (config key)'), category: CATEGORY.embedding, description: () => pick('系统配置表中的 Ollama 嵌入模型名称。', 'System config key for Ollama embedding model.'), type: 'text', order: 480 }),
  createMeta({ key: 'vector_db_url', label: () => pick('向量库地址', 'Vector DB URL'), category: CATEGORY.embedding, description: () => pick('向量数据库连接地址。', 'Vector database connection URL.'), type: 'text', order: 490 }),
  createMeta({ key: 'vector_db_auth_token', label: () => pick('向量库访问令牌', 'Vector DB token'), category: CATEGORY.embedding, description: () => pick('向量数据库访问令牌。', 'Access token for vector database.'), type: 'password', order: 500 }),
  createMeta({ key: 'vector_top_k_chunks', label: () => pick('剧情分块检索数量', 'Top K chunks'), category: CATEGORY.embedding, description: () => pick('每次检索返回多少条剧情分块。', 'How many chunks to retrieve.'), type: 'number', order: 510 }),
  createMeta({ key: 'vector_top_k_summaries', label: () => pick('章节摘要检索数量', 'Top K summaries'), category: CATEGORY.embedding, description: () => pick('每次检索返回多少条章节摘要。', 'How many summaries to retrieve.'), type: 'number', order: 520 }),
  createMeta({ key: 'vector_chunk_size', label: () => pick('分块目标字数', 'Chunk size'), category: CATEGORY.embedding, description: () => pick('章节内容切块时每块目标字数。', 'Target size of each chunk.'), type: 'number', order: 530 }),
  createMeta({ key: 'vector_chunk_overlap', label: () => pick('分块重叠字数', 'Chunk overlap'), category: CATEGORY.embedding, description: () => pick('相邻分块之间的重叠字数。', 'Overlap size between chunks.'), type: 'number', order: 540 }),
]

const metaMap = new Map(SYSTEM_CONFIG_META.map(item => [item.key, item]))

export function getSystemConfigMeta(key: string) {
  return metaMap.get(key)
}
