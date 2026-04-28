<template>
  <div class="ci-shell">
    <div v-if="loading || !uiControl" class="ci-loading">
      <div class="ci-loading__spinner"></div>
      <p>正在准备下一轮问题...</p>
    </div>

    <div v-else-if="uiControl.type === 'single_choice'" class="ci-stack">
      <section class="ci-section">
        <div class="ci-section__head">
          <div>
            <p class="ci-section__eyebrow">优先做选择</p>
            <h3>先点最接近的方向，再补一句你真正想要的效果。</h3>
          </div>
          <span class="ci-counter">已选 {{ selectedOptionIds.length }} 项</span>
        </div>

        <div class="ci-options">
          <button
            v-for="option in uiControl.options"
            :key="option.id"
            type="button"
            class="ci-option"
            :class="isSelected(option.id) ? 'ci-option--selected' : ''"
            @click="toggleOption(option.id, option.label)"
          >
            <span class="ci-option__title">{{ option.label }}</span>
            <span class="ci-option__hint">{{ isSelected(option.id) ? '已选择' : '点击选择' }}</span>
          </button>
        </div>
      </section>

      <section class="ci-section ci-section--subtle">
        <div class="ci-section__head">
          <div>
            <p class="ci-section__eyebrow">灵感快捷推荐</p>
            <h3>不想手打时，先点几个常见推进点。</h3>
          </div>
        </div>

        <div class="ci-tags">
          <button
            v-for="tag in inspirationQuickTags"
            :key="`quick-${tag}`"
            type="button"
            class="ci-tag"
            @click="appendQuickTag(tag)"
          >
            {{ tag }}
          </button>
        </div>

        <div class="ci-mini-actions">
          <button type="button" class="ci-mini-btn" @click="selectAllOptions">全选</button>
          <button type="button" class="ci-mini-btn" @click="invertSelection">反选</button>
          <button
            type="button"
            class="ci-mini-btn"
            :disabled="!selectedOptionLabels.length"
            @click="appendSelectedOptionsToInput"
          >
            把已选项写进输入框
          </button>
          <button type="button" class="ci-mini-btn" :disabled="!selectedOptionLabels.length" @click="clearSelection">
            清空已选
          </button>
        </div>

        <div v-if="selectedOptionLabels.length" class="ci-selected-tags">
          <span v-for="label in selectedOptionLabels" :key="`selected-${label}`" class="ci-selected-tag">
            {{ label }}
          </span>
        </div>
      </section>

      <form class="ci-composer" @submit.prevent="handleSingleChoiceSubmit">
        <label class="ci-composer__label" for="single-choice-input">补充说明</label>
        <textarea
          id="single-choice-input"
          ref="textInputRef"
          v-model="textInput"
          :placeholder="uiControl.placeholder || '可以继续补充要求，也可以只发送已选项'"
          class="ci-textarea"
          rows="5"
          @input="handleTextareaInput"
        ></textarea>

        <div class="ci-composer__footer">
          <p class="ci-composer__hint">
            先选方向，再补一句“为什么这样选”通常更稳定。
          </p>
          <button type="submit" class="ci-submit-btn" :disabled="!canSubmitSingleChoice">
            发送这一轮
          </button>
        </div>
      </form>
    </div>

    <form v-else-if="uiControl.type === 'text_input'" class="ci-composer ci-composer--single" @submit.prevent="handleTextSubmit">
      <div class="ci-section__head">
        <div>
          <p class="ci-section__eyebrow">直接补充</p>
          <h3>这一轮没有选项，直接说你想要的内容就行。</h3>
        </div>
      </div>

      <textarea
        ref="textInputRef"
        v-model="textInput"
        :placeholder="uiControl.placeholder || '请输入你的想法...'"
        class="ci-textarea"
        rows="5"
        required
        @input="handleTextareaInput"
      ></textarea>

      <div class="ci-composer__footer">
        <p class="ci-composer__hint">一句话也行，不需要一次性把所有设定写完。</p>
        <button type="submit" class="ci-submit-btn" :disabled="!textInput.trim()">发送</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { UIControl } from '@/api/novel'

interface Props {
  uiControl: UIControl | null
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  submit: [userInput: { id: string; value: string; selected_ids?: string[] } | null]
}>()

const textInput = ref('')
const textInputRef = ref<HTMLTextAreaElement>()
const selectedOptionIds = ref<string[]>([])
const selectedOptionLabels = ref<string[]>([])

