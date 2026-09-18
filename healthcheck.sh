#!/bin/bash
# US-005: 玄穹文枢健康检查（TCP 精确分类：OK / SLOW / FAILED）
#
# 退出码语义：
#   0 = 正常（所有目标 TCP 连接成功且 < SLOW_THRESHOLD）
#   1 = 慢/超时（连接超时，服务可能仍在启动 / 黑洞地址）
#   2 = 失败（ConnectionRefused，端口无监听，服务确实失败）
#
# 可配置环境变量：
#   HEALTH_TARGETS         逗号分隔 host:port，默认 127.0.0.1:8013,127.0.0.1:5174
#   HEALTH_MAX_RETRIES     每目标最大重试次数，默认 3
#   HEALTH_RETRY_INTERVAL  退避基数秒，默认 2（指数退避 2,4,8...）
#   HEALTH_CONNECT_TIMEOUT 单次连接超时秒，默认 3
#   HEALTH_SLOW_THRESHOLD  成功但超过该秒数判为慢，默认 8

set -eu

BASE=/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu

export HEALTH_TARGETS="${HEALTH_TARGETS:-127.0.0.1:8013,127.0.0.1:5174}"
export HEALTH_MAX_RETRIES="${HEALTH_MAX_RETRIES:-3}"
export HEALTH_RETRY_INTERVAL="${HEALTH_RETRY_INTERVAL:-2}"
export HEALTH_CONNECT_TIMEOUT="${HEALTH_CONNECT_TIMEOUT:-3}"
export HEALTH_SLOW_THRESHOLD="${HEALTH_SLOW_THRESHOLD:-8}"

cd "$BASE"
python3 backend/app/utils/healthcheck_classifier.py
exit $?
