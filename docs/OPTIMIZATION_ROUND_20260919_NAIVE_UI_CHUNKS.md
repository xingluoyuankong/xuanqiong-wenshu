# 优化轮次 R44：Naive UI 按组件拆分构建 chunk（2026-09-19）

## 根因

原 `frontend/vite.config.ts` 将所有 `naive-ui` 模块强制归入单一 `naive-ui` chunk，生产构建产物约 `557.33 kB`（gzip 约 `156.37 kB`），即使页面只使用少量组件也会承担完整大块。

## 本轮变更

调整 `manualChunks`：

- `naive-ui/es/<component>` 按组件目录拆分为 `naive-<component>`；
- `_internal`、`_styles`、`_utils`、`_virtual` 等共享内部模块归入 `naive-ui-runtime`；
- 其他依赖的既有 chunk 策略不变；
- 不修改 Vue 组件业务逻辑，不改变运行时 API。

## 验收结果

### 前端功能

```text
npm run type-check: PASS
npm run test:run: 23 files passed, 117 tests passed
npm run build-only: PASS
```

### 构建结果

- `4710 modules transformed`；
- 构建耗时：`47.51s`；
- `INEFFECTIVE_DYNAMIC_IMPORT`：无；
- `Some chunks are larger than 500 kB`：无；
- 最大 Naive UI 组件 chunk：`naive-data-table`，约 `301.06 kB`；
- `naive-alert`：约 `57.53 kB`；
- `naive-form`：约 `35.04 kB`；
- `naive-card`：约 `37.23 kB`；
- `naive-menu`：约 `32.21 kB`；
- `naive-button`：约 `24.80 kB`。

相较原单块约 `557.33 kB`，最大单个 Naive UI chunk 降至约 `301.06 kB`，并按页面组件形成独立加载边界。

## 未在本轮宣称完成的内容

- 尚未通过真实浏览器网络瀑布证明每条路由的首屏传输量下降；
- `naive-data-table` 仍较大，后续可继续评估其内部功能拆分；
- 不以降低 warning 阈值替代优化；
- RAG embedding 专用 key、MySQL migration runner、依赖可重建安装仍在其他队列推进。

## 回滚

回滚本轮提交即可恢复原 Naive UI 单 chunk 策略，不涉及后端、数据库或运行时配置。