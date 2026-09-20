# 优化轮次 R64：Vitest Node Web Storage 测试噪声收敛（2026-09-20）

## 触发证据

服务器当前 Node 版本为 `v25.6.0`。前端 Vitest 在每个 worker 加载 `src/test/setup.ts` 时直接读取 `window.localStorage`；Node 25 的 Web Storage getter 在未设置 `--localstorage-file` 时产生：

```text
Warning: `--localstorage-file` was provided without a valid path
at Object.get (node:internal/webstorage:32:25)
at ensureStorage (frontend/src/test/setup.ts:7:33)
```

这不是业务测试失败，却淹没真实的组件失败输出；测试环境只需要隔离的内存存储，不需要 Node 持久化 Web Storage。

## 本轮变更

```text
frontend/src/test/setup.ts
frontend/src/test/storageSetup.spec.ts
```

- `ensureStorage` 改为沿原型链检查属性描述符；
- 只有已经是可用数据属性的 Storage 才复用；
- 不调用 Node 25 的 accessor getter；
- 对 accessor 或缺失实现安装独立内存 Storage；
- 新增回归覆盖 local/session storage 的读写、长度和隔离。

## 验收

专项（含 `NODE_OPTIONS=--trace-warnings`）：

```text
2 files passed
4 tests passed
未出现 localstorage-file warning
```

完整前端：

```text
npm run type-check  PASS
npm run test:run    24 files, 118 tests passed
npm run build-only  PASS
```

生产构建仍如实报告 `export-vendor`、`naive-data-table` 等大块；本轮未调高构建阈值掩盖该待优化项。

## 反向验证

临时将 `src/test/setup.ts` 完整还原到本轮前的 `HEAD` 版本，并执行单个 Vitest 测试：

```text
REVERSE_PREVIOUS_SETUP_EXIT=0
REVERSE_PREVIOUS_SETUP_WARNING=True
```

原始调用栈重新出现于 `ensureStorage(...): window[name]`。验证完成后自动恢复本轮实现。

## 范围和后续

- 不修改生产运行时的 Web Storage 行为；
- 不关闭 warning、不删除业务失败路径断言；
- 该轮只消除服务器 Node 25 与测试 setup 交互产生的确定性基础设施噪声；
- 前端首屏真实请求瀑布、`export-vendor` 和 `naive-data-table` 的按路由传输量仍需独立性能验收。
