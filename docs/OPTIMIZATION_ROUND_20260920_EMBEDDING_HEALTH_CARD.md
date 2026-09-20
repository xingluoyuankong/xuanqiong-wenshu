# 优化轮次 R58：管理台 Embedding 健康检查卡片（2026-09-20）

## 目标

把 R55 已验证的只读接口接入管理台系统配置页，让管理员可以手动检查 embedding 能力，而无需启动章节生成，也不会看到密钥。

## 本轮变更

前端新增：

- `GET /api/llm-config/embedding-health-check` 的 TypeScript API 封装；
- 系统配置页 Embedding 能力检查卡片；
- 手动“检查”按钮和 loading/error 状态；
- 显示 provider、model、vector dimension、稳定 failure code；
- 不回显 API key、Authorization header 或上游正文。

后端接口沿用 R55，未改变 Provider、数据库或生成流程。

## 验收

```text
npm run type-check: PASS
npm run test:run: 23 files passed, 117 tests passed
npm run build-only: PASS
```

构建结果：

- `4710 modules transformed`；
- build `44.42s`；
- `Some chunks are larger than 500 kB`：无；
- `INEFFECTIVE_DYNAMIC_IMPORT`：无；
- SettingsManagement chunk 约 `28.74 kB`；
- Embedding API 单独 chunk 约 `1.56 kB`。

R55 已完成真实 HTTP 验收：

```text
login=200
embedding_health=200
vector_nonempty=false
vector_dimension=0
code=EMBEDDING_CONFIG_MISSING
```

## 后续

配置独立 embedding key/base URL 后，在此卡片点击检查即可验证真实非空向量和维度；当前配置缺 key，页面应明确显示降级状态，不把它误报成正文 Provider 故障。