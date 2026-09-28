# Color Studio · Mabinogi Mobile

By **南千和 (MinamiChiwa)** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

An automatic dyeing tool for **Mabinogi Mobile, Hong Kong / Macau / Taiwan service**, running on Windows. It reads the game screen and uses mouse gestures to search for the selected dye colors across three regions.

> Please note that using this tool in-game may carry some risk.

Supporting the creator is entirely voluntary and never affects access to the tool: [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

This tool was developed with AI assistance.

## Getting started

Download `ColorStudio-v0.3.2.zip` from Releases, extract it and run `ColorStudio.exe`. Keep the adjacent `_internal` folder. OCR and English recognition data are included; Python and a separate Tesseract installation are not required. Close the previous version before upgrading, and extract into a separate folder to avoid mixing files.

1. Set the game window to 1280 × 960. All three regions are enabled by default; turn off any not required. Enter HEX colors, use the color picker or screen eyedropper, and optionally add alternatives.
2. Choose Exact HEX or Similar independently for each region. Even if only one or two regions use Exact HEX, they take priority over the remaining Similar regions: candidates rank first by exact-match count, then by maximum and average color error across all enabled regions. Exact regions require identical HEX codes.
3. Similar regions use the configured Delta E tolerance; there is no fixed ΔE 8 ceiling. If no candidate meets every setting, the tool still positions the closest executable compromise using the same priority.
4. Select the game window, then click Start or press **F8**. Open the timed dye screen after the overlay appears. The tool first builds this round’s stitched board, then searches, positions and verifies in-game HEX. Press **F9** to stop.

Auto-detection accepts spacing variations in the title and recognizes the game executable. Select manually if multiple candidates exist; select again if that window closes. Borderless fullscreen is supported. Keep the game in the foreground and its geometry unchanged during active searching.

After positioning, the tool shows the in-game HEX. Review it in the game, then apply the dye manually if desired.

Exact and Similar modes both search the current stitched board and calculate rotation, zoom and translation for each candidate. Avoid moving the mouse during automatic operation. Moving or resizing the game window during a search stops it; press F8 to detect the new layout.

Choose Simplified Chinese, Traditional Chinese or English in the upper-right selector. The main window, overlay and open information dialogs switch immediately without restarting. The main layout adapts from three columns to two or one; the help button opens the tutorial, and Support offers Afdian and Patreon.

## Preview and history

- Click the ordered color overview to open the complete allowed-color atlas.
- Use +/− to zoom, drag to pan, and hover to inspect individual HEX values without pagination.
- The last 50 results retain the three colors, per-region ΔE, maximum and mean differences.
- The normal search workflow verifies the in-game HEX values and shows the result in the overlay. Exact mode disables the tolerance slider.
- Settings, results and diagnostic screenshots are stored in the adjacent `data` folder by default. If the install directory is not writable, the tool uses `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`, then the system temporary directory as a last resort.
- Old-session cleanup runs in the background when a new run starts. The latest 20 sessions and sessions updated within the last five minutes are protected. Other sessions may be removed after 30 days or when total session storage exceeds 512 MiB. Protected data can therefore keep the total above 512 MiB. Data in the system temporary directory may be removed by the operating system.

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

A timed search cannot guarantee an exact match, satisfaction of every tolerance or a global optimum. The layout calculation matrix covers 1024×768, 1920×1080, 3840×2160 and 5120×2880 at 100%, 125%, 150%, 200% and 250% DPI. Separate tests cover physical-pixel coordinate mapping and monitors with negative desktop coordinates. These checks do not establish real-game validation for every 4K, multi-monitor or mixed-DPI configuration.

The main window, overlay, tutorial, support dialog and runtime messages switch between all three languages immediately. OCR uses fixed `eng` data independently of the interface language and handles non-UTF-8 output from Windows installation paths. Tool windows size to the monitor work area. On a 4K display, keep the game in 1280 × 960 windowed mode; the desktop resolution does not need to change.

After starting, keep the game in the foreground and wait on the timed dye screen until the tool finishes. Press F9 to stop. If the game window is moved or resized, stop and start again. If Windows prevents game activation, activate the game window manually and let detection continue. Hotkey registration status appears at the bottom; close other tool copies or use the buttons if a key is unavailable.

The color cards retain fixed dimensions and reflow only when crossing a column breakpoint. Enabled cards have a teal border and background; disabled cards show an explicit label. The overlay can be moved, collapsed and adjusted for opacity while showing the current step and elapsed time. Long content scrolls while the title and F9 stop button remain visible. Click or drag to adjust color values, preventing accidental wheel changes. During the initial wait, the game may be returned to the foreground after focus is changed briefly. Interruptions and errors display a dialog.

Screenshot color predictions can still differ from actual in-game HEX values. The tool reads and displays those values after positioning; applying the dye remains a manual action in the game. See the [0.3.2 release notes](RELEASE_NOTES_0.3.2.md) and [0.3.2 validation report](work/studio/RELEASE_VALIDATION_0.3.2.md).

In a source environment, `run_preflight.bat` performs a read-only check of game capture, physical client size and DPI. Protection checks are simulated and send no game input. This script requires the source environment and is not a prerequisite for the release ZIP.
