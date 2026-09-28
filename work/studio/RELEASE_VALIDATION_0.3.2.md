# Color Studio 0.3.2 — Release validation

Date: 2026-09-28. This tool was developed with AI assistance.

## Scope

This release hardens the atlas execution path after a real session reached the game's native zoom boundary. Ordinary action, registration, candidate-planning and verification faults now enter a safe recovery state instead of the global error dialog. A repeated frame may be used to try a measured fallback; otherwise the tool stops input and keeps the current game frame. F9, focus loss, geometry changes and the game deadline remain safety interrupts.

## Automated regression

Command: `python -m unittest discover -s work/studio -p "test_*.py"`.

The release working tree completed 425 tests: 408 passed and 17 were skipped because private game captures or execution archives were unavailable. No test failed.

Coverage includes:

- Native wheel-stop recheck and recovery without a user-facing error.
- Safe fallback candidate rebasing from a reliable measured pose.
- Terminal recovery when the pose is not reliable, without further mouse input.
- Recovery event fields and overlay rendering when HEX data is partial.
- Candidate callback, capture, build, budget and selection exceptions.
- Preservation of F9, focus-loss and geometry-change interruption behavior.
- English and Traditional Chinese coverage for all new runtime messages.

## Package checks

The Windows package was built in `outputs/release/ColorStudio` with the bundled OCR runtime and no application data directory. The release build script copies only user documentation and validation reports; local settings, screenshots, session history, conversation transcripts and continuation notes are excluded. The visible application title and brand area show `v0.3.2`.

The package was built from the tested working tree. No physical game input was sent during automated package checks. Real-game validation remains required for the new recovery behavior.

## Existing limitations

The current-round atlas search and in-game HEX verification remain unchanged in their color model. Screenshot predictions may differ from actual in-game HEX values, and searches do not guarantee an exact match, satisfaction of every tolerance or a global optimum. Dye application remains a manual in-game action.