const inspirationQuickTags = [
  '高概念开局',
  '主角隐藏身份',
  '反派先赢一手',
  '第一章埋大伏笔',
  '感情线加速升温',
  '世界观代价机制',
  '时间线错位谜题',
  '双线并行叙事',
  '多阵营博弈',
  '章尾反转钩子',
  '误导线索再反杀',
  '救赎线并行推进',
  '强敌压境倒计时',
  '身份错位修罗场',
  '资源争夺战升级',
  '关键证据反复易手',
  '双主角立场分裂',
  '配角黑化预警',
  '世界观秘密揭露一角',
  '本章必须情绪爆点',
  '制造信任危机',
  '以小事件折射大阴谋',
  '章节结尾抛新问号',
  '主角犯错引发连锁反应',
]

const MIN_ROWS = 5
const MAX_ROWS = 8

const canSubmitSingleChoice = computed(() => selectedOptionIds.value.length > 0 || !!textInput.value.trim())

const adjustTextareaHeight = () => {
  const textarea = textInputRef.value
  if (!textarea || typeof window === 'undefined') return

  const lineHeight = parseFloat(window.getComputedStyle(textarea).lineHeight || '0') || 24
  const minHeight = lineHeight * MIN_ROWS
  const maxHeight = lineHeight * MAX_ROWS

  textarea.style.height = 'auto'
  const targetHeight = Math.min(maxHeight, Math.max(minHeight, textarea.scrollHeight))
  textarea.style.height = `${targetHeight}px`
}

const handleTextareaInput = () => {
  adjustTextareaHeight()
}

const isSelected = (id: string) => selectedOptionIds.value.includes(id)

const selectAllOptions = () => {
  const options = props.uiControl?.options || []
  selectedOptionIds.value = options.map((option) => option.id)
  selectedOptionLabels.value = options.map((option) => option.label)
}

const invertSelection = () => {
  const options = props.uiControl?.options || []
  const nextIds: string[] = []
  const nextLabels: string[] = []

  for (const option of options) {
    if (!selectedOptionIds.value.includes(option.id)) {
      nextIds.push(option.id)
      nextLabels.push(option.label)
    }
  }

  selectedOptionIds.value = nextIds
  selectedOptionLabels.value = nextLabels
}

const toggleOption = (id: string, label: string) => {
  const index = selectedOptionIds.value.indexOf(id)
  if (index >= 0) {
    selectedOptionIds.value.splice(index, 1)
    selectedOptionLabels.value.splice(index, 1)
    return
  }

  selectedOptionIds.value.push(id)
  selectedOptionLabels.value.push(label)
}

const appendQuickTag = (tag: string) => {
  const current = textInput.value.trim()
  if (!current) {
    textInput.value = tag
  } else if (!current.includes(tag)) {
    textInput.value = `${current}，${tag}`
  }
  nextTick(() => adjustTextareaHeight())
}

const clearSelection = () => {
  selectedOptionIds.value = []
  selectedOptionLabels.value = []
}

const appendSelectedOptionsToInput = () => {
  const selectedText = selectedOptionLabels.value.join('，').trim()
  if (!selectedText) return

  const current = textInput.value.trim()
  textInput.value = current ? `${current}\n${selectedText}` : selectedText
  nextTick(() => adjustTextareaHeight())
}

const handleSingleChoiceSubmit = () => {
  const selectedText = selectedOptionLabels.value.join('，')
  const manualText = textInput.value.trim()
  const combined = [selectedText, manualText].filter(Boolean).join('\n')
  if (!combined) return

  emit('submit', {
    id: selectedOptionIds.value.length > 1 ? 'multi_choice' : selectedOptionIds.value[0] || 'text_input',
    value: combined,
    selected_ids: selectedOptionIds.value.length ? [...selectedOptionIds.value] : undefined,
  })

  textInput.value = ''
  clearSelection()
  nextTick(() => adjustTextareaHeight())
}

const handleTextSubmit = () => {
  const value = textInput.value.trim()
  if (!value) return

  emit('submit', { id: 'text_input', value })
  textInput.value = ''
  nextTick(() => adjustTextareaHeight())
}

watch(
  () => props.uiControl,
  async () => {
    textInput.value = ''
    clearSelection()
    await nextTick()
    adjustTextareaHeight()
    if (props.uiControl?.type === 'text_input') {
      textInputRef.value?.focus()
    }
  },
  { deep: true },
)
</script>

