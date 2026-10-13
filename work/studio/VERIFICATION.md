# Release preparation 0.4.4 (2026-10-13)

- Screenshot Search is the default. Existing preferences migrate once; colors, tolerances and priorities are preserved. Explicit memory access is labeled as higher risk in five languages. Update health staging does not modify player settings before commit.
- Includes mixed exact/similar screenshot search, measured refinement and best-result recovery, and deduplicated final recovery reads. The rc1/rc2 tests are live user trials; saved-image replays are separate evidence. No guarantee of multiple exact matches.
- Single-region Screenshot Search checks the current view and each new exploration view immediately, without building or fully scanning a periodic palette. Only the enabled region's HEX is decoded. Failed trials retain exploration progress and reserve best-result recovery time; a confirmed target ends exploration. Saved-image replay and offline regressions are not a new live-match claim.
- Final single-region focused regression: 188 passed, no skips, failures or errors, 58.33 seconds. The new local package has 154 source-matching production modules; frozen saved-image preflight verified three HEX values and a 109-second timer with no game input or memory access.
- Live frozen-app single-region test reached #000000 in 3.67 seconds and independently confirmed it at 3.92 seconds, with 2 positioning inputs and about 116 seconds remaining. No full palette sampling or game-memory reading occurred. One dye was consumed; the result was canceled without applying it. This proves that session, not every target or material.
- Final review added a gated actual-HEX check when exploration already places a match beneath the excluded marker; swatches only request verification and never certify a match. Eleven single-region tests pass; the original live frames also confirm #000000 in a separate latest-source offline replay.
- Latest focused checks: 189 passed, no skips, failures or errors, 67.53 seconds. The first 858-test release run retained 3 known missing-history skips and 5 errors from an intermediate single-region revision; every error is covered by the corrected final focused run. The original report remains available, and complete historical release evidence is not claimed.
- The rc2 endpoint report is investigated and the user has authorized publication after this live test. Current verification is recorded in docs/verification-release-0.4.4.md.

# Release 0.4.3 (2026-10-13)

- Five UI/readme languages: Simplified Chinese, Traditional Chinese, English, Japanese and Korean. Taiwan is supported; Korean and Japanese client support remains in testing. Language changes preserve HEX values and saved rules. Real Tk layout/switching checks passed for narrow and wide windows; update dialogs and helper error messages include Japanese/Korean.
- Includes rc12 priority/joint-compromise search, game-font HEX/countdown recognition, continuous measured-color display, screenshot fallback and server selection described below. No additional live dyeing or consumable use in this release task.
- One release selection ran 806 tests. An offline worker wait timed out once; isolated reruns and the final 34 focused checks passed. Restoring existing minimal local fixture groups and rerunning all skipped/failed cases yielded 803 passed, 3 historical missing-fixture skips, zero remaining failures/errors across the selected contracts. The missing cases are two original rc16 similarity captures and one supplemental OCR archive. Full historical release verification remains incomplete; the skip allowlist was not expanded.
- Package documents use paths accepted by the actual 0.4.2 updater. Old preflight CMD/window-check files are removed from the distribution. Offline archives start with UPDATE-ONLY and are verified with the same signed manifest and blobs as online updates. Full package/module checks and signed upgrade evidence are recorded in docs/verification-release-0.4.3.md.
- Source tests, restored original fixtures and report files stay local where applicable; no user settings, captures or original game fonts are distributed. Detailed historical entries below retain their original scope.

# Local preview 0.4.3rc12: prioritized joint compromises (2026-10-13)

