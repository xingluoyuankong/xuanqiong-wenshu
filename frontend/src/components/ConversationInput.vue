<template>
  <div class="ci-shell">
    <div v-if="loading || !uiControl" class="ci-loading">
      <div class="ci-loading__spinner"></div>
      <p>{{ pick('正在准备下一轮问题...', 'Preparing the next round of questions…') }}</p>
    </div>

    <div v-else-if="isOptionControl" class="ci-stack">
      <section class="ci-section">
        <div class="ci-section__head">
          <div>
            <p class="ci-section__eyebrow">{{ pick('优先做选择', 'Choose first') }}</p>
            <h3>{{ isMultiChoiceControl
              ? pick('可以同时勾多个方向，再补一句你真正想要的效果。', 'Tick several directions at once, then add a line about the effect you actually want.')
              : pick('先点最接近的方向，再补一句你真正想要的效果。', 'Pick the closest direction, then add a line about the effect you actually want.') }}</h3>
          </div>
          <span class="ci-counter">{{ pick(`已选 ${selectedOptionIds.length} 项`, `${selectedOptionIds.length} selected`) }}</span>
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
            <span class="ci-option__hint">{{ isSelected(option.id)
              ? pick('已选择', 'Selected')
              : (isMultiChoiceControl ? pick('点击加入', 'Click to add') : pick('点击选择', 'Click to select')) }}</span>
          </button>
        </div>
      </section>

      <section class="ci-section ci-section--subtle">
        <div class="ci-section__head">
          <div>
            <p class="ci-section__eyebrow">{{ pick('灵感快捷推荐', 'Quick inspiration prompts') }}</p>
            <h3>{{ pick(
              '不想手打时，先点几个灵感维度，把世界、人物和冲突先钉住。',
              'When you would rather not type, tap a few inspiration angles to pin down the world, the characters, and the conflict.'
            ) }}</h3>
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
          <button type="button" class="ci-mini-btn" @click="selectAllOptions">{{ isMultiChoiceControl ? pick('全选', 'Select all') : pick('选第一项', 'Select the first') }}</button>
          <button type="button" class="ci-mini-btn" @click="invertSelection">{{ isMultiChoiceControl ? pick('反选', 'Invert selection') : pick('切换下一项', 'Switch to next') }}</button>
          <button
            type="button"
            class="ci-mini-btn"
            :disabled="!selectedOptionLabels.length"
            @click="appendSelectedOptionsToInput"
          >
            {{ pick('把已选项写进输入框', 'Copy selection into the box') }}
          </button>
          <button type="button" class="ci-mini-btn" :disabled="!selectedOptionLabels.length" @click="clearSelection">
            {{ pick('清空已选', 'Clear selection') }}
          </button>
        </div>

        <div v-if="selectedOptionLabels.length" class="ci-selected-tags">
          <span v-for="label in selectedOptionLabels" :key="`selected-${label}`" class="ci-selected-tag">
            {{ label }}
          </span>
        </div>
      </section>

      <form class="ci-composer" @submit.prevent="handleOptionSubmit">
        <label class="ci-composer__label" for="single-choice-input">{{ pick('补充说明', 'Extra notes') }}</label>
        <textarea
          id="single-choice-input"
          ref="textInputRef"
          v-model="textInput"
          :placeholder="uiControl.placeholder || pick('可以继续补充要求，也可以只发送已选项', 'Add more requirements, or just send what you selected')"
          class="ci-textarea"
          rows="3"
          @input="handleTextareaInput"
        ></textarea>

        <div class="ci-composer__footer">
          <p class="ci-composer__hint">
            {{ isMultiChoiceControl
              ? pick('可以先组合几个方向，再补一句“为什么这样搭配”。', 'Combine a few directions first, then add a line on why they fit together.')
              : pick('先选方向，再补一句“为什么这样选”通常更稳定。', 'Picking a direction and then saying why usually gives steadier results.') }}
          </p>
          <button type="submit" class="ci-submit-btn" :disabled="!canSubmitSingleChoice">
            {{ pick('发送这一轮', 'Send this round') }}
          </button>
        </div>
      </form>
    </div>

    <form v-else-if="uiControl.type === 'text_input'" class="ci-composer ci-composer--single" @submit.prevent="handleTextSubmit">
      <div class="ci-section__head">
        <div>
          <p class="ci-section__eyebrow">{{ pick('直接补充', 'Just describe it') }}</p>
          <h3>{{ pick('这一轮没有选项，直接说你想要的内容就行。', 'No options this round — simply say what you want.') }}</h3>
        </div>
      </div>

      <textarea
        ref="textInputRef"
        v-model="textInput"
        :placeholder="uiControl.placeholder || pick('请输入你的想法...', 'Type your idea…')"
        class="ci-textarea"
        rows="3"
        required
        @input="handleTextareaInput"
      ></textarea>

      <div class="ci-composer__footer">
        <p class="ci-composer__hint">{{ pick('一句话也行，不需要一次性把所有设定写完。', 'One sentence is fine — you do not have to write out every setting at once.') }}</p>
        <button type="submit" class="ci-submit-btn" :disabled="!textInput.trim()">{{ pick('发送', 'Send') }}</button>
      </div>
    </form>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useLocale } from '@/composables/useLocale'
