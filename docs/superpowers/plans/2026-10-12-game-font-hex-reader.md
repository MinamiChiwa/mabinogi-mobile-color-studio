# Game-font HEX reader implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement the authorized plan inline. Preserve existing uncommitted work and recorded sessions.

**Goal:** Improve fixed-game HEX and countdown reading using the game's actual font resources and independent screenshot validation.

**Architecture:** Resolve the dye text's font variation 5 and its runtime font stack from unpacked resources. Generate a small 17-character reader asset from the actual glyphs with rendering variations, then evaluate held-out screenshots before enabling a production path. Native expected HEX and swatch RGB never supply text characters.

**Tech Stack:** Python 3.12, NumPy/OpenCV, local Unity asset parsing, existing screenshot/native frame collectors.

**Spec:** User-approved conversation design: font-derived samples across sizes/scales/fractional pixels, real screenshot calibration, independent historical validation, no new dye item.

## Global constraints

- No live game input or new consumable session; use saved files.
- Preserve exact six HEX digits, actual two/three-region layouts and user target tolerances.
- Record unknown or ambiguous text without claiming target success; retain existing independent fallback.
- Preserve cancellation and real session deadline; no new image-age abort gate.
- Countdown uses the same font tracing/sample/held-out validation flow; retain the initial 30-second OCR grace and at most 3-second tail.
- Separate development font/corpus resources from the portable package; bundle only validated small inference assets.
- Build a new local candidate only after source/replay/package checks; no remote publication.

## Tasks

1. **Trace actual font resources.** Parse package index dependency sets and paths; follow locale font stack and each dye HEX/countdown variation to `MMFontAsset` and glyph data. Save source hashes, control font size/style/spacing and attribution evidence. Read source game files without modification.
2. **Generate and evaluate samples.** Decode `#0123456789ABCDEF` glyphs, simulate observed sizes and fractional placement, and calibrate against separately labeled training captures. Keep session-separated test captures; report correct/unknown/wrong and time separately. Do not enable a font reader that regresses reliable existing evidence.
3. **Implement the minimal reader with failing tests first.** Tests cover known A/8 conflict, missing/extra characters, ambiguous font matches, various actual sizes and real stop/deadline. Isolate pure text reading in a focused module with no expected native HEX input. Preserve source/diagnostics and cached-card semantics.
4. **Integrate and verify.** Connect validated reader to both actual frame pipelines where appropriate; keep final independent checks and conflict evidence. Run affected text/cache/geometry/controller tests, one quick profile and independent code review. Re-read saved failure and held-out images through the production IO.
5. **Document and package.** Record font tracing, training/held-out split, limitations and measured results. Produce an independently verified local candidate without player data, game source fonts or private fixtures.

Execution is already authorized by the user's “推进吧”; routine implementation and read-only research do not require renewed approval. Mark findings and scope changes in the research report rather than silently substituting another font.

## Execution record

- Tasks 1–3 complete: actual locale stacks/prefabs traced, both compression paths decoded offline, all 17 Bold glyphs rendered into a small inference asset; failing real A/8, slow timer and dim-leading1 tests observed before their fixes.
- Task 4 complete: both production backends integrated; 39 real HEX plus 20 real countdown samples correct, session-separated holdout 33/16 correct. Quick passed 714 with 14 whole skips; later timer review fix passed 49 covering checks. Independent re-review found no remaining important issue. Early 30-second grace and 3-second tail unchanged.
- Task 5 complete: local rc10 build,148 module/asset source checks, frozen actual saved-frame preflight and clean ZIP CRC all pass. Preflight reads three correct HEX and95 seconds with0 inputs. No public publication, new game input or new dye item. Archive:project/outputs/server-preview-0.4.3rc10/ColorStudio-0.4.3rc10.zip.
- The user's subsequent actual-color label update bug is recorded separately in docs/research/2026-10-12-live-color-display.md and included in a subsequent local rc11 candidate.
- Scope ruling: use deterministic font-derived nearest-glyph recognition rather than retraining a general OCR language model. The limited alphabet permits fast pixel-only inference; existing independent OCR remains for unknowns. This is supported by the user's approved font-sample workflow and the held-out measurements. Arbitrary font/theme accuracy is not implied.
- Workspace ruling: continue on the existing authorized feature checkout to preserve the extensive uncommitted native/screenshot work. No reset, branch deletion, new worktree or cleanup of historical evidence.
