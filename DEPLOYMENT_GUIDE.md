# 玄穹文枢部署指南

> 本文档已从旧项目口径中收口，只保留当前仓库可复用的 Docker 部署说明。

## 1. 当前部署原则

- 不再使用硬编码公网 IP、固定 root 账号、旧仓库地址的远程一键脚本
- 不再使用会自动覆盖服务器本地改动的 `git reset --hard` 流程
- 不再自动写入默认管理员弱密码或占位密钥
- 统一以 `deploy/.env` + `deploy/docker-compose.yml` + `deploy/scripts/deploy_docker.sh` 为当前 Docker 部署入口

## 2. 部署前准备

```bash
cp deploy/.env.example deploy/.env
```

必须至少替换以下配置：

- `SECRET_KEY`
- `ADMIN_DEFAULT_PASSWORD`
- `OPENAI_API_KEY`
- 如启用 MySQL：`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`

建议同时确认：

- `APP_PORT`
- `DB_PROVIDER`
- `OPENAI_API_BASE_URL`
- `OPENAI_MODEL_NAME`

## 3. 执行部署

在项目根目录运行：

```bash
bash deploy/scripts/deploy_docker.sh
```

脚本会执行：

1. 校验 `deploy/.env` 是否存在
2. 校验关键环境变量是否已配置
3. 检查 `docker compose` 是否可用
4. 按 `DB_PROVIDER` 选择 SQLite 或 MySQL 路径
5. 构建并启动容器
6. 对 `app` 容器内 `/api/health` 做健康检查

## 4. 验证服务

部署成功后可检查：

- 前端：`http://localhost:${APP_PORT}`
- 后端 API：`http://localhost:${APP_PORT}/api`
- 健康检查：`http://localhost:${APP_PORT}/api/health`

查看日志：

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f
```

停止服务：

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml down
```

## 5. 关于旧脚本

以下脚本已改为安全提示入口，不再执行真实远程部署：

- `deploy/scripts/quick_deploy.sh`
- `deploy/scripts/server_deploy.sh`

如果确实需要远程自动化部署，请基于当前项目名、真实目标环境、最小权限账号和非破坏性更新策略重新编写。