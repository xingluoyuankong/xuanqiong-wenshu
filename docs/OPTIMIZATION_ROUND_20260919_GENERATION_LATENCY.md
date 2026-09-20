# 优化轮次 R45：生成阶段 p50/p95 延迟报告（2026-09-19）

## 目标

将真实生成日志中的 `Pipeline total duration` 和阶段耗时转换为可重复的 p50/p95 报告，为后续 Provider、导演脚本、上下文和正文生成优化提供基线；本轮只读日志，不发起新的 Provider 请求。

## 新增入口

```bash
bash scripts/report_generation_latency.sh
```

可选参数：

```bash
bash scripts/report_generation_latency.sh --glob 'backend/logs/**/*.log' --glob 'logs/**/*.log'
bash scripts/report_generation_latency.sh --output docs/generated_latency_report.json
```

输出：

- 总流水线 count/min/p50/p95/max；
- 每个阶段 count/min/p50/p95/max；
- 使用的日志文件列表；
- 解析错误数量；
- `PASS` / `EMPTY` / `PARTIAL` 状态。

## 验收标准

1. 从真实日志找到至少一条完整 pipeline total 记录；
2. 阶段字典可解析且无 parse errors；
3. 不读取或输出 API key、token、正文；
4. 报告只读，不修改 SQLite、不启动生成；
5. 后端回归、topology audit、remote sync 保持通过。

## 后续使用

当前默认同时扫描 `backend/logs/**/*.log` 与受管服务 `logs/**/*.log`；每次 Provider 或 pipeline 优化后，用相同 glob 重新生成报告，对比：

- `generate_mission`；
- `prepare_context`；
- `generate_variants`；
- `ai_review`；
- `continuity_gate`；
- `persist_versions`；
- total pipeline。

本轮不以历史数据宣称性能已改善，只建立可复验基线。