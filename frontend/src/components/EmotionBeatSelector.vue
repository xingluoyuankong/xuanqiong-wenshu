<!-- [DEPRECATED] This component has 0 runtime references as of 2026-08-07 audit. Retained for backward compatibility. -->
<!-- AIMETA P=情感节拍选择_情感标记选择|R=情感选择|NR=不含分析功能|E=component:EmotionBeatSelector|X=internal|A=选择器|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="emotion-beat-selector">
    <!-- 标题和开关 -->
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <span class="text-sm font-medium text-gray-700">🎭 情绪节拍控制</span>
        <span class="text-xs text-gray-400">(控制读者的阅读体验)</span>
      </div>
      <label class="relative inline-flex items-center cursor-pointer">
        <input type="checkbox" v-model="enabled" class="sr-only peer">
        <div class="w-9 h-5 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-purple-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-purple-500"></div>
      </label>
    </div>

    <!-- 情绪设置面板 -->
    <transition name="fade">
      <div v-if="enabled" class="space-y-4 p-4 bg-gradient-to-br from-purple-50 to-pink-50 rounded-lg border border-purple-200">
        <!-- 主要情绪选择 -->
        <div>
          <label class="block text-sm font-medium text-purple-700 mb-2">目标情绪</label>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
            <button
              v-for="emotion in emotionTypes"
              :key="emotion.value"
              @click="selectEmotion(emotion.value)"
              :class="[
                'px-3 py-2 text-sm rounded-lg border transition-all',
                localBeat.primary_emotion === emotion.value
                  ? 'bg-purple-500 text-white border-purple-500 shadow-md'
                  : 'bg-white text-gray-700 border-gray-200 hover:border-purple-300 hover:bg-purple-50'
              ]"
            >
              {{ emotion.icon }} {{ emotion.label }}
            </button>
          </div>
        </div>

        <!-- 情绪强度 -->
        <div>
          <label class="block text-sm font-medium text-purple-700 mb-2">
            情绪强度: <span class="text-purple-500 font-bold">{{ localBeat.intensity }}</span>/10
          </label>
          <input
            type="range"
            v-model.number="localBeat.intensity"
            min="1"
            max="10"
            class="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-purple-500"
          />
          <div class="flex justify-between text-xs text-gray-400 mt-1">
            <span>平静</span>
            <span>起伏</span>
            <span>高潮</span>
            <span>极致</span>
          </div>
        </div>

        <!-- 情绪曲线 -->
        <div>
          <label class="block text-sm font-medium text-purple-700 mb-2">情绪曲线</label>
          <div class="grid grid-cols-3 gap-4">
            <div>
              <label class="block text-xs text-gray-500 mb-1">开始</label>
              <select
                v-model.number="localBeat.curve.start"
                class="w-full p-2 text-sm border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none bg-white"
              >
                <option v-for="n in 10" :key="n" :value="n">{{ n }}级</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-gray-500 mb-1">高潮</label>
              <select
                v-model.number="localBeat.curve.peak"
                class="w-full p-2 text-sm border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none bg-white"
              >
                <option v-for="n in 10" :key="n" :value="n">{{ n }}级</option>
              </select>
            </div>
            <div>
              <label class="block text-xs text-gray-500 mb-1">结束</label>
              <select
                v-model.number="localBeat.curve.end"
                class="w-full p-2 text-sm border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none bg-white"
              >
                <option v-for="n in 10" :key="n" :value="n">{{ n }}级</option>
              </select>
            </div>
          </div>
          <!-- 曲线可视化 -->
          <div class="mt-3 h-16 bg-white rounded-lg border border-purple-100 relative overflow-hidden">
            <svg class="w-full h-full" viewBox="0 0 100 40" preserveAspectRatio="none">
              <path
                :d="curvePath"
                fill="none"
                stroke="url(#gradient)"
                stroke-width="2"
                stroke-linecap="round"
              />
              <defs>
                <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
                  <stop offset="0%" stop-color="#a855f7" />
                  <stop offset="50%" stop-color="#ec4899" />
                  <stop offset="100%" stop-color="#a855f7" />
                </linearGradient>
              </defs>
            </svg>
            <div class="absolute bottom-1 left-2 text-xs text-gray-400">开始</div>
            <div class="absolute bottom-1 left-1/2 -translate-x-1/2 text-xs text-gray-400">高潮</div>
            <div class="absolute bottom-1 right-2 text-xs text-gray-400">结束</div>
          </div>
        </div>

        <!-- 情绪转折点 -->
        <div>
          <label class="block text-sm font-medium text-purple-700 mb-2">情绪转折点 (可选)</label>
          <textarea
            v-model="localBeat.turning_point"
            placeholder="描述情绪发生转折的关键时刻，例如：当主角发现真相时，从震惊转为愤怒"
            class="w-full p-2 text-sm border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none bg-white"
            rows="2"
          ></textarea>
        </div>

        <!-- 预设模板 -->
        <div>
          <label class="block text-sm font-medium text-purple-700 mb-2">快速预设</label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="preset in presets"
              :key="preset.name"
              @click="applyPreset(preset)"
              class="px-3 py-1 text-xs bg-white border border-purple-200 rounded-full hover:bg-purple-100 hover:border-purple-300 transition-colors"
            >
              {{ preset.name }}
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 禁用时的提示 -->
    <div v-if="!enabled" class="text-xs text-gray-400 mt-2">
      启用后可以精确控制章节的情绪走向，让读者的阅读体验更加沉浸
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue';

