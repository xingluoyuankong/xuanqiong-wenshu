# 代码优化计划 — 2026-09-08

## 1. 大文件识别

| 文件 | 大小 | 行数 | 问题 |
|------|------|------|------|
| pipeline_orchestrator.py | 477KB | 8643行/158方法 | 超大单文件，职责过多 |
| test_generation_quality_guards.py | 237KB | - | 测试文件过大 |
| test_blueprint_observability.py | 195KB | - | 测试文件过大 |
| novel_service.py | 146KB | - | 业务逻辑集中 |
| self_critique_service.py | 127KB | - | 服务逻辑集中 |
| agent_runtime.py | 121KB | - | 运行时逻辑集中 |

## 2. pipeline_orchestrator.py 重构计划

### 2.1 当前问题
- 单文件8643行，158个方法
- 职责混合：配置、质量门、生成、评审、修复、超时、提示词构建
- 难以维护和测试

### 2.2 重构方案

#### 提取模块1：pipeline_config.py
- PipelineConfig 类
- 配置相关方法
- 预计：~200行

#### 提取模块2：quality_gate.py
- _evaluate_structural_quality_gate_for_content
- _build_structural_quality_gate
- _attach_quality_gate_status_to_guard
- _build_quality_gate_patch_repair_issues
- 相关辅助方法
- 预计：~800行

#### 提取模块3：generation_timeouts.py
- _resolve_chapter_generation_timeout
- _resolve_chapter_generation_soft_timeout
- _resolve_scene_split_generation_soft_timeout
- _resolve_local_rewrite_soft_timeout
- _resolve_chapter_mission_timeout
- 所有超时相关方法
- 预计：~300行

#### 提取模块4：prompt_builder.py
- _build_chapter_overview_bundle
- _format_chapter_draft_contract_for_prompt
- _build_chapter_mission_schema
- _normalize_chapter_mission
- _resolve_writer_prompt_budget
- 所有提示词构建方法
- 预计：~600行

#### 提取模块5：consistency_service.py
- _normalize_consistency_issues_for_local_fix
- _collect_unresolved_consistency_violations
- _summarize_consistency_severity
- _should_accept_consistency_improvement
- 一致性相关方法
- 预计：~400行

#### 提取模块6：self_critique_service.py（已存在，扩展）
- _summarize_self_critique_snapshot
- _should_accept_self_critique_revision
- 自我批评相关方法
- 预计：~300行

#### 提取模块7：reader_polish_service.py
- _map_reader_problem_to_dimension
- _normalize_reader_issues_for_local_fix
- _build_structural_reader_polish_issues
- _should_run_reader_polish
- 读者润色相关方法
- 预计：~400行

#### 保留：pipeline_orchestrator.py
- 核心编排逻辑
- 流水线执行
- 预计：~3000行（从8643行减少）

### 2.3 重构原则
1. **渐进式**：每次提取一个模块，确保测试通过
2. **向后兼容**：保留原有API，内部重组
3. **测试覆盖**：每次重构后运行全量测试
4. **文档更新**：更新相关文档

### 2.4 预期收益
- 代码可读性提升
- 维护成本降低
- 测试更容易编写
- 职责更清晰

## 3. 其他优化项

### 3.1 测试文件拆分
- 	est_generation_quality_guards.py → 按功能拆分
- 	est_blueprint_observability.py → 按场景拆分

### 3.2 服务层优化
- 
ovel_service.py：提取复杂查询到repository层
- self_critique_service.py：已计划提取
- gent_runtime.py：提取状态机到独立模块

### 3.3 性能优化
- 识别热路径
- 缓存策略
- 异步优化

## 4. 执行计划

### Phase 1：质量门提取（优先级P0）
1. 创建 quality_gate.py
2. 移动相关方法
3. 运行测试验证
4. 更新导入

### Phase 2：超时配置提取（优先级P1）
1. 创建 generation_timeouts.py
2. 移动超时方法
3. 运行测试验证

### Phase 3：提示词构建提取（优先级P2）
1. 创建 prompt_builder.py
2. 移动提示词方法
3. 运行测试验证

### Phase 4：一致性服务提取（优先级P3）
1. 扩展现有 consistency_service.py
2. 移动一致性方法
3. 运行测试验证

### Phase 5：读者润色服务提取（优先级P4）
1. 创建 eader_polish_service.py
2. 移动读者润色方法
3. 运行测试验证

## 5. 风险控制

| 风险 | 缓解 |
|------|------|
| 重构引入bug | 每次重构后运行全量测试 |
| 循环导入 | 仔细设计模块边界 |
| API破坏 | 保留原有接口，内部重组 |
| 性能退化 | 性能测试对比 |

## 6. 当前状态

- [x] 识别大文件
- [x] 制定重构计划
- [ ] Phase 1：质量门提取
- [ ] Phase 2：超时配置提取
- [ ] Phase 3：提示词构建提取
- [ ] Phase 4：一致性服务提取
- [ ] Phase 5：读者润色服务提取

## 7. 下一步动作

1. 等待后端全量测试完成
2. 开始Phase 1：质量门提取
3. 每次重构后更新本文档
