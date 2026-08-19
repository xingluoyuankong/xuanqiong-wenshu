// AIMETA P=小说状态_store|R=currentNovel_chapters_fetch|NR=不含UI|E=store:novel|X=internal|A=useNovelStore|D=pinia|S=none|RD=./README.ai
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  NovelProject,
  NovelProjectSummary,
  ConverseResponse,
  BlueprintGenerationResponse,
  BlueprintGenerationJobResponse,
  Blueprint,
  ChapterVersion,
  DeleteNovelsResponse,
  ChapterOutline,
  CancelChapterOptions,
  GenerateChapterOptions,
  GenerateOutlineOptions,
  RewriteChapterOutlineOptions,
  OptimizeResponse,
} from '@/api/novel'
import { NovelAPI, OptimizerAPI } from '@/api/novel'
import { editChapterContent as editChapterContentRequest } from '@/api/modules/chapterEditing'
import {
  cancelChapterGeneration as cancelChapterGenerationRequest,
  deleteChapter as deleteChapterRequest,
  deleteChapterVersion as deleteChapterVersionRequest,
  evaluateChapter as evaluateChapterRequest,
  generateChapter as generateChapterRequest,
  generateChapterOutline as generateChapterOutlineRequest,
  rewriteChapterOutline as rewriteChapterOutlineRequest,
  resumeChapterGeneration as resumeChapterGenerationRequest,
  selectChapterVersion as selectChapterVersionRequest,
  updateChapterOutline as updateChapterOutlineRequest,
} from '@/api/modules/chapterWorkflow'
import { useNotificationStore } from '@/stores/notification'
import { pick } from '@/composables/useLocale'

