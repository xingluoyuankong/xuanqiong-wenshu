# Agent Routing for Novel Optimization Project

## Default Channel
- api_url: https://api.xzxyuan.ccwu.cc/v1
- api_key: sk-ykQ1t4epc10nwZ5Q7cKqBMPIJzs5u5HZkXDlIy3efSwLmU4l

## Available Free Models (no quota limit, high concurrency)
- grok-4.5
- Qwen-3.8-Max-Preview
- LongCat-2.0
- deepseek-ai/deepseek-v4-pro
- z-ai/glm-5.2

## Rate Limiting & Retry
- max_rpm: 10
- backoff_type: exponential
- pause_on_429: 60
- pause_on_timeout: 60
- fallback_to_next_model: true

## Subagent Configuration
- Use the above models for all subagents to enable parallel optimization without quota issues.
- Default subagent model routing: grok-4.5 for quality, Qwen for continuity, deepseek for production alignment.
- All subagents must use the free cloud channel, never local 8317.

## Notes
API endpoint currently returns 404 (connection issue, not high demand). Retry logic will handle temporary failures. Configuration fixed for reliable subagent spawning.
