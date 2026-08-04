<template>
  <Transition name="float-card">
    <div
      v-if="visible"
      class="floating-progress-card"
      :class="statusToneClass"
    >
      <div class="floating-progress-card__header">
        <div class="floating-progress-card__icon">
          <span v-if="isComplete" class="floating-progress-card__icon--complete">✓</span>
          <span v-else-if="isError" class="floating-progress-card__icon--error">✗</span>
          <span v-else class="floating-progress-card__icon--loading">
            <span class="floating-progress-card__spinner"></span>
          </span>
        </div>
        <div class="floating-progress-card__info">
          <strong class="floating-progress-card__title">{{ title }}</strong>
          <span class="floating-progress-card__stage">{{ stageLabel }}</span>
        </div>
        <button
          type="button"
          class="floating-progress-card__close"
          @click="$emit('close')"
          aria-label="关闭"
        >×</button>
      </div>
      
      <div class="floating-progress-card__body">
        <div class="floating-progress-card__progress-row">
          <span class="floating-progress-card__progress-label">{{ progressLabel }}</span>
          <strong class="floating-progress-card__progress-value">{{ progressPercent }}%</strong>
        </div>
        <div class="floating-progress-card__track">
          <div
            class="floating-progress-card__bar"
            :class="barClass"
            :style="barStyle"
          ></div>
          <span
            v-if="!isComplete && !isError"
            class="floating-progress-card__runner"
            :style="{ left: (progressPercent || 0) + '%' }"
          >{{ runnerEmoji }}</span>
        </div>
        <div v-if="wordCount > 0" class="floating-progress-card__stats">
          <span>已生成 {{ wordCount.toLocaleString() }} 字</span>
        </div>
      </div>

      <div v-if="funMessage" class="floating-progress-card__fun">
        <span class="floating-progress-card__fun-text">{{ funMessage }}</span>
      </div>

      <div v-if="detailMessage && !isComplete && !isError" class="floating-progress-card__detail">
        <span class="floating-progress-card__detail-text">{{ detailMessage }}</span>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from "vue"

const props = defineProps<{
  visible: boolean
  title?: string
  stage?: string
  progressPercent?: number
  wordCount?: number
  status?: string
  detailMessage?: string
}>()

defineEmits<{
  close: []
}>()

const statusTone = computed(() => {
  if (props.status === "successful") return "success"
  if (props.status === "failed" || props.status === "evaluation_failed") return "error"
  if (props.status === "generating" || props.status === "evaluating") return "active"
  return "neutral"
})

const isComplete = computed(() => props.status === "successful")
const isError = computed(() => props.status === "failed" || props.status === "evaluation_failed")

const runnerEmoji = computed(() => {
  const stage = props.stage || ""
  if (stage.includes("generate")) return "✍️"
  if (stage.includes("diagnose") || stage.includes("review") || stage.includes("evaluat")) return "🔍"
  if (stage.includes("optimize") || stage.includes("enrichment")) return "✨"
  if (stage.includes("consistency")) return "🔗"
  if (stage.includes("context") || stage.includes("prepare") || stage.includes("audit")) return "📚"
  if (stage.includes("mission")) return "📝"
  if (stage.includes("cast") || stage.includes("character")) return "👥"
  if (stage.includes("foreshadow") || stage.includes("clue")) return "🔮"
  if (stage.includes("save") || stage.includes("persist")) return "💾"
  if (stage.includes("reader")) return "👓"
  return "🏃"
})

const statusToneClass = computed(() => {
  return "floating-progress-card--" + statusTone.value
})

const barClass = computed(() => {
  return "floating-progress-card__bar--" + statusTone.value
})

const barStyle = computed(() => {
  return { width: (props.progressPercent || 0) + "%" }
})

const stageLabel = computed(() => {
  const stageMap: Record<string, string> = {
queued: "🚦 排队等候",
    prepare_context: "📚 整理上下文",
    audit_context: "🔍 审计长期记忆",
    cast_plan: "👥 装配角色阵容",
    foreshadowing_plan: "🔮 规划伏笔回收",
    foreshadowing_chapter_task: "🕵️ 检测伏笔线索",
    longform_context: "📖 装配长篇上下文",
    enhanced_context: "⚙️ 装配增强约束",
    generate_mission: "📝 编写导演脚本",
    generate_variants: "✍️ AI奋笔疾书中",
    ai_review: "🤖 AI评审中",
    optimize_content: "✨ 诊断优化中",
    reader_simulator: "👓 读者模拟中",
    consistency: "🔗 一致性检查",
    enrichment: "📈 字数扩写",
    continuity_gate: "🚪 连续性校验",
    persist_versions: "💾 保存版本",
    diagnose_once: "🔬 单次诊断",
    diagnose_structural: "🏗️ 结构诊断",
    diagnose_character: "🧑 角色诊断",
    diagnose_previous_chapter: "⏪ 回溯前章",
    diagnose_context_bundle: "📦 汇总上下文",
    optimize_character: "🎭 角色优化",
    diagnose_continuity: "⛓️ 连续性诊断",
    generate_variants_candidate: "📄 生成候选稿",
    generating: "⏳ 正在生成",
    evaluating: "🔎 正在评审",
    selecting: "🎯 等待选择",
    successful: "✅ 已完成",
    failed: "❌ 生成失败",
    waiting_for_confirm: "🤔 等待确认",
    evaluation_failed: "⚠️ 评审未通过",
  }
  return stageMap[props.stage || props.status || ""] || "处理中"
})