- Full acceptance remains first. Compromises interleave each user-priority region's hit status and 0.5 Delta-E bin; satisfied Similar regions release priority to later regions. Bins never relax exact HEX or tolerance. Scalar/vector, native routes, screenshot proposals and actual-best retention share this order and Delta-E tie metrics.
- Missing exact targets receive near-color sites across the complete sampled tile, with color and spatial diversity. Near pools expand from 32 through 128/512 to all sampled sites if time permits; old candidates survive expansion or deadline. Every joint pose and input route is independently evaluated under original rules. No continuous-space exhaustion or new live-match claim.
- Local refinement resumes the same CPU iterator in approximately two-second batches without extra input, capture or memory access. Full audits may cross a batch. Changed/accepted references and errors clear pending state; real cancellation/deadline checks remain active. Best-result recovery, 30-second startup grace and three-second game tail remain.
- Production planner replay of rc11 session 20261012-233913-840b41cd: old measured Delta-E 44.6436/40.7514/0; new full-route prediction 8.4961/0.5493/33.8928, colors E7E7E7/020202/505050. Twelve modeled gestures total 5.426 descriptor seconds; CPU planning 23.422 seconds. No new live input or guarantee that all three can be close simultaneously; priority 1 and 2 intentionally win this tradeoff.
- Quick: 741 selected, 727 passed, 14 whole skips, zero failures/errors, 173.389 seconds. Later near expansion verified by 56 related tests: 54 passed, 2 optional historical skips, 19.622 seconds. Additional overlapping score/recovery/UI/language checks passed. A frozen-clock tail test was isolated from repeated global solving; production budgets and endpoint checks remain unchanged. Independent review found and verified the pending-state cleanup, then found no remaining important issue in the reviewed scope.
- Report: docs/research/2026-10-13-priority-compromise-search.md. Local rc12 only; no new dye item, game-process read, public publication or full-release verdict.
- Frozen rc12: all 148 production modules and assets match source; no player data. Saved-image preflight reads F27233/EAD310/72514A and 95 seconds with zero input/no game memory. Source fingerprint: `db945c4209c38b1d53fe1e4fd7ccd43d531eec4456e11a05f3fe8c57c53e8c40`.

# Local preview 0.4.3rc11: continuous actual-color display (2026-10-12)

- Every completed native readback now publishes its measured client HEX to the main cards: full screenshot checks, planning references and intermediate route checkpoints. The service previously dropped native_observed and full observe had no uniform update. Predictions never populate this event; it does not change target acceptance, screenshot proof or saved-result history.
- Current-color updates reuse existing observations without extra OCR, capture or game input. Two-region boards preserve the unavailable third card. Screenshot search retains its existing scene updates.
- Four targeted chain/label tests passed after reproducing the missing controller events, lost service events and unchanged UI labels. The 49 covering controller/service/planning/real-Tk/completion/retry checks passed in 63.331 seconds. Font/timer functionality and the prior 714-pass quick evidence remain; unrelated full history was not repeated for this display change.
- Frozen rc11 verification matched all 148 production modules and bundled assets, with personal data excluded. Saved-image preflight returned the three recorded HEX values and 95 seconds with zero input and no game memory access. Source fingerprint: `cda6c9b0dbaa3d2ab08714cfd5211e21b2e8bfa9182d1943d4b2fc870bb0404f`.
- Research report: docs/research/2026-10-12-live-color-display.md. Local rc11 includes the completed rc10 game-font workflow. No new consumable/game input or public publication.

# Local preview 0.4.3rc10: game-font HEX and countdown (2026-10-12)

- All 17 original Bold MSDF glyphs were decoded offline from installed font packs, with fractional placement/size variants and prior screenshot calibration. Both native and screenshot strategies use complete multithreshold text. No native HEX, target, swatch or previous seconds supplies characters. Original source font packs and private captures are excluded from the package.
- Actual saved 79–113px cards:39/39 correct; actual saved countdowns:20/20 correct, including the original117→17 failure, narrow-leading105 and Korean9. Session-separated new holdout:33/33 HEX,16/16 timers. Four declared resized samples also pass. This is finite historical evidence, not a universal OCR accuracy or new live dye claim.
- Timer location now includes the actual narrow leading1 and antialias margin. A leading-zero string cannot become a short countdown. Initial30-second grace, real cancellation/deadline and at-most3-second tail remain. Full screenshot/swatches/region binding and independent conflict fallback still apply.
- Compiled equivalent template distance avoids large per-character tensor allocations. Saved-sample fast means approximately0.10s per HEX and0.03s per timer, excluding capture/layout and cold preparation.
- Quick:728 selected,714 passed,14 whole-test skips,0 failures/errors;19 skip events include5 subtests. Execution129.194s,total137.192s. No full release verdict. Subsequently, review found a dim-leading1 locator omission; it was reproduced and fixed using170 digit detection with a complete icon-right crop. The final11 recognition cases pass, including that failure and scaled Korean single-digit text; independent re-review found no remaining important issue. Earlier focused run had a timing-sensitive archived6-second route search fail once, then pass independently in4.086s and in the final41 boundary suite, without a production budget change.
- Production ProjectProbeIO double-frame saved-failure replays confirmed all3 codes, first1.50s/warm0.58s; no live capture/checkpoint cost included. The final locator fix was verified by the covering tests and fresh full59-sample evaluation, not by repeating unrelated full regression.
- Source, font, corpus and evaluation evidence:docs/research/2026-10-12-game-font-hex-countdown.md and local project/outputs/game-font-20261012. Independent review and clean package checks are recorded with the local candidate. No GitHub publication or game input was performed for this task.

