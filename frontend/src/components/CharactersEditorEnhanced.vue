<!-- AIMETA P=增强角色编辑器_增强版角色编辑|R=增强角色编辑|NR=不含基础功能|E=component:CharactersEditorEnhanced|X=internal|A=增强编辑器|D=vue|S=dom|RD=./README.ai -->
<template>
  <div class="space-y-4 max-h-[600px] overflow-y-auto p-1">
    <div v-for="(character, index) in localCharacters" :key="index" class="p-4 border border-gray-200 rounded-lg bg-gray-50 relative">
      <button @click="removeCharacter(index)" class="absolute top-2 right-2 text-red-400 hover:text-red-600 transition-colors p-1">
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
          <path fill-rule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm4 0a1 1 0 012 0v6a1 1 0 11-2 0V8z" clip-rule="evenodd" />
        </svg>
      </button>
      
      <!-- 基础信息 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('姓名', 'Name') }}</label>
          <input type="text" v-model="character.name" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('身份', 'Identity') }}</label>
          <input type="text" v-model="character.identity" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('性格', 'Personality') }}</label>
          <input type="text" v-model="character.personality" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('目标', 'Goals') }}</label>
          <input type="text" v-model="character.goals" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('能力', 'Abilities') }}</label>
          <input type="text" v-model="character.abilities" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-600 mb-1">{{ pick('与主角关系', 'Relationship to protagonist') }}</label>
          <input type="text" v-model="character.relationship_to_protagonist" class="w-full p-1 border-b-2 border-gray-300 focus:border-indigo-500 outline-none transition bg-transparent" />
        </div>
      </div>

      <!-- DNA档案展开按钮 -->
      <div class="mt-4 border-t border-gray-200 pt-3">
        <button 
          @click="toggleDNA(index)" 
          class="flex items-center gap-2 text-sm font-medium text-purple-600 hover:text-purple-800 transition-colors"
        >
          <svg 
            xmlns="http://www.w3.org/2000/svg" 
            class="h-4 w-4 transition-transform" 
            :class="{ 'rotate-90': expandedDNA[index] }"
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
          <span>🧬 {{ pick('角色DNA档案', 'Character DNA profile') }}</span>
          <span class="text-xs text-gray-400">{{ pick('(让角色更立体)', '(adds depth to the character)') }}</span>
        </button>
      </div>

      <!-- DNA档案内容 -->
      <transition name="slide">
        <div v-if="expandedDNA[index]" class="mt-3 p-4 bg-purple-50 rounded-lg border border-purple-200">
          <div class="grid grid-cols-1 gap-4">
            <!-- 童年经历 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('童年经历/创伤', 'Childhood / trauma') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('影响角色的防御机制和情感触发点', 'Shapes the character’s defenses and emotional triggers') }}</span>
              </label>
              <textarea
                v-model="getDNAProfile(character).childhood_trauma"
                @input="updateDNA(character, 'childhood_trauma', ($event.target as HTMLTextAreaElement).value)"
                :placeholder="pick('例如：父母离异后由祖母抚养，从小学会察言观色，害怕被抛弃', 'e.g. raised by a grandmother after the parents split, learned early to read the room, fears abandonment')"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 核心恐惧 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('核心恐惧', 'Core fear') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('驱动角色行为的深层恐惧', 'The deep fear that drives the character’s behavior') }}</span>
              </label>
              <input
                type="text"
                v-model="getDNAProfile(character).core_fear"
                @input="updateDNA(character, 'core_fear', ($event.target as HTMLInputElement).value)"
                :placeholder="pick('例如：害怕被抛弃、害怕失控、害怕不被爱', 'e.g. fear of abandonment, of losing control, of being unloved')"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              />
            </div>

            <!-- 内心渴望 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('内心渴望', 'Inner desire') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('角色真正想要的，可能连自己都不清楚', 'What the character truly wants — perhaps without knowing it') }}</span>
              </label>
              <input
                type="text"
                v-model="getDNAProfile(character).inner_desire"
                @input="updateDNA(character, 'inner_desire', ($event.target as HTMLInputElement).value)"
                :placeholder="pick('例如：渴望被认可、渴望归属感、渴望证明自己', 'e.g. craves recognition, belonging, or a chance to prove themselves')"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              />
            </div>

            <!-- 说话习惯 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('说话习惯', 'Speech habits') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('口头禅、语气词、紧张时的变化', 'Catchphrases, filler words, how speech shifts under stress') }}</span>
              </label>
              <textarea
                v-model="getDNAProfile(character).speech_habits"
                @input="updateDNA(character, 'speech_habits', ($event.target as HTMLTextAreaElement).value)"
                :placeholder="pick(`例如：喜欢用反问句，紧张时语速加快，常说'怎么说呢...'`, `e.g. favors rhetorical questions, speeds up when nervous, often says 'how should I put it...'`)"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 身体语言 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('身体语言', 'Body language') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('紧张时的小动作、特有的姿态', 'Nervous tics and signature postures') }}</span>
              </label>
              <textarea
                v-model="getDNAProfile(character).body_language"
                @input="updateDNA(character, 'body_language', ($event.target as HTMLTextAreaElement).value)"
                :placeholder="pick('例如：紧张时会摸耳朵，思考时喜欢转笔，说谎时不敢直视对方', 'e.g. touches an ear when nervous, spins a pen while thinking, avoids eye contact when lying')"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>

            <!-- 思维模式 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('思维模式', 'Thinking pattern') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('理性/感性、乐观/悲观', 'Rational vs. intuitive, optimistic vs. pessimistic') }}</span>
              </label>
              <select 
                v-model="getDNAProfile(character).thinking_pattern"
                @change="updateDNA(character, 'thinking_pattern', ($event.target as HTMLSelectElement).value)"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              >
                <!-- option 的 value 会写入 dna_profile 并进入生成提示词，属于数据，保持中文原文不翻译 -->
                <option value="">{{ pick('请选择...', 'Select...') }}</option>
                <option value="理性分析型，遇事先冷静思考">{{ pick('理性分析型', 'Analytical') }}</option>
                <option value="直觉感受型，跟着感觉走">{{ pick('直觉感受型', 'Intuitive') }}</option>
                <option value="乐观主义者，总能看到希望">{{ pick('乐观主义者', 'Optimist') }}</option>
                <option value="悲观主义者，习惯做最坏打算">{{ pick('悲观主义者', 'Pessimist') }}</option>
                <option value="全局思考型，喜欢从大局出发">{{ pick('全局思考型', 'Big-picture thinker') }}</option>
                <option value="细节关注型，注重每个细节">{{ pick('细节关注型', 'Detail-focused') }}</option>
              </select>
            </div>

            <!-- 决策方式 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('决策方式', 'Decision style') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('如何做出选择', 'How the character makes choices') }}</span>
              </label>
              <select
                v-model="getDNAProfile(character).decision_style"
                @change="updateDNA(character, 'decision_style', ($event.target as HTMLSelectElement).value)"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
              >
                <!-- 同上：option 的 value 是数据，不翻译 -->
                <option value="">{{ pick('请选择...', 'Select...') }}</option>
                <option value="快速决断，不喜欢犹豫">{{ pick('快速决断型', 'Decisive') }}</option>
                <option value="反复权衡，考虑各种可能">{{ pick('深思熟虑型', 'Deliberate') }}</option>
                <option value="依赖逻辑，用数据说话">{{ pick('逻辑驱动型', 'Logic-driven') }}</option>
                <option value="依赖情感，跟着心走">{{ pick('情感驱动型', 'Emotion-driven') }}</option>
                <option value="喜欢独立决策，不爱听别人意见">{{ pick('独立决策型', 'Independent') }}</option>
                <option value="喜欢征求他人意见再做决定">{{ pick('群策群力型', 'Consensus-seeking') }}</option>
              </select>
            </div>

            <!-- 隐藏的秘密 -->
            <div>
              <label class="block text-sm font-medium text-purple-700 mb-1">
                {{ pick('隐藏的秘密', 'Hidden secret') }}
                <span class="text-xs text-gray-500 font-normal ml-1">{{ pick('不愿让人知道的事', 'What the character will not let others know') }}</span>
              </label>
              <textarea
                v-model="getDNAProfile(character).hidden_secret"
                @input="updateDNA(character, 'hidden_secret', ($event.target as HTMLTextAreaElement).value)"
                :placeholder="pick('例如：曾经因为自己的失误导致好友受伤，一直心怀愧疚', 'e.g. a past mistake injured a close friend, and the guilt never left')"
                class="w-full p-2 border border-purple-200 rounded-md focus:border-purple-500 focus:ring-1 focus:ring-purple-500 outline-none transition bg-white text-sm"
                rows="2"
              ></textarea>
            </div>
          </div>

          <!-- DNA完成度提示 -->
          <div class="mt-4 flex items-center gap-2">
            <div class="flex-1 bg-gray-200 rounded-full h-2">
              <div
                class="bg-purple-500 h-2 rounded-full transition-all duration-300"
                :style="{ width: getDNACompleteness(character) + '%' }"
              ></div>
            </div>
            <span class="text-xs text-gray-500">{{ pick(`${getDNACompleteness(character)}% 完成`, `${getDNACompleteness(character)}% complete`) }}</span>
          </div>
          <p class="mt-2 text-xs text-gray-500">
            {{ pick('💡 提示：DNA档案越完整，AI生成的角色行为和对话就越真实立体', '💡 Tip: the fuller the DNA profile, the more believable the generated behavior and dialogue') }}
          </p>
        </div>
      </transition>
    </div>

    <button @click="addCharacter" class="w-full mt-4 px-4 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 border border-indigo-200 rounded-md hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500">
      {{ pick('+ 添加新角色', '+ Add character') }}
    </button>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive, nextTick } from 'vue';

