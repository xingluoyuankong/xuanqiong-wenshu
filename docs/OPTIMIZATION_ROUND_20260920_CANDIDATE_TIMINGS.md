# 优化轮次 R50：候选版本级生成耗时观测（2026-09-20）

## 目标

R47/R48 的真实数据表明，短章节 `generate_variants` 仍约 55–59 秒，但此前 runtime 只记录整轮 attempt 总时长和候选总和，无法区分：

- 不同候选的 Provider generation 时间；
- guardrail check 时间；
- guardrail rewrite 时间；
- 单候选总耗时；
- 并发候选等待和序列化开销。

## 本轮变更

在 `PipelineOrchestrator` 的候选 attempt 收口处新增：

```text
runtime_metadata.candidate_timings[]
```

每个候选记录：

```json
{
  "index": 0,
  "generation_ms": 0,
  "guardrail_check_ms": 0,
  "guardrail_rewrite_ms": 0,
  "total_ms": 0
}
```

同时写入：

```text
Pipeline candidate timings: project=... chapter=... attempt=... timings=...
```

不改变：

- 候选并发策略；
- Provider retry；
- token ceiling；
- 质量门；
- 取消 drain；
- usage attribution。

## 验收

```text
后端全量：285 passed, 1 warning
```

本轮是观测增强，不发起计费型真实请求；下一次真实 smoke 的 runtime metadata 将能区分候选级耗时。

## 下一步

拿到候选级数据后，按以下条件选择优化：

1. 单候选 generation 长尾：优化 Provider 请求参数/重试；
2. guardrail rewrite 长尾：优化只在违规时触发的回炉策略；
3. 候选间耗时差异：评估并发限流和 provider semaphore；
4. attempt 总时长明显高于候选 max：定位 gather、heartbeat 或数据库收口开销。

本轮不使用单次 pipeline 总时长推断根因。