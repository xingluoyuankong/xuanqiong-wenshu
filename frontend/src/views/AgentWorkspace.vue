<template>
  <AgentWorkspaceShell
    :busy="busy"
    :project-title="selectedProject?.title"
    :session-status="session?.status || null"
    :has-selected-project="Boolean(selectedProject)"
  >
    <template #sidebar>
      <div class="workspace-sidebar-stack" data-testid="agent-sidebar-stack">
        <details class="workspace-section" open data-testid="agent-project-section">
          <summary>
            <span>项目与内容</span>
            <small>{{ selectedProject ? `${selectedProject.completed_chapters || 0}/${selectedProject.total_chapters || 0} 章` : '未选择' }}</small>
          </summary>
          <div class="workspace-section-body">
            <XqPanel title="项目上下文" subtitle="Agent 只能操作当前项目。">
              <label for="agent-project">小说项目</label>
              <select
                id="agent-project"
                v-model="selectedProjectId"
                data-testid="agent-project-select"
                @change="switchProject"
              >
                <option value="">请选择项目</option>
                <option v-for="project in projects" :key="project.id" :value="project.id">
                  {{ project.title || '未命名项目' }}
                </option>
              </select>
              <p class="muted">
                {{
                  selectedProject
                    ? `${selectedProject.completed_chapters || 0}/${selectedProject.total_chapters || 0} 章已完成`
                    : '项目、章节、版本、质量和任务状态会作为受控上下文。'
                }}
              </p>
              <XqButton
                variant="secondary"
                size="sm"
                :disabled="!selectedProject"
                @click="openWritingDesk"
              >打开写作台</XqButton>
            </XqPanel>
            <ProjectContentTree
              v-if="selectedProject"
              :volumes="contentVolumes"
              :selected-chapter-number="contentSelectedChapterNumber"
              :selected-version-id="contentSelectedVersionId"
              :selected-chapter="contentSelectedChapter"
              :selected-version="contentSelectedVersion"
              :loading="contentTreeLoading"
              :loading-chapter="contentTreeLoadingChapter"
              :error="contentTreeError"
              @select-chapter="selectContentChapter"
              @select-version="selectContentVersion"
              @open-writing-desk="openContentInWritingDesk"
            />
          </div>
        </details>

        <details class="workspace-section" data-testid="agent-session-section">
          <summary>
            <span>会话</span>
            <small>{{ Array.isArray(sessions) ? sessions.length : 0 }} 个</small>
          </summary>
          <div class="workspace-section-body">
            <XqPanel
              title="Agent 会话"
              subtitle="同一项目下可切换历史会话。"
              data-testid="agent-session-panel"
            >
              <select
                v-model="selectedSessionId"
                data-testid="agent-session-select"
                :disabled="sessionLoading"
              >
                <option v-for="item in sessions" :key="item.id" :value="item.id">
                  {{ item.title || '未命名会话' }} · {{ item.status }}
                </option>
              </select>
              <div class="session-actions">
                <XqButton
                  size="sm"
                  @click="createNewSession"
                  :disabled="!selectedProject || sessionLoading"
                >新建</XqButton>
                <XqButton
                  variant="secondary"
                  size="sm"
                  @click="archiveCurrentSession"
                  :disabled="!session || session.status === 'archived'"
                >归档</XqButton>
              </div>
            </XqPanel>
          </div>
        </details>

        <details class="workspace-section" data-testid="agent-tools-section">
          <summary>
            <span>项目工具</span>
            <small>{{ tools.length }} 项</small>
          </summary>
          <div class="workspace-section-body">
            <XqPanel title="可用项目工具" subtitle="来自后端注册表的能力。">
              <p v-if="toolsError" class="error">{{ toolsError }}</p>
              <p v-else-if="loadingTools" class="muted">正在读取工具注册表…</p>
              <template v-else>
                <p v-if="catalogGeneration" class="muted" data-testid="agent-tool-catalog-generation">
                  能力目录第 {{ catalogGeneration }} 代 · {{ tools.length }} 项
                </p>
                <ul class="tool-list" data-testid="agent-tool-list">
                  <li v-for="tool in tools" :key="tool.name">
                    <strong>{{ tool.name }}</strong>
                    <span>{{ riskLabel(tool.risk_level) }}</span>
                    <small>{{ tool.description }}</small>
                    <small>{{ toolSource(tool) }}</small>
                  </li>
                </ul>
              </template>
            </XqPanel>
          </div>
        </details>

        <details class="workspace-section" data-testid="agent-data-section">
          <summary>
            <span>数据与候选</span>
            <small>按需展开</small>
          </summary>
          <div class="workspace-section-body">
            <AgentDataPanel
              :is-admin="isAdmin"
              :provider-health="providerHealth"
              :provider-health-loading="providerHealthLoading"
              :provider-health-error="providerHealthError"
              :active-run-id="activeRun?.id || null"
              :provider-usage-summary="activeProviderUsageSummary"
              :provider-usage-summary-loading="providerUsageSummaryLoading"
              :provider-usage-summary-error="activeProviderUsageSummaryError || ''"
              :timeline="timeline"
              :timeline-loading="timelineLoading"
              :timeline-event-type="timelineEventType"
              :timeline-run-status="timelineRunStatus"
              :jobs="jobs"
              :jobs-loading="jobsLoading"
              :dead-letters="deadLetters"
              :dead-letters-loading="deadLettersLoading"
              :audit-ledger="auditLedger"
              :audit-loading="auditLoading"
              :can-list-dead-letters="typeof AgentAPI.listDeadLetters === 'function'"
              @update:timeline-event-type="timelineEventType = $event"
              @update:timeline-run-status="timelineRunStatus = $event"
              @cancel-job="cancelJobAction"
              @replay-dead-letter="replayDeadLetterAction"
            />
            <AgentProjectDataWorkbench
              :project-id="selectedProjectId"
              :selected-entity-refs="manualEntityContextRefs"
              @toggle-entity="toggleEntityContextRef"
            />
          </div>
        </details>
      </div>
    </template>

    <template #main>
      <section class="workspace-chat-column" data-testid="agent-chat-column">
        <AgentConversation
          :messages="messages"
          :session-title="session?.title || null"
          :session-loading="sessionLoading"
          :stream-connection-state="streamConnectionState"
          :session-error="sessionError"
          :runtime-supported="runtimeSupported"
          :sending="sending"
          :planning="planning"
          :streaming-assistant="streamingAssistant"
          :latest-progress-message="latestProgressMessage"
          :latest-progress-action-id="runProjection.activeEventProjection.value.latestProgressActionId"
          :latest-progress-phase="runProjection.activeEventProjection.value.latestProgressPhase"
          :latest-progress="runProjection.activeEventProjection.value.latestProgress"
          :artifact-preview="artifactPreview"
          :artifact-preview-loading="artifactPreviewLoading"
          :artifact-preview-artifact-id="artifactPreviewArtifactId"
          :artifact-preview-error="artifactPreviewError"
          :public-work-summary="publicWorkSummary"
          :work-trace-deltas="runProjection.activeWorkTraceDeltas.value"
          :latest-work-trace="runProjection.latestWorkTrace.value"
          :has-sequence-gap="runProjection.activeEventProjection.value.hasSequenceGap"
          :replay-required="runProjection.replayRequired.value"
          :pending-sequences="runProjection.activeEventProjection.value.pendingSequences"
          :context-refs="activeContextRefs"
          :project-title="selectedProject?.title"
          :chapter-title="contentSelectedChapter?.title"
          :goal="goal"
          @update:goal="goal = $event"
          @submit="submitMessage"
          @remove-context-ref="removeContextRef"
          @close-artifact-preview="artifactPreview = ''"
        />
      </section>
    </template>

    <template #activity>
      <div class="workspace-activity-stack" data-testid="agent-activity-stack">
        <XqPanel v-if="runs.length" title="本会话运行" data-testid="agent-run-selector-panel">
          <label class="run-selector-label">
            <span>查看运行</span>
            <select
              v-model="selectedRunId"
              data-testid="agent-run-selector"
              @change="onRunSelectChange"
            >
              <option v-for="run in runs" :key="run.id" :value="run.id">
                {{ run.id.slice(0, 8) }} · {{ runStatus(run.status) }} · {{ Math.round(run.progress) }}%
              </option>
            </select>
          </label>
          <p class="muted" data-testid="agent-selected-run-id">
            {{ selectedRunId ? `当前：${selectedRunId.slice(0, 8)}` : '尚未选择运行' }}
          </p>
        </XqPanel>

        <XqPanel class="workspace-log-panel" title="运行日志" subtitle="实时事件摘要；独立滚动，不占用聊天阅读区。" data-testid="agent-log-panel">
          <small v-if="hiddenLogEventCount" class="workspace-log-window" data-testid="agent-log-window">已折叠更早的 {{ hiddenLogEventCount }} 条日志</small>
          <div ref="logListEl" class="events workspace-log-list" data-testid="agent-process-stream" @scroll="onLogScroll">
            <article v-for="event in visibleLogEvents" :key="event.id">
              <strong>{{ event.label }}</strong>
              <small v-if="event.actionId || event.phase || event.resultRef" class="workspace-log-meta">
                <span v-if="event.phase">阶段：{{ event.phase }}</span>
                <button v-if="event.actionId" type="button" class="workspace-log-ref" data-testid="agent-log-action-ref" @click="selectLogLocation('action', event.actionId)">动作：{{ event.actionId }}</button>
                <button v-if="event.resultRef" type="button" class="workspace-log-ref" data-testid="agent-log-result-ref" @click="selectLogLocation('result', event.resultRef)">结果：{{ event.resultRef }}</button>
                <span v-if="event.progress !== undefined">{{ Math.round(event.progress) }}%</span>
              </small>
              <p>{{ event.detail }}</p>
            </article>
          </div>
        </XqPanel>

        <details ref="inspectorSectionEl" class="workspace-section workspace-inspector-section" data-testid="agent-inspector-section">
          <summary>
            <span>当前运行</span>
            <small>{{ activeRun ? `${runStatus(activeRun.status)} · ${Math.round(activeRun.progress)}%` : '暂无运行' }}</small>
          </summary>
          <div class="workspace-section-body">
            <AgentRunInspector
              :run="activeRun"
              :state="runState"
              :steps="runSteps"
              :tool-results="toolResults"
              :provenance="providerProvenance"
              :has-sequence-gap="runProjection.activeEventProjection.value.hasSequenceGap"
              :gap-repair-state="gapRepairState"
              :connection-state="streamConnectionState"
              :control-pending="Boolean(activeRun && runControlLoading[activeRun.id])"
              :progress-message="latestProgressMessage"
              :selected-action-ref="selectedActionRef"
              :selected-result-ref="selectedResultRef"
              :execution-facts="activeExecutionFacts"
              :execution-facts-error="activeExecutionFactsError"
              @command="runControlAction"
              @recover="activeRun && recoverRunAction(activeRun)"
              @reconnect="reconnectActiveRun"
            />
          </div>
        </details>

        <details class="workspace-section workspace-activity-section" data-testid="agent-run-details-section">
          <summary><span>运行详情</span><small>计划、审批、候选</small></summary>
          <div class="workspace-section-body">
            <AgentRunFactPanel
              :context-snapshot="runProjection.activeContextSnapshot.value"
              :plan-revision="runProjection.activePlanRevision.value"
              :conversation-summaries="runProjection.activeConversationSummaries.value"
            />
            <XqPanel
              v-if="plan"
              title="执行计划"
              subtitle="写入工具后续需要审批。"
              data-testid="agent-plan-panel"
            >
              <p>{{ plan.goal }}</p>
              <p v-if="!plan.steps.length" class="muted" data-testid="agent-plan-queued">
                Agent 已接收目标，正在由执行器生成真实计划。
              </p>
              <ol v-else class="plan-list">
                <li v-for="step in plan.steps" :key="step.step_id || step.order">
                  <b>{{ step.order }}. {{ step.tool_name }}</b>
                  <span>{{ step.description }}</span>
                  <small v-if="step.expected_result">预计：{{ step.expected_result }}</small>
                  <em v-if="step.requires_confirmation">需要确认</em>
                </li>
              </ol>
            </XqPanel>
            <XqPanel
              v-if="approvals.length"
              title="待审批操作"
              subtitle="批准只代表允许执行，当前写入工具仍不会直接覆盖正文。"
              data-testid="agent-approval-panel"
            >
              <article v-for="approval in approvals" :key="approval.id" class="approval-card">
                <b>{{ approval.tool_name }}</b>
                <span :class="`approval-${approval.status}`">{{ approvalStatus(approval.status) }}</span>
                <small v-if="approval.reason">{{ approval.reason }}</small>
                <div v-if="approval.status === 'pending'" class="approval-actions">
                  <XqButton size="sm" data-testid="agent-approve-button" @click="decideApproval(approval, true)">批准</XqButton>
                  <XqButton variant="secondary" size="sm" data-testid="agent-reject-button" @click="decideApproval(approval, false)">拒绝</XqButton>
                </div>
                <div v-else-if="approval.status === 'approved' && typeof AgentAPI.executeApproval === 'function'" class="approval-actions">
                  <XqButton size="sm" data-testid="agent-execute-button" @click="executeApprovalAction(approval)">生成候选</XqButton>
                </div>
              </article>
            </XqPanel>
            <AgentArtifactWorkbench
              :artifacts="artifacts"
              :quality-facts="artifactQualityFacts"
              :quality-facts-loading="artifactQualityFactsLoading"
              :quality-facts-errors="artifactQualityFactsErrors"
              :lineage-facts="artifactLineageFacts"
              :lineage-facts-loading="artifactLineageFactsLoading"
              :lineage-facts-errors="artifactLineageFactsErrors"
              :quality-blockers="qualityBlockers"
              :quality-blockers-artifact-id="qualityBlockersArtifactId"
              :quality-blockers-error="qualityBlockersError"
              :quality-blockers-loading-by-artifact="qualityBlockersLoadingByArtifact"
              :quality-blockers-loading="qualityBlockersLoading"
              :rewrite-instructions="rewriteInstructions"
              :rewrite-loading="rewriteLoading"
              :rewrite-errors="rewriteErrors"
              :artifact-diff="artifactDiff"
              :artifact-diff-artifact-id="artifactDiffArtifactId"
              :artifact-diff-error="artifactDiffError"
              :artifact-diff-loading="artifactDiffLoading"
              :selected-quality-finding-ids="manualQualityFindingContextRefs.map((item) => item.findingId).filter((findingId): findingId is string => Boolean(findingId))"
              :has-selected-project="Boolean(selectedProject)"
              :can-preview="typeof AgentAPI.getArtifactContent === 'function'"
              :can-diff="typeof AgentAPI.getArtifactDiff === 'function'"
              :can-locate-blockers="typeof AgentAPI.listArtifactQualityBlockers === 'function'"
              :can-load-rewrite-instructions="typeof AgentAPI.listArtifactRewriteInstructions === 'function'"
              :can-compare-with-version="typeof AgentAPI.getArtifactVersionDiff === 'function'"
              :can-accept="typeof AgentAPI.acceptArtifact === 'function'"
              @preview="previewArtifact"
              @compare="compareArtifact"
              @locate-blockers="loadQualityBlockers"
              @load-rewrite-instructions="loadRewriteInstructions"
              @compare-with-version="compareArtifactWithVersion"
              @accept="acceptArtifactAction"
              @toggle-quality-finding="toggleQualityFindingContextRef"
              @open-writing-desk="({ artifact, focus }) => openWritingDesk(artifact, focus)"
            />
          </div>
        </details>

        <details class="workspace-section workspace-activity-section" data-testid="agent-governance-section">
          <summary><span>运行规则</span><small>边界与质量来源</small></summary>
          <div class="workspace-section-body workspace-rule-grid">
            <XqPanel title="执行规则">
              <ul>
                <li>读取：自动执行</li>
                <li>建议：自动规划</li>
                <li>写入：展示计划</li>
                <li>高风险：明确确认</li>
              </ul>
            </XqPanel>
            <XqPanel title="质量来源">
              <ul>
                <li>自动指标</li>
                <li>模型分析</li>
                <li>人工标签</li>
                <li>用户确认</li>
              </ul>
            </XqPanel>
          </div>
        </details>
      </div>
    </template>
  </AgentWorkspaceShell>
