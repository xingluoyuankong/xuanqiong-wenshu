# 优化轮次 R65：Python runtime 依赖隔离重建验收（2026-09-20）

## 触发证据

R43 的依赖审计已经能证明服务器当前版本和 import 正常，但服务仍主要从 `/app/user-packages/python` 加载 runtime 包；这证明的是当前环境可运行，不是仓库可以在新机器独立重建。

## 本轮交付

```text
scripts/verify_runtime_rebuild.py
scripts/verify_runtime_rebuild.sh
```

运行：

```bash
bash scripts/verify_runtime_rebuild.sh
```

脚本行为：

1. 从 `deploy/runtime_requirements.txt` 创建一次性临时 `.venv`；
2. 真实安装锁定的 runtime distributions；
3. 使用清空后的 `PYTHONPATH`，仅加入仓库 root/backend；
4. 校验所有 snapshot distribution 的版本；
5. 校验所有 distribution 来源位于新建 venv 的 `purelib/platlib`；
6. 校验 manifest 中关键 import 的 `__file__` 也来自新建 venv；
7. 退出时删除临时环境，生产 8013/8099 和项目 `.venv` 不受影响。

## 验收标准

```text
snapshot_count=94
observed_count=94
status=PASS
failures=[]
```

真实服务器验收结果：Python 使用 `/tmp/xq-runtime-rebuild-*/bin/python`，94 个 snapshot distribution 与关键 runtime import 均来自该临时 venv；不出现 `/app/user-packages/python` 或 `/app/venv/lib/python3.11/site-packages` 作为重建环境的 import/source root。

反向验证：在保留的临时 venv 中卸载 `aiosqlite` 后，审计返回 `exit=10`、`status=FAIL`、`failure_count=3`，其中含 `aiosqlite` 缺失；随后删除临时 venv。

## 与生产运行时的关系

- 本轮只验证可重建性，不替换当前生产解释器；
- 不修改服务启动、端口、数据库或外部 provider；
- R43 的线上 runtime audit 继续作为当前部署一致性门禁；
- 后续若切换生产依赖来源，必须另行执行完整后端回归、服务重启和 topology audit。

## 当前未完成项

- 当前生产服务仍使用受管服务器提供的 runtime package source；
- 未执行生产依赖切换；
- MySQL FK cycle 和 embedding 独立凭据仍保持原阻断状态。