const progressLabel = computed(() => {
  if (isComplete.value) return "生成完成"
  if (isError.value) return "生成遇到问题"
  return "生成进度"
})

const funMessages = [
  "正在奋笔疾书...",
  "文思泉涌中...",
  "妙笔生花...",
  "才高八斗...",
  "笔下生风...",
  "灵感爆棚...",
  "正在构思惊天反转...",
  "角色们正在自己演起来了...",
  "伏笔回收计划启动...",
  "AI正在脑补宏大场景...",
  "键盘都要冒烟了...",
  "故事正在自己成长...",
  "文曲星附体中...",
  "万物皆可写...",
  "这一章绝对精彩...",
  "正在给角色安排命运...",
  "文字的力量在汇聚...",
  "脑中剧场已经开演...",
  "连标点符号都在发光...",
  "作文之神降临了...",
  "角色在纸上活过来了...",
  "大纲正在延展为画面...",
  "剧情线正在收束...",
  "冲突在升温...",
  "这一段的张力拉满了...",
  "读者们已经等不及了...",
  "每一个字都在燃烧...",
  "反转正在酝酿中...",
  "情绪曲线在攀升...",
  "场景画面正在渲染...",
]

// Use a reactive counter that updates every 3 seconds for smoother rotation
import { ref, onMounted, onUnmounted } from "vue"

const messageIndex = ref(0)
let messageTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  messageTimer = setInterval(() => {
    messageIndex.value = (messageIndex.value + 1) % funMessages.length
  }, 3000)
})

onUnmounted(() => {
  if (messageTimer) clearInterval(messageTimer)
})

const funMessage = computed(() => {
  if (isComplete.value || isError.value) return ""
  return funMessages[messageIndex.value] || funMessages[0]
})
</script>

<style scoped>
.floating-progress-card {
  position: fixed;
  top: 68px;
  right: 12px;
  z-index: 1000;
  width: 280px;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(16px);
  border-radius: 10px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.1), 0 1px 4px rgba(0, 0, 0, 0.06);
  border: 1px solid rgba(148, 163, 184, 0.15);
  overflow: hidden;
  transition: all 0.3s ease;
}

.floating-progress-card--active {
  border-left: 3px solid #3b82f6;
}

.floating-progress-card--success {
  border-left: 3px solid #10b981;
}

.floating-progress-card--error {
  border-left: 3px solid #ef4444;
}

.floating-progress-card--neutral {
  border-left: 3px solid #94a3b8;
}

.floating-progress-card__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.08);
}

.floating-progress-card__icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  font-size: 12px;
  flex-shrink: 0;
}

.floating-progress-card__icon--complete {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}

.floating-progress-card__icon--error {
  background: rgba(239, 68, 68, 0.12);
  color: #ef4444;
}

.floating-progress-card__icon--loading {
  background: rgba(59, 130, 246, 0.12);
}

.floating-progress-card__spinner {
  width: 14px;
  height: 14px;
  border: 2px solid rgba(59, 130, 246, 0.25);
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.floating-progress-card__info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.floating-progress-card__title {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.floating-progress-card__stage {
  font-size: 10px;
  color: #64748b;
}

.floating-progress-card__close {
  width: 18px;
  height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 14px;
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.2s;
}

.floating-progress-card__close:hover {
  background: rgba(148, 163, 184, 0.12);
  color: #475569;
}

.floating-progress-card__body {
  padding: 8px 10px;
}

.floating-progress-card__progress-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.floating-progress-card__progress-label {
  font-size: 10px;
  color: #64748b;
  font-weight: 500;
}

.floating-progress-card__progress-value {
  font-size: 11px;
  font-weight: 700;
  color: #1e293b;
}

.floating-progress-card__track {
  position: relative;
  width: 100%;
  height: 8px;
  background: rgba(148, 163, 184, 0.15);
  border-radius: 999px;
  overflow: visible;
}

.floating-progress-card__bar {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s ease;
}

.floating-progress-card__bar--active {
  background: linear-gradient(90deg, #3b82f6, #6366f1);
}

.floating-progress-card__bar--success {
  background: linear-gradient(90deg, #10b981, #34d399);
}

.floating-progress-card__bar--error {
  background: linear-gradient(90deg, #ef4444, #f87171);
}

.floating-progress-card__bar--neutral {
  background: linear-gradient(90deg, #94a3b8, #cbd5e1);
}

.floating-progress-card__runner {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 14px;
  line-height: 1;
  transition: left 0.5s ease;
  animation: runner-bounce 0.6s ease-in-out infinite;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.1));
  z-index: 2;
}

@keyframes runner-bounce {
  0%, 100% { transform: translate(-50%, -50%) scaleX(1); }
  50% { transform: translate(-50%, -60%) scaleX(1.1); }
}

.floating-progress-card__stats {
  margin-top: 6px;
  font-size: 9px;
  color: #64748b;
  text-align: center;
}

.floating-progress-card__fun {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 10px;
  background: rgba(59, 130, 246, 0.04);
  border-top: 1px solid rgba(148, 163, 184, 0.08);
}

.floating-progress-card__fun-text {
  font-size: 10px;
  color: #64748b;
  font-style: italic;
}

.float-card-enter-active,
.float-card-leave-active {
  transition: all 0.3s ease;
}

.float-card-enter-from,
.float-card-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
</style>