</template>
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getActivePinia } from 'pinia'
import { useRoute, useRouter } from 'vue-router'
import {
  AgentAPI,
  type AgentApproval,
  type AgentArtifact,
  type AgentArtifactLineage,
  type AgentArtifactQuality,
  type AgentArtifactDiff,
  type AgentAuditRecord,
  type AgentEvent,
  type AgentJob,
  type AgentQualityBlocker,
  type AgentMessage,
  type AgentPlanResponse,
  type AgentProviderProvenance,
  type AgentProviderUsageSummary,
  type AgentRewriteInstruction,
  type AgentRiskLevel,
  type AgentRun,
  type AgentRunStep,
  type AgentExecutionFact,
  type AgentSession,
  type AgentTimelineEvent,
  type AgentStateProjection,
  type AgentToolDescriptor,
  type AgentToolHealth,
  type AgentToolResult,
  type AgentContextRef,
  type AgentSessionDetail,
} from '@/api/agent'
import { type SSEConnectionState } from '@/utils/sseStream'
import { toSafeAgentEvent } from '@/utils/agentEventSafety'
import { useAgentRunStream } from '@/features/agent/composables/useAgentRunStream'
import { type AgentDisplayEvent } from '@/features/agent/reducers/agentEventReducer'
import { useAgentRunProjection } from '@/features/agent/stores/agentRunProjection'
import { parseAgentRouteState, writingDeskQueryFromAgent } from '@/features/agent/routeState'
import AgentToolResultPanel from '@/features/agent/AgentToolResultPanel.vue'
import AgentConversation from '@/features/agent/AgentConversation.vue'
import AgentWorkspaceShell from '@/features/agent/AgentWorkspaceShell.vue'
import AgentRunControlBar from '@/features/agent/AgentRunControlBar.vue'
import AgentRunCommandHistory from '@/features/agent/AgentRunCommandHistory.vue'
import AgentRunFactPanel from '@/features/agent/AgentRunFactPanel.vue'
import AgentRunInspector from '@/features/agent/run/AgentRunInspector.vue'
import AgentArtifactWorkbench from '@/features/agent/artifacts/AgentArtifactWorkbench.vue'
import AgentDataPanel from '@/features/agent/data/AgentDataPanel.vue'
import AgentProjectDataWorkbench from '@/features/agent/data/AgentProjectDataWorkbench.vue'
import { buildAgentContextRefs, type AgentManualEntityRef, type AgentManualQualityFindingRef } from '@/features/agent/contextRefs'
import ProjectContentTree from '@/features/agent/content-tree/ProjectContentTree.vue'
import { useProjectContentTree } from '@/features/agent/content-tree/useProjectContentTree'
import { useAgentWorkspaceRuntime } from '@/features/agent/composables/useAgentWorkspaceRuntime'
import { useAgentSessionLifecycle } from '@/features/agent/composables/useAgentSessionLifecycle'
import { useAgentRunCommands } from '@/features/agent/composables/useAgentRunCommands'
import { useAgentProjectGovernanceData } from '@/features/agent/composables/useAgentProjectGovernanceData'
import { useNovelStore } from '@/stores/novel'
import { useAuthStore } from '@/stores/auth'
import { XqButton, XqPanel } from '@/shared/ui'

