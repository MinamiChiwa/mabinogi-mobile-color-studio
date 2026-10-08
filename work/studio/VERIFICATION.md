# Current verification scope
> **Release status: validation-in-progress technical candidate.** 0.3.6 has code-regression evidence and a published build, but game-mechanism acceptance is incomplete. The published/latest label must not be read as proof of cross-board, cross-device or multi-region precision. See GAME_MECHANISM_VALIDATION_GATE.md before changing code or release status.

Version: 0.3.6. Policy revision: balanced-landing-single-zoom-v3. Date: 2026-10-08. This tool was developed with AI assistance.

## Automated checks

The 2026-10-09 Task 1 full run (`python -m pytest -q -rs --test-profile=all`) reported 867 passed, 19 skipped and 326 passed subtests in 32.13 seconds. Production contains 706 cases; diagnostic 105, legacy 56 and private fixtures 19 are separate. Counts reflect added behavioral checks, not increased game-mechanism confidence. Compilation and whitespace checks are recorded per implementation checkpoint.

Task 1 adds per-round stage durations, conservative estimates, real capture/read frame IDs and separate current versus best observations. Insufficient independent frames or unreadable enabled HEX cannot become verified evidence. Final remaining time is explicitly derived from the monotonic game deadline, not an independently read final countdown. Final runner metadata is recorded after a safety interruption without accessing the game.

Search and route binding now reserve positioning and finalization time by default. A soft search cutoff retains already-computed translation candidates, while F9 and hard game interrupts propagate. Slow binding stops subsequent work without erasing already-bound candidates. Return cost is charged once inside the protected tail and increases the tail when necessary. CPU/slow-OCR/long-return checks were performed offline; no new game input or dye round occurred.

Stage components and the two-frame verification envelope are separately labeled; verification duration overlaps capture/OCR/registration and must not be added again to wall time. Sparse timing estimates use the observed maximum and a default floor; with at least 20 samples they use P95 with the floor. This remains a conservative scheduling model, not a realtime guarantee. Native calls may overrun a CPU checkpoint; input guards remain independent.

The inherited test cleanup retains all original tests in the all profile. ECC assertions reject an incorrect finite matrix, anchor replay tests validate the complete continuous reference route without claiming shorter acquisition, and fixture availability is checked per visual case. See [test scopes](TESTING.md).

The controlled mechanism entry is `run_response_probe.ps1`. It is opt-in, records only observed frames/HEX/timing and never confirms, applies or cancels dye. Each timed game session must run one protocol only; outputs include mechanism_experiment.json, and an early stop preserves a partial report. These records are evidence collection, not a production response model.

The measured HEX feedback path now carries a retained local best separately from the live pose. If a better sample cannot be restored before the deadline, the service emits `atlas_best_not_restored` and the overlay labels the historical sample as not restored; it never reuses that HEX as the current game colour. Multi-region compromise notices are translated in Simplified Chinese, Traditional Chinese and English.

## Game observation

The earlier self-review package was exercised with a 1280 × 960 game window. Two single-region runs verified final game HEX values: one reached `#FFFFFF` with ΔE76 0.00 and one retained `#161414` with ΔE76 6.68 after no further improvement. In one multi-region run, an approximately 81-second atlas produced eight candidates, but only about 8.64 seconds remained and the default route was not sent. In another multi-region run, the material-color check failed during positioning; two game HEX readings were available (`#D5EBE9 / #D8415F / #B83E53`, ΔE76 11.62 / 11.37 / 8.63), but the pose was marked unreliable and movement stopped. These observations confirm reporting and fallback paths under the earlier package; they do not validate the new single-region zoom strategy or establish a guaranteed target match for every board.

A v0.3.6-rc.2 single-region run on 2026-10-03 used Exact `#000000` and finished with verified `#020204` (ΔE76 0.99); the saved best was still current. The tool reported the non-match as a verified result after a 66.23-second session. This confirms the compromise-reporting path on that run, not cross-board zoom reliability.

The single-region runs use direct board exploration and do not build a full atlas. Multi-region runs retain the full atlas route and its quality checks. Recovery and insufficient-time statuses remain visible to the user and are not treated as successful target matches. The current candidate adds a read-only fallback after ordinary build, quality, candidate or time-budget failures: it checks two consecutive game HEX readings for consistency within a bounded 3.5-second observation window and does not send mouse input. This fallback reports current colors only, without claiming a candidate, reliable pose or recovered best result.

## Saved-capture replay

The 2026-10-05 `translation_shared` mechanism probe completed 10 recorded
actions without sending a formal multi-region dye search. The run measured
about 3.595 seconds of input time, 4.720 seconds of registration time, and a
registration P95 of about 0.509 seconds; about 79.3 seconds remained at the
end. Four center/offset pairs of ±8-pixel translations measured approximately
±8 pixels and returned to the initial three-region HEX combination after the
reverse move. One down/up wheel pair measured scales of about 0.99013 and
1.00988 and also returned close to the initial combination. This is same-game
mechanism evidence only; it contains no target ΔE, precise-hit count, or
multi-region candidate result, and does not establish cross-session or
cross-device behavior.

