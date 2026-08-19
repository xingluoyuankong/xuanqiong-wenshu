<template>
  <div class="pixel-mascot-picker">
    <button
      type="button"
      class="pixel-mascot-picker__trigger"
      :aria-expanded="open"
      :aria-label="pick('选择进度小动物', 'Choose progress mascot')"
      @click="open = !open"
    >
      <PixelMascot :mascot-id="mascotId" :color="color" :size="24" :moving="open" />
      <span class="pixel-mascot-picker__trigger-name">{{ pick(mascot.name, mascot.nameEn) }}</span>
      <svg class="pixel-mascot-picker__caret" viewBox="0 0 12 12" aria-hidden="true">
        <path d="M3 5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.5" />
      </svg>
    </button>

    <div v-if="open" class="pixel-mascot-picker__panel">
      <p class="pixel-mascot-picker__label">{{ pick('进度小动物', 'Progress mascot') }}</p>
      <div class="pixel-mascot-picker__grid">
        <button
          v-for="item in PIXEL_MASCOTS"
          :key="item.id"
          type="button"
          :class="['pixel-mascot-picker__option', { 'is-active': item.id === mascotId }]"
          :title="pick(item.name, item.nameEn)"
          @click="onPickMascot(item.id)"
        >
          <PixelMascot :mascot-id="item.id" :color="color" :size="28" :moving="false" />
          <span class="pixel-mascot-picker__option-name">{{ pick(item.name, item.nameEn) }}</span>
        </button>
      </div>

      <p class="pixel-mascot-picker__label">{{ pick('推进姿态', 'Gait') }}</p>
      <div class="pixel-mascot-picker__gaits">
        <button
          type="button"
          :class="['pixel-mascot-picker__gait', { 'is-active': gaitMode === 'auto' }]"
          @click="setGait('auto')"
        >
          {{ pick('随机', 'Random') }}
        </button>
        <button
          v-for="item in MASCOT_GAITS"
          :key="item.id"
          type="button"
          :class="['pixel-mascot-picker__gait', { 'is-active': gaitMode === item.id }]"
          @click="setGait(item.id)"
        >
          {{ pick(item.name, item.nameEn) }}
        </button>
      </div>

      <p class="pixel-mascot-picker__label">{{ pick('颜色', 'Color') }}</p>
      <div class="pixel-mascot-picker__colors">
        <button
          v-for="preset in MASCOT_COLOR_PRESETS"
          :key="preset"
          type="button"
          :class="['pixel-mascot-picker__swatch', { 'is-active': preset.toLowerCase() === color.toLowerCase() }]"
          :style="{ '--swatch': preset }"
          :aria-label="preset"
          @click="setColor(preset)"
        />
        <label class="pixel-mascot-picker__custom">
          <span>{{ pick('自定义', 'Custom') }}</span>
          <input type="color" :value="color" @input="onColorInput" />
        </label>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useLocale } from '@/composables/useLocale'
import {
  MASCOT_COLOR_PRESETS,
  MASCOT_GAITS,
  PIXEL_MASCOTS,
  usePixelMascot,
  type PixelMascotId,
} from '@/composables/usePixelMascot'
import PixelMascot from './PixelMascot.vue'

const { pick } = useLocale()
const { mascot, mascotId, color, gaitMode, setMascot, setColor, setGait } = usePixelMascot()
const open = ref(false)

function onPickMascot(id: PixelMascotId) {
  setMascot(id)
  open.value = false
}

function onColorInput(event: Event) {
  setColor((event.target as HTMLInputElement).value)
}
</script>

<style scoped>
.pixel-mascot-picker {
  position: relative;
}

.pixel-mascot-picker__trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--xq-space-2);
  height: 32px;
  padding: 0 var(--xq-space-3);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-sm);
  background: var(--xq-surface);
  color: var(--xq-text-body);
  font-size: var(--xq-text-xs);
  cursor: pointer;
  transition: border-color var(--xq-fast), background var(--xq-fast);
}

.pixel-mascot-picker__trigger:hover {
  border-color: var(--xq-border-strong);
  background: var(--xq-surface-hover);
}

.pixel-mascot-picker__trigger:focus-visible {
  outline: none;
  border-color: var(--xq-accent);
  box-shadow: var(--xq-ring);
}

.pixel-mascot-picker__trigger-name {
  font-weight: var(--xq-weight-medium);
}

.pixel-mascot-picker__caret {
  width: 12px;
  height: 12px;
  color: var(--xq-text-faint);
}

.pixel-mascot-picker__panel {
  position: absolute;
  right: 0;
  top: calc(100% + var(--xq-space-2));
  z-index: 20;
  width: 268px;
  padding: var(--xq-space-4);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-lg);
  background: var(--xq-surface);
  box-shadow: var(--xq-shadow-md);
}

.pixel-mascot-picker__label {
  margin: 0 0 var(--xq-space-2);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  font-weight: var(--xq-weight-medium);
}

.pixel-mascot-picker__label + * {
  margin-bottom: var(--xq-space-4);
}

.pixel-mascot-picker__grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: var(--xq-space-1);
}

.pixel-mascot-picker__option {
  display: grid;
  justify-items: center;
  gap: var(--xq-space-1);
  min-width: 0;
  padding: var(--xq-space-2) var(--xq-space-1);
  border: 1px solid transparent;
  border-radius: var(--xq-radius-sm);
  background: transparent;
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  cursor: pointer;
  transition: background var(--xq-fast), border-color var(--xq-fast);
}

.pixel-mascot-picker__option:hover {
  background: var(--xq-surface-hover);
}

.pixel-mascot-picker__option.is-active {
  border-color: var(--xq-accent-border);
  background: var(--xq-accent-soft);
  color: var(--xq-accent-text);
}

.pixel-mascot-picker__option-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pixel-mascot-picker__gaits {
  display: flex;
  flex-wrap: wrap;
  gap: var(--xq-space-1);
}

.pixel-mascot-picker__gait {
  height: 24px;
  padding: 0 var(--xq-space-2);
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-pill);
  background: var(--xq-surface);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  cursor: pointer;
  transition: background var(--xq-fast), border-color var(--xq-fast), color var(--xq-fast);
}

.pixel-mascot-picker__gait:hover {
  background: var(--xq-surface-hover);
}

.pixel-mascot-picker__gait.is-active {
  border-color: var(--xq-accent-border);
  background: var(--xq-accent-soft);
  color: var(--xq-accent-text);
}

.pixel-mascot-picker__colors {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--xq-space-2);
}

.pixel-mascot-picker__swatch {
  width: 20px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-pill);
  background: var(--swatch);
  cursor: pointer;
  transition: box-shadow var(--xq-fast);
}

.pixel-mascot-picker__swatch.is-active {
  box-shadow: var(--xq-ring);
}

.pixel-mascot-picker__custom {
  display: inline-flex;
  align-items: center;
  gap: var(--xq-space-1);
  color: var(--xq-text-muted);
  font-size: var(--xq-text-2xs);
  cursor: pointer;
}

.pixel-mascot-picker__custom input {
  width: 24px;
  height: 20px;
  padding: 0;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-xs);
  background: transparent;
  cursor: pointer;
}
</style>