const route = useRoute()
const router = useRouter()
const runProjection = useAgentRunProjection()
const store = useNovelStore()
const authStore = getActivePinia() ? useAuthStore() : null
const deadLetters = ref<AgentJob[]>([])
const deadLettersLoading = ref(false)
const timeline = ref<AgentTimelineEvent[]>([])
const timelineEventType = ref('')
const timelineRunStatus = ref('')
const timelineLoading = ref(false)
const auditLedger = ref<AgentAuditRecord[]>([])
const auditLoading = ref(false)
const jobs = ref<AgentJob[]>([])
const jobsLoading = ref(false)
const selectedProjectId = ref('')
const manualEntityContextRefs = ref<AgentManualEntityRef[]>([])
const manualQualityFindingContextRefs = ref<AgentManualQualityFindingRef[]>([])
const goal = ref('')
const tools = ref<AgentToolDescriptor[]>([])
const catalogGeneration = ref<number | null>(null)
const loadingTools = ref(false)
const toolsError = ref('')
const planning = ref(false)
const sending = ref(false)
const sessionLoading = ref(false)
const sessionError = ref('')
const session = ref<AgentSession | null>(null)
const sessions = ref<AgentSession[]>([])
const selectedSessionId = ref('')
const messages = ref<AgentMessage[]>([])
const runs = runProjection.runs
const selectedRunId = runProjection.selectedRunId
const selectedActionRef = ref<string | null>(null)
const selectedResultRef = ref<string | null>(null)
const inspectorSectionEl = ref<HTMLDetailsElement | null>(null)
const executionFactsByRunId = ref<Record<string, AgentExecutionFact[]>>({})
const executionFactsErrorByRunId = ref<Record<string, string>>({})
const providerUsageSummaryByRunId = ref<Record<string, AgentProviderUsageSummary>>({})
const providerUsageSummaryLoadingByRunId = ref<Record<string, boolean>>({})
const providerUsageSummaryErrorByRunId = ref<Record<string, string>>({})
const activeRun = runProjection.activeRun
const runState = runProjection.activeRunState
const runSteps = runProjection.activeRunSteps
const approvals = runProjection.activeApprovals
const artifacts = runProjection.activeArtifacts
const responseToolResults = runProjection.activeToolResults
const activeExecutionFacts = computed<AgentExecutionFact[]>(() =>
  activeRun.value ? executionFactsByRunId.value[activeRun.value.id] || [] : [],
)
const activeExecutionFactsError = computed(() =>
  activeRun.value ? executionFactsErrorByRunId.value[activeRun.value.id] || null : null,
)
const activeProviderUsageSummary = computed(() =>
  activeRun.value ? providerUsageSummaryByRunId.value[activeRun.value.id] || null : null,
)
const providerUsageSummaryLoading = computed(() =>
  activeRun.value ? Boolean(providerUsageSummaryLoadingByRunId.value[activeRun.value.id]) : false,
)
const activeProviderUsageSummaryError = computed(() =>
  activeRun.value ? providerUsageSummaryErrorByRunId.value[activeRun.value.id] || null : null,
)
const workspaceEvents = ref<AgentDisplayEvent[]>([
  { id: 'ready', label: '已就绪', detail: '请选择小说项目，然后描述你希望 Agent 完成的目标。', sequence: 0, eventType: 'workspace' },
])
const workspaceEventKeys = new Set<string>()
const localPlan = ref<AgentPlanResponse | null>(null)
const plan = computed(() => activeRun.value ? runProjection.activePlan.value : localPlan.value)
const events = computed<AgentDisplayEvent[]>(() => {
  const source = activeRun.value
    ? runProjection.activeEventProjection.value.events
    : workspaceEvents.value
  if (!activeRun.value || !activeExecutionFacts.value.length) return source
  return source.map((event) => {
    if (event.resultRef || !event.actionId) return event
    const fact = activeExecutionFacts.value.find((item) => item.action_id === event.actionId)
    return fact ? { ...event, resultRef: fact.result_ref } : event
  })
})
const LOG_RENDER_LIMIT = 120
const LOG_TAIL_THRESHOLD = 24
const logListEl = ref<HTMLElement | null>(null)
const logFollowTail = ref(true)
const visibleLogEvents = computed(() => events.value.slice(-LOG_RENDER_LIMIT))
const hiddenLogEventCount = computed(() => Math.max(0, events.value.length - visibleLogEvents.value.length))
const isLogNearTail = (element: HTMLElement) =>
  element.scrollHeight - element.scrollTop - element.clientHeight <= LOG_TAIL_THRESHOLD
