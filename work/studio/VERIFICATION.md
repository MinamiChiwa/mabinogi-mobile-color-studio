# Current verification scope
> **Release status: validation-in-progress technical candidate.** 0.3.6 has code-regression evidence and a published build, but game-mechanism acceptance is incomplete. The published/latest label must not be read as proof of cross-board, cross-device or multi-region precision. See GAME_MECHANISM_VALIDATION_GATE.md before changing code or release status.

Version: 0.3.6. Policy revision: balanced-landing-single-zoom-v3. Date: 2026-10-05. This tool was developed with AI assistance.

## Automated checks

The current source regression command reports 841 tests: 823 passed, 18 skipped because optional local capture archives were unavailable, and no failures or errors. `compileall` passed. The skipped count depends on private game screenshots/OCR fixtures that are not distributed with the snapshot; earlier 794/795/797/803/823/826 figures are historical. Coverage includes candidate-route diversity, projected return budgets, countdown correction, read-only early-exit observations, single-region zoom limits, safe stop after an unmeasured pose, wheel geometry fallback (including the direct `SingleRegionIO` fallback path), adjacent-frame feature caching, separate exploration and finalization budgets, measured-best recovery, multilingual UI, display geometry and session retention. The new single-region zoom behavior and its recovery paths still await independent real-game validation.

The 2026-10-05 test audit found no unconditional skips, duplicate test methods, or core tests that can be safely removed. The 18 skipped cases are all optional fixture/integration checks for private screenshots, OCR data, or archived failures. The test files currently define 847 test methods; the archived execution class uses a class-level `SkipTest`, so the unittest run reports 841 cases. Probe, replay, and review modules remain useful for offline diagnostics and input-safety evidence, but their results are not game-mechanism validation. Shared deterministic fixtures used by the return and single-region suites now live in `test_support.py`, so those tests no longer import helpers from one another. The audit therefore keeps the full behavior suite and records the optional fixture tests instead of deleting them; a future CI job may run those fixtures as an opt-in integration profile.

Command: `python -m unittest discover -s work/studio -p "test_*.py"` (841 total / 823 passed / 18 skipped / 0 failed / 0 errors).

The controlled mechanism entry is `run_response_probe.ps1`. It is opt-in, records only observed frames/HEX/timing and never confirms, applies or cancels dye. Each timed game session must run one protocol only; outputs include mechanism_experiment.json, and an early stop preserves a partial report. These records are evidence collection, not a production response model.

The measured HEX feedback path now carries a retained local best separately from the live pose. If a better sample cannot be restored before the deadline, the service emits `atlas_best_not_restored` and the overlay labels the historical sample as not restored; it never reuses that HEX as the current game colour. Multi-region compromise notices are translated in Simplified Chinese, Traditional Chinese and English.

## Game observation

The earlier self-review package was exercised with a 1280 × 960 game window. Two single-region runs verified final game HEX values: one reached `#FFFFFF` with ΔE76 0.00 and one retained `#161414` with ΔE76 6.68 after no further improvement. In one multi-region run, an approximately 81-second atlas produced eight candidates, but only about 8.64 seconds remained and the default route was not sent. In another multi-region run, the material-color check failed during positioning; two game HEX readings were available (`#D5EBE9 / #D8415F / #B83E53`, ΔE76 11.62 / 11.37 / 8.63), but the pose was marked unreliable and movement stopped. These observations confirm reporting and fallback paths under the earlier package; they do not validate the new single-region zoom strategy or establish a guaranteed target match for every board.

A v0.3.6-rc.2 single-region run on 2026-10-03 used Exact `#000000` and finished with verified `#020204` (ΔE76 0.99); the saved best was still current. The tool reported the non-match as a verified result after a 66.23-second session. This confirms the compromise-reporting path on that run, not cross-board zoom reliability.

The single-region runs use direct board exploration and do not build a full atlas. Multi-region runs retain the full atlas route and its quality checks. Recovery and insufficient-time statuses remain visible to the user and are not treated as successful target matches. The current candidate adds a read-only fallback after ordinary build, quality, candidate or time-budget failures: it checks two consecutive game HEX readings for consistency within a bounded 3.5-second observation window and does not send mouse input. This fallback reports current colors only, without claiming a candidate, reliable pose or recovered best result.

## Saved-capture replay

A separate 1280 × 960 capture previously stopped because an adjacent image pair had only 18 default feature inliers. Denser feature extraction found 43 inliers without reducing the existing matching, geometry or atlas-quality thresholds. Reconstruction of all 48 steps passed the original checks and retained eight candidates after integer-route binding. This replay sent no game input.

Three additional saved atlases from a 1920 × 1009 client retained eight bound candidates each. Their best central maximum ΔE76 predictions were 8.39 / 10.81 / 10.80. These values are offline predictions, not measurements from new game sessions.

## Distribution checks

The v0.3.6 package is built from the release commit and includes OCR with English recognition data, the three current README files and this verification summary. Build metadata records the application version, policy revision, source fingerprint and release commit. The published ZIP contains no local profiles, session history, screenshots or development notes.

## Limits

A finite search does not guarantee an exact match, every configured tolerance, or a global optimum. Screenshot predictions may differ from game HEX readings. Integer input generation and neighborhood color sampling do not certify rotation or zoom response across every device and game-window size.

Automated display checks cover 1024 × 768 through 5120 × 2880 and 100% through 250% scaling, including negative multi-monitor coordinates. These checks do not establish full game validation on every 4K or mixed-DPI setup. The recommended game window remains 1280 × 960.

When one region is enabled, this test candidate explores the current board directly instead of building a full atlas. Exact mode prioritizes an identical HEX during its main exploration phase; Similar mode stops after two consecutive in-tolerance readings. Limited translation and small, measured zoom steps include one optional relative-range expansion. The entry scale is not known absolutely; the tool cannot guarantee never reaching a game scale limit. Unknown zoom responses end that route, and repeated limit attempts are avoided. The new zoom behavior has not yet received independent real-game validation. Multi-region searches still use the complete atlas route. Progressive multi-region capture remains experimental; no fixed scan reduction or guaranteed time saving is enabled.