# Local preview 0.4.3rc9: conflicting HEX reread (2026-10-12)

- The second rc8 session reached its endpoint after three inputs, then repeatedly failed independent color merging. All three saved screenshots print#72514A; the single-pass native OCR path consistently read#725148. CPU/client colors and poses agreed. This is different from the fixed rc7 screenshot-age gate.
- Only nonempty conflicting cards get an additional independent multithreshold text read. Expected/native digits never enter that reader; the original native <=3 swatch threshold remains. Missing/conflicting text never becomes screenshot success through native fill. Wrong card cache entries are removed, and only independently confirmed text is cached. Normal matched cards retain the fast path.
- Conflicting decode evidence is saved even when merging fails. Optional diagnostic OSError cannot overwrite F9 or a real deadline. Two/three-region layout, DPI/session binding, unchanged user rules and rc8 actual-state age revalidation remain active.
- The three actual failure images now pass two production ProjectProbeIO double-frame file replays with all three screenshot HEX values confirmed; first2.719seconds, warm1.328seconds. File timing does not include live game capture/checkpoint costs; no new inputs or dye item, no target success claim.
- Focused decoder/startup/cache/text checks:44 passed in22.517seconds. Final conflict/two-region/DPI/slow-close checks:27 passed in5.399seconds, including a newly fixed diagnostic-write boundary. Counts overlap.
- Quick:713 selected,699 passed,14 whole-test skips,0 failures/errors;110.964seconds execution,118.940total.19 skip events include5 subtests;5 desktop checks omitted. It loaded before the final optional diagnostic-write catch; the final boundary change passed the subsequent focused suite. No full release verdict.
- Independent review found no remaining important issue. Report:docs/research/2026-10-12-rc8-hex-conflict.md. Local candidate0.4.3rc9 uses conflicting-hex-reread-v1; no GitHub publication or new live dye validation.
- Frozen build exited0;147 production modules match source bytecode, assets agree and no user data/fixtures are present. Saved-failure-image preflight independently reads all three correct HEX values with0input/no game memory. Source fingerprint:0cb866398bb81122b0ff140eb962afd021b10d514137522c1915377b91069c84. This is dependency/file verification, not new live controller acceptance.

# Local preview 0.4.3rc8: staged color verification (2026-10-12)

- Saved rc7 startup failed before planning/input: its last screenshot was 5.422 seconds old after an 11.922-second complete observation. Bound CPU/client colors agreed; the internal five-second image-age gate caused the stop.
- Initial and moving-route reference reads now validate the actual visible two/three-region layout without paying final HEX/timer OCR. Native colors remain explicitly unverified screenshot evidence. Initial apparent hits, stationary compromise endpoints and final moving endpoints still require full independent screenshot reads.
- Slow decoding triggers an actual checkpoint reread. Only unchanged binding/pose/colors/geometry/mapping can provide proof bound to the original two capture timestamps. This proof also supersedes the pure fifteen-second plan-age cap; future plans, changed references/rules, capture order and actual route budgets remain checked. Closing a newly revalidated endpoint avoids duplicate OCR.
- Focused layout/controller/retry/two-region/DPI checks:109 passed in27.189 seconds. Latest slow-plan/package/recovery checks:17 passed in29.158 seconds, including the formerly failing sixteen-second decoding case. These counts overlap. Old fixed-two-action expectations now check the complete selected/sent route and confirmed final colors.
- Final quick without desktop checks:706 selected,692 passed,14 whole-test skips,0 failures/errors;101.497 seconds execution,109.584 total. Nineteen skip events include five subtests; five desktop checks were omitted. This is not full release validation.
- Real saved startup-image layout decoding took0.125/0.110seconds and entered the actual planner; original screenshot timestamps reproduced the old error. Saved-file timing excludes live capture/checkpoint overhead. No new dye session, process read or game input; no prediction is represented as a new live precise hit.
- Frozen package:147 production modules match source bytecode; resources match and personal data/fixtures are absent. Saved-image screenshot preflight found all three recorded HEX values with0input/no game memory access; this checks that image and bundled screenshot-reader dependencies, not the native controller's live completion. Source fingerprint:7231c023a35de09e865787145bbc804ddd8b5a6b26f3eca7850ae8d6f02080fc.
- Report:docs/research/2026-10-12-startup-color-verification.md. Candidate:project/outputs/server-preview-0.4.3rc8/ColorStudio. No GitHub publication.

