# Color Studio 0.3.0

This tool was developed with AI assistance.

## Updates

- Added measured wheel-detent fallback: a small scale residual can be corrected by a bounded translation when all three markers remain within the one-pixel positioning gate.
- Preserved the normal game HEX verification step and the rule that the tool never clicks apply or confirm.
- Added bounded session cleanup: timestamped sessions are retained for 30 days, up to 20 recent sessions and a 512 MiB storage budget; active/recent sessions are protected.
- Release builds exclude local profiles, screenshots, diagnostic traces and search history. Existing build data is backed up locally before packaging.
- Synchronized Simplified Chinese, Traditional Chinese and English documentation, including support links and the current prediction limitation.
- Updated the support information for [Afdian](https://afdian.com/a/minamichiwa) and [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink). Support is voluntary and does not affect use.

## Known limitation

The atlas can position the board accurately while its predicted RGB/HEX color still differs from the game’s verified HEX. This release displays the verified result and marks a miss as not accepted; it does not silently apply it. See [the validation report](work/studio/RELEASE_VALIDATION_20260928.md) for the latest measured example.

## Packaging

Download the complete Windows package and keep the `_internal` directory next to `ColorStudio.exe`. Set the game window to 1280 × 960. Start with F8 or the Start button, enter the timed dye screen manually after the overlay appears, and use F9 to stop.
