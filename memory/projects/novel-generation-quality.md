# Novel Generation Quality Overhaul

## Goal
Make the novel generation feature truly usable at first draft quality: enough words, natural dialogue, logical causality, real plot movement, reversals, and continuity across chapters.

## User Pain Points
- Content is mostly description.
- Dialogue is too little, unnatural, and does not change the situation.
- Logic and causality are weak.
- Substantive plot movement and reversals are too rare.
- Chapter-to-chapter and paragraph-to-paragraph continuity is poor.
- Word-count targets should be followed as closely as practical.
- Later polish should improve a strong draft, not patch a scattered weak draft.

## Completed Quality Work
- Added story quality scoring in `backend/app/services/pipeline_orchestrator.py` for scene fulfillment, dialogue state change, ending pressure, static description risk, and quality metric snapshots.
- Added first-draft retry/version selection signals so weak drafts can be rejected or outweighed by stronger candidates.
- Added structural reader polish issue generation so reader polish prioritizes structure over sentence-level smoothing.
- Injected previous chapter tail and open hooks into RAG continuity context.
- Added outline hard-rejection reason surfacing in `backend/app/api/routers/writer.py`.
- Added quality metadata exposure through `backend/app/services/novel_service.py`.
- Tightened enrichment prompts in `backend/app/services/enrichment_service.py` so expansion only adds action, dialogue, consequence, and short sequel decisions.
- Added frontend quality summary utility and UI display in writing desk header/sidebar, failure state, version modal, candidate cards, and active version preview.
- Added backend `quality_issue_summary` with stable codes, Chinese labels, hints, and tone so the frontend can show exact failure reasons instead of inferring everything locally.
- Updated frontend quality utility to prefer backend-provided quality issue labels and only fall back to local metric heuristics when the backend summary is absent.

## Verified Tests
- `python -m pytest backend/app/services/test_blueprint_observability.py::test_build_chapter_schema_uses_runtime_actual_word_count_and_exposes_version_word_counts backend/app/services/test_generation_quality_guards.py`
- `npm run test:run -- src/components/writing-desk/workspace/review/VersionSelector.spec.ts src/utils/chapterQuality.spec.ts src/components/writing-desk/layout/WDSidebar.spec.ts src/api/novel.spec.ts src/components/writing-desk/workspace/states/ChapterFailed.spec.ts src/components/writing-desk/dialogs/WDVersionDetailModal.spec.ts`
- `npm run type-check`

## Latest Verification
- Backend quality suite: 26 passed.
- Frontend quality display suite: 6 files, 12 tests passed.
- Frontend type-check passed.

## Next Useful Work
- Add a compact backend endpoint or payload field that normalizes quality blocker codes into frontend-ready Chinese labels.
- Add a stricter confirmation affordance for dangerous candidates: require optimization or explicit override when quality risk is severe.
- Build a small generated-output fixture suite for chapter continuity across two or three chapters.
- Add tests that verify first-draft retry feedback includes concrete scene-list failures and open-hook continuity.
- Add frontend snapshots for quality metric rendering when metadata only exists on selected/latest version.
