#!/bin/bash
# 快速重启所有服务
echo "=== 重启玄穹文枢服务 ==="

# 停止服务
echo "停止服务..."
pkill -f "uvicorn.*8013" 2>/dev/null || true
pkill -f "http.server.*5174" 2>/dev/null || true
sleep 2

# 启动后端
echo "启动后端..."
cd /run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu
source ./scripts/server_runtime.sh
xq_prepare_runtime
nohup "${XQ_PYTHON}" -m uvicorn "${XQ_BACKEND_APP}" --host 0.0.0.0 --port 8013 --app-dir "$PWD" >> /tmp/xuanqiong-backend.log 2>&1 &
sleep 5

# 启动前端
echo "启动前端..."
cd /run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu/frontend
nohup python3 -m http.server 5174 --directory dist --bind 0.0.0.0 >> /tmp/xuanqiong-frontend.log 2>&1 &
sleep 3

# 验证
echo "验证服务..."
if curl -s http://127.0.0.1:8013/api/health | grep -q "healthy"; then
    echo "✓ 后端服务正常"
else
    echo "✗ 后端服务异常"
fi

if curl -s http://127.0.0.1:5174/ | grep -q "玄穹文枢"; then
    echo "✓ 前端服务正常"
else
    echo "✗ 前端服务异常"
fi

echo "=== 重启完成 ==="