# Local preview 0.4.3rc7: destination and rotation repair (2026-10-12)

- The rc6 first rotation had a 3.847992-degree residual. Missing the radial-to-arc sample reproduces the observed angle within 0.000435 degrees and position within 1.13e-6. The actual game sampling sequence was not recorded; this is mechanism evidence, not exact frame reconstruction.
- Grouped input holds the radial transition for 90ms total. A real-sender timing simulation at20FPS previously lost about3.85/7.59degrees; four tested frame phases now remain within0.05degrees. This is not new live rotation validation.
- The controller corrects the originally selected endpoint from measured feedback before treating a degraded suffix as destination exhaustion. A complete file replay with the user's actual first response preserves two exact whites and third Delta-E<=10. Future responses and screenshots in this test are simulated, never advertised as measured game results.
- Correction searches the selected joint endpoint colors internally, then independently replays/rescores every output under the unchanged user rules. Final-gesture drift now also preserves the two exact whites; the formerly failing case passed three consecutive isolated runs. Disabled regions and Similar tolerance remain unchanged, and a recovered compromise never becomes an exact user-goal success.
- Window activation/restoration now precedes geometry preparation; the separate startup failure had a minimized window and zero client size. Read-only preflight does not activate the game.
- Final quick without desktop checks:697 selected,683 passed,14 whole-test skips,0 failures/errors,99.780 seconds execution (106.677 total);19 skip events include5 subtests. Final focused route/input/retry/two-region/window/DPI checks:93 passed in32.684 seconds. Restored private stage68/user_black fixtures let historical controller and DPI checks run; five desktop checks remain omitted. This is not a complete release verdict.
- Frozen package:147 production modules exactly match source bytecode; assets match and personal data/fixtures are absent. Saved-image startup confirms OCR and3-region layout with zero input. On this initial frame, both rc6 andrc7 screenshot preflight miss one HEX and confuse B/8 in another; identical outputs are dependency/load evidence, not precise screenshot-color acceptance.
- Report:docs/research/2026-10-12-rc6-route-and-rotation.md. No new dye item, live game input or public publication. Triple-white feasibility is still not established.

# Local server selection preview 0.4.3rc3 (2026-10-12)

- Added Taiwan/Korean/Japanese selection beside the game-window selector. The saved server filters automatic/manual window discovery, clears stale bindings on change, and rejects mismatched registered client fingerprints before input. Precise Search remains the default; the UI no longer requires a separate Japanese preflight entry.
- Replayed two saved Korean 1376x990 frames without game access or input. Native layout and all three HEX values matched the recorded checkpoints; report: `project/outputs/kr-data5-audit-20261012/saved-frame-recheck.json`.
- Focused server-adaptation tests: 46 passed. Quick profile: 687 selected, 623 passed, 64 skipped for unavailable historical/desktop fixtures, zero failures/errors, 71.519 seconds total. This is offline evidence; Japanese live dyeing response remains unverified.
- Fixed release ownership for `SCREENSHOT_PREVIEW.md` and the consolidated `docs/server-selection.md`; removed the obsolete Japanese-only launcher copies from the new package path. No GitHub publication or consumable use in this verification.
- Frozen package: `project/outputs/server-preview-0.4.3rc3/ColorStudio`; `ColorStudio.exe` SHA-256 `ebfb51db6b5fdf044dda5b027f2ebef5781424e939d9fe14dd19db51a61cb9eb`, updater SHA-256 `c2ef98de5ecc53b6da737375747c0be1c89d40c1a93e6b8317b6063bff563a46`. Packaged screenshot preflight on the saved Korean frame returned 3 regions, matching HEX values, OCR available, and `input_count: 0`.

# Local preview 0.4.3rc2: recorded feedback repairs (2026-10-12)

The rc1 recorded countdown 39/30/19 and complete final HEX now read correctly. Missing timer bars cannot corroborate a shortened deadline. Actual HEX requires two complete agreeing text reads; O is normalized to zero without filling missing digits or truncating excess digits. Recorded cards pass at 0.5, 0.75, 1, 1.25, 1.5 and 2 scales.

