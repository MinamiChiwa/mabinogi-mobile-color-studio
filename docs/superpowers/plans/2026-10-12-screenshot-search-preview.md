# Screenshot Search Preview Implementation Plan

**Goal:** Replace the old visual-search entry with the screenshot experiment, supporting current user rules and delivering a local preview.

**Architecture:** Keep the native strategy independent. Connect a screenshot service to the existing Runner lifecycle; retain profile identifier `atlas`. Split raw observations, proposal geometry, reliable text, input control and session orchestration into focused modules.

**Spec:** `docs/research/screenshot-search-preview.md`

- [x] Add sample/geometry/text modules with tests for raw extreme colors, arbitrary targets, periodic pairs/triples and actual text.
- [x] Add controllable session runner with measured input, best recovery, same-round retry, remaining-time policy and no apply/cancel.
- [x] Connect the old visual entry and existing main/overlay events; update three-language text and tutorials.
- [x] Run focused and quick regression, build a separate preview, inspect startup and read-only game preflight, preserve verification and package paths.

Validation commands use the existing `project/.venv/Scripts/python.exe`; exact tests are added with their implementation. Source lives on branch `codex/screenshot-search-preview`, all research captures stay outside the distribution.

Delivered local preview: `C:/Users/47932/Desktop/ColorStudio-ScreenshotPreview-0.4.3rc1/ColorStudio.exe`. Existing desktop tool and its data were preserved; only persistent configuration was copied to the preview and its strategy selected as `atlas` (Screenshot Search). No public release or push.

Focused:43 passed. Quick:649 selected,585 passed,64 skipped,zero failures/errors. Frozen read-only OCR correctly read `#FDEAEF / #F1F1F1 / #EEEBE8` from saved full-board capture. Source read-only game preflight captured an occluded ordinary client; this is not a live precision check. Full verification and limits are in the preview report.
