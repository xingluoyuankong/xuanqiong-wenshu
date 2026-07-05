# Memory

## Active Project
| Name | What |
|------|------|
| xuanqiong-wenshu | Novel generation quality and continuity overhaul. |

## Current Priorities
- Make first-draft novel generation satisfy quality requirements before later polish.
- Reduce static description, increase natural dialogue, causal progression, reversals, and chapter continuity.
- Keep quality metrics visible in API responses, metadata, logs, and frontend review surfaces.
- Use repeatable regression tests for bad samples such as all-description, no-logic, no-reversal, flat endings.

## Latest Progress
- Backend story quality guards now score scene fulfillment, dialogue state change, ending pressure, static description risk, and quality metric snapshots.
- Frontend writing desk now exposes quality summaries in chapter header/sidebar, failed-state diagnostics, version detail modal, candidate cards, and active version preview.
- Enrichment prompts are constrained to action, dialogue, consequence, and short sequel decisions instead of empty descriptive padding.
- Verified core quality tests: backend quality guards and frontend quality display regression suites pass.

Details: memory/projects/novel-generation-quality.md
