# Current verification scope

Version: 0.3.5. Date: 2026-09-30. This tool was developed with AI assistance.

## Automated checks

The source regression suite contains 662 tests: 645 passed, 17 skipped because optional local capture archives were unavailable, and no failures or errors. Coverage includes candidate ordering, integer route endpoints, trial and return budgets, recovery observations, sparse-feature registration, multilingual UI, display geometry and session retention.

Command: `python -m unittest discover -s work/studio -p "test_*.py"`.

## Game observation

A session using a 1280 × 960 game client completed atlas capture, candidate publication, rotation and zoom positioning, and two-frame game HEX verification. All 48 scan steps and 17 execution registration checks completed. One intermediate rotation deviation triggered route rebinding; positioning then reached the same candidate. F9 ended candidate selection after the result was verified. The log contains no execution error or unverified recovery exit.

The configured targets were exact white in regions 1 and 3, and similar yellow in region 2. The measured colors were `#C5CDC4 / #837431 / #CBCBCB`, with target ΔE76 values of 19.35 / 76.52 / 18.41. The result was correctly marked as a compromise. Final prediction-to-measurement differences were 1.05 / 0.48 / 0.36, and marker-position residuals were at most 0.504 pixels. This confirms positioning and result reporting for this session, not satisfaction of the target colors.

The scan took 55.38 seconds. The result was verified approximately 88.40 seconds after the dye screen was recognized; waiting for the screen and subsequent candidate selection are excluded.

## Saved-capture replay

A separate 1280 × 960 capture previously stopped because an adjacent image pair had only 18 default feature inliers. Denser feature extraction found 43 inliers without reducing the existing matching, geometry or atlas-quality thresholds. Reconstruction of all 48 steps passed the original checks and retained eight candidates after integer-route binding. This replay sent no game input.

Three additional saved atlases from a 1920 × 1009 client retained eight bound candidates each. Their best central maximum ΔE76 predictions were 8.39 / 10.81 / 10.80. These values are offline predictions, not measurements from new game sessions.

## Distribution checks

The Windows distribution includes OCR with English recognition data, the three current README files and this verification summary. Build metadata records the application version, policy revision, source fingerprint and Git commit. Local profiles, session history, screenshots and development notes are excluded.

## Limits

A finite search does not guarantee an exact match, every configured tolerance, or a global optimum. Screenshot predictions may differ from game HEX readings. Integer input generation and neighborhood color sampling do not certify rotation or zoom response across every device and game-window size.

Automated display checks cover 1024 × 768 through 5120 × 2880 and 100% through 250% scaling, including negative multi-monitor coordinates. These checks do not establish full game validation on every 4K or mixed-DPI setup. The recommended game window remains 1280 × 960.

Progressive atlas capture is still experimental; the production scan uses its existing complete route. A saved-image comparison suggests that some boards may need fewer scan steps, but no fixed scan reduction or guaranteed time saving is enabled in this release.
