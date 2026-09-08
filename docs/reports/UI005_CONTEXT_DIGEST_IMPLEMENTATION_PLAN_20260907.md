# UI005 下一批严格引用与内容摘要合同实施计划 — 2026-09-07

> **本地2026-09-07阶段六更新**：本计划所列审批F3/F5已实施并接入API；190项正常组合、3/5/2有效组合变异及backend全量2273通过，476文件无漂移。完成证据见UI005_STAGE6_INTEGRATION_20260907.md；下方保留原设计与限制，不再代表尚未实施。下一批worker编排另见UI005_WORKER_CONTINUATION_PLAN_20260907.md。

## 已核实的实现事实

1. `D:\小说写作\xuanqiong-wenshu\backend\app\agent\execution.py` 当前validator虽接收session，但审批入口未传session，绑定检查仍读取通常不存在的顶层context_bindings。Planner调用resolve_agent_context_refs不覆盖后续审批。
2. `D:\小说写作\xuanqiong-wenshu\backend\app\services\agent_context_service.py`已有get_run_snapshot与verify_snapshot，可验证context总摘要和每项ref摘要。ORM before_update只是常规应用更新保护，不替代读取时完整性检查。
3. Runtime initial context snapshot保存用户context_refs并追加novel_refs；replan snapshot保存resolved_context.canonical_refs。不能把snapshot.refs中所有payload都强制解析为AgentContextRef，也不能将Run全文context_json等同于旧快照全文（进度/规划元数据会变）。
4. set_run_context保留catalog/resolver绑定，但允许显式replan更新context snapshot定位。审批验证应取当前Run关联快照并核对身份；若要绑定审批创建时的旧context版本，需先决定持久化合同，不应假装当前数据已保存该字段。
5. CatalogRelease._payload材料：schema_version/catalog_id/generation/providers/tools；digest不包含自身digest和release_id，ID为catalog_id加digest前16位。
6. CapabilityResolverSnapshot._payload材料：resolver_schema_version/release_id/release_digest/generation/request/tools/exclusions；ID为resolver-v{schema}:{digest前16位}。关系snapshot_id另加:run:{run.id}后缀，不可直接等同resolver ID。
7. `build_catalog_release`会读取live registry拼合contract，不适合直接用它“重建并验证”已冻结JSON，否则会把live状态混入历史内容；读取时应对已有canonical材料验摘要或提供纯反序列化helper。

## F3：真实引用验证的最小写集

建议新增 `backend/app/agent/approval_context_contract.py` 与配套独立测试，validator/API仅接线；既有_relational_context_snapshot的宽松返回语义不偷偷改为全局严格。

流程：

1. API传实际session至validator。现代Run有context snapshot标识时要求ID/key完整且查到所属run的row；缺失或损坏按结构化field报错，拒绝退回JSON。
2. 核对snapshot的id/key、run/session/user/project/correlation/transaction；调用verify_snapshot。避免错误消息输出整份context或批准请求。
3. 从已验证snapshot.context_json的context_refs取用户引用，按AgentContextRef严格解析；对比当前Run相应用户引用的规范化结果，不比较全部context JSON。缺refs按空列表处理，仅当存储类型错误时失败。
4. 核对用户引用在snapshot.refs中的规范化序列/内容一致；initial包含novel_refs扩展，按实际来源合同验证其前缀/类型，不将自动检索知识引用当用户选中章节。replan正例必须覆盖。
5. 使用resolve_agent_context_refs重新校验真实资源存在、项目归属、版本所属章节、artifact可访问性，再使用已冻结且通过RunBound兼容的ToolManifest投影approved arguments。
6. 投影结果必须等于已经批准的参数；发生新增/冲突应失败，不静默改写批准内容。保留无选中refs但显式chapter_number合法的正例；None值不误判成必须提供来源。
7. legacy无现代关系定位保留旧路径，但仍按现有业务scope要求执行；不要将老数据一刀切拒绝。

优先回归：refs chapter12/approved chapter99、资源删除、version错章、artifact跨项目、context digest损坏、ref digest损坏、定位ID/key/Run漂移、有效initial/replan/no-refs-explicit/legacy。负例handler=0，execution/artifact无新增。反向仅取消API接线或strict helper关键检查，要求对应业务断言红灯。

## F5：摘要内容重算的最小写集

建议新增纯函数 `backend/app/agent/approval_snapshot_integrity.py` 与配套测试，复用现有canonical JSON序列化规则（sort_keys、ensure_ascii=False、separators、allow_nan=False）。

1. 校验材料字段存在且类型正确，摘要为规定格式；只抽取明确定义的payload字段，禁止“hash整个带digest字典”。
2. 用完整存储providers/tools内容重新计算catalog digest和内容ID，并同时核对Run副本与关系row。列表顺序按builder实际排序合同；JSON tuple/list往返必须正例通过。
3. 对resolver材料重算digest和resolver ID，核对release引用、schema/generation及request.user/project与Run范围。不要仅比较两个可同时被修改的字符串。
4. 关系snapshot的request_json、selected_capability_ids_json、exclusions_json、resolved_scope_json的resolver ID/release ID/tool_names必须对应已验证resolver；保持membership检查。
5. 校验relation snapshot.digest == resolver.digest == Run关系digest；另校验snapshot.snapshot_id符合Run-qualified格式。
6. 已有SimpleNamespace fixture使用release-digest/snapshot-digest常量，需重构为真实builder生成的合法基础，而不是放宽验证以保住假fixture。可保留隔离的关系字段单测，但明确在内容验证之前的入口层次。

优先回归：catalog tool/provider内容篡改保留旧digest、resolver request/tools/exclusions篡改、selected列表与resolver不一致、关系request/scope/exclusions漂移、合法真实Runtime与JSON往返。对相同材料摘要应稳定，不引入无关排序差异。

摘要只保证内容一致性，不是对拥有全库写权限者同步改内容与重算摘要的密码学信任锚；报告必须保留此边界。

## 执行节奏

1. 已取得阶段五全量2170通过及471文件一致性，可开始F3/F5下一批；不得把阶段五结果外推给随后新实现。
2. F3/F5可按独立helper文件并行实施，但validator/API接线由主代理串行集成，避免同文件交叉编辑。
3. 先红→实现→定向→加载期/进程内反向→正常runner组合→新后端全量。保持原30秒CLI/60秒ASGI等阈值。
4. 更新当前状态文件顶部和本计划状态；七项文学质量与Docker/MySQL实机仍独立列出，不被审批测试掩盖。
