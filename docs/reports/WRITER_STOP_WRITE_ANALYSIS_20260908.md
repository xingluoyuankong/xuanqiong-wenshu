# Writer停写协调机制分析 — 2026-09-08

## 当前实现状态

### 已实现的Cancel机制

位置：ackend/app/services/pipeline_orchestrator.py

#### 1. Cancel请求标记
`python
normalized_runtime: Dict[str, Any] = {
    "run_id": generation_run_id,
    "cancel_requested": bool(runtime.get("cancel_requested")),
    "progress_stage": stage,
    ...
}
`

#### 2. Cancel检测点
在流水线执行过程中检测cancel状态：
`python
cancel_requested = bool(runtime_state.get("cancel_requested"))

if (
    chapter.status != ChapterGenerationStatus.GENERATING.value
    or current_run_id != generation_run_id
    or cancel_requested
):
    raise HTTPException(
        status_code=409,
        detail={
            "code": "GENERATION_CANCELLED",
            "message": "章节生成任务已失效或被取消。",
            "hint": f"后台流水线在 {stage} 阶段检测到任务已取消，请重新发起生成。",
            "retryable": False,
        },
    )
`

#### 3. 任务Rebound时的Cancel重置
`python
rebound.update({
    "run_id": generation_run_id,
    "cancel_requested": False,
    "progress_stage": stage,
    "progress_message": "generation task rebound",
    ...
})
`

#### 4. 前端可用操作
`python
allowed_actions = ["refresh_status", "cancel_generation"]
if stage == "waiting_for_confirm":
    allowed_actions = ["refresh_status", "confirm_version", "review_versions"]
`

## 缺失的停写协调机制

### 1. 优雅停止（Graceful Shutdown）
**现状**：Cancel是立即中断，没有优雅停止机制
**问题**：
- 正在进行的Provider调用被强制中断
- 中间状态可能不一致
- 已生成的内容可能丢失

**建议**：
- 在安全点（如场景边界、段落边界）检查cancel标志
- 完成当前安全单元后再停止
- 保存已生成的部分内容

### 2. 停写协调器（Stop Coordinator）
**现状**：没有统一的停写协调器
**问题**：
- 多个并发生成任务时，停写逻辑分散
- 无法保证所有相关资源都被正确释放
- 缺少停写后的清理逻辑

**建议**：
- 创建 WriterStopCoordinator 类
- 管理所有活跃生成任务的停写
- 统一处理资源释放和状态清理

### 3. 停写后的状态恢复
**现状**：Cancel后需要用户手动重新发起生成
**问题**：
- 没有自动恢复到可生成状态
- 中间状态可能残留
- 用户需要手动清理

**建议**：
- Cancel后自动清理中间状态
- 恢复到 draft 或 idle 状态
- 提供明确的重新生成入口

### 4. 超时自动停止
**现状**：有soft timeout，但没有自动停止机制
**问题**：
- Provider调用可能无限期挂起
- 没有强制超时机制
- 可能导致资源泄漏

**建议**：
- 实现硬超时机制
- 超时后自动触发cancel
- 记录超时事件用于诊断

### 5. 停写事件通知
**现状**：Cancel只返回HTTP 409错误
**问题**：
- 前端无法区分用户主动cancel和系统自动cancel
- 缺少停写原因通知
- 无法触发后续处理逻辑

**建议**：
- 添加停写事件类型（user_cancel, timeout, error, system）
- 通过SSE通知前端停写原因
- 触发相应的UI更新

## 测试覆盖

### 已有测试
- Cancel请求标记和检测
- Cancel后的HTTP 409响应
- 任务rebound时的cancel重置

### 缺失测试
- 优雅停止场景
- 多任务并发停写
- 停写后的状态恢复
- 超时自动停止
- 停写事件通知

## 优先级建议

### P0：超时自动停止
- 影响：防止资源泄漏
- 难度：中
- 风险：低

### P1：停写后的状态恢复
- 影响：改善用户体验
- 难度：中
- 风险：中

### P2：优雅停止
- 影响：减少内容丢失
- 难度：高
- 风险：高

### P3：停写协调器
- 影响：代码可维护性
- 难度：高
- 风险：高

### P4：停写事件通知
- 影响：前端体验
- 难度：中
- 风险：低

## 下一步动作

1. 实现超时自动停止机制（P0）
2. 添加停写后的状态恢复逻辑（P1）
3. 补充相关测试
4. 更新文档
