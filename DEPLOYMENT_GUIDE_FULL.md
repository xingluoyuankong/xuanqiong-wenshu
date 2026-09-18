# 玄穹文枢完整部署指南

> 这是当前项目的完整 Docker 部署说明，已移除旧项目名、旧公网 IP、旧仓库地址以及高风险远程一键部署流程。

## 目录

1. 环境要求
2. 部署原则
3. 快速部署
4. 手动部署
5. 数据库迁移
6. 配置说明
7. 健康检查
8. 日志查看
9. 回滚建议
10. 常见问题

---

## 1. 环境要求

### 服务器配置

- 操作系统：Ubuntu 22.04 或更高版本
- CPU：2 核心或以上
- 内存：4GB 或以上
- 磁盘：20GB 可用空间
- 网络：可访问 Docker 镜像源与所需模型服务

### 软件依赖

- Docker 20.10+
- Docker Compose v2
- Git 2.x
- MySQL 8.0（仅在 `DB_PROVIDER=mysql` 时需要）

---

## 2. 部署原则

当前部署口径以安全和可回溯为先：

- 不使用硬编码公网 IP、root 账号、旧仓库地址的远程一键脚本
- 不使用 `git reset --hard` 这类会覆盖服务器本地改动的破坏性更新方式
- 不自动写入默认管理员弱密码
- 所有 Docker 部署统一走：
  - `deploy/.env`
  - `deploy/docker-compose.yml`
  - `deploy/scripts/deploy_docker.sh`

> `deploy/scripts/quick_deploy.sh` 与 `deploy/scripts/server_deploy.sh` 现在只保留安全提示，不再执行真实远程部署。

---

## 3. 快速部署

在目标机器已准备好当前仓库工作目录的前提下：

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
bash deploy/scripts/deploy_docker.sh
```

最少必须替换：

- `SECRET_KEY`
- `ADMIN_DEFAULT_PASSWORD`
- `OPENAI_API_KEY`
- 如果使用 MySQL：`MYSQL_PASSWORD`、`MYSQL_ROOT_PASSWORD`

---

## 4. 手动部署

### 4.1 准备环境

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | bash
sudo systemctl enable docker
sudo systemctl start docker
sudo apt install -y docker-compose-plugin

docker --version
docker compose version
```

### 4.2 准备仓库

```bash
cd /srv
# 这里改成你自己的仓库来源或现有工作目录
# git clone <your-repo-url> xuanqiong-wenshu
cd xuanqiong-wenshu
```

### 4.3 配置环境变量

```bash
cp deploy/.env.example deploy/.env
nano deploy/.env
```

建议重点核对：

```env
SECRET_KEY=请替换为真实随机密钥
APP_PORT=8088
DB_PROVIDER=sqlite
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=请替换为管理员密码
OPENAI_API_KEY=sk-...
OPENAI_API_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL_NAME=gpt-4o-mini
```

如果切换到 MySQL：

```env
DB_PROVIDER=mysql
MYSQL_HOST=db
MYSQL_PORT=3306
MYSQL_USER=xuanqiong_wenshu
MYSQL_PASSWORD=请替换为真实数据库密码
MYSQL_DATABASE=xuanqiong_wenshu
MYSQL_ROOT_PASSWORD=请替换为真实 root 密码
```

### 4.4 启动服务

```bash
bash deploy/scripts/deploy_docker.sh
```

---

## 5. 数据库迁移

### 自动迁移

如果使用 MySQL，可按需运行：

```bash
bash deploy/scripts/run_migrations.sh
bash deploy/scripts/verify_migration.sh
```

### 说明

- SQLite 默认走快速启动路径，通常无需单独迁移步骤
- `deploy/scripts/deploy_docker.sh` 会根据 `DB_PROVIDER` 决定是否启用 MySQL profile
- 当前项目还包含运行期 schema 补齐逻辑，见 `backend/app/db/init_db.py`

---

## 6. 配置说明

### 核心配置

| 配置项 | 说明 |
| --- | --- |
| `SECRET_KEY` | 应用密钥，必填 |
| `ENVIRONMENT` | 运行环境，通常为 `production` |
| `DEBUG` | 生产建议为 `false` |
| `APP_PORT` | 应用对外端口 |

### 数据库配置

| 配置项 | 说明 |
| --- | --- |
| `DB_PROVIDER` | `sqlite` 或 `mysql` |
| `MYSQL_HOST` | MySQL 主机 |
| `MYSQL_PORT` | MySQL 端口 |
| `MYSQL_USER` | MySQL 用户 |
| `MYSQL_PASSWORD` | MySQL 密码 |
| `MYSQL_DATABASE` | MySQL 数据库名 |
| `MYSQL_ROOT_PASSWORD` | 内置 MySQL 初始化用 root 密码 |

### LLM 配置

| 配置项 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | 主生成模型 API Key |
| `OPENAI_API_BASE_URL` | 模型服务地址 |
| `OPENAI_MODEL_NAME` | 主生成模型名 |
| `WRITER_CHAPTER_VERSION_COUNT` | 章节候选版本数 |
| `EMBEDDING_PROVIDER` | `openai` 或 `ollama` |
| `EMBEDDING_MODEL` | 默认嵌入模型 |

---

## 7. 健康检查

部署完成后检查：

```bash
curl http://127.0.0.1:${APP_PORT}/api/health
```

或查看容器内状态：

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml ps
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs --tail=100 app
```

---

## 8. 日志查看

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f
```

仅看应用：

```bash
docker compose --env-file deploy/.env -f deploy/docker-compose.yml logs -f app
```

---

## 9. 回滚建议

当前建议采用“保留历史发布目录 / 镜像 tag / 数据备份”的非破坏性回滚策略，而不是在服务器上直接 `git reset --hard`。

最低要求：

- 回滚前先备份数据库
- 记录当前镜像 tag 或提交号
- 确认 `deploy/.env` 与数据目录可复原

如果是容器级回滚，应优先通过已验证镜像版本恢复，而不是依赖旧脚本中的强覆盖 git 操作。

---

## 10. 常见问题

### Q1：脚本提示缺少 `deploy/.env`
先复制示例配置：

```bash
cp deploy/.env.example deploy/.env
```

### Q2：脚本提示缺少 `OPENAI_API_KEY`
说明还在使用示例配置或未填真实密钥，请先补全配置再部署。

### Q3：为什么不再提供旧版远程一键部署？
因为旧脚本包含硬编码公网主机、root 登录、默认弱口令和破坏性代码覆盖行为，不适合作为当前项目正式交付口径。

### Q4：如何做自动化远程部署？
建议单独维护面向真实环境的 CI/CD 或运维脚本，要求至少满足：

- 目标主机与仓库来源可配置
- 使用最小权限账号
- 不使用 `git reset --hard`
- 不自动写入默认密码
- 有明确的失败回滚与日志留存机制
