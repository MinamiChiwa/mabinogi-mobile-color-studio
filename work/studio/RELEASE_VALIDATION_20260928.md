# Release validation · 2026-09-28

This tool was developed with AI assistance.

## Scope

This report records the validation evidence used for the 0.3.0 build. It contains measurements and conclusions only; personal screenshots, session files and conversation transcripts remain local.

## Automated validation

- `python -m unittest discover -s work/studio -q`
- 384 tests passed; 15 private-capture tests were skipped because their fixtures are not distributed.
- The regression suite covers multilingual UI strings, fixed-card resizing, session cleanup, candidate ranking, wheel-detent fallback, positioning feedback and two-frame game HEX verification.

## Manual session

The isolated build was tested once with two candidate attempts. Both attempts reached the game HEX verification stage and measured marker errors below 0.6 px. The actual game colors were:

| Region | Predicted by atlas candidate 1 | Actual game HEX | Actual ΔE |
| --- | --- | --- | ---: |
| 1 | `#C65C2B` | `#B85F29` | 23.33 |
| 2 | `#EDE7EA` | `#EDE7EA` | 8.39 |
| 3 | `#2A2A2A` | `#343434` | 21.64 |

For this attempt the prediction error was 7.45 ΔE in region 1, 0.00 in region 2 and 4.63 in region 3. No exact region matched, so the result was correctly marked as not accepted and was not applied. The first candidate had the same verified game colors and a larger predicted error.

The wheel-detent fallback behaved as intended: it accepted a small residual between measured wheel steps, used a bounded translation correction, and continued to HEX verification. This fixes the earlier false “unreachable pose” stop. It does not correct the remaining color-model error.

## Release boundary

The build provides an atlas workflow with explicit HEX verification and conservative failure handling. These measurements do not establish that screenshot prediction is exact or that every random board will meet a requested ΔE. The displayed in-game HEX values are the final verification result; dye application remains a manual in-game action. Further color calibration remains necessary.