export const useNovelStore = defineStore('novel', () => {
  // State
  const projects = ref<NovelProjectSummary[]>([])
  const currentProject = ref<NovelProject | null>(null)
  const currentConversationState = ref<any>({})
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const pendingChapterEdits = new Map<string, symbol>()
  const inflightProjectRequests = new Map<string, Promise<NovelProject>>()
  let inflightProjectsRequest: Promise<NovelProjectSummary[]> | null = null
  let latestLoadProjectRequestId = 0

  // Getters
  const projectsCount = computed(() => projects.value.length)
  const hasCurrentProject = computed(() => currentProject.value !== null)

  function syncProjectSummary(project: NovelProject | null) {
    if (!project) return
    const totalChapters =
      project.workspace_summary?.total_chapters
      ?? project.blueprint?.chapter_outline?.length
      ?? project.chapters?.length
      ?? 0
    const completedChapters =
      project.workspace_summary?.completed_chapters
      ?? (project.chapters || []).filter((chapter) => chapter.generation_status === 'successful').length
    const nextSummary: NovelProjectSummary = {
      id: project.id,
      title: project.title,
      genre: project.blueprint?.genre || '',
      last_edited: new Date().toISOString(),
      completed_chapters: completedChapters,
      total_chapters: totalChapters,
    }
    const index = projects.value.findIndex((item) => item.id === project.id)
    if (index >= 0) {
      projects.value.splice(index, 1, {
        ...projects.value[index],
        ...nextSummary,
      })
    } else {
      projects.value.unshift(nextSummary)
    }
  }

  const fetchProjectsOnce = () => {
    if (inflightProjectsRequest) {
      return inflightProjectsRequest
    }

    inflightProjectsRequest = NovelAPI.getAllNovels().finally(() => {
      inflightProjectsRequest = null
    })

    return inflightProjectsRequest
  }

  const fetchProjectOnce = (projectId: string) => {
    const existingRequest = inflightProjectRequests.get(projectId)
    if (existingRequest) {
      return existingRequest
    }

    const request = NovelAPI.getNovel(projectId).finally(() => {
      if (inflightProjectRequests.get(projectId) === request) {
        inflightProjectRequests.delete(projectId)
      }
    })

    inflightProjectRequests.set(projectId, request)
    return request
  }

  // Actions
  async function loadProjects() {
    isLoading.value = true
    error.value = null
    try {
      projects.value = await fetchProjectsOnce()
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('加载项目失败', 'Failed to load the project')
    } finally {
      isLoading.value = false
    }
  }

  async function createProject(title: string, initialPrompt: string) {
    isLoading.value = true
    error.value = null
    try {
      const project = await NovelAPI.createNovel(title, initialPrompt)
      currentProject.value = project
      syncProjectSummary(project)
      currentConversationState.value = {}
      const notif = useNotificationStore()
      notif.success(pick(`小说《${title}》创建成功！`, `Novel “${title}” created.`))
      return project
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('创建项目失败', 'Failed to create the project')
      const notif = useNotificationStore()
      notif.error(pick(
        `创建失败：${err instanceof Error ? err.message : '未知错误'}`,
        `Creation failed: ${err instanceof Error ? err.message : 'unknown error'}`
      ))
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function loadProject(
    projectId: string,
    silent: boolean = false,
    throwOnError: boolean = false
  ) {
    const requestId = ++latestLoadProjectRequestId
    if (!silent) {
      isLoading.value = true
    }
    error.value = null
    try {
      const project = await fetchProjectOnce(projectId)
      if (requestId !== latestLoadProjectRequestId) {
        return
      }
      currentProject.value = project
      syncProjectSummary(project)
    } catch (err) {
      const message = err instanceof Error ? err.message : pick('加载项目失败', 'Failed to load the project')
      if (requestId !== latestLoadProjectRequestId) {
        return
      }
      error.value = message
      if (throwOnError) {
        throw err instanceof Error ? err : new Error(message)
      }
    } finally {
      if (!silent && requestId === latestLoadProjectRequestId) {
        isLoading.value = false
      }
    }
  }

  async function loadChapter(chapterNumber: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const chapter = await NovelAPI.getChapter(currentProject.value.id, chapterNumber)
      const project = currentProject.value
      if (!Array.isArray(project.chapters)) {
        project.chapters = []
      }
      const index = project.chapters.findIndex(ch => ch.chapter_number === chapterNumber)
      if (index >= 0) {
        project.chapters.splice(index, 1, chapter)
      } else {
        project.chapters.push(chapter)
      }
      project.chapters.sort((a, b) => a.chapter_number - b.chapter_number)
      return chapter
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('加载章节失败', 'Failed to load the chapter')
      throw err
    }
  }

  async function sendConversation(userInput: any): Promise<ConverseResponse> {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const response = await NovelAPI.converseConcept(
        currentProject.value.id,
        userInput,
        currentConversationState.value
      )
      currentConversationState.value = response.conversation_state
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('对话失败', 'The conversation request failed')
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateBlueprint(): Promise<BlueprintGenerationResponse> {
    // Legacy convenience entry: keep the store API stable, but route through the
    // background blueprint job so old UI/tests do not bypass progress/cancel.
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      return await NovelAPI.generateBlueprint(currentProject.value.id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('生成蓝图失败', 'Failed to generate the blueprint')
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function startBlueprintGeneration(
    options: { forceStage?: 'novel_outline' | 'chapter_outline' } = {}
  ): Promise<BlueprintGenerationJobResponse> {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      return await NovelAPI.startBlueprintGeneration(currentProject.value.id, options)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('启动蓝图生成失败', 'Failed to start blueprint generation')
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function getBlueprintGenerationStatus(): Promise<BlueprintGenerationJobResponse> {
    if (!currentProject.value) {
      throw new Error(pick('没有当前项目', 'No active project'))
    }
    return await NovelAPI.getBlueprintGenerationStatus(currentProject.value.id)
  }

  async function cancelBlueprintGeneration(): Promise<BlueprintGenerationJobResponse> {
    if (!currentProject.value) {
      throw new Error(pick('没有当前项目', 'No active project'))
    }
    return await NovelAPI.cancelBlueprintGeneration(currentProject.value.id)
  }

  async function saveBlueprint(blueprint: Blueprint) {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      if (!blueprint) {
        throw new Error(pick('缺少蓝图数据', 'Blueprint data is missing'))
      }
      currentProject.value = await NovelAPI.saveBlueprint(currentProject.value.id, blueprint)
      const notif = useNotificationStore()
      notif.success(pick('小说蓝图已保存！', 'Blueprint saved.'))
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('保存蓝图失败', 'Failed to save the blueprint')
      const notif = useNotificationStore()
      notif.error(pick(
        `保存失败：${err instanceof Error ? err.message : '未知错误'}`,
        `Save failed: ${err instanceof Error ? err.message : 'unknown error'}`
      ))
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateChapter(
    chapterNumber: number,
    options: GenerateChapterOptions = {}
  ): Promise<NovelProject> {
    // 不设置全局 isLoading，由调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await generateChapterRequest(currentProject.value.id, chapterNumber, options)
      // 更新当前项目缓存
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('生成章节失败', 'Failed to generate the chapter')
      throw err
    }
  }

  async function cancelChapterGeneration(
    chapterNumber: number,
    options: CancelChapterOptions = {}
  ): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await cancelChapterGenerationRequest(currentProject.value.id, chapterNumber, options)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('终止章节任务失败', 'Failed to stop the chapter job')
      throw err
    }
  }

  async function resumeChapterGeneration(
    runId: string,
  ): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await resumeChapterGenerationRequest(currentProject.value.id, runId)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('恢复章节任务失败', 'Failed to resume the chapter job')
      throw err
    }
  }

  async function evaluateChapter(chapterNumber: number, versionIndex?: number, versionId?: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await evaluateChapterRequest(currentProject.value.id, chapterNumber, versionIndex, versionId)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('评估章节失败', 'Failed to evaluate the chapter')
      throw err
    }
  }

  async function evaluateAllVersions(chapterNumber: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await evaluateChapterRequest(currentProject.value.id, chapterNumber, undefined, undefined, true)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('多版本评审失败', 'Failed to review all versions')
      throw err
    }
  }

  async function optimizeChapterVersion(
    projectId: string,
    chapterNumber: number,
    versionIndex: number,
    versionId?: number,
    dimension: 'dialogue' | 'environment' | 'psychology' | 'rhythm' = 'rhythm',
    additionalNotes?: string
  ): Promise<OptimizeResponse> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }

      const chapter = currentProject.value.chapters.find((c) => c.chapter_number === chapterNumber)
      const version = versionId
        ? chapter?.versions?.find((item) => item.id === versionId)
        : chapter?.versions?.[versionIndex]

      if (!version?.content) {
        throw new Error(pick('版本内容为空', 'The version content is empty'))
      }

      const versionSelector = typeof versionId === 'number'
        ? { version_id: versionId }
        : { version_index: versionIndex }
      const result = await OptimizerAPI.optimizeChapter({
        project_id: projectId,
        chapter_number: chapterNumber,
        dimension,
        additional_notes: additionalNotes?.trim() || undefined,
        ...versionSelector
      })

      if (!result.optimized_content?.trim()) {
        throw new Error(pick('优化结果为空', 'The optimization result is empty'))
      }

      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('优化版本失败', 'Failed to optimize the version')
      throw err
    }
  }

  async function selectChapterVersion(chapterNumber: number, versionIndex: number, versionId?: number) {
    // 不设置全局 isLoading，由调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await selectChapterVersionRequest(
        currentProject.value.id,
        chapterNumber,
        versionIndex,
        versionId
      )
      // 更新当前项目缓存
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('选择章节版本失败', 'Failed to select the chapter version')
      throw err
    }
  }

  async function deleteChapterVersion(chapterNumber: number, versionIndex: number, versionId?: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await deleteChapterVersionRequest(
        currentProject.value.id,
        chapterNumber,
        versionIndex,
        versionId
      )
      // 更新当前项目缓存
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('删除章节版本失败', 'Failed to delete the chapter version')
      throw err
    }
  }

  async function deleteProjects(projectIds: string[]): Promise<DeleteNovelsResponse> {
    isLoading.value = true
    error.value = null
    try {
      const response = await NovelAPI.deleteNovels(projectIds)

      // 从本地项目列表中移除已删除的项目
      projects.value = projects.value.filter(project => !projectIds.includes(project.id))

      // 如果当前项目被删除，则清空当前项目
      if (currentProject.value && projectIds.includes(currentProject.value.id)) {
        currentProject.value = null
        currentConversationState.value = {}
      }

      const notif = useNotificationStore()
      notif.success(pick(`已删除 ${projectIds.length} 个项目`, `Deleted ${projectIds.length} project(s)`))

      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('删除项目失败', 'Failed to delete the projects')
      const notif = useNotificationStore()
      notif.error(pick(
        `删除失败：${err instanceof Error ? err.message : '未知错误'}`,
        `Deletion failed: ${err instanceof Error ? err.message : 'unknown error'}`
      ))
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateChapterOutline(chapterOutline: ChapterOutline) {
    // 不设置全局 isLoading，由调用方处理局部加载状态
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await updateChapterOutlineRequest(
        currentProject.value.id,
        chapterOutline
      )
      // 更新当前项目缓存
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('更新章节大纲失败', 'Failed to update the chapter outline')
      throw err
    }
  }

  async function rewriteChapterOutline(
    chapterOutline: ChapterOutline,
    options: RewriteChapterOutlineOptions = {}
  ) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await rewriteChapterOutlineRequest(
        currentProject.value.id,
        chapterOutline,
        options
      )
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('AI 重写章节大纲失败', 'AI failed to rewrite the chapter outline')
      throw err
    }
  }

  async function deleteChapter(chapterNumbers: number | number[]) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
      const updatedProject = await deleteChapterRequest(
        currentProject.value.id,
        numbersToDelete
      )
      // 更新当前项目缓存
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('删除章节失败', 'Failed to delete the chapter')
      throw err
    }
  }

  async function generateChapterOutline(
    startChapter: number,
    numChapters: number,
    options: GenerateOutlineOptions = {}
  ) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error(pick('没有当前项目', 'No active project'))
      }
      const updatedProject = await generateChapterOutlineRequest(
        currentProject.value.id,
        startChapter,
        numChapters,
        options
      )
      // 更新当前项目缓存
      currentProject.value = updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : pick('生成大纲失败', 'Failed to generate the outline')
      throw err
    }
  }

  async function editChapterContent(projectId: string, chapterNumber: number, content: string) {
    error.value = null
    const requestKey = `${projectId}:${chapterNumber}`
    const requestToken = Symbol(requestKey)
    pendingChapterEdits.set(requestKey, requestToken)
    const project = currentProject.value
    const chapter = project?.chapters.find(ch => ch.chapter_number === chapterNumber)
    const previousSnapshot = chapter
      ? {
          content: chapter.content ?? null,
          wordCount: chapter.word_count,
          versions: Array.isArray(chapter.versions)
            ? chapter.versions.map(version => ({ ...version }))
            : chapter.versions,
        }
      : null

    if (chapter) {
      chapter.content = content
      chapter.word_count = content.length
      if (Array.isArray(chapter.versions) && previousSnapshot && previousSnapshot.content !== null) {
        const versionIndex = chapter.versions.findIndex(v => v.content === previousSnapshot.content)
        if (versionIndex >= 0) {
          const currentVersion = chapter.versions[versionIndex]
          chapter.versions.splice(versionIndex, 1, {
            // '标准' 是后端约定的 style 字段值，属内部真源，不随界面语言变化
            ...(currentVersion || ({ style: '标准' } as ChapterVersion)),
            content,
          })
        }
      }
    }

    try {
      const updatedChapter = await editChapterContentRequest(projectId, chapterNumber, content)
      if (pendingChapterEdits.get(requestKey) !== requestToken) {
        return
      }
      if (project) {
        const chapters = project.chapters
        const index = chapters.findIndex(ch => ch.chapter_number === chapterNumber)
        if (index >= 0) {
          chapters.splice(index, 1, updatedChapter)
        } else {
          chapters.push(updatedChapter)
          chapters.sort((a, b) => a.chapter_number - b.chapter_number)
        }
      }
      pendingChapterEdits.delete(requestKey)
    } catch (err) {
      if (pendingChapterEdits.get(requestKey) === requestToken) {
        pendingChapterEdits.delete(requestKey)
        if (chapter && previousSnapshot) {
          chapter.content = previousSnapshot.content
          chapter.word_count = previousSnapshot.wordCount
          chapter.versions = Array.isArray(previousSnapshot.versions)
            ? previousSnapshot.versions.map(version => ({ ...version }))
            : previousSnapshot.versions ?? null
        }
      }
      error.value = err instanceof Error ? err.message : pick('编辑章节内容失败', 'Failed to save the chapter content')
      throw err
    }
  }

  function clearError() {
    error.value = null
  }

  function setCurrentProject(project: NovelProject | null) {
    currentProject.value = project
  }

  return {
    // State
    projects,
    currentProject,
    currentConversationState,
    isLoading,
    error,
    // Getters
    projectsCount,
    hasCurrentProject,
    // Actions
    loadProjects,
    createProject,
    loadProject,
    loadChapter,
    sendConversation,
    generateBlueprint,
    startBlueprintGeneration,
    getBlueprintGenerationStatus,
    cancelBlueprintGeneration,
    saveBlueprint,
    generateChapter,
    cancelChapterGeneration,
    resumeChapterGeneration,
    evaluateChapter,
    evaluateAllVersions,
    optimizeChapterVersion,
    selectChapterVersion,
    deleteChapterVersion,
    deleteProjects,
    updateChapterOutline,
    rewriteChapterOutline,
    deleteChapter,
    generateChapterOutline,
    editChapterContent,
    clearError,
    setCurrentProject
  }
})