const onLogScroll = (event: Event) => {
  const element = event.currentTarget as HTMLElement | null
  if (element) logFollowTail.value = isLogNearTail(element)
}
const keepLogTailVisible = () => {
  const element = logListEl.value
  if (element && logFollowTail.value) element.scrollTop = element.scrollHeight
}
watch(
  () => visibleLogEvents.value.map((event) => event.id).join('|'),
  async () => {
    await nextTick()
    keepLogTailVisible()
  },
  { flush: 'post' },
)
watch(
  () => selectedRunId.value,
  async () => {
    clearRunLocation()
    logFollowTail.value = true
    await nextTick()
    keepLogTailVisible()
  },
  { flush: 'post' },
)
const streamingAssistant = computed(() => runProjection.activeEventProjection.value.assistantText)
const latestProgressMessage = computed(() => runProjection.activeEventProjection.value.latestProgressMessage)
const publicWorkSummary = computed(() => runState.value?.latest_public_summary || null)
const agentRunStream = useAgentRunStream()
const streamConnectionState = computed<SSEConnectionState>({
  get: () => runProjection.activeConnectionState.value,
  set: (state) => {
    if (activeRun.value) runProjection.setConnectionState(activeRun.value.id, state)
  },
})
const streaming = ref(false)
let loadGeneration = 0
const contentTree = useProjectContentTree()
const contentVolumes = contentTree.volumes
const contentSelectedChapterNumber = contentTree.selectedChapterNumber
const contentSelectedVersionId = contentTree.selectedVersionId
const contentSelectedChapter = contentTree.selectedChapter
const contentSelectedVersion = contentTree.selectedVersion
const contentTreeLoading = contentTree.loading
const contentTreeLoadingChapter = contentTree.loadingChapter
const contentTreeError = contentTree.error
const recordOf = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
const projects = computed(() => store.projects)
const isAdmin = computed(() => Boolean(authStore?.user?.is_admin))
const providerHealth = ref<AgentToolHealth | null>(null)
const providerHealthLoading = ref(false)
const providerHealthError = ref('')
const selectedProject = computed(() => projects.value.find((p) => p.id === selectedProjectId.value))
const activeContextRefs = computed(() =>
  buildAgentContextRefs({
    projectId: selectedProjectId.value,
    chapterNumber: contentSelectedChapterNumber.value,
    versionId: contentSelectedVersionId.value,
    entityRefs: manualEntityContextRefs.value,
    qualityFindingRefs: manualQualityFindingContextRefs.value,
  }),
)
const toolResults = computed<AgentToolResult[]>(() => {
  const runId = activeRun.value?.id
  if (!runId) return []
  const completedSteps = runSteps.value.filter((step) => step.run_id === runId && step.status === 'completed')
  if (responseToolResults.value.length) {
    return responseToolResults.value.map((item, index) => {
      const step = completedSteps[index] || completedSteps.find((candidate) => candidate.tool_name === item.tool_name)
      const fact = step ? activeExecutionFacts.value.find((candidate) => candidate.step_id === step.id) : undefined
      const executionId = step && typeof step.output_json.execution_id === 'string' ? step.output_json.execution_id : fact?.execution_id || ''
      return {
        ...item,
        result_ref: item.result_ref || (step ? (executionId ? `execution:${executionId}` : `step:${step.id}`) : undefined),
      }
    })
  }
  return completedSteps
    .map((step) => {
      const fact = activeExecutionFacts.value.find((candidate) => candidate.step_id === step.id)
      const executionId = typeof step.output_json.execution_id === 'string' ? step.output_json.execution_id : fact?.execution_id || ''
      return {
        tool_name: step.tool_name,
        result: recordOf(step.output_json),
        result_ref: executionId ? `execution:${executionId}` : `step:${step.id}`,
      }
    })
    .filter((item) => Boolean(item.tool_name) && Object.keys(item.result).length > 0)
})
watch(
  () => [selectedActionRef.value, selectedResultRef.value, runSteps.value.length, toolResults.value.length].join('|'),
  () => { void revealSelectedLocation() },
  { flush: 'post' },
)
const runtimeSupported = computed(
  () =>
    typeof AgentAPI.createSession === 'function' &&
    typeof AgentAPI.getSession === 'function' &&
    typeof AgentAPI.sendMessage === 'function' &&
    typeof AgentAPI.sessionStreamUrl === 'function',
)
const riskLabel = (risk: AgentRiskLevel) =>
  ({ read: '读取', suggest: '建议', write: '写入', destructive: '高风险' })[risk]
const toolSource = (tool: AgentToolDescriptor) => {
  if (tool.source === 'legacy' || !tool.provider_id) return '兼容内置能力'
  const origin = tool.source === 'configured' ? '部署 Provider' : '内置 Provider'
  return `${origin} · ${tool.provider_id}${tool.provider_version ? ` v${tool.provider_version}` : ''}`
}
const add = (
  label: string,
  detail: string,
  key?: string,
  _sequence?: number,
  eventType = 'local',
) => {
  const runId = activeRun.value?.id
  if (runId) {
    runProjection.appendLocalActivity(runId, label, detail, key, eventType)
    return
  }
  const id = key || `workspace:${Date.now()}:${workspaceEvents.value.length}`
  if (key && workspaceEventKeys.has(key)) return
  if (key) workspaceEventKeys.add(key)
  workspaceEvents.value = [
    ...workspaceEvents.value,
    { id, label, detail, sequence: 0, eventType },
  ].slice(-240)
}
const resetRuntime = () => {
  closeRunLifecycle()
  clearRunLocation()
  runProjection.reset()
  executionFactsByRunId.value = {}
  executionFactsErrorByRunId.value = {}
  localPlan.value = null
  resetArtifactFacts()
  workspaceEventKeys.clear()
  workspaceEvents.value = [
    {
      id: 'ready',
      label: '已就绪',
      detail: '请选择项目并发送目标，Agent 的历史消息会显示在这里。',
      sequence: 0,
      eventType: 'workspace',
    },
  ]
  artifactPreview.value = ''
}
const appendMessages = (items: AgentMessage[]) => {
  const byId = new Map(messages.value.map((item) => [item.id, item]))
  items.forEach((item) => byId.set(item.id, item))
  messages.value = [...byId.values()].sort((a, b) => a.sequence - b.sequence)
}
const governanceData = useAgentProjectGovernanceData({
  selectedProjectId,
  isAdmin,
  timeline,
  timelineLoading,
  timelineEventType,
  timelineRunStatus,
  auditLedger,
  auditLoading,
  jobs,
  jobsLoading,
  deadLetters,
  deadLettersLoading,
  addActivity: add,
})
const {
  clear: clearGovernanceData,
  loadTimeline,
  loadAudit,
  loadJobs,
  loadDeadLetters,
  reload: reloadGovernanceData,
  replayDeadLetterAction,
} = governanceData
const workspaceRuntime = useAgentWorkspaceRuntime({
  runProjection,
  activeRun,
  plan,
  artifacts,
  approvals,
  selectedProjectId,
  session,
  selectedRunId,
  streaming,
  stream: agentRunStream,
  tools,
  addActivity: add,
  onTerminalRefresh: () => { void refreshSessionMessages() },
})
const {
  qualityBlockers,
  qualityBlockersArtifactId,
  qualityBlockersError,
  qualityBlockersLoadingByArtifact,
  qualityBlockersLoading,
  rewriteInstructions,
  rewriteErrors,
  rewriteLoading,
  artifactDiff,
  artifactDiffLoading,
  artifactDiffArtifactId,
  artifactDiffError,
  artifactPreview,
  artifactPreviewLoading,
  artifactPreviewArtifactId,
  artifactPreviewError,
  artifactQualityFacts,
  artifactQualityFactsLoading,
  artifactQualityFactsErrors,
  artifactLineageFacts,
  artifactLineageFactsLoading,
  artifactLineageFactsErrors,
  providerProvenanceByRunId,
  gapRepairStateByRunId,
  loadRunSteps,
  loadRunPlan,
  loadRunState,
  loadRunFacts,
  applyEvent,
  repairSequenceGap,
  loadArtifactFacts,
  loadArtifactsWithFacts,
  loadQualityBlockers,
  loadRewriteInstructions,
  compareArtifact,
  compareArtifactWithVersion,
  previewArtifact,
  loadEventsAndStream,
  closeRunLifecycle,
  executeApprovalAction,
  acceptArtifactAction,
  resetArtifactFacts,
} = workspaceRuntime
const providerProvenance = computed(() =>
  activeRun.value ? providerProvenanceByRunId.value[activeRun.value.id] || null : null,
)
const gapRepairState = computed(() =>
  activeRun.value ? gapRepairStateByRunId.value[activeRun.value.id] || 'idle' : 'idle',
)
const runStatus = (status: string) =>
  ({
    queued: '排队中',
    planning: '正在规划',
    running: '正在执行',
    awaiting_approval: '等待审批',
    paused: '已暂停',
    cancelling: '正在取消',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  })[status] || status