Return corrections use marker-span pixel precision and directly register to the measured best frame. Zoom, candidate and paired-wheel refinement admission includes the projected cost to restore that result. Unknown poses do not imply a free return. A short retry reuses samples/current visible data, and unaffordable candidates do not suppress affordable alternatives. Early 30-second OCR grace and the three-second game tail remain.

Final focused verification: 60 passed, including isolated Tk controls/retry and runtime translations. Independent read-only review found no remaining blocker. Feature caching produced identical matrices on six recorded registrations; lossless PNG saving preserved decoded pixels. The package and bounded quick report are recorded with the rc2 output. This is offline/saved-image validation, not a new live dye round or three-white success proof. No consumable or game input was used; no GitHub publication was performed.

Final quick: 666 selected, 602 passed, 64 skipped for missing historical private fixtures, zero failures/errors; 44.408 seconds total. The 75 skip events include subtests. This is not full release verification. Report: `project/outputs/screenshot-preview-0.4.3rc2-quick.json` in the local development workspace.

The rc2 build exited 0. Frozen saved-image preflight identified three regions, 19 seconds and #FFFFFF / #CBCBCB / #B9E0F0, with zero inputs and no game memory access. Packaged source hash matches current production sources: `16ae841bad5799c8fe9d85daa1cbf7a6abccfb61d3111c6cbdccaaad883d4f96`. Output: `project/outputs/screenshot-preview-0.4.3rc2-frozen-final` in the development workspace.

Independent desktop rc2 launched successfully: correct version in the main-window title, input idle and responding. Only the prior player profile was migrated; rc1 sessions remain in their original directory and the clean build contains no player data. No game action was started.

# Local preview 0.4.3rc1: screenshot replacement (2026-10-12)

The old visual entry now connects to screenshot search. Native search remains independent. Rules, alternatives, priorities, two/three actual regions, exact/similar matching and same-round retry are retained. Screenshot RGB is only a planning sample; results require agreeing actual HEX reads. No automatic dye entry, apply or cancel action exists in this backend.

Fresh focused verification: 43 checks passed, including isolated Tk UI/retry/control recovery. Quick profile: 649 selected, 585 passed, 64 skipped, zero failures/errors, approximately45seconds. Archived private fixtures are absent; 75 skip events include subtests. This is local preview verification, not full release or new consumable validation. Package/startup evidence is retained with the local preview output.

Read-only source preflight captured the current400x735 client at96DPI with zero input; it was not foreground, so it does not validate live board accuracy. The earlier five-item screenshot experiment did not meet the three-region >=253/channel criterion. No further dye item was consumed for integration.

# Release 0.4.2 — labeled retry and signed update bootstrap (2026-10-12)

- Retry search is explicitly marked Testing only in Simplified Chinese, Traditional Chinese and English. The actual button fits and remains accessible at100%,150%,200% scaling in all three languages. Search behavior is unchanged by this label.
- Release regression:678 selected,675 passed,3 skipped,zero failures/errors;195.387 seconds total. Two required original rc16 similarity captures and one supplemental historical OCR archive are unavailable, so release_complete remains false. Publication does not convert those missing checks into passing evidence. Korean live dye/input validation remains pending.
- Update asset ownership now includes the two shipped Korean launchers and guide, while rejecting arbitrary scripts and player data.31 focused asset/manifest/translation checks passed. Independent review found no blocker in this release diff.
- Official bootstrap uses an Ed25519 production public key. The private key is held outside source/packages in current-user Windows DPAPI storage.0.4.1 users upgrade manually once; subsequent signed file updates and offline imports preserve settings and records.

Release notes compare GitHub v0.4.1 with v0.4.2. Package, signatures and upload checks are recorded in `docs/verification-release-0.4.2.md` and local release evidence. No game input or dye consumable was used in this release preparation.

# Local candidate 0.4.2rc13 — retry retention and measured route admission (2026-10-12)

