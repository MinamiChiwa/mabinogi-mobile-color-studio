# Color Studio · Mabinogi Mobile

By **南千和 (MinamiChiwa)** · [Support on Afdian](https://afdian.com/a/minamichiwa)

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

An automatic dyeing tool for **Mabinogi Mobile, Hong Kong / Macau / Taiwan service**, running on Windows. It reads the game screen and uses mouse gestures to search for your selected dye colors across three regions.

> Using this program in-game carries risks. Please consider those risks and use your own judgment.

## Getting started

Download the complete ZIP from Releases, extract it and run `ColorStudio.exe`. Keep the adjacent `_internal` folder.

1. Enable the regions to match. Enter HEX colors, use the color picker or screen eyedropper, and optionally add alternative colors.
2. Choose Exact HEX or Similar. Try ΔE 8–12 initially for Similar; lower values mean a closer match.
3. Use Auto-detect under Game window, or select a window manually. Click Start or press **F8** to focus the game. Open regular dye and finish the tutorial; searching starts automatically. **F9** stops the tool.

Auto-detection accepts spacing variations in the title and recognizes the game executable. Select manually if multiple candidates exist; select again if that window closes. Borderless fullscreen is supported. Keep the game in the foreground and its geometry unchanged during active searching.

Similar mode continues improving after finding a result within tolerance. Unless every enabled region reaches an exact target or alternative, the final approximately 30 seconds are reserved for returning to the best observed set. The game HEX codes are verified before completion. You decide whether to use a compromise result.

Exact mode enlarges nearby color islands around the pointer to expose small pure-color areas. Rotation pivots around the initial right-button position; zoom pivots around the pointer. Moving or resizing the game window during a search stops it; press F8 to detect the new layout.

Choose Simplified Chinese, Traditional Chinese or English in the upper-right language selector. Switching language saves the preset and restarts the app.

## Preview and history

- Click the ordered color overview to open the complete allowed-color atlas.
- Use +/− to zoom, drag to pan, and hover to inspect individual HEX values without pagination.
- The last 50 results retain the three colors, per-region ΔE, maximum and mean differences.
- Automatic verification and apply is off by default. Exact mode disables the tolerance slider.
- Settings, results and diagnostic screenshots are stored locally in the adjacent `data` folder.

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

After starting, the tool waits for the dye board and timer until F9 cancels. If Windows prevents game activation, click the game yourself; there is no need to start again. Hotkey registration status appears at the bottom. Close other tool copies or use buttons if a key is unavailable.

The main window keeps three region cards with stable font sizes and control heights; resizing adjusts spacing and flexible areas. The exact-color notice remains visible. Enabled cards have a teal border and background; disabled cards show an explicit label. Wheel input is disabled throughout the tool UI; click or drag to adjust values. During the initial wait, you may return to the game after briefly changing focus. Interruptions and errors display a dialog.