const stepStatus = (status: string) =>
  ({
    pending: '等待执行',
    running: '正在执行',
    completed: '已完成',
    failed: '执行失败',
    cancelled: '已取消',
    awaiting_approval: '等待审批',
  })[status] || status
const stepErrorLabel = (error: string) =>
  error === 'LeaseExpiredRecovery' ? '执行器失联，已释放为可恢复步骤' : error
const approvalStatus = (status: string) =>
  ({
    pending: '等待确认',
    approved: '已批准（待执行器）',
    executing: '正在生成候选',
    executed: '候选已生成',
    execution_failed: '候选生成失败',
    rejected: '已拒绝',
  })[status] || status
const decideApproval = async (approval: AgentApproval, approved: boolean) => {
  try {
    const updated = await AgentAPI.decideApproval(approval.id, approved)
    runProjection.setRunApprovals(
      approval.run_id,
      approvals.value.map((item) => (item.id === updated.id ? updated : item)),
    )
    add(
      approved ? '审批已批准' : '审批已拒绝',
      `${approval.tool_name}：${approvalStatus(updated.status)}`,
    )
  } catch (error) {
    add('审批失败', error instanceof Error ? error.message : '审批请求失败')
  }
}
const loadExecutionFacts = async (runId: string) => {
  if (typeof AgentAPI.listExecutionFacts !== 'function') return
  try {
    const facts = await AgentAPI.listExecutionFacts(runId)
    executionFactsByRunId.value = { ...executionFactsByRunId.value, [runId]: facts }
    const nextErrors = { ...executionFactsErrorByRunId.value }
    delete nextErrors[runId]
    executionFactsErrorByRunId.value = nextErrors
  } catch (error) {
    executionFactsErrorByRunId.value = {
      ...executionFactsErrorByRunId.value,
      [runId]: error instanceof Error ? error.message : '执行事实接口暂时不可用',
    }
  }
}
const loadProviderUsageSummary = async (runId: string) => {
  if (typeof AgentAPI.getProviderUsageSummary !== 'function') return
  providerUsageSummaryLoadingByRunId.value = {
    ...providerUsageSummaryLoadingByRunId.value,
    [runId]: true,
  }
  try {
    const summary = await AgentAPI.getProviderUsageSummary(runId)
    providerUsageSummaryByRunId.value = { ...providerUsageSummaryByRunId.value, [runId]: summary }
    const nextErrors = { ...providerUsageSummaryErrorByRunId.value }
    delete nextErrors[runId]
    providerUsageSummaryErrorByRunId.value = nextErrors
  } catch (error) {
    providerUsageSummaryErrorByRunId.value = {
      ...providerUsageSummaryErrorByRunId.value,
      [runId]: error instanceof Error ? error.message : 'Provider 调用统计暂时不可用',
    }
  } finally {
    providerUsageSummaryLoadingByRunId.value = {
      ...providerUsageSummaryLoadingByRunId.value,
      [runId]: false,
    }
  }
}
const refreshSessionMessages = async () => {
  if (!session.value || typeof AgentAPI.getSession !== 'function') return
  try {
    const detail = await AgentAPI.getSession(session.value.id)
    appendMessages(detail.messages || [])
    runProjection.replaceRuns(detail.runs || [])
    const selected = activeRun.value
    if (selected && typeof AgentAPI.listApprovals === 'function')
      runProjection.setRunApprovals(selected.id, await AgentAPI.listApprovals(selected.id))
    if (selected) await Promise.all([loadRunSteps(selected.id), loadRunState(selected.id), loadExecutionFacts(selected.id), loadProviderUsageSummary(selected.id)])
  } catch {
    /* terminal refresh is best effort */
  }
}
const clearRunLocation = () => {
  selectedActionRef.value = null
  selectedResultRef.value = null
}
const revealSelectedLocation = async () => {
  await nextTick()
  const section = inspectorSectionEl.value
  if (!section || !activeRun.value) return
  section.open = true
  await nextTick()
  const reference = selectedResultRef.value || selectedActionRef.value
  if (!reference) return
  const candidates = Array.from(section.querySelectorAll<HTMLElement>('[data-location-ref], [data-result-ref]'))
  const target = candidates.find((element) => element.dataset.locationRef === reference || element.dataset.resultRef === reference)
  target?.scrollIntoView?.({ block: 'nearest' })
}
const selectLogLocation = (kind: 'action' | 'result', reference: string | null | undefined) => {
  const normalized = typeof reference === 'string' ? reference.trim() : ''
  if (!activeRun.value || !normalized) return
  if (kind === 'action') {
    selectedActionRef.value = normalized
    selectedResultRef.value = null
  } else {
    selectedResultRef.value = normalized
    selectedActionRef.value = null
  }
  void revealSelectedLocation()
}

const selectRunAction = async (runId: string) => {
  clearRunLocation()
  if (!session.value || !runProjection.selectRun(runId)) return
  const run = activeRun.value
  if (!run) return
  artifactPreview.value = ''
  resetArtifactFacts({ preserveScopedState: true })
  const loads: Promise<unknown>[] = [loadRunSteps(run.id), loadRunState(run.id), loadRunFacts(run.id), loadExecutionFacts(run.id), loadProviderUsageSummary(run.id)]
  if (typeof AgentAPI.listApprovals === 'function') {
    loads.push(AgentAPI.listApprovals(run.id).then((items) => runProjection.setRunApprovals(run.id, items)))
  }
  if (typeof AgentAPI.listArtifacts === 'function') loads.push(loadArtifactsWithFacts(run.id))
  await Promise.all(loads)
  syncAgentRoute({
    projectId: selectedProjectId.value,
    sessionId: session.value.id,
    runId: run.id,
    artifactId: undefined,
  })
  await loadEventsAndStream(session.value, run)
}
const onRunSelectChange = (event: Event) => {
  const value = (event.target as HTMLSelectElement | null)?.value || ''
  void selectRunAction(value)
}
const reconnectActiveRun = () => {
  if (!session.value || !activeRun.value) return
  void loadEventsAndStream(session.value, activeRun.value)
}
const {
  loadingByRunId: runControlLoading,
  anyPending: runCommandPending,
  recoverRunAction,
  runControlAction,
} = useAgentRunCommands({
  activeRun,
  runState,
  session,
  selectedRunId,
  streaming,
  runProjection,
  stream: agentRunStream,
  loadRunState,
  loadEventsAndStream,
  addActivity: add,
  runStatus,
})
const busy = computed(() =>
  sessionLoading.value ||
  sending.value ||
  streaming.value ||
  runCommandPending.value,
)
const cancelJobAction = async (job: AgentJob) => {
  if (typeof AgentAPI.cancelJob !== 'function') return
  try {
    const updated = await AgentAPI.cancelJob(job.id)
    jobs.value = jobs.value.map((item) => (item.id === updated.id ? updated : item))
    add('Job 已请求取消', `${job.kind} · ${job.id.slice(0, 8)}`)
  } catch (error) {
    add('Job 取消失败', error instanceof Error ? error.message : '无法取消 Job')
  }
}
const loadTools = async () => {
  loadingTools.value = true
  try {
    const result = await AgentAPI.listTools()
    tools.value = result.tools
    const generation = Number(result.generation)
    catalogGeneration.value = Number.isInteger(generation) && generation >= 1 ? generation : null
    add(
      '工具注册表已载入',
      `发现 ${result.count} 个项目内工具${catalogGeneration.value ? ` · 能力目录第 ${catalogGeneration.value} 代` : ''}。`,
    )
  } catch (error) {
    toolsError.value = error instanceof Error ? error.message : '工具注册表不可用'
    add('工具注册表不可用', toolsError.value)
  } finally {
    loadingTools.value = false
  }
}
const loadProviderHealth = async () => {
  if (!isAdmin.value || typeof AgentAPI.listToolHealth !== 'function') return
  providerHealthLoading.value = true
  providerHealthError.value = ''
  try {
    providerHealth.value = await AgentAPI.listToolHealth()
  } catch (error) {
    providerHealthError.value = error instanceof Error ? error.message : 'Provider 健康状态不可用'
  } finally {
    providerHealthLoading.value = false
  }
}
const planProvenance = (value: AgentPlanResponse) =>
  value.provider_called
    ? 'Provider 已参与受控工具规划。'
    : value.planner_fallback_reason
      ? `Provider 规划降级：${value.planner_fallback_reason}。`
      : '未调用 Provider（受控本地计划）。'
