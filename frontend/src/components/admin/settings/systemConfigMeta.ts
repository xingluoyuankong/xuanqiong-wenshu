import type { SelectOption } from 'naive-ui'

export type SystemConfigValueType = 'text' | 'number' | 'boolean' | 'select' | 'password' | 'multiline'

export interface SystemConfigMeta {
  key: string
  labelZh: string
  labelEn: string
  categoryZh: string
  categoryEn: string
  descriptionZh: string
  descriptionEn: string
  type: SystemConfigValueType
  placeholder?: string
  options?: SelectOption[]
  order: number
}

const boolOptions: SelectOption[] = [
  { label: '开启 / true', value: 'true' },
  { label: '关闭 / false', value: 'false' },
]

const loggingOptions: SelectOption[] = ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG', 'NOTSET'].map(item => ({ label: item, value: item }))
const embeddingProviderOptions: SelectOption[] = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Ollama', value: 'ollama' },
]
const dbProviderOptions: SelectOption[] = [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'MySQL', value: 'mysql' },
]
const environmentOptions: SelectOption[] = [
  { label: '开发 / development', value: 'development' },
  { label: '生产 / production', value: 'production' },
  { label: '测试 / test', value: 'test' },
]

const createMeta = (meta: SystemConfigMeta) => meta

