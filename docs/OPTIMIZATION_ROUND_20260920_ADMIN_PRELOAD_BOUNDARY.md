# 优化轮次 R56：移除 Admin Vendor 首屏预加载（2026-09-20）

## 触发证据

R44 已将 Naive UI 按组件拆分，但 R56 构建入口仍在 `dist/index.html` 中 modulepreload：

```text
/assets/admin-vendor-oRUcABn8.js
```

该 vendor 主要服务管理域，而 `/admin` 路由已经是异步路由；首屏公共入口不应主动预加载管理域 vendor。

## 本轮变更

移除 Vite `manualChunks` 中专门的 `admin-vendor` 归类，让 lodash-like 依赖回到普通 vendor 图，由 Rollup 根据实际动态依赖边界处理。

没有修改业务组件、路由权限、管理功能或后端接口。

## 验收结果

```text
npm run type-check: PASS
npm run test:run: 23 files passed, 117 tests passed
npm run build-only: PASS
```

构建结果：

- `4710 modules transformed`；
- 构建耗时 `43.86s`；
- `Some chunks are larger than 500 kB`：无；
- `INEFFECTIVE_DYNAMIC_IMPORT`：无；
- `dist/index.html` 已不再包含 `admin-vendor` modulepreload；
- 首屏 preload 保留公共依赖：headlessui、naive-alert、pinia、vue-router；
- AdminView 继续通过异步路由和异步面板加载。

## 真实静态入口基线

```text
index.html=0.82 kB
naive-data-table=308.81 kB
naive-alert=70.33 kB
WritingDesk=88.61 kB
```

R56 证明的是公共入口 preload 边界改善；真实浏览器网络瀑布、缓存命中和首屏 LCP 仍需后续浏览器指标采集，不把静态入口变化直接等同于 LCP 改善。

## 回滚

回滚本轮提交即可恢复 `admin-vendor` 手动 chunk 归类，不涉及后端、数据库或服务配置。