const requestPlan = async (text: string) => {
  planning.value = true
  localPlan.value = null
  add('正在理解目标', text)
  try {
    localPlan.value = await AgentAPI.createPlan({
      goal: text,
      project_id: selectedProjectId.value || undefined,
    })
    add('执行计划已生成', `${localPlan.value.steps.length} 个步骤，${planProvenance(localPlan.value)}`)
  } catch (error) {
    add('计划生成失败', error instanceof Error ? error.message : '请求失败')
  } finally {
    planning.value = false
  }
}
const submitMessage = async () => {
  const text = goal.value.trim()
  if (!text || sessionLoading.value) return
  goal.value = ''
  if (!runtimeSupported.value || !session.value) {
    await requestPlan(text)
    return
  }
  sending.value = true
  add('正在发送消息', text)
  try {
    const messageContextRefs = activeContextRefs.value.map((ref) => ({ ...ref }))
    const result = await AgentAPI.sendMessage(session.value.id, {
      content: text,
      context_refs: messageContextRefs,
    })
    appendMessages([
      result.message,
      ...(result.assistant_message ? [result.assistant_message] : []),
    ])
    runProjection.upsertRun(result.run, { select: true })
    runProjection.setRunPlan(result.run.id, result.plan)
    runProjection.setRunApprovals(result.run.id, result.approvals || [])
    runProjection.setRunToolResults(
      result.run.id,
      Array.isArray(result.tool_results) ? result.tool_results : [],
    )
    if (typeof AgentAPI.listArtifacts === 'function') {
      await loadArtifactsWithFacts(result.run.id)
    }
    if (result.plan.steps.length) {
      add(
        'Agent 已返回计划',
        `${result.plan.steps.length} 个步骤，${planProvenance({ ...result.plan, provider_called: result.provider_called ?? result.plan.provider_called, planner_fallback_reason: result.planner_fallback_reason ?? result.plan.planner_fallback_reason })}`,
      )
    } else {
      add('Agent 已排队', 'Run 已创建；正在由执行器实时生成计划。')
    }
    await loadEventsAndStream(session.value, result.run)
    syncAgentRoute({
      projectId: selectedProjectId.value,
      sessionId: session.value.id,
      runId: result.run.id,
      artifactId: undefined,
    })
    await loadTimeline()
  } catch (error) {
    add('消息发送失败', error instanceof Error ? error.message : '请求失败')
    goal.value = text
  } finally {
    sending.value = false
  }
}
const switchProject = () => {
  manualEntityContextRefs.value = []
  manualQualityFindingContextRefs.value = []
  clearGovernanceData()
  contentTree.clearChapterSelection()
  syncAgentRoute({
    projectId: selectedProjectId.value,
    sessionId: undefined,
    runId: undefined,
    artifactId: undefined,
    chapter: undefined,
    versionId: undefined,
    focus: undefined,
  })
  void loadContentTree({})
  void restoreSession()
  void reloadGovernanceData()
}
watch(selectedSessionId, (value, oldValue) => {
  // restoreSession sets the session selector before its durable detail is loaded.
  // Do not start a second load during that window: the competing request can
  // otherwise replace a deep-linked historical Run with the newest Run.
  if (value && value !== oldValue && value !== session.value?.id && !sessionLoading.value)
    void loadSelectedSession()
})
const agentRouteState = computed(() =>
  parseAgentRouteState(route.query as unknown as Parameters<typeof parseAgentRouteState>[0]),
)
const syncAgentRoute = (overrides: Partial<ReturnType<typeof parseAgentRouteState>> = {}) => {
  const state = { ...agentRouteState.value, ...overrides }
  const query: Record<string, string> = {}
  if (state.projectId) query.project_id = state.projectId
  if (state.sessionId) query.session_id = state.sessionId
  if (state.runId) query.run_id = state.runId
  if (state.artifactId) query.artifact_id = state.artifactId
  if (state.chapter) query.chapter = String(state.chapter)
  if (state.versionId) query.version_id = String(state.versionId)
  if (state.focus) query.focus = state.focus
  void router.replace({ path: '/agent', query }).catch(() => undefined)
}
const hydrateSessionRun = async (
  detail: AgentSessionDetail,
  requestedRunId?: string,
  requestedArtifactId?: string,
): Promise<{ runId?: string; artifactId?: string }> => {
  const requestedRun = requestedRunId
    ? runs.value.find((item) => item.id === requestedRunId)
    : undefined
  const selected = requestedRun || activeRun.value
  if (requestedRunId && !requestedRun) {
    add('运行深链不可用', '请求的运行不属于当前会话，已安全降级为最近运行。')
  }
  if (!selected) return {}
  if (typeof AgentAPI.listApprovals === 'function') {
    runProjection.setRunApprovals(selected.id, await AgentAPI.listApprovals(selected.id))
  }
  let artifactId: string | undefined
  if (typeof AgentAPI.listArtifacts === 'function') {
    const selectedArtifacts = await loadArtifactsWithFacts(selected.id)
    const requestedArtifact = requestedArtifactId
      ? selectedArtifacts.find((item) => item.id === requestedArtifactId)
      : undefined
    if (requestedArtifactId && !requestedArtifact) {
      add('候选深链不可用', '请求的 Artifact 不属于当前运行，未载入候选内容。')
    } else if (requestedArtifact) {
      artifactId = requestedArtifact.id
      await previewArtifact(requestedArtifact)
    }
  }
  await Promise.all([loadRunFacts(selected.id), loadExecutionFacts(selected.id), loadProviderUsageSummary(selected.id)])
  await loadEventsAndStream(detail, selected)
  return { runId: selected.id, artifactId }
}
const sessionLifecycle = useAgentSessionLifecycle({
  selectedProjectId,
  selectedProjectTitle: computed(() => selectedProject.value?.title),
  runtimeSupported,
  routeIntent: computed(() => agentRouteState.value),
  runProjection,
  sessionLoading,
  sessionError,
  session,
  sessions,
  selectedSessionId,
  messages,
  resetRuntime,
  appendMessages,
  hydrateSelectedRun: hydrateSessionRun,
  syncRoute: syncAgentRoute,
  addActivity: add,
})
const {
  restoreSession,
  loadSelectedSession,
  createNewSession,
  archiveCurrentSession,
  invalidate: invalidateSessionLifecycle,
} = sessionLifecycle
const loadContentTree = async (selection?: { chapterNumber?: number; versionId?: number }) => {
  await contentTree.loadProject(
    selectedProjectId.value,
    selection || {
      chapterNumber: agentRouteState.value.chapter,
      versionId: agentRouteState.value.versionId,
    },
  )
}
const selectContentChapter = async (chapterNumber: number) => {
  contentTree.clearVersionSelection()
  const detail = contentTree.selectChapter(chapterNumber)
  syncAgentRoute({
    projectId: selectedProjectId.value,
    chapter: chapterNumber,
    versionId: undefined,
    focus: 'version',
  })
  await detail
  syncAgentRoute({
    projectId: selectedProjectId.value,
    chapter: contentSelectedChapterNumber.value,
    versionId: contentSelectedVersionId.value,
    focus: 'version',
  })
}
const selectContentVersion = (versionId: number) => {
  contentTree.selectVersion(versionId)
  syncAgentRoute({
    projectId: selectedProjectId.value,
    chapter: contentSelectedChapterNumber.value,
    versionId: contentSelectedVersionId.value,
    focus: 'version',
  })
}
const toggleEntityContextRef = (entity: AgentManualEntityRef) => {
  const entityId = Number(entity.entityId)
  if (!Number.isInteger(entityId) || entityId < 1) return
  const index = manualEntityContextRefs.value.findIndex(
    (item) => item.kind === entity.kind && item.entityId === entityId,
  )
  if (index >= 0) {
    manualEntityContextRefs.value.splice(index, 1)
    return
  }
  if (manualEntityContextRefs.value.length >= 16) return
  manualEntityContextRefs.value.push({ kind: entity.kind, entityId })
}
const toggleQualityFindingContextRef = (finding: { finding_id: string }) => {
  const findingId = finding.finding_id.trim()
  if (!findingId) return
  const index = manualQualityFindingContextRefs.value.findIndex((item) => item.findingId === findingId)
  if (index >= 0) {
    manualQualityFindingContextRefs.value.splice(index, 1)
    return
  }
  if (manualEntityContextRefs.value.length + manualQualityFindingContextRefs.value.length >= 16) return
  manualQualityFindingContextRefs.value.push({ findingId })
}
const removeContextRef = (ref: AgentContextRef) => {
  if (ref.kind === 'quality_finding') {
    manualQualityFindingContextRefs.value = manualQualityFindingContextRefs.value.filter(
      (item) => item.findingId !== ref.finding_id,
    )
    return
  }
  if ('entity_id' in ref) {
    manualEntityContextRefs.value = manualEntityContextRefs.value.filter(
      (item) => !(item.kind === ref.kind && item.entityId === ref.entity_id),
    )
    return
  }
  if (ref.kind === 'chapter_version') {
    contentTree.clearVersionSelection()
    syncAgentRoute({
      projectId: selectedProjectId.value,
      chapter: contentSelectedChapterNumber.value,
      versionId: undefined,
      focus: 'version',
    })
    return
  }
  if (ref.kind === 'chapter') {
    contentTree.clearChapterSelection()
    syncAgentRoute({
      projectId: selectedProjectId.value,
      chapter: undefined,
      versionId: undefined,
      focus: undefined,
    })
  }
}
const openContentInWritingDesk = () => {
  if (!selectedProject.value || !contentSelectedChapterNumber.value) return
  void router.push({
    path: `/novel/${selectedProject.value.id}`,
    query: writingDeskQueryFromAgent({
      chapter: contentSelectedChapterNumber.value,
      versionId: contentSelectedVersionId.value,
      focus: 'version',
    }),
  })
}
const openWritingDesk = (
  artifact?: AgentArtifact,
  focus: 'artifact' | 'quality-blocker' | 'version' = 'artifact',
) => {
  if (!selectedProject.value) return
  if (!artifact) {
    void router.push(`/novel/${selectedProject.value.id}`)
    return
  }
  const metadata = artifact.metadata_json || {}
  const chapter = Number(metadata.chapter_number)
  const versionId = Number(metadata.accepted_version_id || metadata.source_version_id)
  void router.push({
    path: `/novel/${selectedProject.value.id}`,
    query: writingDeskQueryFromAgent({
      artifactId: artifact.id,
      chapter: Number.isInteger(chapter) && chapter >= 1 ? chapter : undefined,
      versionId: Number.isInteger(versionId) && versionId >= 1 ? versionId : undefined,
      focus: focus === 'artifact' ? 'version' : focus,
    }),
  })
}
onMounted(async () => {
  await store.loadProjects()
  const requestedProjectId = agentRouteState.value.projectId
  selectedProjectId.value = store.projects.some((project) => project.id === requestedProjectId)
    ? requestedProjectId || ''
    : store.projects[0]?.id || ''
  await loadTools()
  await loadProviderHealth()
  await loadContentTree()
  await restoreSession()
  await reloadGovernanceData()
})
onBeforeUnmount(() => {
  invalidateSessionLifecycle()
  contentTree.reset()
  closeRunLifecycle()
})
</script>
<style scoped>
.agent-page {
  display: grid;
  gap: 1rem;
  padding: 1rem;
}
.agent-hero {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.4rem;
  border-radius: var(--xq-radius-lg);
}
.agent-kicker {
  margin: 0 0 0.4rem;
  color: var(--xq-gold-deep);
  font-size: 0.76rem;
  font-weight: 900;
  letter-spacing: 0.16em;
}
.agent-hero h1 {
  margin: 0;
  font-family: var(--xq-font-serif);
  font-size: clamp(1.7rem, 3vw, 2.5rem);
}
.agent-hero p {
  max-width: 52rem;
  color: var(--xq-ink-muted);
  line-height: 1.7;
}
.agent-status {
  display: grid;
  align-content: center;
  min-width: 15rem;
  gap: 0.4rem;
  padding: 1rem;
  border: 1px solid var(--xq-border);
  border-radius: var(--xq-radius-md);
  background: rgba(255, 255, 255, 0.7);
}
.agent-status small,
.muted {
  color: var(--xq-ink-muted);
  line-height: 1.6;
}
.status-dot {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  background: var(--xq-jade);
}
.status-dot.busy {
  background: #d97706;
}
.agent-sidebar label {
  display: block;
  margin-bottom: 0.4rem;
  font-weight: 800;
}
.agent-sidebar select,
.composer textarea {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid var(--xq-border);
  border-radius: 0.7rem;
  padding: 0.7rem;
  background: rgba(255, 255, 255, 0.85);
  font: inherit;
}
.agent-sidebar select {
  min-height: 2.5rem;
}
.session-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.55rem;
}
.timeline-filters {
  display: grid;
  gap: 0.4rem;
  margin-bottom: 0.6rem;
}
.timeline-filters select {
  width: 100%;
  border: 1px solid var(--xq-border);
  border-radius: 0.5rem;
  padding: 0.45rem;
  background: rgba(255, 255, 255, 0.85);
  font: inherit;
}
.timeline-list {
  display: grid;
  gap: 0.65rem;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 24rem;
  overflow: auto;
}
.timeline-list li {
  display: grid;
  gap: 0.2rem;
  padding-bottom: 0.55rem;
  border-bottom: 1px dashed var(--xq-border);
}
.timeline-list span,
.timeline-list small {
  color: var(--xq-ink-muted);
  line-height: 1.45;
}
.tool-list,
.step-list {
  display: grid;
  gap: 0.65rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tool-list li,
.step-list li {
  display: grid;
  gap: 0.25rem;
  padding-bottom: 0.6rem;
  border-bottom: 1px dashed var(--xq-border);
}
.tool-list span {
  width: max-content;
  padding: 0.12rem 0.45rem;
  border-radius: 999px;
  background: rgba(37, 99, 235, 0.1);
  color: #2563eb;
  font-size: 0.72rem;
  font-weight: 800;
}
.tool-list small,
.step-list small,
.step-list span {
  color: var(--xq-ink-muted);
  line-height: 1.5;
}
.session-bar {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  color: rgba(255, 255, 255, 0.86);
  font-size: 0.82rem;
}
.session-bar small {
  color: rgba(255, 255, 255, 0.68);
}
.messages {
  display: grid;
  gap: 0.7rem;
  max-height: 26rem;
  overflow: auto;
  margin-bottom: 1rem;
}
.message {
  max-width: 88%;
  padding: 0.7rem 0.85rem;
  border-radius: 0.8rem;
  background: rgba(255, 255, 255, 0.1);
}
.message-streaming {
  border-left: 3px solid var(--xq-jade);
  opacity: 0.92;
}
.blocker-list {
  display: grid;
  gap: 0.4rem;
  margin: 0.6rem 0 0;
  padding: 0;
  list-style: none;
}
.blocker-list li {
  display: grid;
  gap: 0.2rem;
  padding: 0.45rem;
  border-left: 3px solid var(--xq-cinnabar);
  background: rgba(239, 68, 68, 0.06);
}
.blocker-list span,
.blocker-list small {
  color: var(--xq-ink-muted);
  line-height: 1.45;
}
.artifact-diff-list {
  display: grid;
  gap: 0.25rem;
  max-height: 20rem;
  overflow: auto;
  margin: 0.6rem 0 0;
  padding: 0;
  list-style: none;
  font-family: monospace;
}
.artifact-diff-list li {
  display: grid;
  grid-template-columns: 2.5rem 1fr;
  gap: 0.5rem;
  padding: 0.2rem 0.35rem;
  border-radius: 0.25rem;
}
.diff-added {
  background: rgba(16, 185, 129, 0.15);
}
.diff-modified {
  background: rgba(245, 158, 11, 0.18);
}
.diff-deleted {
  text-decoration: line-through;
  background: rgba(239, 68, 68, 0.12);
}
.artifact-preview {
  max-height: 28rem;
  overflow: auto;
  white-space: pre-wrap;
  line-height: 1.65;
  margin: 0 0 0.65rem;
  font: inherit;
}
.message p {
  margin: 0.25rem 0 0;
  white-space: pre-wrap;
  line-height: 1.6;
}
.message-user {
  justify-self: end;
  background: rgba(8, 145, 178, 0.35);
}
.message-assistant {
  justify-self: start;
  background: rgba(255, 255, 255, 0.12);
}
.empty-chat {
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.6;
}
.events {
  display: grid;
  gap: 0.65rem;
  max-height: 28rem;
  overflow: auto;
}
.events article {
  border-left: 3px solid #0891b2;
  padding: 0.15rem 0.75rem;
}
.events p {
  margin: 0.25rem 0;
  line-height: 1.55;
}
.composer {
  display: grid;
  gap: 0.65rem;
  margin-top: 1rem;
}
.composer textarea {
  resize: vertical;
  line-height: 1.6;
}
.composer > div {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  align-items: center;
}
.composer small {
  color: rgba(255, 255, 255, 0.7);
}
.plan-list {
  display: grid;
  gap: 0.7rem;
  margin: 0;
  padding: 0;
  list-style: none;
}
.plan-list li {
  display: grid;
  gap: 0.2rem;
}
.plan-list span {
  color: var(--xq-ink-muted);
}
.plan-list em {
  color: #b45309;
  font-style: normal;
  font-size: 0.78rem;
}
.approval-card {
  display: grid;
  gap: 0.35rem;
  padding: 0.65rem;
  border: 1px solid var(--xq-border);
  border-radius: 0.6rem;
  margin-bottom: 0.55rem;
}
.approval-card span {
  font-size: 0.78rem;
  color: var(--xq-gold-deep);
}
.approval-approved {
  color: var(--xq-jade) !important;
}
.approval-rejected {
  color: var(--xq-cinnabar) !important;
}
.approval-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.35rem;
}
.run-summary {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.45rem 0.75rem;
  margin: 0;
}
.run-summary dt {
  color: var(--xq-ink-muted);
}
.run-summary dd {
  margin: 0;
  font-weight: 700;
}
.error {
  color: var(--xq-cinnabar);
}
.agent-activity ul {
  margin: 0;
  padding-left: 1.2rem;
  line-height: 1.9;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
}
@media (max-width: 650px) {
  .agent-hero {
    flex-direction: column;
  }
  .composer > div {
    align-items: flex-start;
    flex-direction: column;
  }
}
.rewrite-instruction-list {
  display: grid;
  gap: 0.45rem;
  margin: 0.5rem 0;
  padding: 0.55rem;
  border: 1px solid rgba(245, 158, 11, 0.35);
  border-radius: 0.55rem;
  background: rgba(245, 158, 11, 0.06);
}
.rewrite-instruction {
  display: grid;
  gap: 0.2rem;
  padding: 0.35rem 0;
  border-bottom: 1px dashed var(--xq-border);
}
.rewrite-instruction:last-child {
  border-bottom: 0;
}
.rewrite-instruction span,
.rewrite-instruction small {
  color: var(--xq-ink-muted);
  line-height: 1.45;
}


