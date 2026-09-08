# 文学质量双盲审阅协议 v1.0

> 创建日期：2026-09-08
> 状态：草案，待人工审阅者确认
> 关联：logs/stage13-literary-review-packet-20260907/

## 1. 目标

本协议定义如何对25个既有去重样本进行双人盲审，以采集文学质量真值，闭合7项hard gap中的人工标签依赖项。

## 2. 审阅包结构

| 文件 | 用途 | 约束 |
|------|------|------|
| rozen-manifest.json | 样本绑定元数据 | 只读，审计绑定件 |
| eviewer-A.csv | 审阅者A评分表 | 独立填写，不暴露B |
| eviewer-B.csv | 审阅者B评分表 | 独立填写，不暴露A |
| djudication.csv | 仲裁记录 | 仅A/B分歧时填写 |
| alidate_packet.py | 验证器 | 运行验收 |

## 3. 审阅流程

### 3.1 准备阶段
1. 确认packet hash: 3b10ef55d91448c703a583b1baf516f26daf8b06d9e1c69d6620837ef884b94
2. 确认25样本完整：general 19 + T18 6
3. 分发前备份原始CSV为空表状态

### 3.2 分发阶段
1. 向审阅者A分发eviewer-A.csv + 样本内容
2. 向审阅者B分发eviewer-B.csv + 样本内容（相同顺序）
3. 隐藏rozen-manifest.json和对方身份

### 3.3 审阅阶段
每位审阅者对每个样本填写8个必填字段：
- human_overall_accept: 整体是否接受
- human_ending_pressure: 结尾是否有压力
- human_dialogue_changes_state: 对话是否推动状态
- human_late_reversal: 是否有后期反转
- human_speaker_distinct: 说话者是否区分
- human_balance_acceptable: 平衡性是否可接受
- human_scene_transition_clear: 场景转换是否清晰
- human_static_description_excessive: 静态描写是否过多

合法值：	rue / alse / 
a（需说明原因）

### 3.4 仲裁阶段
1. 比对A/B结果，找出分歧字段
2. 对每个分歧，向仲裁者提供：
   - 样本内容
   - A的判断和理由
   - B的判断和理由
3. 仲裁者填写djudication.csv

### 3.5 验收阶段
运行验证器：
`powershell
& backend\.venv\Scripts\python.exe logs\stage13-literary-review-packet-20260907\validate_packet.py --write-result
`

## 4. 质量保障

### 4.1 防污染
- 审阅者不得查看自动标签、质量门结果或豁免记录
- 审阅者不得相互讨论
- 仲裁者不得是A或B

### 4.2 可追溯
- 每行必须填写eviewer_id和eviewed_at_utc
- 仲裁行必须绑定两条原始行的canonical-row SHA-256

### 4.3 完整性
- 8个必填字段不得留空
- 
a必须在eview_notes中说明原因

## 5. 预期产出

完成后，本协议应产出：
1. 25个样本的人工质量标签
2. 审阅者一致性统计
3. 仲裁结论
4. 7项hard gap中至少3项可闭合：
   - T-18_exemption_quality_truth
   - T-26_dialogue_marker_calibration
   - human_quality_labels

## 6. 当前状态

- [x] 审阅包已冻结
- [x] 验证器已通过
- [x] 4种变异检出
- [ ] 审阅者已确认
- [ ] 审阅进行中
- [ ] 仲裁完成
- [ ] 验证器最终通过
- [ ] Hard gap闭合

## 7. 下一步动作

1. 确认两名独立审阅者
2. 确认仲裁者
3. 分发审阅包
4. 设定截止时间
5. 收集结果并运行验收

## 8. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 审阅者无法找到 | 准备候补名单 |
| 审阅时间过长 | 设定明确截止时间 |
| 一致性过低 | 增加培训或校准会议 |
| 仲裁分歧无法解决 | 保留原始判断，标记为争议样本 |

## 9. 审计绑定

本协议一旦启动，不得修改样本内容、packet hash或验证器逻辑。任何变更需记录在logs/stage14-literary-protocol-change/并重新冻结。
