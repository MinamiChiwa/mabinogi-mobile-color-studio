# Native Dye Tool Implementation Plan

> Execution: sequential in the existing non-Git project snapshot. User requested direct implementation; no new design approval or subagent delegation is needed.

**Goal:** Connect verified native palette reading and bounded input/HEX feedback to the existing ColorStudio application for user-supplied rules.

**Architecture:** Package the validated research dependency closure as `work/studio/native_live`, keeping numerical modules already in studio authoritative. Add an injectable user-goal controller and a Runner service with explicit session ownership. Expose native and existing visual search in the existing UI; never silently change strategies during a session.

**Tech Stack:** Python3.12, CustomTkinter, NumPy/OpenCV/Pillow, Tesseract, read-only Win32 process API, existing Game SendInput, PyInstaller.

**Spec:** `docs/research/native-dye-handoff-2026-10-10.md`; latest user authorizes full implementation, overriding its earlier A/B-only recommendation.

## Global Constraints

- No automatic dye entry, final confirmation, process writes, injection, or remote calls.
- No new item-consuming session without explicit authorization; arm the local script first.
- Unknown build, changed session/window, unreadable HEX/timer, invalid response or inadequate time stops execution.
- Reuse exact CPU arithmetic and integer descriptors; enabled/exact/alternatives/tolerance remain user-owned.
- Every input uses a fresh checkpoint/HEX pair and revalidation; replan after actual response.
- Preserve existing visual strategy as an explicit choice. Do not fall back after native input.
- Local build is a candidate, not publication or general precision certification.

## Tasks

- [x] Core package: failing import/asset and saved-session endpoint tests; mechanically migrate research dependencies, relative imports and assets; remove fixed research paths; resolve game build files from selected process; bounded output stays in session directory. Run package tests.
- [x] User goal service: failing tests for real rules, exact/tolerance/already-matched/no-candidate/time/cancellation/mismatch; implement injected controller with max4 gestures and checkpoint feedback. Add Runner service with preflight/manual-entry wait and no sender in preflight. Reproduce latest saved mixed target.
- [x] Runner and UI: failing native dispatch/lifecycle/state tests; wire explicit native/visual selection and result events into existing UI/overlay/history. Add translations and maintain manual final confirmation. Run focused UI and Runner tests.
- [x] Candidate build: include packaged assets in build/source identity; complete project regressions and compile; run zero-input native preflight; build to a new output directory and verify packaged dependencies. Actual UI used for two user-goal sessions; native app screenshot automation was unavailable. Record validation and remaining live acceptance. Do not publish or auto-enter dye.

## Latest Validation

0.4.0rc2: 1036 project tests,1018 passed,18 skipped,zero failures/errors;33 native integration tests. Frozen-package preflight0input passes. Two authorized real candidate UI sessions recorded under `outputs/native-integration/verification`; both use actual user three-black exact rules,0input/no matches. Test1 startup deadline fixed;test2 completes finite search without accepted route. New arbitrary-target input positioning remains unverified. No additional dye session authorized.

## Verification Commands

Run commands with project `.venv/Scripts/python.exe`:

```powershell
python -m unittest discover -s work/studio -p 'test_native_live*.py'
python -m unittest discover -s work/studio -p 'test_*.py'
python -m compileall -q work/studio
python work/studio/native_preflight.py --help
```

Build uses `COLOR_STUDIO_DIST` pointing at a new candidate-only directory, followed by packaged preflight; existing release/data are not overwritten. Git commits do not apply to this checkout without `.git`.