- The recorded retry had 63.313 seconds left at admission and 32.797 after reset/search. Its selected ten-action route needed about 34 seconds with measured input/readback, despite a 9.2-second model estimate. This was a route-budget failure, not a blanket inability to retry with 60 seconds left.
- Retains the prior best measurement, prepares a checked return before zoom-out, and reserves its actual actions/execution plus bounded preparation. Missing wheel corrections cannot spend that allowance. Normal same-epoch route behavior is preserved; no new game-end idle reserve is added.
- Affordable exact candidates continue after rejected exact candidates. Return completion requires independently verified actual colors; F9, changed sessions and unknown input cannot claim restoration.
- Final quick:619 selected,618 passed,one optional historical OCR skip,zero failures/errors;90.751 seconds total. Independent final retry/protected review:75 tests passed with time, quota, correction and rejected-exact boundary reproductions. Full release/live-round verification remains incomplete; two original rc16 similarity captures are still absent.

Report:`docs/verification-retry-retention-2026-10-12.md`. No live input, new dye item or public release in this change.

# Local candidate 0.4.2rc12 — Korean validation integration (2026-10-12)

- Fingerprint-bound Korean palette/marker/input/getter parameters and shared Unity/managed layouts are connected. Normal launch retains diagnostic capability; an explicit known-build validation launch permits the complete existing input/search/retry workflow without claiming input verification.
- Fresh Korean read-only preflight passed:1280x720 client, legacy mouse, identity viewport, exact fingerprints; dye class marker repeated consistently, zero input and zero heap scans. Active dye pixels and gesture response remain unverified.
- Quick baseline:606 selected,605 passed,one optional OCR skip,zero failures/errors;85.786 seconds total. Further focused cases cover Korean-only preflight, wrapper drift and independent scan absence. Package/preflight evidence is saved separately.
- rc11 final lossless regression after ndarray-subclass repair:597 selected,596 passed,one optional skip;65.122 seconds total. Independent review found no remaining issue. No new dye item or public release.

Reports:`docs/server-adaptation/2026-10-12-kr-integration-report.md` and `docs/verification-lossless-speed-2026-10-12.md`.

# Local candidate 0.4.2rc11 — lossless computation speedup (2026-10-12)

- Pure canonical RGB/LAB distance reuse is bounded and owns immutable target tuples; mutated alternatives are re-evaluated. Replay float32 vectors retain checks and buffer ownership while avoiding redundant float64 conversion.
- Saved route and 80 randomized references: complete replay trace, diagnostics, endpoint and guard counts equal the prior implementation. 816 exact/LAB colour-pair results are identical. Fixed microbenchmarks: replay 1.18x; repeated colour distances 4.02x. These are not whole-round speed claims.
- Quick: 596 selected, 595 passed, one optional OCR fixture skip, no failures/errors (75.701 seconds total). Focused final contracts: 60 passed. A stale recorded compromise test now verifies the existing superior-prefix retention policy instead of requiring a worse suffix and unnecessary return; no production strategy was changed for that test.
- No live game input or public release. Required historical rc16 similarity evidence remains missing.

Evidence: `outputs/native-integration/verification/lossless-speed-2026-10-12/`; report: `docs/verification-lossless-speed-2026-10-12.md`.

# Local candidate 0.4.2rc10 — continuous retry zoom (2026-10-12)

- Same-anchor downward retry wheels share one preparation and one final complete scale/color observation. Windows still receives individual -120 events at the established 18 ms cadence, with one 100 ms settle at the end. Ordinary route input validation remains unchanged.
- Actual scale controls correction after missed events; an unconfirmed minimum or input outcome cannot start a new search. F9, focus, geometry and deadline checks remain active at every notch. Search coverage, priorities, best-result retention, initial OCR grace and the three-second tail are unchanged.
- Quick: 591 selected, 590 passed, one optional historical OCR fixture skipped, zero failures/errors; 70.109 seconds total. Continuous retry coverage includes two/three regions, a lost last notch, unknown input, Windows per-notch cancellation and unchanged standard wheel bounds. Related controller/recovery/IO suites: 100 passed before the final correction addition; counts overlap.
- Saved-session float32 replay has the same endpoint with grouped or individual notches. Measured-cost simulation reduces reset from 17.153 to 7.742 seconds; this is an estimate, not a new live-round measurement. No new dye round or public release. Original rc16 similarity fixtures remain missing, so no complete release verdict is claimed.

Evidence: `outputs/native-integration/verification/retry-continuous-2026-10-12/` in the development workspace. Details: `docs/verification-retry-continuous-2026-10-12.md`.

# Close/startup race fix (2026-10-12)

