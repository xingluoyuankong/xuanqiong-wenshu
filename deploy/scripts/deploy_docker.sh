#!/bin/bash
# Docker 部署脚本

set -e

echo "========================================="
echo "玄穹文枢 Docker 部署脚本"
echo "========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否在项目根目录
if [ ! -f "deploy/docker-compose.yml" ]; then
    echo -e "${RED}错误：请在项目根目录执行此脚本${NC}"
    exit 1
fi

ENV_FILE="deploy/.env"
ENV_EXAMPLE="deploy/.env.example"

# 检查 .env 文件
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}警告：未找到 $ENV_FILE${NC}"
    echo "是否使用示例配置创建 $ENV_FILE？(y/n)"
    read -r response
    if [ "$response" = "y" ]; then
        if [ -f "$ENV_EXAMPLE" ]; then
            cp "$ENV_EXAMPLE" "$ENV_FILE"
            echo -e "${GREEN}✓ 已创建 $ENV_FILE，请编辑后重新运行脚本${NC}"
            exit 0
        else
            echo -e "${RED}错误：未找到 $ENV_EXAMPLE${NC}"
            exit 1
        fi
    else
        echo -e "${RED}部署已取消${NC}"
        exit 1
    fi
fi

# 加载环境变量
set -a
source "$ENV_FILE"
set +a

echo ""
echo "检查必需的环境变量..."
REQUIRED_VARS=(
    "SECRET_KEY"
    "ADMIN_DEFAULT_PASSWORD"
    "OPENAI_API_KEY"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}✗ 缺少环境变量: $var${NC}"
        exit 1
    else
        echo -e "${GREEN}✓ $var 已设置${NC}"
    fi
done

# 检查 Docker 是否安装
echo ""
echo "检查 Docker 环境..."
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误：未安装 Docker${NC}"
    echo "请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✓ Docker 已安装${NC}"

if ! docker compose version &> /dev/null; then
    echo -e "${RED}错误：当前环境缺少 docker compose 子命令${NC}"
    echo "请先安装或启用 Docker Compose v2"
    exit 1
fi
echo -e "${GREEN}✓ docker compose 已可用${NC}"

# 确定使用的数据库
DB_PROVIDER="${DB_PROVIDER:-sqlite}"
echo ""
echo "数据库配置："
echo "  提供商: $DB_PROVIDER"

if [ "$DB_PROVIDER" = "mysql" ]; then
    if [ -z "${MYSQL_PASSWORD}" ]; then
        echo -e "${RED}✗ DB_PROVIDER=mysql 时必须设置 MYSQL_PASSWORD${NC}"
        exit 1
    fi
    COMPOSE_PROFILES="--profile mysql"
    echo "  MySQL 主机: ${MYSQL_HOST:-db}"
    echo "  MySQL 端口: ${MYSQL_PORT:-3306}"
    echo "  MySQL 数据库: ${MYSQL_DATABASE:-xuanqiong_wenshu}"
else
    COMPOSE_PROFILES=""
    echo "  使用 SQLite（默认快速启动路径）"
fi

# 询问是否执行数据库迁移
if [ "$DB_PROVIDER" = "mysql" ]; then
    echo ""
    echo -e "${YELLOW}是否执行数据库迁移？(y/n)${NC}"
    read -r response
    if [ "$response" = "y" ]; then
        echo "执行数据库迁移..."
        bash deploy/scripts/run_migrations.sh
        echo -e "${GREEN}✓ 数据库迁移完成${NC}"
    fi
fi

# 停止旧容器
echo ""
echo "停止旧容器..."
cd deploy
docker compose --env-file .env $COMPOSE_PROFILES down || true
cd ..

# 构建镜像
echo ""
echo "构建 Docker 镜像..."
cd deploy
docker compose --env-file .env $COMPOSE_PROFILES build --no-cache

# 启动容器
echo ""
echo "启动容器..."
docker compose --env-file .env $COMPOSE_PROFILES up -d

# 等待服务启动
echo ""
echo "等待服务启动..."
sleep 10

# 检查容器状态
echo ""
echo "检查容器状态..."
docker compose --env-file .env $COMPOSE_PROFILES ps

# 检查健康状态
echo ""
echo "检查服务健康状态..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if docker compose --env-file .env $COMPOSE_PROFILES exec -T app curl -f http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        echo -e "${GREEN}✓ 服务健康检查通过${NC}"
        break
    else
        RETRY_COUNT=$((RETRY_COUNT + 1))
        echo "等待服务启动... ($RETRY_COUNT/$MAX_RETRIES)"
        sleep 2
    fi
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}✗ 服务健康检查失败${NC}"
    echo "查看日志："
    docker compose --env-file .env $COMPOSE_PROFILES logs --tail=50 app
    exit 1
fi

cd ..

# 显示部署信息
echo ""
echo "========================================="
echo -e "${GREEN}部署成功！${NC}"
echo "========================================="
echo ""
echo "访问地址："
echo "  前端: http://localhost:${APP_PORT:-80}"
echo "  后端 API: http://localhost:${APP_PORT:-80}/api"
echo "  健康检查: http://localhost:${APP_PORT:-80}/api/health"
echo ""
echo "管理员账号："
echo "  用户名: ${ADMIN_DEFAULT_USERNAME:-admin}"
echo "  密码: [已配置，出于安全原因不在控制台回显]"
echo ""
echo "查看日志："
echo "  docker compose --env-file deploy/.env -f deploy/docker-compose.yml $COMPOSE_PROFILES logs -f"
echo ""
echo "停止服务："
echo "  docker compose --env-file deploy/.env -f deploy/docker-compose.yml $COMPOSE_PROFILES down"
echo ""
