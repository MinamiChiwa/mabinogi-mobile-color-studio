# Color Studio 0.3.1 — Release validation

Date: 2026-09-28. This tool was developed with AI assistance.

## Scope

This maintenance release addresses startup reliability, multilingual status messages, display geometry and local data handling. It retains the current-round stitched-board search, candidate ranking and in-game HEX verification. It does not change the color model or establish a new dye-matching success rate.

## Automated regression

Command: `python -m unittest discover -s work/studio -v`.

The release working tree completed 420 tests in 17.270 seconds: 403 passed, 17 skipped, no failures. Skipped cases require unavailable private game captures or execution archives. A skipped case is not evidence that its scenario passed.

Coverage includes:

- OCR startup probing with CP936, CP950 and CP1252 path output, independent probe timeouts, fallback between OCR installations and recovery after transient frame errors. OCR requests explicitly use `eng`.
- OCR image transfer through binary pipes, preserving pixel values without temporary image files. Data paths containing spaces and Unicode characters are passed as single arguments without literal grouping quotes.
- Immediate interface-language switching and translated progress, candidate-execution, countdown and recognition-failure messages.
- Layout calculations at 1024×768, 1920×1080, 3840×2160 and 5120×2880, with 100%, 125%, 150%, 200% and 250% DPI.
- Physical screenshot coordinate mapping, negative virtual-desktop coordinates, monitor-work-area sizing and overlay bounds.
- Cancellable startup waiting, retrying countdown recognition before input, background session cleanup, session-name collisions and writable data-directory fallback.
- Candidate ranking, bounded movement, F9 cleanup, focus/window-change protections and two-frame game HEX verification.

The display matrix uses simulated dimensions and DPI values. It does not certify every physical 4K, mixed-DPI or multi-monitor setup. Interface-language tests do not replace end-to-end tests on separately installed Windows languages.

## Packaged application checks

The Windows executable was built with the bundled OCR runtime and copied into a separate directory containing Simplified Chinese, Traditional Chinese and spaces. All three saved interface-language settings started successfully, displayed the corresponding application title and exited normally with code 0 after a window-close request.

The application's OCR wrapper, using that copy's bundled Tesseract and English data, correctly read the generated test image `0123456789`. The check exposed and verified the fix for quoted data paths during actual recognition, beyond merely listing available OCR languages. No game input was sent. This was a startup and OCR transport check, not a new dye session or a physical 4K test.

## Existing game evidence and limitations

The previous 0.3.0 validation recorded two candidate attempts that reached in-game HEX verification with marker-position errors below 0.6 pixels. Color prediction still differed from in-game HEX by up to 7.45 ΔE in the measured attempt. These are historical measurements, not new 0.3.1 game sessions; see `RELEASE_VALIDATION_20260928.md`.

The current workflow does not guarantee an exact match, satisfaction of every configured tolerance or a global optimum. Candidates rank first by exact-match count, then by maximum and average ΔE across all enabled regions. An unmatched result remains a compromise. Dye application is a manual in-game action.

Sixty seconds remains a performance reference. Normal work is not stopped solely for exceeding that reference. The real game countdown, F9, loss of focus, window changes and unreliable recognition continue to guard input.

## Distribution boundaries

The Windows archive must contain the application, its runtime dependencies, Tesseract with `eng.traineddata`, and the matching user documentation. Personal settings, game captures, session history, conversation transcripts and local continuation notes are excluded. Source-only preflight scripts are not a prerequisite for using the packaged executable.
