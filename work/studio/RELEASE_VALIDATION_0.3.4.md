# Color Studio 0.3.4 — Release validation

Date: 2026-09-29. This tool was developed with AI assistance.

## Scope

This release completes the reachable-route and colour-family safeguards introduced after 0.3.3. Landing-neighbourhood checks now allow small interpolation fluctuations without discarding every same-family compromise. A separate cross-family fallback is available only when the search produces no same-family candidate; it remains bounded by colour-family and landing limits and is ranked by actual colour error.

## Automated regression

Command: `python -m unittest discover -s work/studio -p "test_*.py"`.

The tested working tree completed 599 tests: 582 passed and 17 were skipped because private game captures or execution archives are unavailable. No test failed. Coverage includes discrete route binding, landing-neighbourhood stability, same-family priority, bounded cross-family fallback, candidate ranking, recovery paths, multilingual UI, high-DPI layout and session cleanup.

## Manual session

The latest session `20260929-202450-6997efce` completed atlas collection, candidate publication, positioning and in-game HEX verification. It contained four raw same-family compromise candidates; four routes passed the stable-route gate and no cross-family fallback was used. Three trial route diagnostics were rejected before input because their landing or gesture stability conditions were not met. The default route was verified, then the user stopped the flow with F9. No global error, unrecovered exception or forced timeout occurred.

The configured targets were exact white in all three regions. The verified game colours were `#F4DCE7`, `#FCE2D4` and `#DEDAE9`, with ΔE76 values 14.50, 14.78 and 14.70. The result was correctly reported as a same-family compromise because this board did not provide an exact white hit.

The previous no-candidate session `20260929-193640-711abb21` was replayed with the release code. Its 5,693 compromise and 175 same-family raw search candidates previously failed the strict landing gate; the updated gate retained three stable same-family routes.

## Package checks

The Windows package is built from this tested working tree with bundled OCR data. The package contains user documentation and validation reports only; local settings, screenshots, session history, conversation transcripts and continuation notes are excluded. The visible application title and brand area show `v0.3.4`. Automated package checks send no physical game input.

## Limitations

Screenshot predictions may still differ from actual in-game HEX values. A timed search does not guarantee an exact match, satisfaction of every tolerance or a global optimum. The tool does not click the game’s apply, confirm or cancel controls; applying the dye remains a manual in-game action.
