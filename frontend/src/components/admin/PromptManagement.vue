<template>
  <n-card :bordered="false" class="admin-card prompt-admin-card">
    <template #header>
      <div class="card-header">
        <div>
          <span class="card-title">提示词管理</span>
          <p class="card-subtitle">左侧只保留提示词标题，点选后再查看用途说明、内部标识和正文内容。</p>
        </div>
        <n-space :size="12">
          <n-button quaternary size="small" :loading="loading" @click="fetchPrompts">刷新</n-button>
          <n-button type="primary" size="small" @click="openCreateModal">新建提示词</n-button>
        </n-space>
      </div>
    </template>

    <n-space vertical size="large">
      <n-alert v-if="error" type="error" closable @close="error = null">{{ error }}</n-alert>

      <n-spin :show="loading">
        <div :class="['prompt-layout', { mobile: isMobile }]">
          <PromptListSidebar
            :prompts="prompts"
            :selected-prompt-id="selectedPrompt?.id ?? null"
            :loading="loading"
            @select="selectPrompt"
          />

          <div class="prompt-editor">
            <div v-if="!selectedPrompt" class="empty-editor">
              <n-empty description="请先从左侧选择一个提示词" />
            </div>

            <div v-else class="editor-content">
              <div class="editor-header">
                <div>
                  <p class="editor-header__eyebrow">当前编辑</p>
                  <h3 class="editor-header__title">{{ translatedPromptTitle }}</h3>
                  <p class="editor-header__meta">内部标识：{{ editForm.name }}</p>
                </div>
                <p class="editor-header__description">{{ translatedPromptDescription }}</p>
              </div>

              <n-form label-placement="top" :model="editForm">
                <n-form-item label="提示词名称（中文）">
                  <n-input v-model:value="editForm.title" placeholder="例如：章节规划提示词" />
                </n-form-item>
                <n-form-item label="标签">
                  <n-dynamic-tags v-model:value="editForm.tags" size="small" placeholder="输入标签后回车" />
                </n-form-item>
                <n-form-item label="提示词内容">
                  <n-input
                    v-model:value="editForm.content"
                    type="textarea"
                    :autosize="{ minRows: isMobile ? 10 : 18, maxRows: 42 }"
                    placeholder="请输入完整提示词内容"
                    class="prompt-textarea"
                  />
                </n-form-item>
              </n-form>

              <n-space justify="space-between" align="center" class="editor-actions">
                <p class="editor-actions__hint">标题和说明用于管理后台识别，真正执行时仍会按内部标识调用对应提示词。</p>
                <n-space>
                  <n-popconfirm
                    v-if="selectedPrompt"
                    placement="bottom"
                    positive-text="删除"
                    negative-text="取消"
                    type="error"
                    @positive-click="deletePrompt"
                  >
                    <template #trigger>
                      <n-button type="error" quaternary :loading="deleting">删除</n-button>
                    </template>
                    确认删除提示词“{{ translatedPromptTitle }}”？删除后无法恢复。
                  </n-popconfirm>
                  <n-button type="primary" :loading="saving" @click="savePrompt">保存修改</n-button>
                </n-space>
              </n-space>
            </div>
          </div>
        </div>
      </n-spin>
    </n-space>
  </n-card>

  <PromptCreateModal
    :show="createModalVisible"
    :creating="creating"
    :form="createForm"
    @update:show="createModalVisible = $event"
    @cancel="closeCreateModal"
    @create="createPrompt"
  />
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { NAlert, NButton, NCard, NDynamicTags, NEmpty, NForm, NFormItem, NInput, NPopconfirm, NSpace, NSpin } from 'naive-ui'
import PromptCreateModal from './prompts/PromptCreateModal.vue'
import PromptListSidebar from './prompts/PromptListSidebar.vue'
import { usePromptManagement } from '@/composables/admin/usePromptManagement'
import { useResponsiveFlag } from '@/composables/admin/useResponsiveFlag'
import { describePromptName, translatePromptName } from './adminI18n'

const {
  prompts,
  selectedPrompt,
  loading,
  saving,
  deleting,
  creating,
  error,
  editForm,
  createModalVisible,
  createForm,
  fetchPrompts,
  selectPrompt,
  savePrompt,
  deletePrompt,
  openCreateModal,
  closeCreateModal,
  createPrompt,
} = usePromptManagement()

const { matched: isMobile } = useResponsiveFlag(920)

const translatedPromptTitle = computed(() => editForm.title || translatePromptName(editForm.name))
const translatedPromptDescription = computed(() => describePromptName(editForm.name))

onMounted(() => {
  fetchPrompts()
})
</script>

<style scoped>
.admin-card { width: 100%; }
.card-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
.card-title { font-size: 1.1rem; font-weight: 700; color: #1f2937; }
.card-subtitle { margin: 6px 0 0; color: #64748b; font-size: 0.85rem; }
.prompt-layout { display: flex; align-items: stretch; gap: 18px; min-height: 520px; }
.prompt-layout.mobile { flex-direction: column; }
.prompt-editor { flex: 1; min-width: 0; }
.empty-editor { height: 100%; display: flex; align-items: center; justify-content: center; padding: 48px 0; }
.editor-content { display: flex; flex-direction: column; gap: 14px; }
.editor-header {
  display: grid;
  gap: 10px;
  border: 1px solid rgba(99, 102, 241, 0.14);
  border-radius: 16px;
  padding: 14px 16px;
  background: rgba(238, 242, 255, 0.72);
}
.editor-header__eyebrow { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.08em; color: #4f46e5; }
.editor-header__title { margin-top: 6px; font-size: 1rem; font-weight: 700; color: #1f2937; }
.editor-header__meta,
.editor-header__description { margin: 0; font-size: 0.84rem; line-height: 1.65; color: #475569; }
.editor-actions { gap: 16px; }
.editor-actions__hint { font-size: 0.82rem; color: #64748b; }
.prompt-textarea :deep(textarea) {
  font-family: 'Fira Code', 'JetBrains Mono', 'SFMono-Regular', Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 1.5;
}
</style>
