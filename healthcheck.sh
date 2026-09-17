#!/bin/bash
# 玄穹文枢健康检查脚本（US-005: 区分慢响应和失败）

set -eu

# ==================== 配置参数 ====================
MAX_RETRIES=${MAX_RETRIES:-3}              # 最大重试次数
RETRY_BASE_INTERVAL=${RETRY_BASE_INTERVAL:-2}  # 基础重试间隔（秒）
BACKEND_TIMEOUT=${BACKEND_TIMEOUT:-10}      # 后端超时时间（秒）
FRONTEND_TIMEOUT=${FRONTEND_TIMEOUT:-10}    # 前端超时时间（秒）
SLOW_THRESHOLD=${SLOW_THRESHOLD:-8}         # 慢响应阈值（秒）

# ==================== URL 定义 ====================
API_URL="https://wenshu-api-qwenpaw-mingzhu.xzxyuan.ccwu.cc/api/health"
FRONTEND_URL="https://wenshu-qwenpaw-mingzhu.xzxyuan.ccwu.cc"
DB_PATH="/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu/storage/xuanqiong_wenshu.db"
DISK_PATH="/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405"

# ==================== 状态变量 ====================
MAIN_STATUS=0                               # 主状态码：0=ok, 1=slow, 2=failed
IS_BACKEND_SLOW=false                       # 后端是否慢响应
IS_FRONTEND_SLOW=false                      # 前端是否慢响应

# ==================== 函数定义 ====================

# 带退避重试的 HTTP 检查函数
# 参数：$1=url, $2=service_name, $3=max_attempts, $4=timeout, $5=slow_threshold
check_service_with_backoff() {
    local url=$1
    local service_name=$2
    local max_attempts=$3
    local timeout=$4
    local slow_threshold=$5
    
    echo ""
    echo "【$service_name】开始检查..."
    
    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        echo "尝试 $attempt/$max_attempts ($service_name): $(date +%H:%M:%S)"
        
        # 使用 curl 的 time_total 获取实际响应时间（秒，带小数）
        REAL_TIME=$(curl -s --write-out '%{time_total}\n' --max-time "$timeout" "$url" -o /tmp/check_response_$$.txt 2>&1 | tail -1)
        IS_SUCCESS=$?
        
        if [ $IS_SUCCESS -eq 0 ] && [ -s /tmp/check_response_$$.txt ]; then
            # 检查是否满足服务条件（后端 check healthy，前端检查包含文本）
            case $service_name in
                *后端*)
                    if grep -q "healthy" /tmp/check_response_$$.txt; then
                        echo "✓ $service_name 健康 (耗时：${REAL_TIME}s)"
                        rm -f /tmp/check_response_$$.txt
                        return 0
                    fi
                    ;;
                *前端*)
                    if grep -q "玄穹文枢" /tmp/check_response_$$.txt; then
                        echo "✓ $service_name 正常 (耗时：${REAL_TIME}s)"
                        rm -f /tmp/check_response_$$.txt
                        return 0
                    fi
                    ;;
            esac
        fi
        
        # 未成功完成，记录问题
        RESPONSE_CODE=$IS_SUCCESS
        if [ $RESPONSE_CODE -eq 28 ]; then
            echo "⚠ $service_name 超时报错 (timeout after ${timeout}s)"
        elif [ $RESPONSE_CODE -eq 7 ]; then
            echo "✖ $service_name 连接拒绝 (connection refused)"
        else
            echo "✖ $service_name 错误代码：$RESPONSE_CODE"
        fi
        
        # 使用 awk 计算慢响应（无需 bc）
        IS_TOO_SLOW=$(awk "BEGIN {print ($REAL_TIME > $slow_threshold) ? 1 : 0}")
        if [ "$IS_TOO_SLOW" = "1" ]; then
            echo "   ⏱️  响应较慢 (${REAL_TIME}s > ${slow_threshold}s 阈值)"
            IS_SLOW=true
        fi
        
        # 最后一次尝试失败则返回失败
        if [ $attempt -lt $max_attempts ]; then
            # 指数退避策略：每次重试间隔加倍
            CURRENT_INTERVAL=$((RETRY_BASE_INTERVAL * (1 << (attempt - 1))))
            echo "   将在 ${CURRENT_INTERVAL}s 后重试（指数退避）..."
            sleep $CURRENT_INTERVAL
        fi
    done
    
    echo "❌ $service_name 在 $max_attempts 次尝试后均失败"
    rm -f /tmp/check_response_$$.txt
    return 2
}

