# 玄穹文枢后端

## Alembic 数据库迁移

Alembic 使用异步 SQLAlchemy 引擎运行，连接串统一读取
app.core.config.settings.sqlalchemy_database_uri。backend/alembic.ini 中的
sqlalchemy.url 仅作为回退展示值，不要把密码写入配置文件。

在仓库根目录执行：

    cd backend
    .\.venv\Scripts\python.exe -m alembic upgrade head

常用命令：

    # 查看当前版本
    .\.venv\Scripts\python.exe -m alembic current

    # 查看迁移头
    .\.venv\Scripts\python.exe -m alembic heads

    # 回退最近一次迁移
    .\.venv\Scripts\python.exe -m alembic downgrade -1

    # 生成迁移 SQL（不实际执行）
    .\.venv\Scripts\python.exe -m alembic upgrade head --sql

临时验证 SQLite 时，在运行命令前设置 DATABASE_URL 和满足配置校验的
SECRET_KEY，例如：

    $env:DATABASE_URL = "sqlite+aiosqlite:///C:/Temp/xuanqiong-alembic.db"
    $env:SECRET_KEY = "a" * 32
    .\.venv\Scripts\python.exe -m alembic upgrade head
    .\.venv\Scripts\python.exe -m alembic downgrade -1

迁移脚本必须保持可逆；生产部署前先在备份或临时数据库执行升级与降级验证。