<style scoped>
.ci-shell {
  display: grid;
  gap: 14px;
}

.ci-loading,
.ci-section,
.ci-composer {
  border-radius: 24px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 14px 40px -32px rgba(15, 23, 42, 0.25);
}

.ci-loading {
  display: grid;
  place-items: center;
  gap: 12px;
  min-height: 180px;
  color: #64748b;
}

.ci-loading__spinner {
  width: 42px;
  height: 42px;
  border-radius: 999px;
  border: 4px solid rgba(148, 163, 184, 0.2);
  border-top-color: #2563eb;
  animation: ci-spin 0.8s linear infinite;
}

.ci-stack {
  display: grid;
  gap: 14px;
}

.ci-section {
  padding: 18px;
}

.ci-section--subtle {
  background: rgba(248, 250, 252, 0.9);
}

.ci-section__head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  align-items: start;
}

.ci-section__eyebrow {
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #2563eb;
}

.ci-section__head h3 {
  margin-top: 8px;
  font-size: 1.02rem;
  line-height: 1.5;
  font-weight: 700;
  color: #0f172a;
}

.ci-counter {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 999px;
  background: rgba(219, 234, 254, 0.9);
  color: #1d4ed8;
  font-size: 0.8rem;
  font-weight: 700;
}

.ci-options {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.ci-option {
  display: grid;
  gap: 6px;
  text-align: left;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(239, 246, 255, 0.8);
  color: #1e3a8a;
  transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease;
}

.ci-option:hover {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.3);
  box-shadow: 0 12px 26px -24px rgba(37, 99, 235, 0.35);
}

.ci-option--selected {
  background: linear-gradient(135deg, #1d4ed8, #0f766e);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 16px 30px -24px rgba(29, 78, 216, 0.55);
}

.ci-option__title {
  font-size: 0.94rem;
  font-weight: 700;
}

.ci-option__hint {
  font-size: 0.78rem;
  opacity: 0.8;
}

.ci-tags,
.ci-selected-tags,
.ci-mini-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.ci-tags {
  margin-top: 14px;
}

.ci-tag,
.ci-mini-btn,
.ci-selected-tag {
  display: inline-flex;
  align-items: center;
  min-height: 34px;
  padding: 0 12px;
  border-radius: 999px;
  font-size: 0.82rem;
}

.ci-tag {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: #fff;
  color: #475569;
}

.ci-tag:hover,
.ci-mini-btn:hover {
  transform: translateY(-1px);
}

.ci-mini-actions {
  margin-top: 14px;
}

.ci-mini-btn {
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.92);
  color: #334155;
  font-weight: 600;
  transition: transform 0.16s ease, opacity 0.16s ease, border-color 0.16s ease;
}

.ci-mini-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}

.ci-selected-tags {
  margin-top: 14px;
}

.ci-selected-tag {
  background: rgba(219, 234, 254, 0.82);
  color: #1d4ed8;
  font-weight: 700;
}

.ci-composer {
  padding: 18px;
  display: grid;
  gap: 14px;
}

.ci-composer--single {
  background: rgba(255, 255, 255, 0.95);
}

.ci-composer__label {
  font-size: 0.9rem;
  font-weight: 700;
  color: #334155;
}

.ci-textarea {
  width: 100%;
  min-height: 140px;
  max-height: 320px;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.92);
  color: #0f172a;
  line-height: 1.8;
  resize: none;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, background-color 0.16s ease;
}

.ci-textarea:focus {
  border-color: rgba(37, 99, 235, 0.34);
  box-shadow: 0 0 0 4px rgba(37, 99, 235, 0.1);
  background: #fff;
}

.ci-composer__footer {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.ci-composer__hint {
  color: #64748b;
  font-size: 0.84rem;
  line-height: 1.6;
}

.ci-submit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 50px;
  padding: 0 20px;
  border-radius: 18px;
  border: none;
  background: linear-gradient(135deg, #0f172a, #2563eb 58%, #0f766e);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 16px 30px -18px rgba(37, 99, 235, 0.32);
  transition: transform 0.16s ease, opacity 0.16s ease;
}

.ci-submit-btn:hover {
  transform: translateY(-1px);
}

.ci-submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

@keyframes ci-spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 900px) {
  .ci-options {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .ci-section,
  .ci-composer {
    padding: 14px;
    border-radius: 20px;
  }

  .ci-composer__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .ci-submit-btn {
    width: 100%;
  }
}
</style>
