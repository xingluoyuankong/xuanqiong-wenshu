# 优化轮次 R32：前端 WritingDesk 懒加载边界（2026-09-19）

## 目标

消除构建器报告的弹窗组件重复静态/动态导入，减少 WritingDesk 首屏静态依赖，同时保持弹窗按需加载和现有组件 barrel 的兼容性。

## 根因

`frontend/src/views/WritingDesk.vue` 从 `@/components/writing-desk` barrel 引入了四个实际使用的组件；该 barrel 同时静态导出了多个弹窗。相同弹窗又在 `WritingDesk.vue` 中通过 `defineAsyncComponent(() => import(...))` 动态引入，构建器因此报告 `INEFFECTIVE_DYNAMIC_IMPORT`，并把部分弹窗带入静态依赖图。

## 本轮变更

只修改 `frontend/src/views/WritingDesk.vue`：

- `WDHeader`、`WDSidebar`、`WDWorkspace` 改为直接从 `layout/` 导入；
- `WDGenerateOutlineModal` 改为直接从 `dialogs/` 导入；
- 保留 `frontend/src/components/writing-desk/index.ts` 的 barrel 导出，不破坏其他调用方；
- 其余七个弹窗继续使用 `defineAsyncComponent` 动态导入。

## 验收标准与结果

### 功能回归

```text
npm run type-check       PASS
npm run test:run         23 files passed, 117 tests passed
npm run build-only       PASS
```

### 构建结果对比

| 指标 | R31 基线 | R32 | 结果 |
|---|---:|---:|---|
| 转换模块数 | 4714 | 4710 | 减少 4 |
| WritingDesk JS | 145.86 kB | 88.66 kB | 减少约 39% |
| WritingDesk CSS | 40.90 kB | 25.14 kB | 减少约 38% |
| `INEFFECTIVE_DYNAMIC_IMPORT` | 有 | 0 条 | 消除 |
| >500 kB chunk | 有 | 仍有 1 个 | 保留后续优化 |

当前唯一超过 500 kB 的明确产物为 `naive-ui`，约 `557.33 kB`（gzip 约 `156.37 kB`）。这项不通过调高阈值掩盖，列入下一轮拆分评估。

## 未完成项

1. 评估 Naive UI 按路由或功能域进一步拆分，验证首屏加载和交互性能后再改构建策略；
2. 继续核对真实浏览器首屏请求瀑布，不能只用静态构建体积替代线上加载证据；
3. 后端真实 Provider 产物、迁移 runner 和外置 Python 依赖可重建性仍按 R30/R31 队列推进。

## 回滚锚点

回滚本轮提交即可恢复 `WritingDesk.vue` 的 barrel 导入；不涉及数据库、后端进程或服务配置。