import type { UIControl } from '@/api/novel'

interface Props {
  uiControl: UIControl | null
  loading: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  submit: [userInput: { id: string; value: string; selected_ids?: string[] } | null]
}>()

const { pick } = useLocale()

const textInput = ref('')
const textInputRef = ref<HTMLTextAreaElement>()
const selectedOptionIds = ref<string[]>([])
const selectedOptionLabels = ref<string[]>([])

// 快捷推荐问句会被写进输入框并发给后端，属于用户文本；这里按界面语言给出对应语种的问句
const inspirationQuickTags = computed(() => [
  pick('主角最想守住什么？', 'What does the protagonist most want to protect?'),
  pick('这个世界最反常的规则是什么？', 'What is the strangest rule of this world?'),
  pick('生存压力来自哪里？', 'Where does the survival pressure come from?'),
  pick('修炼或成长要付出什么代价？', 'What does cultivation or growth cost?'),
  pick('文明秩序靠什么维持？', 'What holds this civilization’s order together?'),
  pick('日常生活最依赖哪种资源？', 'Which resource does daily life depend on most?'),
  pick('海域 / 地理环境最危险的地方是什么？', 'What is the most dangerous part of the seas or terrain?'),
  pick('主角会遇到什么阵营或同盟？', 'Which factions or alliances will the protagonist meet?'),
  pick('最想先保住的核心画面是什么？', 'Which core image do you most want to keep?'),
  pick('这个世界最不能触碰的禁忌是什么？', 'What taboo must never be touched in this world?'),
])

// 拼接已选项时的分隔符：中文用全角逗号，英文用半角逗号加空格
const joinSeparator = () => pick('，', ', ')

const MIN_ROWS = 3
const MAX_ROWS = 5

const isOptionControl = computed(() => props.uiControl?.type === 'single_choice' || props.uiControl?.type === 'multi_choice')
const isMultiChoiceControl = computed(() => props.uiControl?.type === 'multi_choice')
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
  if (!options.length) return
  if (!isMultiChoiceControl.value) {
    selectedOptionIds.value = [options[0].id]
    selectedOptionLabels.value = [options[0].label]
    return
  }
  selectedOptionIds.value = options.map(option => option.id)
  selectedOptionLabels.value = options.map(option => option.label)
}

const invertSelection = () => {
  const options = props.uiControl?.options || []
  if (!options.length) return
  if (!isMultiChoiceControl.value) {
    const currentId = selectedOptionIds.value[0]
    const currentIndex = options.findIndex((option) => option.id === currentId)
    const nextOption = options[(currentIndex + 1 + options.length) % options.length]
    selectedOptionIds.value = [nextOption.id]
    selectedOptionLabels.value = [nextOption.label]
    return
  }

  const selectedSet = new Set(selectedOptionIds.value)
  const inverted = options.filter(option => !selectedSet.has(option.id))
  selectedOptionIds.value = inverted.map(option => option.id)
  selectedOptionLabels.value = inverted.map(option => option.label)
}

