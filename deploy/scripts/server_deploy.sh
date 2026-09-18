#!/bin/bash
# 服务器端部署入口（安全收口版）

set -euo pipefail

echo "========================================="
echo "玄穹文枢服务器端部署入口"
echo "========================================="

echo ""
echo "此脚本已切换为安全入口，不再执行任何带硬编码服务器信息、默认弱口令或 git reset --hard 的旧部署流程。"
echo ""
echo "请改用以下方式部署："
echo "  1. 在目标机器上手动准备仓库工作目录"
echo "  2. 复制 deploy/.env.example 为 deploy/.env，并填入真实密钥与管理员密码"
echo "  3. 在项目根目录执行: bash deploy/scripts/deploy_docker.sh"
echo ""
echo "如果需要远程自动化部署，请基于当前仓库路径、目标主机、最小权限账号和非破坏性更新策略，重新编写专用脚本。"
echo "旧脚本中已移除的高风险行为包括："
echo "  - 硬编码公网 IP / root / 旧仓库地址"
echo "  - 自动写入默认管理员弱密码"
echo "  - git reset --hard origin/main 覆盖服务器本地改动"
echo ""
echo "当前脚本不执行实际部署，直接退出。"