import { useLocale } from '@/composables/useLocale';

interface DNAProfile {
  childhood_trauma: string;
  core_fear: string;
  inner_desire: string;
  speech_habits: string;
  body_language: string;
  thinking_pattern: string;
  decision_style: string;
  hidden_secret: string;
}

interface Character {
  name: string;
  identity: string;
  personality: string;
  goals: string;
  abilities: string;
  relationship_to_protagonist: string;
  extra?: {
    dna_profile?: DNAProfile;
    [key: string]: any;
  };
}

const props = defineProps({
  modelValue: {
    type: Array as () => Character[],
    default: () => []
  }
});

const emit = defineEmits(['update:modelValue']);

const { pick } = useLocale();

const localCharacters = ref<Character[]>([]);
const expandedDNA = reactive<Record<number, boolean>>({});
let syncing = false;

// 初始化DNA档案
const initDNAProfile = (): DNAProfile => ({
  childhood_trauma: '',
  core_fear: '',
  inner_desire: '',
  speech_habits: '',
  body_language: '',
  thinking_pattern: '',
  decision_style: '',
  hidden_secret: ''
});

// 获取角色的DNA档案
const getDNAProfile = (character: Character): DNAProfile => {
  if (!character.extra) {
    character.extra = {};
  }
  if (!character.extra.dna_profile) {
    character.extra.dna_profile = initDNAProfile();
  }
  return character.extra.dna_profile;
};

