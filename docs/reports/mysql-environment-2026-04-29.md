# MySQL 环境隔离与修复记录（2026-04-29）

- 配置文件：ackend/.env
- 正式 DB_PROVIDER：mysql
- MYSQL_HOST：127.0.0.1
- MYSQL_PORT：3309
- 当前端口状态：$mysqlStatus
- 启动脚本：	ools/start_local_mysql.ps1
- 隔离策略：
  - 正式启动 start.ps1 使用本地 MySQL 3309。
  - 自动化 smoke/E2E 不污染正式 MySQL，分别通过环境变量覆盖为 SQLite：
    - 	ools/dev-smoke.ps1 使用 storage/xuanqiong_wenshu_smoke.db
    - 	ools/e2e-inspiration-to-export.ps1 使用 storage/xuanqiong_wenshu_e2e.db
- 连接验证：DB_PROVIDER=mysql 下后端 SQLAlchemy select 1 已通过。

结论：MySQL 正式环境已恢复到 3309 监听并可连接；测试链路继续使用 SQLite 隔离库，避免托管测试污染正式数据。
