# 优化轮次 R49：统一生成延迟日志根目录（2026-09-20）

## 触发问题

R45/R46 的延迟报告默认只扫描 `backend/logs/**/*.log`，但受管 8013/8099 服务的当前运行日志位于仓库 `logs/**`，导致最新 live 样本未完整进入统计。

## 本轮变更

`report_generation_latency.py` 现在默认同时扫描：

```text
backend/logs/**/*.log
logs/**/*.log
```

也支持重复传入 `--glob` 覆盖或扩展日志根目录。输出字段从单值 `glob` 改为 `globs`，明确报告覆盖范围。

## 验收

当前服务器真实报告：

```text
source_file_count=24
pipeline_samples=28
parse_errors=[]
status=PASS
```

阶段统计已包含受管服务新日志，避免只用历史 run 日志支持当前性能结论。本轮只读日志，不启动 Provider、不修改 SQLite。

## 当前性能结论

R45/R46/R47 的数据混合了不同 provider 状态、不同服务进程和不同请求规模；当前报告用于基线与定位，不直接宣称整体 p50/p95 改善。后续性能优化需按 commit、target_word_count、provider/model 和成功/超时终态分组。