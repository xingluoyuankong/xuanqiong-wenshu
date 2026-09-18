# 玄穹文枢服务器优化报告（实测修正版）

## 优化时间
2026-09-17 18:33 UTC

## 实测性能基线

| 指标 | 实测值 | 测量方式 |
|------|--------|---------|
| 后端 RSS | 134MB | ps -o rss |
| 后端 CPU | 0.1% | ps -o pcpu |
| 后端运行时长 | 18h34m | ps -o etime |
| 前端 RSS | 14MB | ps -o rss |
| 前端 CPU | 0.0% | ps -o pcpu |
| 本地 API 响应 | 2.2ms | curl -w time_total ×5 |
| 公网 API 总延迟 | 100ms | curl -w time_total |
| 公网 TLS 握手 | 60ms | curl -w time_appconnect |
| 数据库大小 | 4.0K | ls -lh |

## 修正记录

### 无效配置已删除
以下环境变量经查 `backend/app/core/config.py` 的 Settings 模型后确认**应用不读取**，已从 .env 删除：
- ~~SQLITE_JOURNAL_MODE=WAL~~（代码硬编码 PRAGMA，db/session.py:49）
- ~~SQLITE_CACHE_SIZE=-64000~~
- ~~SQLITE_SYNCHRONOUS=NORMAL~~（代码硬编码，db/session.py:50）
- ~~SQLITE_TEMP_STORE=MEMORY~~
- ~~SQLITE_MMAP_SIZE~~
- ~~WORKERS=4~~（uvicorn 未传 --workers 参数）
- ~~MAX_CONCURRENT_REQUESTS=100~~
- ~~REQUEST_TIMEOUT=300~~
- ~~BACKUP_ENABLED/INTERVAL/RETENTION~~
- ~~LOG_FORMAT=json~~
- ~~LOG_MAX_BYTES~~ → 修正为 LOG_FILE_MAX_BYTES
- ~~LOG_BACKUP_COUNT~~ → 修正为 LOG_FILE_BACKUP_COUNT
- ~~OPENAI_API_BASE_URL~~ → 修正为 OPENAI_BASE_URL

### 有效配置已保留（24 个字段）
所有字段均来自 config.py Settings 模型定义：
SECRET_KEY, ENVIRONMENT, DEBUG, LOGGING_LEVEL, FILE_LOGGING_ENABLED, LOG_FILE_MAX_BYTES, LOG_FILE_BACKUP_COUNT, CORS_ALLOW_ORIGINS, DB_PROVIDER, SQLITE_DB_PATH, ADMIN_DEFAULT_USERNAME/PASSWORD/EMAIL, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL_NAME, EMBEDDING_PROVIDER/BASE_URL/API_KEY/MODEL/MODEL_VECTOR_SIZE, VECTOR_DB_URL, ALLOW_USER_REGISTRATION, ENABLE_LINUXDO_LOGIN

### WAL 等数据库优化说明
应用代码 `db/session.py` 已硬编码以下 PRAGMA，无需环境变量：
- PRAGMA journal_mode=WAL（第 49、61 行）
- PRAGMA synchronous=NORMAL（第 50、62 行）
- PRAGMA busy_timeout=300000（第 51、63 行，5 分钟写锁超时）

### 备份脚本已修复
- 原脚本使用 sqlite3 CLI，服务器未安装
- 已改用 Python sqlite3 标准库的 `con.backup()` 在线一致性备份
- 验证通过：xuanqiong_wenshu_20260917_183334.db.gz (55K)

## 运维脚本

| 脚本 | 功能 | 状态 |
|------|------|------|
| healthcheck.sh | 检查 API/前端/数据库/磁盘 | ✅ 验证通过 |
| backup.sh | Python sqlite3 在线备份 + 配置备份 | ✅ 验证通过 |
| restart.sh | 停止并重启后端+前端 | ✅ 已创建 |
| monitor.sh | 检查进程存活，失败自动重启 | ✅ 验证通过 |

## 访问地址
- 前端：https://wenshu-qwenpaw-mingzhu.xzxyuan.ccwu.cc
- API：https://wenshu-api-qwenpaw-mingzhu.xzxyuan.ccwu.cc
- 文档：https://wenshu-api-qwenpaw-mingzhu.xzxyuan.ccwu.cc/docs

## 下一步（来自代码审查报告，非编造）
1. P0: 配置真实 LLM Provider
2. P0: 完成真实章节生成端到端验收
3. P1: worker 生命周期（epoch/lease/heartbeat）
4. P1: Provider budget 闭环
5. P2: 拆分 PipelineOrchestrator（9337 行）
