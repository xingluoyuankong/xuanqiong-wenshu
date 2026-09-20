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

## R57：精确 freeze 快照与可重建输入

新增：

```text
deploy/runtime_requirements.txt
deploy/test_requirements.txt
```

当前快照规模：

```text
runtime=100 distributions
test=6 distributions
```

`audit_runtime_dependencies.sh` 现在同时检查：

- manifest 中关键包的版本、canonical source root 和 import；
- runtime/test freeze snapshot 中每个 distribution 的存在性和精确版本；
- 缺包或版本漂移时返回 `status=FAIL`。

快照是可重建输入，不代表本轮在服务器上重新安装或替换外置包。


## R57：runtime/test 快照分层修正

外置 `/app/user-packages/python` 目录同时包含生产包和测试工具，但服务运行时与项目测试入口实际使用不同版本的 pytest。R57 将：

- `pytest`、`pytest-asyncio` 从 `deploy/runtime_requirements.txt` 排除；
- 固定保留在 `deploy/test_requirements.txt`；
- 在 manifest 中记录 `runtime_excluded_test_distributions`；
- 审计 runtime/test snapshot overlap，除明确排除项外的重叠直接失败。

这修正的是可重建输入分层，不改变服务器已安装包，也不改变生产服务启动路径。


R57 分层校正：pytest 的传递依赖 `iniconfig`、`packaging`、`pluggy`、`Pygments` 同样归入 test snapshot；runtime snapshot 只保留生产运行时依赖，审计允许 manifest 明确列出的 test-only distributions。
