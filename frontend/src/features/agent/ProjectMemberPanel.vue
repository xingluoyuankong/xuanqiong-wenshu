<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import {
  ProjectMembersAPI,
  type CreateProjectMemberInput,
  type ProjectMember,
  type ProjectMemberRole,
} from '@/api/projectMembers'

const props = withDefaults(defineProps<{
  projectId: string | null | undefined
  canManage?: boolean | null
  autoLoad?: boolean
}>(), {
  canManage: null,
  autoLoad: true,
})

const emit = defineEmits<{
  loaded: [members: ProjectMember[]]
  changed: [members: ProjectMember[]]
}>()

const members = ref<ProjectMember[]>([])
const loading = ref(false)
const error = ref('')
const serverCanManage = ref(false)
const pendingUserIds = ref(new Set<number>())
const newMemberUserId = ref('')
const newMemberRole = ref<Exclude<ProjectMemberRole, 'owner'>>('viewer')

const memberRoles: Exclude<ProjectMemberRole, 'owner'>[] = ['editor', 'viewer']
const hasProject = computed(() => Boolean(props.projectId?.trim()))
const effectiveCanManage = computed(() => props.canManage ?? serverCanManage.value)
const isMutating = computed(() => pendingUserIds.value.size > 0)
const canSubmit = computed(() => {
  const userId = Number(newMemberUserId.value)
  return effectiveCanManage.value && hasProject.value && Number.isInteger(userId) && userId > 0 && !isMutating.value
})

const cloneMembers = () => members.value.map((member) => ({ ...member }))

const markPending = (userId: number, pending: boolean) => {
  const next = new Set(pendingUserIds.value)
  if (pending) next.add(userId)
  else next.delete(userId)
  pendingUserIds.value = next
}

const setMembers = (next: ProjectMember[], event: 'loaded' | 'changed') => {
  members.value = [...next].sort((left, right) => {
    if (left.role === 'owner' && right.role !== 'owner') return -1
    if (right.role === 'owner' && left.role !== 'owner') return 1
    return left.user_id - right.user_id
  })
  const snapshot = cloneMembers()
  if (event === 'loaded') emit('loaded', snapshot)
  else emit('changed', snapshot)
}

const load = async () => {
  if (!hasProject.value) {
    setMembers([], 'loaded')
    serverCanManage.value = false
    error.value = ''
    return
  }

  loading.value = true
  error.value = ''
  try {
    const response = await ProjectMembersAPI.list(props.projectId!.trim())
    serverCanManage.value = Boolean(response.can_manage)
    setMembers(response.members, 'loaded')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '项目成员加载失败'
  } finally {
    loading.value = false
  }
}

const addMember = async () => {
  if (!canSubmit.value || !props.projectId) return

  const userId = Number(newMemberUserId.value)
  const payload: CreateProjectMemberInput = { user_id: userId, role: newMemberRole.value }
  markPending(userId, true)
  error.value = ''
  try {
    const member = await ProjectMembersAPI.add(props.projectId.trim(), payload)
    const index = members.value.findIndex((item) => item.user_id === member.user_id)
    const next = [...members.value]
    if (index >= 0) next.splice(index, 1, member)
    else next.push(member)
    setMembers(next, 'changed')
    newMemberUserId.value = ''
    newMemberRole.value = 'viewer'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '添加项目成员失败'
  } finally {
    markPending(userId, false)
  }
}

const updateRole = async (member: ProjectMember, role: string) => {
  if (!effectiveCanManage.value || member.role === 'owner' || !props.projectId) return
  if (!memberRoles.includes(role as Exclude<ProjectMemberRole, 'owner'>) || role === member.role) return

  markPending(member.user_id, true)
  error.value = ''
  try {
    const updated = await ProjectMembersAPI.updateRole(props.projectId.trim(), member.user_id, {
      role: role as Exclude<ProjectMemberRole, 'owner'>,
    })
    setMembers(members.value.map((item) => item.user_id === updated.user_id ? updated : item), 'changed')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '更新成员角色失败'
  } finally {
    markPending(member.user_id, false)
  }
}

const removeMember = async (member: ProjectMember) => {
  if (!effectiveCanManage.value || member.role === 'owner' || !props.projectId) return

  markPending(member.user_id, true)
  error.value = ''
  try {
    await ProjectMembersAPI.remove(props.projectId.trim(), member.user_id)
    setMembers(members.value.filter((item) => item.user_id !== member.user_id), 'changed')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '移除项目成员失败'
  } finally {
    markPending(member.user_id, false)
  }
}

watch(() => props.projectId, () => {
  if (props.autoLoad) void load()
})

onMounted(() => {
  if (props.autoLoad) void load()
})

defineExpose({ load })
</script>