// 更新DNA字段
const updateDNA = (character: Character, field: keyof DNAProfile, value: string) => {
  const profile = getDNAProfile(character);
  profile[field] = value;
  // 触发更新
  emit('update:modelValue', JSON.parse(JSON.stringify(localCharacters.value)));
};

// 计算DNA完成度
const getDNACompleteness = (character: Character): number => {
  const profile = getDNAProfile(character);
  const fields = Object.values(profile);
  const filledFields = fields.filter(v => v && v.trim().length > 0);
  return Math.round((filledFields.length / fields.length) * 100);
};

// 切换DNA展开状态
const toggleDNA = (index: number) => {
  expandedDNA[index] = !expandedDNA[index];
};

watch(() => props.modelValue, (newVal) => {
  syncing = true;
  localCharacters.value = JSON.parse(JSON.stringify(newVal || []));
  nextTick(() => {
    syncing = false;
  });
}, { immediate: true });

watch(localCharacters, (newVal) => {
  if (syncing) return;
  emit('update:modelValue', JSON.parse(JSON.stringify(newVal)));
}, { deep: true });

const addCharacter = () => {
  localCharacters.value.push({ 
    name: '', 
    identity: '', 
    personality: '', 
    goals: '', 
    abilities: '', 
    relationship_to_protagonist: '',
    extra: {
      dna_profile: initDNAProfile()
    }
  });
};

const removeCharacter = (index: number) => {
  localCharacters.value.splice(index, 1);
  delete expandedDNA[index];
};
</script>

<style scoped>
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 1000px;
}
</style>