export const SYSTEM_CONFIG_META: SystemConfigMeta[] = [
  createMeta({ key: 'app_name', labelZh: '应用名称', labelEn: 'App Name', categoryZh: '基础应用', categoryEn: 'Application', descriptionZh: '软件后台显示的应用名，影响管理台、接口文档等展示标题。', descriptionEn: 'Application name shown in backend surfaces.', type: 'text', order: 10 }),
  createMeta({ key: 'environment', labelZh: '运行环境', labelEn: 'Environment', categoryZh: '基础应用', categoryEn: 'Application', descriptionZh: '当前运行环境标识，建议明确区分开发、测试、生产。', descriptionEn: 'Runtime environment identifier.', type: 'select', options: environmentOptions, order: 20 }),
  createMeta({ key: 'debug', labelZh: '调试模式', labelEn: 'Debug Mode', categoryZh: '基础应用', categoryEn: 'Application', descriptionZh: '是否开启调试模式。生产环境必须关闭。', descriptionEn: 'Whether debug mode is enabled.', type: 'boolean', options: boolOptions, order: 30 }),
  createMeta({ key: 'allow_registration', labelZh: '允许用户注册', labelEn: 'Allow Registration', categoryZh: '基础应用', categoryEn: 'Application', descriptionZh: '是否允许普通用户自行注册账号。', descriptionEn: 'Whether self-registration is allowed.', type: 'boolean', options: boolOptions, order: 40 }),
  createMeta({ key: 'access_token_expire_minutes', labelZh: '访问令牌有效期（分钟）', labelEn: 'Access Token Expire Minutes', categoryZh: '基础应用', categoryEn: 'Application', descriptionZh: '用户登录后访问令牌的有效时长，单位为分钟。', descriptionEn: 'Access token lifetime in minutes.', type: 'number', order: 50 }),

  createMeta({ key: 'logging_level', labelZh: '文件日志级别', labelEn: 'File Log Level', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '写入文件日志的等级。', descriptionEn: 'Logging level for file logs.', type: 'select', options: loggingOptions, order: 60 }),
  createMeta({ key: 'console_logging_level', labelZh: '控制台日志级别', labelEn: 'Console Log Level', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '终端输出日志的等级。', descriptionEn: 'Logging level for console output.', type: 'select', options: loggingOptions, order: 70 }),
  createMeta({ key: 'sqlalchemy_echo', labelZh: '输出 SQL 调试日志', labelEn: 'SQL Echo', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '是否打印原始 SQL 语句。开发排查时可开启。', descriptionEn: 'Whether raw SQL statements are printed.', type: 'boolean', options: boolOptions, order: 80 }),
  createMeta({ key: 'log_dir', labelZh: '日志目录', labelEn: 'Log Directory', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '日志文件保存目录。留空时默认写入 backend/logs。', descriptionEn: 'Directory used for log files.', type: 'text', order: 90 }),
  createMeta({ key: 'file_logging_enabled', labelZh: '启用文件日志', labelEn: 'File Logging Enabled', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '是否将日志写入文件。', descriptionEn: 'Whether logs are written to files.', type: 'boolean', options: boolOptions, order: 100 }),
  createMeta({ key: 'log_file_max_bytes', labelZh: '单日志文件最大大小', labelEn: 'Max Log File Size', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '单个日志文件允许的最大字节数，超过后触发轮转。', descriptionEn: 'Maximum bytes of a single log file.', type: 'number', order: 110 }),
  createMeta({ key: 'log_file_backup_count', labelZh: '日志备份数量', labelEn: 'Log Backup Count', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '日志轮转后保留多少份旧文件。', descriptionEn: 'How many rotated log files to keep.', type: 'number', order: 120 }),
  createMeta({ key: 'uvicorn_access_log_enabled', labelZh: '启用访问日志', labelEn: 'Access Log Enabled', categoryZh: '日志', categoryEn: 'Logging', descriptionZh: '是否启用 uvicorn access log。', descriptionEn: 'Whether uvicorn access log is enabled.', type: 'boolean', options: boolOptions, order: 130 }),

  createMeta({ key: 'cors_allow_origins', labelZh: '允许跨域来源', labelEn: 'CORS Allowed Origins', categoryZh: '网络', categoryEn: 'Network', descriptionZh: '允许访问后台的前端来源地址，多个地址用逗号分隔。', descriptionEn: 'Allowed origins for CORS.', type: 'multiline', order: 140 }),
  createMeta({ key: 'cors_allow_credentials', labelZh: '跨域允许携带凭证', labelEn: 'CORS Allow Credentials', categoryZh: '网络', categoryEn: 'Network', descriptionZh: '跨域请求是否允许携带 Cookie / 凭证。', descriptionEn: 'Whether credentials are allowed in CORS requests.', type: 'boolean', options: boolOptions, order: 150 }),

  createMeta({ key: 'db_provider', labelZh: '数据库类型', labelEn: 'Database Provider', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '后台实际使用的数据库类型，目前代码中支持 sqlite / mysql。', descriptionEn: 'Database provider used by backend.', type: 'select', options: dbProviderOptions, order: 160 }),
  createMeta({ key: 'mysql_host', labelZh: 'MySQL 主机', labelEn: 'MySQL Host', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'MySQL 数据库主机地址。', descriptionEn: 'MySQL host.', type: 'text', order: 170 }),
  createMeta({ key: 'mysql_port', labelZh: 'MySQL 端口', labelEn: 'MySQL Port', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'MySQL 服务端口。', descriptionEn: 'MySQL port.', type: 'number', order: 180 }),
  createMeta({ key: 'mysql_user', labelZh: 'MySQL 用户名', labelEn: 'MySQL User', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'MySQL 登录用户名。', descriptionEn: 'MySQL username.', type: 'text', order: 190 }),
  createMeta({ key: 'mysql_password', labelZh: 'MySQL 密码', labelEn: 'MySQL Password', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'MySQL 登录密码。', descriptionEn: 'MySQL password.', type: 'password', order: 200 }),
  createMeta({ key: 'mysql_database', labelZh: 'MySQL 数据库名', labelEn: 'MySQL Database', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'MySQL 使用的数据库名称。', descriptionEn: 'MySQL database name.', type: 'text', order: 210 }),
  createMeta({ key: 'mysql_pool_size', labelZh: 'MySQL 连接池基础大小', labelEn: 'MySQL Pool Size', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: 'SQLAlchemy MySQL 连接池基础大小。', descriptionEn: 'Base size of MySQL connection pool.', type: 'number', order: 220 }),
  createMeta({ key: 'mysql_max_overflow', labelZh: 'MySQL 最大溢出连接数', labelEn: 'MySQL Max Overflow', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '连接池满后允许额外创建的连接数量。', descriptionEn: 'Maximum overflow connections for MySQL pool.', type: 'number', order: 230 }),
  createMeta({ key: 'mysql_pool_timeout', labelZh: 'MySQL 取连接超时（秒）', labelEn: 'MySQL Pool Timeout', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '从连接池获取连接的超时时间。', descriptionEn: 'Timeout for acquiring a MySQL connection.', type: 'number', order: 240 }),
  createMeta({ key: 'mysql_pool_recycle', labelZh: 'MySQL 连接回收时间（秒）', labelEn: 'MySQL Pool Recycle', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '连接被强制回收重建前允许存在的秒数。', descriptionEn: 'MySQL connection recycle time in seconds.', type: 'number', order: 250 }),
  createMeta({ key: 'mysql_pool_use_lifo', labelZh: 'MySQL 连接池优先复用最近连接', labelEn: 'MySQL Pool Use LIFO', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '是否优先复用最近归还的连接。', descriptionEn: 'Whether MySQL pool reuses the latest returned connection first.', type: 'boolean', options: boolOptions, order: 260 }),
  createMeta({ key: 'sqlite_db_path', labelZh: 'SQLite 数据库路径', labelEn: 'SQLite DB Path', categoryZh: '数据库', categoryEn: 'Database', descriptionZh: '当数据库类型为 sqlite 时实际使用的数据库文件路径。', descriptionEn: 'SQLite database file path.', type: 'text', order: 270 }),

  createMeta({ key: 'smtp.server', labelZh: 'SMTP 服务器', labelEn: 'SMTP Server', categoryZh: '邮件', categoryEn: 'Email', descriptionZh: '发送邮件验证码所用的 SMTP 服务器地址。', descriptionEn: 'SMTP server used for sending emails.', type: 'text', order: 280 }),
  createMeta({ key: 'smtp.port', labelZh: 'SMTP 端口', labelEn: 'SMTP Port', categoryZh: '邮件', categoryEn: 'Email', descriptionZh: 'SMTP 服务端口。', descriptionEn: 'SMTP server port.', type: 'number', order: 290 }),
  createMeta({ key: 'smtp.username', labelZh: 'SMTP 用户名', labelEn: 'SMTP Username', categoryZh: '邮件', categoryEn: 'Email', descriptionZh: 'SMTP 登录用户名。', descriptionEn: 'SMTP login username.', type: 'text', order: 300 }),
  createMeta({ key: 'smtp.password', labelZh: 'SMTP 密码', labelEn: 'SMTP Password', categoryZh: '邮件', categoryEn: 'Email', descriptionZh: 'SMTP 登录密码。', descriptionEn: 'SMTP login password.', type: 'password', order: 310 }),
  createMeta({ key: 'smtp.from', labelZh: '发件人显示名', labelEn: 'Mail From', categoryZh: '邮件', categoryEn: 'Email', descriptionZh: '邮件显示的发件人名称或邮箱。', descriptionEn: 'Display name or sender email.', type: 'text', order: 320 }),

  createMeta({ key: 'writer_chapter_versions', labelZh: '候选版本数量（代码主键）', labelEn: 'Writer Chapter Versions', categoryZh: '写作生成', categoryEn: 'Writing', descriptionZh: '代码中的章节候选版本数量字段，控制一次生成给出多少版。', descriptionEn: 'Code-level chapter version count field.', type: 'number', order: 330 }),
  createMeta({ key: 'writer.chapter_versions', labelZh: '候选版本数量', labelEn: 'Chapter Variant Count', categoryZh: '写作生成', categoryEn: 'Writing', descriptionZh: '系统配置表中使用的章节候选版本数量键。', descriptionEn: 'System config table key for chapter version count.', type: 'number', order: 340 }),

  createMeta({ key: 'embedding_provider', labelZh: '嵌入模型提供方（代码主键）', labelEn: 'Embedding Provider', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的嵌入模型提供方字段，支持 openai / ollama。', descriptionEn: 'Embedding provider used in code.', type: 'select', options: embeddingProviderOptions, order: 350 }),
  createMeta({ key: 'embedding.provider', labelZh: '嵌入模型提供方', labelEn: 'Embedding Provider (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的嵌入模型提供方键。', descriptionEn: 'System config key for embedding provider.', type: 'select', options: embeddingProviderOptions, order: 360 }),
  createMeta({ key: 'embedding_api_key', labelZh: '嵌入模型 API Key（代码主键）', labelEn: 'Embedding API Key', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的嵌入模型专用 API Key。', descriptionEn: 'Code-level embedding API key.', type: 'password', order: 370 }),
  createMeta({ key: 'embedding.api_key', labelZh: '嵌入模型 API Key', labelEn: 'Embedding API Key (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的嵌入模型专用 API Key。', descriptionEn: 'System config key for embedding API key.', type: 'password', order: 380 }),
  createMeta({ key: 'embedding_base_url', labelZh: '嵌入模型地址（代码主键）', labelEn: 'Embedding Base URL', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的嵌入模型 Base URL。', descriptionEn: 'Code-level embedding base URL.', type: 'text', order: 390 }),
  createMeta({ key: 'embedding.base_url', labelZh: '嵌入模型地址', labelEn: 'Embedding Base URL (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的嵌入模型地址。', descriptionEn: 'System config key for embedding base URL.', type: 'text', order: 400 }),
  createMeta({ key: 'embedding_model', labelZh: '嵌入模型名称（代码主键）', labelEn: 'Embedding Model', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的嵌入模型名称。', descriptionEn: 'Code-level embedding model.', type: 'text', order: 410 }),
  createMeta({ key: 'embedding.model', labelZh: '嵌入模型名称', labelEn: 'Embedding Model (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的嵌入模型名称。', descriptionEn: 'System config key for embedding model.', type: 'text', order: 420 }),
  createMeta({ key: 'embedding_model_vector_size', labelZh: '嵌入维度（代码主键）', labelEn: 'Embedding Vector Size', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的嵌入向量维度。留空时由模型或后端自动判断。', descriptionEn: 'Code-level embedding vector size.', type: 'number', order: 430 }),
  createMeta({ key: 'embedding.model_vector_size', labelZh: '嵌入维度', labelEn: 'Embedding Dimension', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的嵌入向量维度。', descriptionEn: 'System config key for embedding dimension.', type: 'number', order: 440 }),
  createMeta({ key: 'ollama_embedding_base_url', labelZh: 'Ollama 嵌入服务地址（代码主键）', labelEn: 'Ollama Embedding URL', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的 Ollama 嵌入服务地址。', descriptionEn: 'Code-level Ollama embedding URL.', type: 'text', order: 450 }),
  createMeta({ key: 'ollama.embedding_base_url', labelZh: 'Ollama 嵌入服务地址', labelEn: 'Ollama Embedding URL (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的 Ollama 嵌入服务地址。', descriptionEn: 'System config key for Ollama embedding URL.', type: 'text', order: 460 }),
  createMeta({ key: 'ollama_embedding_model', labelZh: 'Ollama 嵌入模型（代码主键）', labelEn: 'Ollama Embedding Model', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '代码中的 Ollama 嵌入模型名称。', descriptionEn: 'Code-level Ollama embedding model.', type: 'text', order: 470 }),
  createMeta({ key: 'ollama.embedding_model', labelZh: 'Ollama 嵌入模型', labelEn: 'Ollama Embedding Model (Config Key)', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '系统配置表中的 Ollama 嵌入模型名称。', descriptionEn: 'System config key for Ollama embedding model.', type: 'text', order: 480 }),
  createMeta({ key: 'vector_db_url', labelZh: '向量库地址', labelEn: 'Vector DB URL', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '向量数据库连接地址。', descriptionEn: 'Vector database connection URL.', type: 'text', order: 490 }),
  createMeta({ key: 'vector_db_auth_token', labelZh: '向量库访问令牌', labelEn: 'Vector DB Token', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '向量数据库访问令牌。', descriptionEn: 'Access token for vector database.', type: 'password', order: 500 }),
  createMeta({ key: 'vector_top_k_chunks', labelZh: '剧情分块检索数量', labelEn: 'Top K Chunks', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '每次检索返回多少条剧情分块。', descriptionEn: 'How many chunks to retrieve.', type: 'number', order: 510 }),
  createMeta({ key: 'vector_top_k_summaries', labelZh: '章节摘要检索数量', labelEn: 'Top K Summaries', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '每次检索返回多少条章节摘要。', descriptionEn: 'How many summaries to retrieve.', type: 'number', order: 520 }),
  createMeta({ key: 'vector_chunk_size', labelZh: '分块目标字数', labelEn: 'Chunk Size', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '章节内容切块时每块目标字数。', descriptionEn: 'Target size of each chunk.', type: 'number', order: 530 }),
  createMeta({ key: 'vector_chunk_overlap', labelZh: '分块重叠字数', labelEn: 'Chunk Overlap', categoryZh: '向量检索', categoryEn: 'Embedding', descriptionZh: '相邻分块之间的重叠字数。', descriptionEn: 'Overlap size between chunks.', type: 'number', order: 540 }),
]

const metaMap = new Map(SYSTEM_CONFIG_META.map(item => [item.key, item]))

export function getSystemConfigMeta(key: string) {
  return metaMap.get(key)
}