- A queued close during CTk's first mainloop titlebar update caused a destroyed-WM exception. App now enters the Tk event loop without that nested pump, cancels pending callbacks on shutdown and avoids duplicate destruction. A fresh-process regression and three frozen EXE close timings pass with exit 0.
- Interrupted update with a missing cryptography file recovers through the embedded-hash external helper using only stdlib; all program/user-file hashes were verified.

# Local candidate 0.4.2rc9 — update bootstrap and retry focus (2026-10-12)

- Main-window GitHub/offline update controls are implemented in Simplified Chinese, Traditional Chinese and English. Checks do not download/install; search/picking/window selection pause downloads and block installs.
- Updates use cryptography Ed25519, signed ownership, SHA-256, bounded resource bundles, an independent onefile helper, same-volume backups and write-ahead recovery. A frozen test upgrade committed successfully and a broken target executable rolled back; application/user/unknown-file hashes were verified.
- Native retry now activates the bound game before requesting reset; activation failure keeps the retry button usable. Search/timer/input policy is unchanged.
- Korean title discovery and unknown-build fingerprints are supported. Korean game layouts/input are not yet validated; no Korean native-search support claim is made.
- Production candidates do not contain a test signing key. A maintained production public key, signed bootstrap ownership and release assets must be provisioned before public updater use.
- Latest quick baseline: 578 selected, 577 passed, one optional historical OCR skip, zero failures. The full release verdict is still incomplete because two required original rc16 similarity fixtures are unavailable; an existing three-second route test passed separately after failing under concurrent build load.
- No game input, new dye session, desktop replacement, remote push or public release. Details: docs/verification-auto-update-2026-10-12.md in the development workspace.

# Current verification scope

## Local candidate 0.4.2rc8 (2026-10-11)

- Targeted presentation, controller, service, localization and desktop retry suite: 73 tests passed in 33.964 seconds. Verified-anchor colors and deltas reach both UI surfaces and update after promotion. Two/three regions, repeated progress without resizing or resetting the stage timer, 100/150% scaling, collapse and F9 were exercised in isolated Tk windows.
- Simplified Chinese, Traditional Chinese and English overlay screenshots were inspected using fixed example colors. Capture exclusion was disabled only inside this isolated fixture to make screenshots possible; production capture exclusion is unchanged.
- Refinement copy now explains stationary calculation, shows measured HEX/delta E and offers F9. Candidate counts and unverified colors are not presented as current results. Search logic, time policy and game inputs are unchanged.
- No live dye session or public release. The missing required historical rc16 release fixtures remain unresolved; this is not a complete release verdict. The automatic updater is a plan only, with GitHub and offline sources selected by the user.

Evidence: `outputs/native-integration/verification/refinement-copy-2026-10-11/` and `outputs/refinement-copy-tests.log`.

## Local candidate 0.4.2rc7 (2026-10-11)

- Final combined quick run: 544 selected, 543 passed, one optional historical OCR skip, zero failures/errors; 68.668 seconds. Current-process read-only service preflight passed with zero input attempts.
- Startup report: the rc6 session took 14.64 seconds to arm, scanning about 4 GB. Its 42.662-second discovery total includes later waiting scans. An uninitialized dye class skips that census, explaining faster starts on a fresh game process.
- Aligned full-pointer search now compares bounded 256 KiB windows in large blocks, retaining resumable candidates, full coverage, cancellation and final inspection. 64 focused discovery/session/service checks passed.
- Alternating old/new read-only sweeps of the same live process covered about 3.28 GB: old 6.703/6.672 seconds, new 4.406/3.953 seconds (34–41% reduction). This used an absent synthetic class pointer on an uninitialized game, not a live dye selection; real active-object validation and slow-machine performance remain unmeasured. Current backend initialization and build hashing took 0.84 seconds; the unresolved class check completed immediately. No inputs were sent.

- Reproduced session `20261011-210621-60790ceb`: refinement action 12 produced `#FFFFFF / #FFFFFF / #DEE7F3`; action 13 replaced region 2 with `#D0D0D0`. Both native poses matched the replay. The controller compared only the complete route endpoint with the older one-white anchor.
- Both local refinement and global routes now visually confirm and retain a superior intermediate landing when the remaining route is predicted worse. Subsequent refinement starts from that newly verified anchor.
- Quick: 543 selected, 542 passed, one optional historical OCR skip, zero failures/errors, 64.732 seconds total. A subsequent confirmation-failure regression increases future selection to 544.
- Final controller/retry suite: 68 passed in 13.165 seconds, including the new confirmation-failure recovery test. The original recorded/local solver and frame-budget suites also passed in the broader run; its one obsolete two-action expectation was updated and is included in the final 68. Counts overlap.
- Original palette replay demonstrated the failure before the fix, then retained double white after one rotation. These are simulated input and screenshot boundaries, not a new live game verification. No public release or new dye item used. Prior missing rc16 release fixtures remain unresolved.

