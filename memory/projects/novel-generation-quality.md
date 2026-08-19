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
- Full backend gate: **691 passed in 61.34s** (`cd backend && PYTHONIOENCODING=utf-8 python -m pytest app -q`, exit 0). History: 659 → 661 (batch 1) → 668 (batch 2) → 679 (batch 3) → 688 (batch 4) → 691 (batch 5).
- Targeted quality suite `test_generation_quality_guards.py`: **116 passed in 4.84s** (113 before batch 5 — 3 net new; one existing test was renamed and its assertion inverted, so the collected count rises by 3 while 4 repair tests are new).
- New fast guard: `pytest app/services/test_generation_quality_guards.py -k "BadSampleRegression"` → 9 passed. Run this before any quality-gate change; it is an order of magnitude faster than the full suite and covers both directions.
- Batch 4 reverse verification: 6 production conditions broken 11 different ways at runtime via `setattr`, **11/11 turned the expected test red**, and all 6 attributes restored to the original objects afterwards. The one break that did *not* turn anything red is recorded as D-25.
- Batch 5 reverse verification: 4 production conditions broken 12 different ways, **12/12 turned the expected test red**, all 4 restored (`is`-compared afterwards). Key technique: the wiring test asserts over `inspect.getsource(generate_chapter)`, so breaking it means replacing `inspect.getsource` itself — replacing `P.generate_chapter` only produces a `TypeError`, which is a fake red.
- Frontend quality display suite: 6 files, 12 tests passed. Frontend type-check passed.
- Real-corpus recheck after batch 3 recalibration: 95.0% of historically-passing chapters still pass the event-density gate (n=107); the 6 rejects are genuinely ultra-low-density long text.
- **Not verified**: real generation end-to-end under the new thresholds — LLM quota is exhausted (`403 pre-consume quota failed`). Retry-and-degrade behaviour is unproven. See §8.4 of the handoff doc.

## Batch Rollout Status (see TASK_HANDOFF_NOVEL_QUALITY.md)
- Batch 1 ✅ T-01/T-20/T-21 — dead code removed, module-boundary comments cleaned, commit-message rule recorded. 661 passed.
- Batch 2 ✅ T-02/T-03/T-15 — ending-pressure gate: semantic hit is now a necessary condition, `"一切都"` false-kill fixed, word lists de-escaped and de-genre-fied. 668 passed.
- Batch 3 ✅ T-04/T-05/T-06 — event-density gate: quotes no longer imply progression, window check uses a real window-level predicate with tail merging, and **all thresholds re-derived from 147 real chapters** after the synthetic-sample version turned out to reject 96% of real text. Absolute `plain_run_limit` replaced by ratio-based `plain_run_ratio_limit` + new `max_plain_unit_run_ratio` field. 679 passed.
- Batch 4 ✅ T-07 — `class TestBadSampleRegression`: 9 tests, 5 bad samples + 1 positive control, one-line production fix (`flat_closure_markers` into the snapshot allowlist). 688 passed. Three samples from the original 8-sample plan (repeated paragraphs / missing focus character / no inheritance) were deferred because D-10/D-12/E-07 aren't implemented yet — there is nothing to assert against.
- Batch 5 ✅ T-22 — structural-gate repair loop now keeps partial improvement instead of discarding a whole revised chapter for missing a full pass. Improvement is a **strict subset contraction** (`len(after) < len(before) and not (after - before)`), capped at `STRUCTURAL_GATE_REPAIR_MAX_ROUNDS = 2` (hard-coded — each round is an LLM call, so it's a cost gate, not a tuning knob). `_attempt_structural_gate_repair` no longer returns `None`: it always returns a dict whose `adopted` bool carries the decision, so callers can tell "tried and failed" from "never tried" (`repair_skipped_reason` ∈ `self_critique_disabled` / `story_guard_missing` / `no_structural_issue` / `revise_failed`). Both call sites record `repair_summary` into `runtime_metadata["quality_gate_repairs"]` **even when not adopted** — otherwise the user faces an unexplained 422. 691 passed.
- Batches 6-10 pending. **Batch 6 now also carries D-24 and D-25.**

## Next Useful Work
- Batch 5's lesson: **a shrinking blocker count is not improvement.** Measured counter-example — `"## 场景 1｜开场\n\n" + GOOD_DRAMATIC` drops from 7 blockers to 1, but that 1 is `chapter_artifact_markers`, an entirely new failure mode; adopting it would make the repair loop converge in the wrong direction. Any future "did it get better" predicate needs the no-new-code-types half, not just the count.
- Batch 6 must fix **D-24**: the ending-pressure gate reads a fixed 260-character tail window, so a short flat ending is masked by the body's own hooks (same ending: 38-char tail → `codes=[]`/1302, 275-char tail → `ending_pressure_missing`/1042). Real endings are 1-3 sentences, so this is the common case in production. Fix needs §11.2.1 real-corpus calibration. When it's fixed, shorten `_FLAT_ENDING_FILLER` in the two ending samples and confirm they're still blocked — that's the proof.
- Batch 6 should also close **D-25**: only branch 1 of the three `static_description_risk` or-conditions has coverage.
- E-08 offline batch evaluation, ideally before batch 9 reweights scoring — the batch-3 real-corpus probe already proved out DB sampling, degenerate-text filtering, and redaction.
- Progression-marker recall is the real ceiling: 93% of sentences in real chapters match no progression word at all (rate p50 = 0.079). Vocabulary coverage, not thresholds, is what limits this gate now.
- Frontend fallback still ignores `event_density_passed` (D-22).
- Add a compact backend endpoint or payload field that normalizes quality blocker codes into frontend-ready Chinese labels.
- Build a small generated-output fixture suite for chapter continuity across two or three chapters.
