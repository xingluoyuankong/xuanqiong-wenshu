#!/bin/bash
# 快捷部署入口（安全收口版）

set -euo pipefail

echo "========================================="
echo "玄穹文枢快捷部署入口"
echo "========================================="

echo ""
echo "旧版 quick_deploy.sh 含硬编码公网主机、root 登录与破坏性 git reset --hard，已停用。"
echo "当前建议流程："
echo "  bash deploy/scripts/deploy_docker.sh"
echo ""
echo "执行前请确认："
echo "  - 已在目标机器准备好当前仓库工作目录"
echo "  - 已创建 deploy/.env 且替换所有示例密钥/密码"
echo "  - 如需 MySQL，已明确 DB_PROVIDER=mysql 并配置真实数据库口令"
echo ""
echo "当前脚本不再发起 SSH、不再使用旧仓库地址，也不再自动覆盖远端代码。"
