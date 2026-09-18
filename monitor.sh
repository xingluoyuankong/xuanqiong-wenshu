#!/bin/bash
# 服务监控脚本
LOG_FILE=/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu/logs/monitor.log

mkdir -p $(dirname $LOG_FILE)

echo "$(date): 开始监控检查" >> $LOG_FILE

# 检查后端进程
if ! pgrep -f "uvicorn.*8013" > /dev/null; then
    echo "$(date): 后端服务未运行，尝试重启..." >> $LOG_FILE
    cd /run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu
    source ./scripts/server_runtime.sh
    xq_prepare_runtime
    nohup "${XQ_PYTHON}" -m uvicorn "${XQ_BACKEND_APP}" --host 0.0.0.0 --port 8013 --app-dir "$PWD" >> /tmp/xuanqiong-backend.log 2>&1 &
    sleep 5
    if pgrep -f "uvicorn.*8013" > /dev/null; then
        echo "$(date): 后端服务重启成功" >> $LOG_FILE
    else
        echo "$(date): 后端服务重启失败" >> $LOG_FILE
    fi
else
    echo "$(date): 后端服务运行正常" >> $LOG_FILE
fi

# 检查前端进程
if ! pgrep -f "http.server.*5174" > /dev/null; then
    echo "$(date): 前端服务未运行，尝试重启..." >> $LOG_FILE
    cd /run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu/frontend
    nohup python3 -m http.server 5174 --directory dist --bind 0.0.0.0 >> /tmp/xuanqiong-frontend.log 2>&1 &
    sleep 3
    if pgrep -f "http.server.*5174" > /dev/null; then
        echo "$(date): 前端服务重启成功" >> $LOG_FILE
    else
        echo "$(date): 前端服务重启失败" >> $LOG_FILE
    fi
else
    echo "$(date): 前端服务运行正常" >> $LOG_FILE
fi

# 检查 Cloudflare Tunnel
if ! pgrep -f "cloudflared.*qwenpaw-mingzhu-v2" > /dev/null; then
    echo "$(date): Cloudflare Tunnel 未运行，尝试重启..." >> $LOG_FILE
    nohup cloudflared --config /root/.cloudflared/config-qwenpaw-mingzhu-v2.yml tunnel run qwenpaw-mingzhu-v2 >> /tmp/cloudflared-v2.log 2>&1 &
    sleep 5
    if pgrep -f "cloudflared.*qwenpaw-mingzhu-v2" > /dev/null; then
        echo "$(date): Cloudflare Tunnel 重启成功" >> $LOG_FILE
    else
        echo "$(date): Cloudflare Tunnel 重启失败" >> $LOG_FILE
    fi
else
    echo "$(date): Cloudflare Tunnel 运行正常" >> $LOG_FILE
fi

echo "$(date): 监控检查完成" >> $LOG_FILE
echo "监控日志: $LOG_FILE"
