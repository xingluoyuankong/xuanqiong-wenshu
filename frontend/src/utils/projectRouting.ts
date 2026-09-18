import type { Blueprint, NovelProject, NovelProjectSummary } from '@/api/novel'

const hasText = (value: unknown) => typeof value === 'string' && value.trim().length > 0

const hasItems = (value: unknown) => Array.isArray(value) && value.length > 0

const hasBlueprintDraft = (blueprint?: Blueprint) => {
  if (!blueprint) return false
  return hasText(blueprint.title)
    || hasText(blueprint.one_sentence_summary)
    || hasText(blueprint.full_synopsis)
    || hasItems(blueprint.characters)
    || hasItems(blueprint.relationships)
}

const hasNovelOutline = (blueprint?: Blueprint) => hasItems(blueprint?.novel_outline)

const hasChapterOutline = (blueprint?: Blueprint) => hasItems(blueprint?.chapter_outline)

export const shouldResumeInspirationFromProject = (project: NovelProject) => {
  if (project.title === '未命名灵感') return true
  if (Array.isArray(project.chapters) && project.chapters.length === 0) return true

  const blueprint = project.blueprint
  return hasBlueprintDraft(blueprint) && !hasNovelOutline(blueprint) && !hasChapterOutline(blueprint)
}

export const shouldResumeInspirationFromSummary = (project: NovelProjectSummary) => {
  return project.title === '未命名灵感' || project.total_chapters === 0
}

export const resolveProjectWritingEntry = (project: NovelProject) => {
  return shouldResumeInspirationFromProject(project)
    ? `/inspiration?project_id=${project.id}`
    : `/novel/${project.id}`
}

export const resolveProjectWritingEntryFromSummary = (project: NovelProjectSummary) => {
  return shouldResumeInspirationFromSummary(project)
    ? `/inspiration?project_id=${project.id}`
    : `/novel/${project.id}`
}
