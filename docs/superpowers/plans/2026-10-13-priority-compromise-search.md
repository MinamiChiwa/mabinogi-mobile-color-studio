# Priority compromise search implementation plan

> **For agentic workers:** Execute inline with superpowers:executing-plans, using test-driven-development and verification-before-completion. Keep the current feature checkout and all existing uncommitted changes.

**Goal:** Improve missing-target compromises without sacrificing the user's region order or precise acceptance.

**Architecture:** Share interleaved region quality between scalar/vector search and actual results. Supply near-color periodic sites when a material has no exact target; every pose and compiled route remains scored with the original rules. Preserve actual best observations and let local CPU work yield progress in resumable batches.

**Tech Stack:** Python, NumPy, existing native palette/input model, Tk UI, PyInstaller.

**Spec:** The approved five-point design in this conversation and docs/research/2026-10-12-mixed-compromise-diagnosis.md.

## Global constraints

- Exact success still requires unchanged full HEX acceptance and actual screenshot proof.
- Similar regions inside tolerance release priority to later regions. Compare non-hit Delta-E in fixed 0.5 bins; bins never grant acceptance.
- Preserve disabled/two-region rules, alternate targets, 30-second startup timer grace and at-most-three-second tail.
- No game input, game-process read, item consumption, commit/push or public publication in this offline implementation.
- Build a clean local candidate, exclude personal captures/configuration and retain all user test evidence.

## Task 1: unified quality

Files: region_priority.py, native_periodic_search.py; tests: test_region_priority.py, test_priority_search_paths.py.

- [x] Add failing tests: the recorded [44.6,40.8,0] compromise loses to [14.1,34.9,1.1]; Similar satisfied high priority yields to lower priorities; 0.5 bins, disabled regions and scalar/vector match.
- [x] Run `python -m unittest test_region_priority test_priority_search_paths -v` and confirm failures before production edits.
- [x] Interleave `(not_hit, error_bin)` per region. Satisfied Similar errors use zero. All-region acceptance remains outside this tuple. Remove assumptions that its first N values are all satisfaction bits.
- [x] Run region, candidate ranking and search-path tests; change obsolete tuple-shape expectations, not acceptance assertions.

## Task 2: near-color joint sites

Files: native_periodic_search.py; tests: test_native_periodic_search.py.

- [x] Add failing real-model tests where only the lowest priority exact target exists, and where no target exists; require original-rule compromises improving the high region.
- [x] Scan each full periodic lattice for actual target sites and derive ordered, spatially diverse near sites from the same sampled colors. Exact sites remain intact. Missing regions participate in joint scale/rotation pairs through near sites.
- [x] Keep separate target/near counts and finite-coverage diagnostics. Score all scalar poses using original targets; fallback sites cannot become accepted surrogate targets.
- [x] Verify original double/triple exact fixtures, canceled/deadline paths and no-priority legacy ranking.

## Task 3: bounded CPU batches and incumbent retention

Files: native_live/refinement.py, native_live/controller.py; tests: existing native refinement/controller/recovery tests plus resumable-search cases.

- [x] Reproduce uninterrupted local-family work and require batched calls to continue the same unchanged-pose iterator rather than restart it.
- [x] Add optional caller-owned search state and slice duration; real stop/deadline checks remain active within proposal generation. Yield only between proposals, retain completed audited improvements and current display data.
- [x] Controller continues pending CPU slices without game actions; candidate admission still budgets its actual route and one checked recovery. Changed references discard the state.
- [x] Verify best actual anchor remains recoverable and simulated late execution fits; no new fixed session cutoff.

## Task 4: actual recorded route evaluation

Files: local outputs/mixed-compromise-20261013/evaluate.py and report docs/research/2026-10-13-priority-compromise-search.md.

- [x] Replay session 20261012-233913-840b41cd with original rules, initial checkpoint, geometry and saved pixels through production planner.
- [x] Require lower first-region Delta-E than 44.6436, original-rule nonacceptance, fully replayed input descriptors, recorded elapsed time and separate model/live claims.
- [x] Cover two/three regions, swapped priority, mixed Similar/Exact, absent targets, late route admission and best-result recovery with focused tests and one quick profile only.

## Task 5: local delivery

Files: build_info.py, VERIFICATION.md, build outputs.

- [x] Review final diff and required evidence. Build rc12, verify all production bytecode/assets and zero player-data inclusion.
- [x] Run frozen saved-image preflight and archive CRC check. Report finite test limits and give the candidate link.

The user approved implementation with “可以，推进吧”; no repeated design/implementation permission is needed.

## Completion evidence

Local candidate rc12: 148 production modules/assets match, frozen saved-image preflight and clean ZIP CRC pass. Original-rule production route replay improves the first two priority regions; third-region compromise is explicit. Quick and subsequent changed-scope focused results plus independent review are in docs/research/2026-10-13-priority-compromise-search.md. No new live validation or public publication. Archive SHA-256: 12f93753d4230cd0b7a85c1dcb1c589b938a7c0936bc200cfe3700453746ca91.
