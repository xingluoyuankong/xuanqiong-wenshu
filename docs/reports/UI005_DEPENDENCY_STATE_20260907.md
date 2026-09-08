# UI005 F02 基础依赖状态判定交付

日期：2026-09-07（项目任务指定日期）。范围仅为独立纯 helper、新测试及证据。本次完成依赖状态判定，不等于 F02 持久化续跑已完成；execution/runtime/worker 接线、严格 context reader、数据库状态迁移由主代理处理。

## 1. 交付文件与范围

- 实现：`D:/小说写作/xuanqiong-wenshu/backend/app/agent/dependency_state.py`，第 13–24 行为冻结结果，第 27–29 行为不可变状态集合，第 32–82 行为纯分类函数。
- 测试：`D:/小说写作/xuanqiong-wenshu/backend/app/agent/test_dependency_state.py`，64 项 pytest 用例；第 84–93 行额外穷举 12³ = 1,728 组三依赖状态组合。
- 本报告：`D:/小说写作/xuanqiong-wenshu/docs/reports/UI005_DEPENDENCY_STATE_20260907.md`。
- 证据目录：`D:/小说写作/xuanqiong-wenshu/logs/ui005_dependency_state_20260907`。

未编辑既有源码或测试、未降低原测试阈值、未新建 Codex task、未申请提权。pytest 仅指定新增测试文件；没有运行共享数据库写入 fixture。helper 本身只使用标准库，不做 IO、不修改输入、不修改全局；模块状态集合均为 frozenset。

## 2. 已确认接口

~~~python
@dataclass(frozen=True, slots=True)
class DependencyState:
    state: Literal["ready", "waiting", "failed", "cancelled"]
    unresolved: tuple[int, ...]
    terminal: tuple[int, ...]


def classify_dependencies(
    dependency_orders: list[int], statuses: Mapping[int, str]
) -> DependencyState:
    ...
~~~

以上为接口摘录，完整实现位于交付文件；不是待补实现。

- completed 是唯一满足依赖的状态。
- waiting：awaiting_approval、pending、running、retrying、字面 missing，以及 mapping 中缺少该依赖。
- failed：failed、execution_failed、dead_letter，以及所有未知/非法状态值。
- cancelled：cancelled、rejected。
- 总结果优先级：failed > cancelled > waiting > ready。空依赖为 ready。
- unresolved：所有非 completed 依赖，包括终态依赖。
- terminal：unresolved 中失败、取消及未知状态的依赖子集。
- 两个元组均保留 dependency_orders 首次出现顺序、去重；忽略无关 mapping 项。
- 不做大小写、空格或类型强制转换。None/布尔值/数字/list/dict 状态是显式损坏值，归 failed；不等同缺失 entry。
- dependency_orders 非 list、元素非严格 int（含 bool）或 statuses 非 Mapping 抛固定消息 TypeError；非正编号抛固定消息 ValueError。编号异常不伪造可调度结果，异常消息不回显输入。

### 主代理接线说明

传入持久化 Step 状态索引，而不是直接把 Approval/Job 的状态串当 Step 状态。approved、executing、executed、succeeded、queued 未列入本接口白名单，按未知状态失败处理；批准不等于 step completed。若上层需要解释跨实体状态，应先在自身合同里明确映射，不在此 helper 偷做生命周期转换。

示例：

~~~python
classify_dependencies([1], {1: "awaiting_approval"})
# DependencyState(state="waiting", unresolved=(1,), terminal=())

classify_dependencies([1, 2], {1: "rejected", 2: "failed"})
# DependencyState(state="failed", unresolved=(1, 2), terminal=(1, 2))

classify_dependencies([3, 1, 3], {1: "completed"})
# DependencyState(state="waiting", unresolved=(3,), terminal=())
~~~

waiting 应由主循环保留待执行，不走 DependencyNotCompleted 终态失败；failed/cancelled 的实际持久化和事件由调用方完成。缺失节点按本任务要求等待：因此此 helper 不负责检测 DAG 环、跨 Run 引用或不存在的计划节点，这些属于计划结构验证。本交付不创建 continuation job、不重试 step、不执行 writer/read、不改审批或候选接受语义。

## 3. Evidence → Finding → Path