/* 工作台布局：导航和诊断信息收纳在独立滚动区，聊天保持唯一主阅读面。 */
.workspace-sidebar-stack,
.workspace-activity-stack,
.workspace-chat-column {
  display: grid;
  min-width: 0;
  gap: 0.65rem;
}
.workspace-chat-column {
  min-height: min(78vh, 60rem);
}
.workspace-section {
  min-width: 0;
  border: 1px solid color-mix(in srgb, var(--xq-border) 82%, transparent);
  border-radius: var(--xq-radius-md);
  background: rgba(255, 255, 255, 0.46);
}
.workspace-section > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  min-height: 1.9rem;
  box-sizing: border-box;
  padding: 0.4rem 0.5rem;
  cursor: pointer;
  list-style: none;
  color: var(--xq-ink);
  font-size: 0.82rem;
  font-weight: 850;
}
.workspace-section > summary::-webkit-details-marker { display: none; }
.workspace-section > summary::before {
  content: '▸';
  flex: 0 0 auto;
  color: var(--xq-gold-deep);
  font-size: 0.78rem;
  transition: transform 160ms ease;
}
.workspace-section[open] > summary::before { transform: rotate(90deg); }
.workspace-section > summary span { flex: 1; min-width: 0; }
.workspace-section > summary small {
  max-width: 8rem;
  overflow: hidden;
  color: var(--xq-ink-muted);
  font-size: 0.7rem;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.workspace-section-body {
  display: grid;
  min-width: 0;
  gap: 0.4rem;
  padding: 0 0.25rem 0.3rem;
}
.workspace-sidebar-stack :deep(.xq-panel),
.workspace-activity-stack :deep(.xq-panel) {
  min-width: 0;
  border-radius: var(--xq-radius-md);
}
.workspace-sidebar-stack :deep(.xq-panel__header),
.workspace-activity-stack :deep(.xq-panel__header) {
  gap: 0.5rem;
  padding: 0.48rem 0.55rem 0;
}
.workspace-sidebar-stack :deep(.xq-panel__title),
.workspace-activity-stack :deep(.xq-panel__title) {
  font-size: 0.88rem;
}
.workspace-sidebar-stack :deep(.xq-panel__subtitle),
.workspace-activity-stack :deep(.xq-panel__subtitle) {
  margin-top: 0.25rem;
  font-size: 0.75rem;
  line-height: 1.4;
}
.workspace-sidebar-stack :deep(.xq-panel__body),
.workspace-activity-stack :deep(.xq-panel__body) {
  padding: 0.55rem;
}
.workspace-sidebar-stack :deep(.muted),
.workspace-activity-stack :deep(.muted) {
  margin: 0.45rem 0;
  font-size: 0.76rem;
  line-height: 1.45;
}
.workspace-sidebar-stack :deep(.tool-list),
.workspace-sidebar-stack :deep(.timeline-list) {
  max-height: 6rem;
  overflow: auto;
}
.workspace-activity-stack {
  align-content: start;
}
.workspace-inspector-section > .workspace-section-body,
.workspace-activity-section > .workspace-section-body {
  gap: 0.65rem;
}
.workspace-rule-grid {
  grid-template-columns: 1fr;
}
.workspace-log-panel {
  min-height: 0;
}
.workspace-log-list {
  min-height: 2.4rem;
  max-height: min(6rem, 11vh);
  overflow-y: auto;
  padding-right: 0.2rem;
  scrollbar-gutter: stable;
}
.workspace-log-list:empty::before {
  content: '暂无运行日志';
  color: var(--xq-ink-muted);
  font-size: 0.78rem;
}
.workspace-log-list article {
  min-width: 0;
}
.workspace-log-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 0.6rem;
  color: var(--xq-ink-muted);
  font-size: 0.7rem;
  line-height: 1.35;
}
.workspace-log-meta span {
  overflow-wrap: anywhere;
}
.workspace-log-ref {
  max-width: 100%;
  padding: 0;
  border: 0;
  color: inherit;
  background: transparent;
  font: inherit;
  text-align: left;
  text-decoration: underline dotted;
  text-underline-offset: 0.15em;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.workspace-log-ref:hover,
.workspace-log-ref:focus-visible {
  color: var(--xq-gold-deep);
}
.workspace-log-ref:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--xq-gold-deep) 60%, transparent);
  outline-offset: 2px;
}
.workspace-log-list p {
  overflow-wrap: anywhere;
}
.workspace-chat-column :deep(.xq-panel--ink) {
  min-height: min(78vh, 60rem);
}
.workspace-chat-column :deep(.messages) {
  min-height: min(30rem, 52vh);
  max-height: min(70vh, 58rem);
  scrollbar-gutter: stable;
}
.workspace-chat-column :deep(.composer textarea) {
  min-height: 6.5rem;
}
@media (max-width: 880px) {
  .workspace-activity-stack {
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    align-items: start;
  }
  .workspace-activity-stack > :first-child,
  .workspace-activity-stack > .workspace-log-panel,
  .workspace-activity-stack > .workspace-activity-section {
    min-width: 0;
  }
  .workspace-activity-stack > :first-child,
  .workspace-activity-stack > .workspace-log-panel {
    grid-column: span 1;
  }
  .workspace-activity-stack > :nth-child(2) {
    grid-column: span 1;
  }
  .workspace-activity-section {
    grid-column: 1 / -1;
  }
}
@media (max-width: 650px) {
  .workspace-activity-stack { grid-template-columns: 1fr; }
  .workspace-activity-stack > * { grid-column: auto !important; }
  .workspace-chat-column :deep(.messages) {
    min-height: 16rem;
    max-height: 55vh;
  }
}

</style>