A follow-up offline replay correction was committed as `9bfb00d`. The
progressive replay report now selects its best row with
`progressive_candidate_rank`, records accepted and landing-safe counts, and
labels the ranking used. This aligns diagnostic metadata with the opt-in
progressive service without changing the production route. On the current
contiguous replay source, both `full48` and `anchor_progressive` still fail
the quality gate and produce no strict three-region candidate; the complete
48-step route therefore remains the production baseline.

A separate 1280 × 960 capture previously stopped because an adjacent image pair had only 18 default feature inliers. Denser feature extraction found 43 inliers without reducing the existing matching, geometry or atlas-quality thresholds. Reconstruction of all 48 steps passed the original checks and retained eight candidates after integer-route binding. This replay sent no game input.

Three additional saved atlases from a 1920 × 1009 client retained eight bound candidates each. Their best central maximum ΔE76 predictions were 8.39 / 10.81 / 10.80. These values are offline predictions, not measurements from new game sessions.

## Historical formal multi-region regression: 2026-10-05 17:16

The 2026-10-05 session `20261005-171605-c8f7403e` was an explicitly authorized one-dye formal regression on 0.3.6 with three enabled rules (Exact `#FFFFFF`, Similar `#C0C0C0`, Similar `#FFFFFF`). It did not apply dye (`auto_apply=false`). The full 48/48 atlas completed from a 120-second start; capture took about 55.4 seconds and stitch/quality/search about 7.1 seconds. Atlas quality passed (coverage about 99.6% / 99.8% / 99.6%, held-out coverage about 98.0% / 98.9% / 97.3%, RGB RMSE about 6.36 / 4.18 / 6.36).

The search produced 63 candidates and none met the configured thresholds. The best predicted candidate had maximum ΔE76 about 10.28 and average about 8.11, while all candidates failed `landing_safe`; the run nevertheless attempted the first candidate, which is a safety gap to close before treating this route as production-ready. The first execution attempted roughly 15 rotations and 3 wheel steps while `game_response_verified=false`; recovery read `#7B523C / #9A6C4A / #8EC09F` (ΔE76 about 65.97 / 41.09 / 36.98), so it was recorded as a failed unverified route. A second execution used three measured translations after re-registration (marker errors about 0.04 px). Its stable game result was `#FCECDE / #E2CFAA / #CADAF1` (ΔE76 about 10.94 / 21.64 / 18.82; maximum 21.64; average 17.14; exact hits 0/1). One `(1, 0)` pixel feedback move did not improve the result; the measured baseline was restored and stably re-registered.

This run separates atlas quality from action-response reliability: a passing map did not make unverified rotation/zoom routes safe, while measured translation produced a small pose error but still did not make the three target colors jointly reachable in this sample. It is one board and one target combination, so it does not authorize a production route change, progressive capture, or a mechanism guarantee. The session has no standalone final countdown value and contains no dye-confirmation event; remaining time and application success are therefore unverified. Full evidence and the observed/inferred/unverified split are in `GAME_MECHANISM_VALIDATION_GATE.md`.

Until response profiles are independently verified, production must treat rotation/zoom predictions as untrusted, prefer measured translation only when the pose can be re-registered, and use the read-only two-frame fallback on quality, candidate, or budget failure.

## Historical capture failure after the route safety gate: 2026-10-05 19:27

The 2026-10-05 session `20261005-192718-bba9bfe1` reran the same three-region configuration after the route safety changes (Exact `#FFFFFF`, Similar `#C0C0C0`, Similar `#FFFFFF`). The run remained `auto_apply=false`; it sent neither a dye-confirmation click nor a cancel click. The user has confirmed that entering the formal timed dye round consumes one dye, so this round counts as one dye regardless of confirmation clicks. Inventory before/after values were not captured; the software log cannot independently audit the deduction.

The initial countdown was read as 120 seconds. Acquisition performed the existing 48-step grid after the measured one-notch zoom calibration. Grid capture reached 48/48 frames, but adjacent-frame alignment failed at `grid_045` with `Measured motion disagrees with capture command`; capture processing took about 3.83 seconds. No atlas quality report, candidate list, route binding, or candidate execution was produced after that failure.

The service stopped automatic movement and performed the read-only two-frame observation. It recorded `actual_colors` `#EC879E / #B2A860 / #2BA5B4`, ΔE76 `52.38 / 40.12 / 49.59`, maximum `52.38`, average `47.36`, and `exact_matches=0/1`. The observation was marked `verified=true` only for the two-frame HEX reading; `pose_reliable=false`, `positioning_complete=false`, `candidate_id=null`, and `compromise=true`. The UI therefore reports the current measured colors as a compromise and does not present them as a located candidate or restored best result.

