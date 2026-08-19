import { pick } from '@/composables/useLocale'

// 三张映射表的键都是后端下发的提示词 name / 异常类型原文，保持原样不翻译；
// 值在函数体内经 pick 求值，切换语言后调用方（computed / 模板）会重新求值
const promptTitleMap = (): Record<string, string> => ({
  extraction: pick('信息提取提示词', 'Information extraction prompt'),
  writing_v2: pick('正文生成提示词', 'Draft generation prompt'),
  editor_review: pick('编辑复审提示词', 'Editorial review prompt'),
  evaluation: pick('章节评估提示词', 'Chapter review prompt'),
  chapter_plan: pick('章节规划提示词', 'Chapter planning prompt'),
  character_dna_guide: pick('角色设定约束提示词', 'Character profile constraint prompt'),
  concept: pick('故事概念提示词', 'Story concept prompt'),
  outline: pick('大纲生成提示词', 'Outline generation prompt'),
  blueprint: pick('蓝图设定提示词', 'Blueprint setup prompt'),
  chapter_writer: pick('章节写作提示词', 'Chapter writing prompt'),
  chapter_reviewer: pick('章节评审提示词', 'Chapter reviewer prompt'),
  chapter_optimizer: pick('章节优化提示词', 'Chapter optimization prompt'),
  worldbook: pick('世界观设定提示词', 'World setting prompt'),
  style_extract: pick('文风提取提示词', 'Style extraction prompt'),
  summary: pick('摘要生成提示词', 'Summary generation prompt'),
  expand_outline: pick('大纲扩写提示词', 'Outline expansion prompt'),
  character_card: pick('角色卡提示词', 'Character card prompt'),
})

const promptDescriptionMap = (): Record<string, string> => ({
  extraction: pick(
    '用于从素材、设定或参考文本中抽取结构化信息。',
    'Extracts structured information from source material, settings, or reference text.'
  ),
  writing_v2: pick(
    '用于生成章节正文，是核心写作链路的主提示词。',
    'Generates the chapter draft — the main prompt of the core writing pipeline.'
  ),
  editor_review: pick(
    '用于从编辑视角复审正文，指出问题并给出修订意见。',
    'Reviews the draft from an editor’s angle, flagging issues and suggesting revisions.'
  ),
  evaluation: pick('用于对章节质量做结构化评分与评价。', 'Scores and reviews chapter quality in a structured way.'),
  chapter_plan: pick(
    '用于把单章目标、节奏、冲突和收束整理成可执行计划。',
    'Turns a chapter’s goal, pacing, conflict, and payoff into an actionable plan.'
  ),
  character_dna_guide: pick(
    '用于约束角色说话方式、行为习惯、动机和一致性。',
    'Constrains how a character speaks, behaves, what drives them, and keeps them consistent.'
  ),
  concept: pick('用于生成故事概念、卖点和题材方向。', 'Generates story concepts, hooks, and genre direction.'),
  outline: pick('用于生成全书结构和章节大纲。', 'Generates the book-level structure and chapter outlines.'),
  blueprint: pick('用于沉淀蓝图、设定和写作基础信息。', 'Captures the blueprint, settings, and writing fundamentals.'),
  chapter_writer: pick('用于直接生成章节正文。', 'Generates the chapter draft directly.'),
  chapter_reviewer: pick('用于定位章节问题并输出评审意见。', 'Pinpoints chapter problems and produces review notes.'),
  chapter_optimizer: pick('用于对已生成章节做局部精修与优化。', 'Polishes and optimizes parts of an already generated chapter.'),
  worldbook: pick('用于补充世界观、规则和设定文档。', 'Fills in world setting, rules, and reference documents.'),
  style_extract: pick('用于从外部文本中提取文风特征。', 'Extracts style traits from external text.'),
  summary: pick('用于生成章节摘要、阶段摘要或上下文摘要。', 'Generates chapter, stage, or context summaries.'),
  expand_outline: pick('用于把简纲扩写成可执行的章节规划。', 'Expands a short outline into an actionable chapter plan.'),
  character_card: pick('用于生成和维护角色卡片。', 'Generates and maintains character cards.'),
})

const errorTypeMap = (): Record<string, string> => ({
  RuntimeError: pick('运行时错误', 'Runtime error'),
  ValueError: pick('参数值错误', 'Invalid value'),
  TimeoutError: pick('超时错误', 'Timeout error'),
  ConnectionError: pick('连接错误', 'Connection error'),
  HTTPException: pick('接口异常', 'API exception'),
  ValidationError: pick('校验错误', 'Validation error'),
  DatabaseError: pick('数据库错误', 'Database error'),
  IntegrityError: pick('数据完整性错误', 'Data integrity error'),
})

// 键是英文字段名原文；中文侧翻译，英文侧原样返回
const diagnosticsFieldMap = (): Record<string, string> => ({
  'Request ID': pick('请求 ID', 'Request ID'),
  Path: pick('接口路径', 'Path'),
  Status: pick('状态码', 'Status'),
  'Occurred At': pick('发生时间', 'Occurred At'),
  'Source Log': pick('来源日志', 'Source Log'),
  'Root Cause': pick('根因', 'Root Cause'),
  Hint: pick('处理建议', 'Hint'),
  'Primary Root Cause': pick('主要根因', 'Primary Root Cause'),
})

const formatFallbackPromptName = (key: string) => key
  .replace(/[_-]+/g, ' ')
  .replace(/\s+/g, ' ')
  .trim()
  .replace(/\b\w/g, (char) => char.toUpperCase())

export function translatePromptName(name?: string | null) {
  const key = String(name || '').trim()
  if (!key) return pick('未命名提示词', 'Unnamed prompt')
  return promptTitleMap()[key] || formatFallbackPromptName(key)
}

export function describePromptName(name?: string | null) {
  const key = String(name || '').trim()
  if (!key) return pick('该提示词用于生成链路中的某个步骤。', 'This prompt drives one step of the generation pipeline.')
  return promptDescriptionMap()[key] || pick(
    '该提示词用于生成链路中的某个步骤，点开后可查看详细内容。',
    'This prompt drives one step of the generation pipeline — open it to see the details.'
  )
}

export function translateErrorType(errorType?: string | null) {
  const key = String(errorType || '').trim()
  return errorTypeMap()[key] || key || pick('未标注错误类型', 'Error type not recorded')
}

export function translateDiagnosticsField(label: string) {
  return diagnosticsFieldMap()[label] || label
}
