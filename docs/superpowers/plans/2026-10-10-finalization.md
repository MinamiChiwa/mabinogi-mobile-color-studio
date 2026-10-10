# Color Studio Finalization Implementation Plan

**Goal:** Deliver a published version with smooth resize, automatic preferences, named presets, current text, meaningful fast regressions, region priorities, and repaired screenshot timeout handling.

**Architecture:** Keep the existing native/visual search and input validation. Share priority ordering between observed and predicted scoring. Keep UI persistence and named presets in independent modules; keep fixed card content inside a resizable viewport. Split test entry points by current product contracts and optional historical experiments.

**User authorization:** Implement and publish requested by the user on 2026-10-10. No new dye round, no automatic dye confirmation. New priority requirement and reported rc16 similar-mode failure are part of this delivery.

## Constraints

- Exact mode accepts only identical six-digit HEX; Similar uses each user's tolerance.
- Search first prefers all enabled regions accepted. When none is available, ordered region satisfaction and color errors determine compromises consistently.
- User-selected priorities are a unique order across three cards; disabled cards do not influence scoring.
- Legacy API rules without priority retain balanced ranking. Existing UI profiles migrate to the visible default order 1, 2, 3; users can change it and save it in the draft/preset.
- Preserve F9, identity, focus, actual deadline, full route audit and measured return budgets.
- Passive timer OCR failure cannot invalidate valid HEX reads or masquerade as whole-session expiration.
- Save draft settings automatically, including temporarily incomplete color input; named presets require valid target rules and never silently replace another preset.
- Keep personal data, captures, runtime paths and sessions out of Git and distributable packages.

## Tasks

- [ ] Resize: reproduce real Tk reflow; fix per-pixel card resizing and redraw suppression; verify same-breakpoint counts, 1/2/3 column transitions, density and screenshots.
- [x] Similar failure: audit original session and frame; introduce local read-timeout behavior and recovery while retaining real deadline/F9; verify original frame plus controller regression.
- [x] Persistence: independent draft/preset module with atomic write and legacy profile migration; autosave after edits/close; named save/load/rename/delete/custom editing dialog; include presets in data relocation.
- [x] Priorities: canonical order validation and shared scalar/vector ranking; propagate through native seeds, route/refinement/recovery and visual candidate generation/selection; test all-accepted dominance, priority swap, disabled regions, exact/similar/alternatives, old-profile compatibility.
- [x] Text: update tutorial, fallback annotation, material limits, multi-color limitation and priority/preset guidance in Simplified Chinese, Traditional Chinese and English; replace stale README sections.
- [ ] Tests: default fast current contracts, release with end-to-end search/visual smoke, explicit full/research historical checks; report counts/time and durations; retain important coverage.
- [ ] Review and package: scope review, current suites, isolated UI resize/dialog screenshots, source compilation, bundle/source hash comparison and packaged smoke without game inputs.
- [ ] Git/release: preserve existing local and remote history, sync current project to clean repository, inspect staged contents, commit and push, tag version, upload complete portable ZIP and current release description.

## Evidence

Use outputs/native-integration/verification/finalization-2026-10-10 for source baseline, audits, tests, UI screenshots, packaging manifests and publication receipt.
