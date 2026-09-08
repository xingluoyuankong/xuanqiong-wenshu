# 当前源码前端最终门禁 — 2026-09-07

## 结论

本批在当前工作区执行三道原始门禁，全部实际退出码 0，无需修改业务源码或测试。

| 命令 | 实测 |
|---|---|
| npm run type-check | exit 0；命令墙钟 45.94 秒 |
| npm run test:run | 83 文件 / 634 passed；Vitest 127.06 秒；exit 0 |
| npm run build-only | 4918 modules transformed；Vite 26.07 秒；exit 0 |

## SSE / Job projection

本轮全量实际包含以下相关测试（不是仅沿用旧报告）：

```text
 ✓ src/views/AgentWorkspace.spec.ts (31 tests) 3017ms
 ✓ src/api/agent.spec.ts (23 tests) 13ms
 ✓ src/features/agent/data/AgentDataPanel.spec.ts (17 tests) 163ms
 ✓ src/utils/sseStream.spec.ts (8 tests) 193ms
 ✓ src/features/agent/composables/useAgentRunStream.transport.spec.ts (11 tests) 53ms
 ✓ src/features/agent/composables/useAgentRunStream.isolation.spec.ts (7 tests) 10ms
 ✓ src/features/agent/composables/useAgentRunStream.spec.ts (7 tests) 9ms
```

已核对测试覆盖错 Run 终态与游标隔离、同 ID 旧 generation、旧协议字段省略兼容、重复 durable event、5000 顺序事件去重、终态取消，以及 Job 公开终态/恢复标记/白名单、false 与缺省、自绑定 ID、私有字段不渲染。

八个重点 SSE/Job 源码及测试文件执行前后 SHA256 一致，见 summary.verified.json。此哈希核对范围是这八个重点文件，不声称全工作区冻结。

## 真实构建

产物已由本轮 vite build 生成：
- D:\小说写作\xuanqiong-wenshu\frontend\dist\index.html
- D:\小说写作\xuanqiong-wenshu\frontend\dist\assets\AgentWorkspace-Dm9b5-AQ.js
- D:\小说写作\xuanqiong-wenshu\frontend\dist\assets\sseStream-BtErK89E.js

已检查产物包含 SSE 和公共 Job 投影相关标识；大小和 SHA256 保存于 verified summary。本轮未重新跑浏览器验收，不将构建成功替代部署/浏览器全链路证明。

## 日志与汇总脚本纠错

完整 stdout/stderr 保存在 type-check.log、test-run.log、build-only.log。原 summary.json 保留：PowerShell 函数的成功输出流把日志文本一起捕获到返回值，污染 final_exit_codes 并导致 wrapper 误报 failed。

已逐项读取原 summary.commands[].exit_code（执行后立即保存的整数，三项均为 0）并核对日志及产物，生成 summary.verified.json。未改测试、未降低标准、未把实际失败测试改写为通过；故障仅在汇总包装层。

既有提示仍存在：baseline-browser-mapping/Browserslist 数据陈旧、Pinia 注入测试警告。完整日志保留。

本轮测试/构建进程已结束，没有待领取的门禁结果。未改 backend、未创建新 task、未终止既有 Vite 服务。
