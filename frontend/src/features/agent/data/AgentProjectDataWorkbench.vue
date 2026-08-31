<template>
  <XqPanel
    title="项目实体上下文"
    subtitle="选择最小实体引用；Agent 再通过受控能力读取摘要。"
    data-testid="agent-project-data-workbench"
  >
    <p v-if="!projectId" class="muted">先选择小说项目，再选择需要提供给 Agent 的实体。</p>
    <p v-else-if="loading" class="muted">正在读取项目实体摘要…</p>
    <p v-else-if="error" class="error">{{ error }}</p>
    <template v-else>
      <p class="muted" data-testid="agent-project-entity-selection-count">
        已选择 {{ selectedKeys.size }} / {{ maxSelections }} 个实体；列表只含类型、标识和状态，不含正文或研究来源。
      </p>
      <ul v-if="entities.length" class="entity-list" data-testid="agent-project-entity-list">
        <li v-for="entity in entities" :key="summaryKey(entity)" class="entity-row">
          <div>
            <strong>{{ kindLabel(entity.kind) }} · {{ entity.label }}</strong>
            <small v-if="entity.status || entity.detail">{{ [entity.status, entity.detail].filter(Boolean).join(' · ') }}</small>
          </div>
          <XqButton
            size="sm"
            :variant="isSelected(entity) ? 'secondary' : 'primary'"
            :disabled="!isSelected(entity) && selectedKeys.size >= maxSelections"
            :data-testid="`agent-project-entity-${entity.kind}-${entity.entity_id}`"
            @click="toggle(entity)"
          >{{ isSelected(entity) ? '移除上下文' : '加入上下文' }}</XqButton>
        </li>
      </ul>
      <p v-else class="muted">当前项目还没有可选择的实体摘要。</p>
    </template>
  </XqPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { AgentAPI, type AgentEntityContextKind, type AgentEntitySummary } from '@/api/agent'
import type { AgentManualEntityRef } from '@/features/agent/contextRefs'
import { XqButton, XqPanel } from '@/shared/ui'

const props = withDefaults(defineProps<{
  projectId?: string
  selectedEntityRefs: AgentManualEntityRef[]
  maxSelections?: number
}>(), {
  projectId: '',
  selectedEntityRefs: () => [],
  maxSelections: 16,
})

const emit = defineEmits<{
  (event: 'toggle-entity', value: AgentManualEntityRef): void
}>()

const entities = ref<AgentEntitySummary[]>([])
const loading = ref(false)
const error = ref('')
let requestGeneration = 0

const entityKey = (entity: AgentManualEntityRef) => `${entity.kind}:${entity.entityId}`
const summaryKey = (entity: AgentEntitySummary) => `${entity.kind}:${entity.entity_id}`
const selectedKeys = computed(() => new Set(props.selectedEntityRefs.map(entityKey)))
const isSelected = (entity: AgentEntitySummary) => selectedKeys.value.has(summaryKey(entity))
const kindLabel = (kind: AgentEntityContextKind) => ({
  character: '人物',
  faction: '势力',
  foreshadowing: '伏笔',
  knowledge_node: '知识节点',
  research_artifact: '研究工件',
}[kind])

const load = async () => {
  const projectId = props.projectId.trim()
  const generation = ++requestGeneration
  entities.value = []
  error.value = ''
  if (!projectId) return
  loading.value = true
  try {
    const result = await AgentAPI.listProjectEntitySummaries(projectId)
    if (generation !== requestGeneration || projectId !== props.projectId.trim()) return
    entities.value = Array.isArray(result.entities) ? result.entities : []
  } catch (cause) {
    if (generation !== requestGeneration) return
    error.value = cause instanceof Error ? cause.message : '项目实体摘要不可用'
  } finally {
    if (generation === requestGeneration) loading.value = false
  }
}

const toggle = (entity: AgentEntitySummary) => {
  emit('toggle-entity', { kind: entity.kind, entityId: entity.entity_id })
}

watch(() => props.projectId, () => void load(), { immediate: true })
</script>

<style scoped>
.entity-list { display: grid; gap: 0.5rem; margin: 0; padding: 0; list-style: none; }
.entity-row { display: flex; align-items: center; justify-content: space-between; gap: 0.75rem; padding: 0.55rem; border: 1px solid rgba(255,255,255,.14); border-radius: 0.55rem; }
.entity-row strong, .entity-row small { display: block; }
.entity-row small { margin-top: .15rem; color: rgba(255,255,255,.62); }
.error { color: #fca5a5; }
</style>
