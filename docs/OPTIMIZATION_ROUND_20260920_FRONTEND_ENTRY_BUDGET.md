# 优化轮次 R59：前端入口 preload 预算门（2026-09-20）

## 目标

把 R56 的静态检查固化为可重复门禁，防止后续构建重新把管理域 `admin-vendor` 放进公共入口 `modulepreload`，并确保 index.html 引用的入口资源全部存在。

## 新增

```text
scripts/audit_frontend_entry.py
scripts/audit_frontend_entry.sh
```

运行：

```bash
bash scripts/audit_frontend_entry.sh
```

检查：

- index.html 中 script/modulepreload/stylesheet 资源存在；
- modulepreload 数量和字节数；
- entry script 与 stylesheet 字节数；
- `admin-vendor` 不出现在 modulepreload；
- 失败时返回非零状态。

本工具只读 `frontend/dist`，不启动浏览器、不修改构建产物、不调用 Provider。