// AIMETA P=灏忚鐘舵€乢褰撳墠灏忚鏁版嵁绠＄悊|R=currentNovel_chapters_fetch|NR=涓嶅惈API璋冪敤|E=store:novel|X=internal|A=useNovelStore|D=pinia|S=none|RD=./README.ai
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  NovelProject,
  NovelProjectSummary,
  ConverseResponse,
  BlueprintGenerationResponse,
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
  selectChapterVersion as selectChapterVersionRequest,
  updateChapterOutline as updateChapterOutlineRequest,
} from '@/api/modules/chapterWorkflow'
import { useNotificationStore } from '@/stores/notification'

export const useNovelStore = defineStore('novel', () => {
  // State
  const projects = ref<NovelProjectSummary[]>([])
  const currentProject = ref<NovelProject | null>(null)
  const currentConversationState = ref<any>({})
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const pendingChapterEdits = new Map<string, symbol>()
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

  // Actions
  async function loadProjects() {
    isLoading.value = true
    error.value = null
    try {
      projects.value = await NovelAPI.getAllNovels()
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鍔犺浇椤圭洰澶辫触'
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
      notif.success(`小说《${title}》创建成功！`)
      return project
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鍒涘缓椤圭洰澶辫触'
      const notif = useNotificationStore()
      notif.error(`创建失败：${err instanceof Error ? err.message : '未知错误'}`)
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
      const project = await NovelAPI.getNovel(projectId)
      if (requestId !== latestLoadProjectRequestId) {
        return
      }
      currentProject.value = project
      syncProjectSummary(project)
    } catch (err) {
      const message = err instanceof Error ? err.message : '鍔犺浇椤圭洰澶辫触'
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
        throw new Error('娌℃湁褰撳墠椤圭洰')
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
      error.value = err instanceof Error ? err.message : '鍔犺浇绔犺妭澶辫触'
      throw err
    }
  }

  async function sendConversation(userInput: any): Promise<ConverseResponse> {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const response = await NovelAPI.converseConcept(
        currentProject.value.id,
        userInput,
        currentConversationState.value
      )
      currentConversationState.value = response.conversation_state
      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '瀵硅瘽澶辫触'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateBlueprint(): Promise<BlueprintGenerationResponse> {
    // Generate blueprint from conversation history
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      return await NovelAPI.generateBlueprint(currentProject.value.id)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鐢熸垚钃濆浘澶辫触'
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function saveBlueprint(blueprint: Blueprint) {
    isLoading.value = true
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      if (!blueprint) {
        throw new Error('缂哄皯钃濆浘鏁版嵁')
      }
      currentProject.value = await NovelAPI.saveBlueprint(currentProject.value.id, blueprint)
      const notif = useNotificationStore()
      notif.success('灏忚钃濆浘宸蹭繚瀛橈紒')
    } catch (err) {
      error.value = err instanceof Error ? err.message : '淇濆瓨钃濆浘澶辫触'
      const notif = useNotificationStore()
      notif.error(`保存失败：${err instanceof Error ? err.message : '未知错误'}`)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function generateChapter(
    chapterNumber: number,
    options: GenerateChapterOptions = {}
  ): Promise<NovelProject> {
    // 娉ㄦ剰锛氳繖閲屼笉璁剧疆鍏ㄥ眬 isLoading锛屽洜涓?WritingDesk.vue 鏈夎嚜宸辩殑灞€閮ㄥ姞杞界姸鎬?    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await generateChapterRequest(currentProject.value.id, chapterNumber, options)
      currentProject.value = updatedProject // 鏇存柊 store 涓殑褰撳墠椤圭洰
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鐢熸垚绔犺妭澶辫触'
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
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await cancelChapterGenerationRequest(currentProject.value.id, chapterNumber, options)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '缁堟绔犺妭浠诲姟澶辫触'
      throw err
    }
  }

  async function evaluateChapter(chapterNumber: number, versionIndex?: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await evaluateChapterRequest(currentProject.value.id, chapterNumber, versionIndex)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '璇勪及绔犺妭澶辫触'
      throw err
    }
  }

  async function evaluateAllVersions(chapterNumber: number): Promise<NovelProject> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await evaluateChapterRequest(currentProject.value.id, chapterNumber, undefined, true)
      currentProject.value = updatedProject
      syncProjectSummary(updatedProject)
      return updatedProject
    } catch (err) {
      error.value = err instanceof Error ? err.message : '多版本评审失败'
      throw err
    }
  }

  async function optimizeChapterVersion(
    projectId: string,
    chapterNumber: number,
    versionIndex: number,
    dimension: 'dialogue' | 'environment' | 'psychology' | 'rhythm' = 'rhythm',
    additionalNotes?: string
  ): Promise<OptimizeResponse> {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }

      const chapter = currentProject.value.chapters.find((c) => c.chapter_number === chapterNumber)
      const version = chapter?.versions?.[versionIndex]

      if (!version?.content) {
        throw new Error('鐗堟湰鍐呭涓虹┖')
      }

      const result = await OptimizerAPI.optimizeChapter({
        project_id: projectId,
        chapter_number: chapterNumber,
        dimension,
        additional_notes: additionalNotes?.trim() || undefined,
        version_index: versionIndex
      })

      if (!result.optimized_content?.trim()) {
        throw new Error('浼樺寲缁撴灉涓虹┖')
      }

      return result
    } catch (err) {
      error.value = err instanceof Error ? err.message : '浼樺寲鐗堟湰澶辫触'
      throw err
    }
  }

  async function selectChapterVersion(chapterNumber: number, versionIndex: number) {
    // 涓嶈缃叏灞€ isLoading锛岃璋冪敤鏂瑰鐞嗗眬閮ㄥ姞杞界姸鎬?    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await selectChapterVersionRequest(
        currentProject.value.id,
        chapterNumber,
        versionIndex
      )
      currentProject.value = updatedProject // 鏇存柊 store
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '閫夋嫨绔犺妭鐗堟湰澶辫触'
      throw err
    }
  }

  async function deleteChapterVersion(chapterNumber: number, versionIndex: number) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await deleteChapterVersionRequest(
        currentProject.value.id,
        chapterNumber,
        versionIndex
      )
      currentProject.value = updatedProject // 鏇存柊 store
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鍒犻櫎绔犺妭鐗堟湰澶辫触'
      throw err
    }
  }

  async function deleteProjects(projectIds: string[]): Promise<DeleteNovelsResponse> {
    isLoading.value = true
    error.value = null
    try {
      const response = await NovelAPI.deleteNovels(projectIds)

      // 浠庢湰鍦伴」鐩垪琛ㄤ腑绉婚櫎宸插垹闄ょ殑椤圭洰
      projects.value = projects.value.filter(project => !projectIds.includes(project.id))

      // 濡傛灉褰撳墠椤圭洰琚垹闄わ紝娓呯┖褰撳墠椤圭洰
      if (currentProject.value && projectIds.includes(currentProject.value.id)) {
        currentProject.value = null
        currentConversationState.value = {}
      }

      const notif = useNotificationStore()
      notif.success(`已删除 ${projectIds.length} 个项目`)

      return response
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鍒犻櫎椤圭洰澶辫触'
      const notif = useNotificationStore()
      notif.error(`删除失败：${err instanceof Error ? err.message : '未知错误'}`)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  async function updateChapterOutline(chapterOutline: ChapterOutline) {
    // 涓嶈缃叏灞€ isLoading锛岃璋冪敤鏂瑰鐞嗗眬閮ㄥ姞杞界姸鎬?    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await updateChapterOutlineRequest(
        currentProject.value.id,
        chapterOutline
      )
      currentProject.value = updatedProject // 鏇存柊 store
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鏇存柊绔犺妭澶х翰澶辫触'
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
        throw new Error('娌℃湁褰撳墠椤圭洰')
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
      error.value = err instanceof Error ? err.message : 'AI 閲嶅啓绔犺妭澶х翰澶辫触'
      throw err
    }
  }

  async function deleteChapter(chapterNumbers: number | number[]) {
    error.value = null
    try {
      if (!currentProject.value) {
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const numbersToDelete = Array.isArray(chapterNumbers) ? chapterNumbers : [chapterNumbers]
      const updatedProject = await deleteChapterRequest(
        currentProject.value.id,
        numbersToDelete
      )
      currentProject.value = updatedProject // 鏇存柊 store
      syncProjectSummary(updatedProject)
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鍒犻櫎绔犺妭澶辫触'
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
        throw new Error('娌℃湁褰撳墠椤圭洰')
      }
      const updatedProject = await generateChapterOutlineRequest(
        currentProject.value.id,
        startChapter,
        numChapters,
        options
      )
      currentProject.value = updatedProject // 鏇存柊 store
    } catch (err) {
      error.value = err instanceof Error ? err.message : '鐢熸垚澶х翰澶辫触'
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
            ...(currentVersion || ({ style: '鏍囧噯' } as ChapterVersion)),
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
      error.value = err instanceof Error ? err.message : '缂栬緫绔犺妭鍐呭澶辫触'
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
    saveBlueprint,
    generateChapter,
    cancelChapterGeneration,
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