const toggleOption = (id: string, label: string) => {
  if (!isMultiChoiceControl.value) {
    if (selectedOptionIds.value[0] === id) {
      selectedOptionIds.value = []
      selectedOptionLabels.value = []
      return
    }

    selectedOptionIds.value = [id]
    selectedOptionLabels.value = [label]
    return
  }

  const nextIds = [...selectedOptionIds.value]
  const nextLabels = [...selectedOptionLabels.value]
  const selectedIndex = nextIds.indexOf(id)
  if (selectedIndex >= 0) {
    nextIds.splice(selectedIndex, 1)
    nextLabels.splice(selectedIndex, 1)
  } else {
    nextIds.push(id)
    nextLabels.push(label)
  }
  selectedOptionIds.value = nextIds
  selectedOptionLabels.value = nextLabels
}

const appendQuickTag = (tag: string) => {
  const current = textInput.value.trim()
  if (!current) {
    textInput.value = tag
  } else if (!current.includes(tag)) {
    textInput.value = `${current}${joinSeparator()}${tag}`
  }
  nextTick(() => adjustTextareaHeight())
}

const clearSelection = () => {
  selectedOptionIds.value = []
  selectedOptionLabels.value = []
}

const appendSelectedOptionsToInput = () => {
  const selectedText = selectedOptionLabels.value.join(joinSeparator()).trim()
  if (!selectedText) return

  const current = textInput.value.trim()
  textInput.value = current ? `${current}\n${selectedText}` : selectedText
  nextTick(() => adjustTextareaHeight())
}

const handleOptionSubmit = () => {
  const selectedText = selectedOptionLabels.value.join(joinSeparator())
  const manualText = textInput.value.trim()
  const combined = [selectedText, manualText].filter(Boolean).join('\n')
  if (!combined) return

  emit('submit', {
    id: selectedOptionIds.value.length === 1 ? selectedOptionIds.value[0] : (selectedOptionIds.value.length > 1 ? 'multi_choice' : 'text_input'),
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
  gap: 10px;
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
  gap: 10px;
  min-height: 120px;
  color: #64748b;
}

.ci-loading__spinner {
  width: 34px;
  height: 34px;
  border-radius: 999px;
  border: 4px solid rgba(148, 163, 184, 0.2);
  border-top-color: #2563eb;
  animation: ci-spin 0.8s linear infinite;
}

.ci-stack {
  display: grid;
  gap: 10px;
}

.ci-section {
  padding: 12px;
}

.ci-section--subtle {
  background: rgba(248, 250, 252, 0.9);
}

.ci-section__head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 8px;
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
  margin-top: 4px;
  font-size: 0.92rem;
  line-height: 1.35;
  font-weight: 700;
  color: #0f172a;
}

.ci-counter {
  display: inline-flex;
  align-items: center;
  min-height: 26px;
  padding: 0 9px;
  border-radius: 999px;
  background: rgba(219, 234, 254, 0.9);
  color: #1d4ed8;
  font-size: 0.8rem;
  font-weight: 700;
}

.ci-options {
  margin-top: 10px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.ci-option {
  display: grid;
  gap: 2px;
  text-align: left;
  min-height: 44px;
  padding: 9px 10px;
  border-radius: 12px;
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
  font-size: 0.84rem;
  line-height: 1.35;
  font-weight: 700;
}

.ci-option__hint {
  font-size: 0.68rem;
  opacity: 0.72;
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
  min-height: 28px;
  padding: 0 9px;
  border-radius: 999px;
  font-size: 0.75rem;
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
  padding: 12px;
  display: grid;
  gap: 10px;
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
  min-height: 84px;
  max-height: 180px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.92);
  color: #0f172a;
  line-height: 1.55;
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
  min-height: 38px;
  padding: 0 14px;
  border-radius: 12px;
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


.ci-tags {
  max-height: 72px;
  overflow-y: auto;
  padding-right: 2px;
  scrollbar-gutter: stable;
}

@media (max-width: 520px) {
  .ci-options {
    grid-template-columns: 1fr;
  }
}

@media (min-width: 1280px) {
  .ci-options {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .ci-options {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .ci-section,
  .ci-composer {
    padding: 12px;
    border-radius: 16px;
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
