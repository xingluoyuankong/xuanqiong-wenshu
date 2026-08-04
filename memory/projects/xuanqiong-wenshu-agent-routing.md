# xuanqiong-wenshu 子代理/生成路由记忆

Updated: 2026-07-29 (reinforced)

## 硬规则
- 本任务默认 LLM / 子代理通道：`https://api.xzxyuan.ccwu.cc/v1`
- **禁止** `localhost:8317` / 本地 CPA
- 密钥只通过 env / `backend/.env`（gitignored）
- 禁止把 API Key 写入仓库、AGENTS.md、日志、最终回复

## 可用模型
1. grok-4.5（主）
2. Qwen-3.8-Max-Preview
3. LongCat-2.0
4. deepseek-ai/deepseek-v4-pro（易 RemoteDisconnected）
5. z-ai/glm-5.2
## Rate Limiting & Retry (new)

- For free models via api.xzxyuan.ccwu.cc/v1: add exponential backoff retry (max 5 retries, 2s base delay), rate limit 10 RPM per model, use semaphore for concurrency.
- If high demand detected (error 429 or timeout), pause subagents for 60s, then retry.
- Never exceed 5 concurrent subagents.
- Check API status before spawning.


## 并行纪律（2026-07-29 实锤）
- live smoke 与 free subagents **不要同时打网关**，否则大量 empty/disconnect/no_available_key
- 启动脚本：
  - smoke only: `_agent_runs/spawn_smoke_only.py`（带 `_tmp_live_verify.lock`）
  - agents after smoke: `_agent_runs/spawn_agents_after_smoke.py`（检测 smoke lock）
- 发现多份 `_tmp_live_verify.py` / `run_cloud9_sequential.py` 时先收敛为单实例

## 已修关键卡死
- Provider soft/hard timeout 后 `await cancelled task` 可能永久挂起 → `_cancel_provider_task` 限时 cancel
- chapter_mission 增加 soft_timeout + allow_truncated，失败走本地 fallback
- chapter_summary 本地降级；history 读 snapshot；摘要候选优先 snapshot

## 保护
- 不触发受保护项目 12/13 章
- 真实生成只用 temp/live-smoke 项目
