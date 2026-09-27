# Color Studio · Mabinogi Mobile

By **南千和 (MinamiChiwa)** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

An automatic dyeing tool for **Mabinogi Mobile, Hong Kong / Macau / Taiwan service**, running on Windows. It reads the game screen and uses mouse gestures to search for your selected dye colors across three regions.

> Please note that using this tool in-game may carry some risk.

Supporting the creator is entirely voluntary and never affects access to the tool: [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

This tool was developed with AI assistance.

## Getting started

Download the complete ZIP from Releases, extract it and run `ColorStudio.exe`. Keep the adjacent `_internal` folder.

1. Set the game window to 1280 × 960. All three regions are enabled by default; turn off any you do not need. Enter HEX colors, use the color picker or screen eyedropper, and optionally add alternatives.
2. Choose Exact HEX or Similar independently for each region. Even if only one or two regions use Exact HEX, they take priority over the remaining Similar regions: candidates rank first by exact-match count, then by maximum and average color error across all enabled regions. Exact regions require identical HEX codes.
3. Similar regions use the Delta E tolerance you set; there is no fixed ΔE 8 ceiling. If no candidate meets every setting, the tool still positions the closest executable compromise using the same priority.
4. Select the game window, then click Start or press **F8**. Open the timed dye screen after the overlay appears. The tool first builds this round’s stitched board, then searches, positions and verifies in-game HEX. Press **F9** to stop.

Auto-detection accepts spacing variations in the title and recognizes the game executable. Select manually if multiple candidates exist; select again if that window closes. Borderless fullscreen is supported. Keep the game in the foreground and its geometry unchanged during active searching.

The 60-second figure is a performance reference, not a hard cutoff. As long as the game timer allows, the tool continues its normal workflow. Screenshot predictions are provisional; game HEX verification is the final check. You decide whether to apply the dye.

Exact mode enlarges nearby color islands around the pointer to expose small pure-color areas. Rotation pivots around the initial right-button position; zoom pivots around the pointer. Moving or resizing the game window during a search stops it; press F8 to detect the new layout.

Choose Simplified Chinese, Traditional Chinese or English in the upper-right selector. The main window, overlay and open information dialogs switch immediately without restarting. The main layout adapts from three columns to two or one; the help button opens the tutorial, and Support offers Afdian and Patreon.

## Preview and history

- Click the ordered color overview to open the complete allowed-color atlas.
- Use +/− to zoom, drag to pan, and hover to inspect individual HEX values without pagination.
- The last 50 results retain the three colors, per-region ΔE, maximum and mean differences.
- Automatic verification and apply is off by default. Exact mode disables the tolerance slider.
- Settings, results and diagnostic screenshots are stored locally in the adjacent `data` folder.
- The tool keeps the 20 most recent search sessions. Sessions older than 30 days or beyond the 512 MiB total budget are cleaned up before a new run; active and recently modified sessions are protected.

## Development

Windows 10/11 and Python 3.12. Sources are in `work/studio`.

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python -m unittest discover -s work/studio -p "test_*.py"
```

Install Tesseract OCR with `eng.traineddata` to run from source or build. Default location: `C:/Program Files/Tesseract-OCR`. Set `TESSERACT_HOME` for a different build location.

```powershell
python work/studio/build_release.py
```

Output: `outputs/release/ColorStudio`. Previous release data is backed up locally to `work/studio/release-test-data`. Private game captures and personal settings are not published; capture-based tests are skipped when their fixtures are absent.

## Validation

A timed search cannot guarantee an exact match or a global optimum. Actual game testing does not cover every DPI and monitor configuration.

After starting, the tool waits for the dye board and timer until F9 cancels. The 60-second figure is a performance reference, not a hard stop: the tool continues to finish a normal build and search even when they take longer. Input stops only when the OCR game countdown reaches its safety deadline, F9 is pressed, focus or window geometry changes, or recognition becomes unreliable. If Windows prevents game activation, click the game yourself; there is no need to start again. Hotkey registration status appears at the bottom. Close other tool copies or use buttons if a key is unavailable.

The main window adapts between three, two and one card columns, and debounces layout work while resizing. Enabled cards have a teal border and background; disabled cards show an explicit label. The overlay can be moved, collapsed and made transparent while showing live progress. Wheel input is disabled throughout the tool UI; click or drag to adjust values. During the initial wait, you may return to the game after briefly changing focus. Interruptions and errors display a dialog.

Screenshot color predictions can still differ from the game’s actual HEX values in this version. The tool reads the in-game HEX after positioning; if verification misses the target, it leaves the result for your review and never applies it automatically.