The visible 45/48 pause was a real feedback defect: the background registration worker could fail between foreground actions, while the UI still showed the last capture count and shutdown waited on pending work. The worker now applies a bounded per-frame wait, exposes failure immediately, prevents further movement after an alignment error, and bounds close time. The capture log and overlay switch to a dedicated recovery stage (“stopping capture and reading the current colors”), so the user can distinguish an early stop from an active scan.

This run confirms the build-failure fallback and its compromise labeling. It does not exercise `transform_routes_suppressed` because the failure occurred before candidate binding, so it cannot be used as evidence that an unverified rotation/zoom candidate would have been blocked. The zoom calibration and sampling inputs belong to the atlas acquisition phase; their game response remains unverified for production use. The next mechanism or target-combination experiment must be separately authorized and must keep the one-run dye budget.

## Production route safety gate added after the regression

The live builder now suppresses any bound route containing rotation or wheel
actions unless both the real-game response profile and the sampled landing
neighbourhood are verified. Suppressed routes remain in route diagnostics with
their reason; they are never sent as the default automatic candidate. A
translation-only route may remain as a measured compromise, and binding,
rebind and replan apply the same gate. If no safe route remains, the service
uses the read-only two-frame current-HEX observation path. This closes the
specific safety gap observed in session `20261005-171605-c8f7403e`; it does not
validate the suppressed game mechanisms or improve the measured colour
reachability of the three-region target.

## Latest formal multi-region regression: strict target availability

The 2026-10-06 session `20261006-000545-e0f0f997` ran the same three-region configuration (Exact `#FFFFFF`, Similar `#C0C0C0`, Similar `#FFFFFF`) with `auto_apply=false`. It completed all 48/48 capture steps and passed the atlas quality gate: atlas coverage was approximately `99.44% / 99.85% / 99.40%`, held-out coverage `96.61% / 99.11% / 97.60%`, and held-out RGB RMSE `6.67 / 4.01 / 6.11`. No dye-confirmation or cancel click was sent.

The search produced 14 candidates, 12 of which were family-consistent, but none satisfied all enabled region rules. The service emitted `no_joint_candidate` before route execution and performed only the read-only two-frame observation. The recovered current game colors were `#79714A / #B7CBC1 / #968C78`, with ΔE76 about `57.49 / 9.31 / 43.20`, maximum `57.49`, average `36.67`, and exact hits `0/1`. The result was `candidate_id=null`, `pose_reliable=false`, `positioning_complete=false`, `compromise=true`, and `early_exit=true`.

Offline inspection records a strict miss in the reconstructed atlas: region 1 had about 1,042,697 valid samples and zero exact `#FFFFFF` pixels; its nearest sample was `#FFFEFE` with ΔE76 about `0.44`. Region 3 contained an exact white atlas sample. These maps undergo interpolation, averaging and rounding; absence in this finite reconstruction does not establish absence in the game or mathematical infeasibility. The observed failure was an old no-joint-candidate stop, not an executed-route failure; limited-search omissions remain possible. The current source adds `exact_target_availability` diagnostics and a message naming the missing region, target, nearest sample and ΔE; that field was added after this session and is not claimed to have been present in its saved log.

This run confirms that strict exact mode must preserve the byte-for-byte rule. In response, the current service treats exact mode as a priority for candidate ranking: if no joint exact candidate exists but a safe route remains, it positions and measures the closest compromise instead of ending with a read-only result. The compromise is explicitly labeled and never auto-applied. Build, alignment, route-safety, return-budget and two-frame verification failures still use the read-only fallback. A later experiment may test a similar rule for region 1 or another target combination, but it requires separate authorization and must remain a new one-run dye-budget experiment. This session counts as one started dye round under the user-confirmed rule. It did not independently capture inventory changes, establish cross-board availability, or record successful dye application.

## Distribution checks

The v0.3.6 package is built from the release commit and includes OCR with English recognition data, the three current README files and this verification summary. Build metadata records the application version, policy revision, source fingerprint and release commit. The published ZIP contains no local profiles, session history, screenshots or development notes.

## Limits

A finite search does not guarantee an exact match, every configured tolerance, or a global optimum. Screenshot predictions may differ from game HEX readings. Integer input generation and neighborhood color sampling do not certify rotation or zoom response across every device and game-window size.

Automated display checks cover 1024 × 768 through 5120 × 2880 and 100% through 250% scaling, including negative multi-monitor coordinates. These checks do not establish full game validation on every 4K or mixed-DPI setup. The recommended game window remains 1280 × 960.

When one region is enabled, this test candidate explores the current board directly instead of building a full atlas. Exact mode prioritizes an identical HEX during its main exploration phase; Similar mode stops after two consecutive in-tolerance readings. Limited translation and small, measured zoom steps include one optional relative-range expansion. The entry scale is not known absolutely; the tool cannot guarantee never reaching a game scale limit. Unknown zoom responses end that route, and repeated limit attempts are avoided. The new zoom behavior has not yet received independent real-game validation. Multi-region searches still use the complete atlas route. Progressive multi-region capture remains experimental; no fixed scan reduction or guaranteed time saving is enabled.

