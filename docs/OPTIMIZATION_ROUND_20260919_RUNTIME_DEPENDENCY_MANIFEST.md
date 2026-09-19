# 优化轮次 R43：服务器 Python 依赖可审计清单（2026-09-19）

## 目标

将生产运行时依赖从隐含的 `/app/user-packages/python` 外置环境，提升为版本、来源路径和 import 可验证的部署契约；测试依赖单独记录在项目 `.venv`。

## 新增

```text
deploy/runtime_dependencies.json
scripts/audit_runtime_dependencies.py
scripts/audit_runtime_dependencies.sh
```

运行：

```bash
bash scripts/audit_runtime_dependencies.sh
```

检查：

- distribution 版本与 manifest 一致；
- 实际安装根目录与 manifest 一致；
- 关键模块可以 import；
- runtime 与 test 依赖来源没有混淆；
- 输出不包含凭据。

## 当前基线

生产依赖主要来自：

```text
/app/user-packages/python
```

测试依赖来自：

```text
.venv/lib/python3.11/site-packages
```

## 验收标准

1. `status=PASS`；
2. 所有版本和 source root 与服务器实际状态一致；
3. 后端全量回归继续通过；
4. topology audit 与 remote sync 通过；
5. 新机器若依赖缺失或漂移，脚本明确返回失败，不静默使用未知环境包。

本轮只增加审计与记录，不复制外置包、不改变业务逻辑、不执行数据库迁移。