# 检查数据库文件
check_database() {
    echo ""
    echo "【数据库】开始检查..."
    
    if [ -f "$DB_PATH" ]; then
        SIZE=$(du -h "$DB_PATH" | cut -f1)
        echo "✓ 数据库存在 (大小：$SIZE)"
        return 0
    else
        echo "✖ 数据库文件不存在：$DB_PATH"
        return 2
    fi
}

# 检查磁盘空间
check_disk_space() {
    echo ""
    echo "【磁盘空间】开始检查..."
    
    AVAIL=$(df -h "$DISK_PATH" | tail -1 | awk '{print $4}')
    USED_PCT=$(df -h "$DISK_PATH" | tail -1 | awk '{print $5}' | tr -d '%')
    
    if [ "$USED_PCT" -gt 90 ]; then
        echo "⚠ 磁盘空间紧张 (已用：${USED_PCT}%, 可用：$AVAIL)"
        return 1
    else
        echo "✓ 磁盘空间充足 (已用：${USED_PCT}%, 可用：$AVAIL)"
        return 0
    fi
}

# ==================== 主检查流程 ====================

echo ""
echo "============================================"
echo "     玄穹文枢健康检查 (US-005 版本)"
echo "============================================"
echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
echo "配置：MAX_RETRIES=$MAX_RETRIES, BASE_INTERVAL=${RETRY_BASE_INTERVAL}s, TIMEOUT=${BACKEND_TIMEOUT}s"
echo "============================================"

# 1. 检查后端 API
if ! check_service_with_backoff "$API_URL" "后端 API" "$MAX_RETRIES" "$BACKEND_TIMEOUT" "$SLOW_THRESHOLD"; then
    BACKEND_RESULT=$?
    if [ $BACKEND_RESULT -eq 2 ]; then
        MAIN_STATUS=2
        echo "🔴 后端 API 检查 FAILED"
    else
        MAIN_STATUS=1
        IS_BACKEND_SLOW=true
        echo "🟡 后端 API 检查 SLOW"
    fi
else
    echo "✅ 后端 API 正常"
fi

# 2. 检查前端
if ! check_service_with_backoff "$FRONTEND_URL" "前端服务" "$MAX_RETRIES" "$FRONTEND_TIMEOUT" "$SLOW_THRESHOLD"; then
    FRONTEND_RESULT=$?
    if [ $FRONTEND_RESULT -eq 2 ]; then
        MAIN_STATUS=2
        echo "🔴 前端服务检查 FAILED"
    else
        MAIN_STATUS=1
        IS_FRONTEND_SLOW=true
        echo "🟡 前端服务检查 SLOW"
    fi
else
    echo "✅ 前端服务正常"
fi

# 3. 检查数据库
check_database || true

# 4. 检查磁盘空间
check_disk_space || true

# ==================== 结果汇总 ====================

echo ""
echo "============================================"
echo "          检查结果汇总"
echo "============================================"

if [ $MAIN_STATUS -eq 0 ]; then
    echo "✓ 所有服务正常运行"
elif [ $MAIN_STATUS -eq 1 ]; then
    echo "⚠ 检测到慢响应服务："
    [ "$IS_BACKEND_SLOW" = true ] && echo "  - 后端 API 响应慢于 ${SLOW_THRESHOLD}s"
    [ "$IS_FRONTEND_SLOW" = true ] && echo "  - 前端服务响应慢于 ${SLOW_THRESHOLD}s"
elif [ $MAIN_STATUS -eq 2 ]; then
    echo "✖ 一个或多个服务失败："
    [ $BACKEND_RESULT -eq 2 ] && echo "  - 后端 API 连接失败"
    [ $FRONTEND_RESULT -eq 2 ] && echo "  - 前端服务不可达"
fi

echo "============================================"
echo "状态码：$MAIN_STATUS (0=正常，1=慢响应，2=失败)"
echo "============================================"

# 使用 exit 而不是 return，因为这是主脚本
case $MAIN_STATUS in
    0) exit 0 ;;
    1) echo "提示：慢响应可能表示网络延迟或服务器过载，建议观察趋势" && exit 1 ;;
    2) echo "错误：请检查服务进程是否运行" && exit 2 ;;
esac