interface EmotionCurve {
  start: number;
  peak: number;
  end: number;
}

interface EmotionBeat {
  primary_emotion: string;
  intensity: number;
  curve: EmotionCurve;
  turning_point: string;
}

interface Preset {
  name: string;
  beat: EmotionBeat;
}

const props = defineProps({
  modelValue: {
    type: Object as () => EmotionBeat | null,
    default: null
  }
});

const emit = defineEmits(['update:modelValue']);

const enabled = ref(false);

const defaultBeat: EmotionBeat = {
  primary_emotion: '',
  intensity: 5,
  curve: { start: 3, peak: 7, end: 5 },
  turning_point: ''
};

const localBeat = ref<EmotionBeat>({ ...defaultBeat });

const emotionTypes = [
  { value: '悬疑紧张', label: '悬疑紧张', icon: '😰' },
  { value: '温暖感动', label: '温暖感动', icon: '🥹' },
  { value: '愤怒不甘', label: '愤怒不甘', icon: '😤' },
  { value: '好奇期待', label: '好奇期待', icon: '🤔' },
  { value: '忧伤惆怅', label: '忧伤惆怅', icon: '😢' },
  { value: '欢快愉悦', label: '欢快愉悦', icon: '😄' }
];

const presets: Preset[] = [
  {
    name: '标准波动',
    beat: { primary_emotion: '', intensity: 5, curve: { start: 3, peak: 7, end: 5 }, turning_point: '' }
  },
  {
    name: '大起大落',
    beat: { primary_emotion: '', intensity: 8, curve: { start: 2, peak: 9, end: 3 }, turning_point: '' }
  },
  {
    name: '持续上升',
    beat: { primary_emotion: '', intensity: 7, curve: { start: 4, peak: 8, end: 9 }, turning_point: '' }
  },
  {
    name: '平缓叙事',
    beat: { primary_emotion: '', intensity: 4, curve: { start: 4, peak: 5, end: 4 }, turning_point: '' }
  },
  {
    name: '悬念结尾',
    beat: { primary_emotion: '悬疑紧张', intensity: 7, curve: { start: 3, peak: 6, end: 8 }, turning_point: '' }
  }
];

// 计算曲线路径
const curvePath = computed(() => {
  const { start, peak, end } = localBeat.value.curve;
  const startY = 40 - (start / 10) * 35;
  const peakY = 40 - (peak / 10) * 35;
  const endY = 40 - (end / 10) * 35;
  
  return `M 5 ${startY} Q 25 ${startY} 50 ${peakY} Q 75 ${peakY} 95 ${endY}`;
});

const selectEmotion = (emotion: string) => {
  localBeat.value.primary_emotion = emotion;
  emitUpdate();
};

const applyPreset = (preset: Preset) => {
  localBeat.value = { 
    ...preset.beat, 
    primary_emotion: localBeat.value.primary_emotion || preset.beat.primary_emotion 
  };
  emitUpdate();
};

const emitUpdate = () => {
  if (enabled.value) {
    emit('update:modelValue', { ...localBeat.value });
  } else {
    emit('update:modelValue', null);
  }
};

// 监听启用状态
watch(enabled, (newVal) => {
  if (newVal) {
    emit('update:modelValue', { ...localBeat.value });
  } else {
    emit('update:modelValue', null);
  }
});

// 监听本地数据变化
watch(localBeat, () => {
  if (enabled.value) {
    emitUpdate();
  }
}, { deep: true });

// 初始化
watch(() => props.modelValue, (newVal) => {
  if (newVal) {
    enabled.value = true;
    localBeat.value = { ...newVal };
  }
}, { immediate: true });
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: all 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #a855f7;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
}

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #a855f7;
  cursor: pointer;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  border: none;
}
</style>