<template>
  <section class="project-member-panel" data-testid="project-member-panel" aria-label="项目成员管理">
    <header class="panel-header">
      <div>
        <h3>项目成员</h3>
        <p>Owner 可管理成员；Editor 与 Viewer 的实际权限由服务端统一校验。</p>
      </div>
      <button
        class="refresh-button"
        type="button"
        :disabled="loading || !hasProject"
        data-testid="project-members-refresh"
        @click="load"
      >刷新</button>
    </header>

    <p v-if="!hasProject" class="state-message" data-testid="project-members-no-project">请选择项目后加载成员。</p>
    <p v-else-if="loading" class="state-message" data-testid="project-members-loading" aria-live="polite">正在加载成员…</p>
    <p v-if="error" class="error-message" role="alert" data-testid="project-members-error">{{ error }}</p>

    <form v-if="hasProject" class="add-member-form" data-testid="project-members-add-form" @submit.prevent="addMember">
      <label>
        用户 ID
        <input
          v-model.trim="newMemberUserId"
          type="number"
          min="1"
          step="1"
          inputmode="numeric"
          :disabled="!effectiveCanManage || isMutating"
          data-testid="project-members-user-id"
        >
      </label>
      <label>
        角色
        <select v-model="newMemberRole" :disabled="!effectiveCanManage || isMutating" data-testid="project-members-new-role">
          <option v-for="role in memberRoles" :key="role" :value="role">{{ role }}</option>
        </select>
      </label>
      <button
        type="submit"
        :disabled="!canSubmit"
        data-testid="project-members-add"
      >添加成员</button>
    </form>

    <p v-if="hasProject && !effectiveCanManage" class="readonly-message" data-testid="project-members-readonly">
      当前角色仅可查看成员列表。
    </p>

    <ul v-if="hasProject && !loading" class="member-list" data-testid="project-members-list">
      <li v-for="member in members" :key="member.id" class="member-row" :data-member-user-id="member.user_id">
        <span class="member-user">用户 #{{ member.user_id }}</span>
        <label class="member-role-label">
          <span class="sr-only">用户 {{ member.user_id }} 的角色</span>
          <select
            :value="member.role"
            :disabled="!effectiveCanManage || member.role === 'owner' || pendingUserIds.has(member.user_id)"
            :data-testid="`project-members-role-${member.user_id}`"
            @change="updateRole(member, ($event.target as HTMLSelectElement).value)"
          >
            <option value="owner">owner</option>
            <option v-for="role in memberRoles" :key="role" :value="role">{{ role }}</option>
          </select>
        </label>
        <button
          type="button"
          class="remove-button"
          :disabled="!effectiveCanManage || member.role === 'owner' || pendingUserIds.has(member.user_id)"
          :data-testid="`project-members-remove-${member.user_id}`"
          @click="removeMember(member)"
        >移除</button>
      </li>
      <li v-if="!members.length" class="state-message" data-testid="project-members-empty">当前项目还没有成员记录。</li>
    </ul>
  </section>
</template>

<style scoped>
.project-member-panel { display: grid; gap: .85rem; padding: 1rem; border: 1px solid var(--xq-border); border-radius: .75rem; background: var(--xq-surface); }
.panel-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
h3, p { margin: 0; }
.panel-header p, .state-message, .readonly-message { color: var(--xq-text-muted); font-size: .875rem; }
.add-member-form { display: flex; flex-wrap: wrap; align-items: end; gap: .75rem; }
.add-member-form label { display: grid; gap: .25rem; font-size: .875rem; }
input, select, button { font: inherit; }
input, select { min-height: 2.25rem; padding: .25rem .5rem; border: 1px solid var(--xq-border); border-radius: .375rem; background: var(--xq-surface); color: var(--xq-text); }
button { min-height: 2.25rem; padding: .25rem .75rem; border: 1px solid var(--xq-border); border-radius: .375rem; background: var(--xq-accent); color: var(--xq-accent-contrast, #fff); cursor: pointer; }
button:disabled, select:disabled, input:disabled { cursor: not-allowed; opacity: .6; }
.refresh-button, .remove-button { background: transparent; color: var(--xq-text); }
.remove-button { color: var(--xq-danger, #b42318); }
.error-message { color: var(--xq-danger, #b42318); }
.member-list { display: grid; gap: .5rem; margin: 0; padding: 0; list-style: none; }
.member-row { display: flex; align-items: center; gap: .75rem; padding: .5rem; border-radius: .375rem; background: var(--xq-surface-muted, rgba(127,127,127,.08)); }
.member-user { min-width: 7rem; font-variant-numeric: tabular-nums; }
.member-role-label { flex: 1; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 640px) { .panel-header, .member-row { align-items: stretch; flex-direction: column; } .member-user { min-width: 0; } .add-member-form { align-items: stretch; flex-direction: column; } }
</style>
