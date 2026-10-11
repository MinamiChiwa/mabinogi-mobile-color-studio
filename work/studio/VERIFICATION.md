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