| 证据 | 发现 | 主代理接线位置/责任 |
|---|---|---|
| 实现第 58–63 行；测试第 21–30 行 | 审批等待和缺失 entry 都稳定 waiting，不消耗 attempt、不伪装成功 | 在主循环执行下游前调用，waiting 留 pending |
| 实现第 64–79 行；测试第 33–46、54–77 行 | 失败/取消/未知均终态，失败优先且不依赖扫描顺序 | 保留真实失败证据；取消不重新 claim |
| 实现第 57、61、64、82 行；测试第 69–73、96–141 行 | 有序去重、结果冻结、输入不变，只读取请求项 | 可复用给持久化状态索引和只读 Mapping |
| 测试第 84–93 行及 mutation_summary.json | 混合状态与反向破坏均受断言约束 | 不用单一 happy-path 代替依赖矩阵 |

## 4. 红 → 绿 → 进程内变异 → 再绿

正常 pytest 命令（工作目录：D:/小说写作/xuanqiong-wenshu/backend）：

~~~powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& .\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider app/agent/test_dependency_state.py
~~~

保持仓库 pytest.ini 和 conftest 的正常加载；仅关闭 pytest cache 与 Python 字节码落盘以遵守写集限制，未禁用测试或改变断言阈值。临时进程环境设置不改工程配置。

| 阶段 | 实际结果 | 证据 |
|---|---|---|
| 红：先写测试、实现不存在 | exit=2，1 个收集错误：ModuleNotFoundError app.agent.dependency_state | D:/小说写作/xuanqiong-wenshu/logs/ui005_dependency_state_20260907/red.log |
| 绿：加入实现 | exit=0，64 passed in 0.14s | D:/小说写作/xuanqiong-wenshu/logs/ui005_dependency_state_20260907/green.log |
| 反向：9 个内存实现变体 | 每轮收集 64 项，均 exit=1 且有实际 call 断言失败 | D:/小说写作/xuanqiong-wenshu/logs/ui005_dependency_state_20260907/mutation_summary.json 及 mutation_*.log |
| 再绿：独立正常 pytest | exit=0，64 passed in 0.14s | D:/小说写作/xuanqiong-wenshu/logs/ui005_dependency_state_20260907/final_green.log |

红阶段是新模块缺失的真实收集失败，不宣称它已证明逻辑断言失败；逻辑敏感性由后续 9 个变异逐项证明。

### 进程内变异结果

| 变异 | 失败用例数 | 结果 |
|---|---:|---|
| approval_wait_as_completed | 2 | 检出，exit=1 |
| missing_as_completed | 2 | 检出，exit=1 |
| unknown_as_waiting | 18 | 检出，exit=1 |
| cancel_beats_failure | 9 | 检出，exit=1 |
| omit_terminal | 34 | 检出，exit=1 |
| keep_duplicates | 2 | 检出，exit=1 |
| sort_dependencies | 8 | 检出，exit=1 |
| cancel_as_waiting | 14 | 检出，exit=1 |
| failure_as_completed | 12 | 检出，exit=1 |

变异机制：从磁盘只读原源码，在内存替换单一判定，AST 仅提取 classify_dependencies 函数，以复制的模块 namespace 编译；经 pytest collection 插件替换测试模块引用。每轮 finally 恢复引用，测试断言本身不变。未修改原模块函数/状态集合，未写任何变异源码到磁盘；磁盘仅保存 pytest 输出与 JSON 摘要。

helper 变异前/后 SHA-256 均为：

`df4cbfd37379d4bce2d76244ad672c9fc90dbb3533dc8eb0945ea34e81a1b264`

本次源文件一致性证明限定于 helper；没有将并行主代理的工作区变动当成本任务改动，也没有执行回滚/清理。

## 5. 覆盖范围和未完成项

已覆盖：所有指定状态、显式 missing 与真正缺项、未知状态 fail closed、错误类型、优先级全排列、有序去重、无关项忽略、只读 Mapping/defaultdict、冻结与哈希、输入分离、连续调用不串状态、固定错误消息、1,728 个混合状态组合。

仍由主代理完成：主循环接线、真实 worker write→read 审批等待回归、审批终态与 continuation 入队事务、claim-step 重试门禁、cancel/pause/replan/legacy 合同及集成门禁。本报告不将 helper 单测通过等同审批后续跑闭环，也不替代既有测试阈值。
