const promptTitleMap: Record<string, string> = {
  extraction: '信息提取提示词',
  writing_v2: '正文生成提示词',
  editor_review: '编辑复审提示词',
  evaluation: '章节评估提示词',
  chapter_plan: '章节规划提示词',
  character_dna_guide: '角色设定约束提示词',
  concept: '故事概念提示词',
  outline: '大纲生成提示词',
  blueprint: '蓝图设定提示词',
  chapter_writer: '章节写作提示词',
  chapter_reviewer: '章节评审提示词',
  chapter_optimizer: '章节优化提示词',
  worldbook: '世界观设定提示词',
  style_extract: '文风提取提示词',
  summary: '摘要生成提示词',
  expand_outline: '大纲扩写提示词',
  character_card: '角色卡提示词',
}

const promptDescriptionMap: Record<string, string> = {
  extraction: '用于从素材、设定或参考文本中抽取结构化信息。',
  writing_v2: '用于生成章节正文，是核心写作链路的主提示词。',
  editor_review: '用于从编辑视角复审正文，指出问题并给出修订意见。',
  evaluation: '用于对章节质量做结构化评分与评价。',
  chapter_plan: '用于把单章目标、节奏、冲突和收束整理成可执行计划。',
  character_dna_guide: '用于约束角色说话方式、行为习惯、动机和一致性。',
  concept: '用于生成故事概念、卖点和题材方向。',
  outline: '用于生成全书结构和章节大纲。',
  blueprint: '用于沉淀蓝图、设定和写作基础信息。',
  chapter_writer: '用于直接生成章节正文。',
  chapter_reviewer: '用于定位章节问题并输出评审意见。',
  chapter_optimizer: '用于对已生成章节做局部精修与优化。',
  worldbook: '用于补充世界观、规则和设定文档。',
  style_extract: '用于从外部文本中提取文风特征。',
  summary: '用于生成章节摘要、阶段摘要或上下文摘要。',
  expand_outline: '用于把简纲扩写成可执行的章节规划。',
  character_card: '用于生成和维护角色卡片。',
}

const errorTypeMap: Record<string, string> = {
  RuntimeError: '运行时错误',
  ValueError: '参数值错误',
  TimeoutError: '超时错误',
  ConnectionError: '连接错误',
  HTTPException: '接口异常',
  ValidationError: '校验错误',
  DatabaseError: '数据库错误',
  IntegrityError: '数据完整性错误',
}

const diagnosticsFieldMap: Record<string, string> = {
  'Request ID': '请求 ID',
  Path: '接口路径',
  Status: '状态码',
  'Occurred At': '发生时间',
  'Source Log': '来源日志',
  'Root Cause': '根因',
  Hint: '处理建议',
  'Primary Root Cause': '主要根因',
}

const formatFallbackPromptName = (key: string) => key
  .replace(/[_-]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()
  .replace(/\b\w/g, (char) => char.toUpperCase())

export function translatePromptName(name?: string | null) {
  const key = String(name || '').trim()
  if (!key) return '未命名提示词'
  return promptTitleMap[key] || formatFallbackPromptName(key)
}

export function describePromptName(name?: string | null) {
  const key = String(name || '').trim()
  if (!key) return '该提示词用于生成链路中的某个步骤。'
  return promptDescriptionMap[key] || '该提示词用于生成链路中的某个步骤，点开后可查看详细内容。'
}

export function translateErrorType(errorType?: string | null) {
  const key = String(errorType || '').trim()
  return errorTypeMap[key] || key || '未标注错误类型'
}

export function translateDiagnosticsField(label: string) {
  return diagnosticsFieldMap[label] || label
}