Evidence: `outputs/native-integration/verification/prefix-best-2026-10-11/`.

## Local candidate 0.4.2rc6 (2026-10-11)

- Quick: 540 selected, 539 passed, one optional historical OCR skip, zero failures/errors; 53.766 seconds total.
- Focused real-refinement and recorded recovery replays: 35 passed in 58.726 seconds. Retry/readback admission: 51 passed in 8.656 seconds. A subsequently added persistent-decoder-timeout recovery case also passed (0.689 seconds); it increases future quick selection to 541. Counts overlap.
- Replays the reported `20261011-203529-ce9a6c15` palette and seven-action route. The forward rotation/wheel route now executes and produces the saved predicted colors in offline input replay; this is not a new live screenshot validation.
- Removes speculative global return admission and short per-refinement read deadlines. Local trials reserve one measured recovery; a second recovery is attempted only if actual time remains. Initial OCR grace and the three-second tail are unchanged.
- No new live dye round or public release. The two missing rc16 similarity fixtures documented below remain unresolved; no complete release verdict is claimed.

Reports: `outputs/native-integration/verification/refinement-stall-2026-10-11/`.

## Local candidate 0.4.2rc5 (2026-10-11)

Public release remains 0.4.1. This candidate is not approved for public release.

- Quick: 536 selected, 535 passed, one optional historical OCR archive skipped, zero failures/errors; 66.579 seconds.
- Release: 578 selected, 575 passed, three skipped, zero assertion failures/errors; 289.576 seconds. `release_complete=false`, nonzero exit.
- Two required similarity replays need the original rc16 session `20261010-235332-5fe7c98a`, which was removed with old candidate outputs. The original files were not found in available local copies or supplied ZIP archives. These checks remain selected; they have not been weakened or reclassified to hide missing evidence.
- The other skip is the supplemental historical private OCR archive. No other missing evidence is allowed for a complete release verdict.
- After the release run, the event/persistence compromise integration case was isolated from repeated global refinement. Both service integration cases pass in 4.399 seconds combined; the previous compromise case alone took 63.230 seconds. Production refinement remains unchanged and retains separate real-solver coverage.
- Python, PowerShell and pytest entry points now share the same selector. Pytest collection and the root Python wrapper both select 536 quick tests. Four real desktop representatives remain in quick, with the full UI matrix in release.

## Product changes covered

The input backend accepts a non-1:1 viewport only with verified target-HWND DPI pixel-mapping evidence. Window, process, session, current pose and input-release checks remain active. This does not establish universal support for every hardware/DPI/game-version combination.

The shared time policy keeps a single three-second tail. New rounds are capped at 117 seconds; unknown-age rounds initially use 90 seconds and may gain at most 27 seconds from reliable same-session countdown evidence. The initial 30-second OCR grace and retry epoch are preserved. Input, readback and complete return routes remain dynamically charged.

Global approaches can use controlled rotations up to 90 degrees while generic compilation retains its 12-degree default and fine candidates. Completed candidates survive CPU search exhaustion; rc5 late moves required speculative recovery; rc6 removes that global admission gate. Actual screenshot HEX remains the only precise-match proof. Three-white end-to-end accuracy is not newly verified.

## Evidence and exclusions

Local reports: `outputs/native-integration/verification/optimization-2026-10-11/`.

Required data3 session evidence was recovered from the user-provided archive (about 700 KB). Other retained fixtures remain local and are excluded from Git and portable packages. Do not delete referenced fixtures when cleaning build outputs. Prior version details remain in Git history and `docs/research`.

No real game input, dye item, automatic application or public release was used for this maintenance work. Package integrity and launch evidence are recorded separately in the local report folder; they do not replace missing live or archived route evidence.

Package check: 122 production modules, native assets and source fingerprint match. A target-bound computer-use smoke confirmed startup, maximized layout, restored layout and normal close on this machine. Generated test configuration was moved out of the portable package.
