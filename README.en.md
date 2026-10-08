# Color Studio · Mabinogi Mobile

By **南千和 (MinamiChiwa)** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

An automatic dyeing tool for **Mabinogi Mobile, Hong Kong / Macau / Taiwan service**, running on Windows. It reads the game screen and uses mouse gestures to search for the selected dye colors across three regions.

> Please note that using this tool in-game may carry some risk.

Sponsorship is entirely voluntary and does not affect access to the tool: [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami?utm_medium=unknown&utm_source=join_link&utm_campaign=creatorshare_creator&utm_content=copyLink)

This tool was developed with AI assistance.

## Getting started

The current release is `ColorStudio-v0.3.6`. Extract the complete package and run `ColorStudio.exe`, keeping the `_internal` folder beside it. OCR and English recognition data are included; Python and a separate Tesseract installation are not required. Close older copies before upgrading and extract this release into a separate folder.

1. Set the game window to 1280 × 960. All three regions are enabled by default; turn off any not required. Enter HEX colors, use the color picker or screen eyedropper, and optionally add alternatives.
2. Choose Exact HEX or Similar independently for each region. Exact mode requires identical HEX codes; Similar mode uses the configured tolerance. Combinations are compared using all regions’ color differences and nearby color variation, favoring stable combinations that meet every setting. Compromises balance closeness across regions; Exact hits take priority when overall quality is equal, without sacrificing another region for one exact match. The overlay identifies measured results outside the targets and color-family mismatches.
3. Similar regions use their individual Delta E tolerances. If no candidate meets every setting, the tool selects an executable compromise that balances differences across regions and nearby color variation.
4. Select the game window, then click Start or press **F8**. Open the timed dye screen after the overlay appears. With one region enabled, the tool searches the current board directly and leaves time for manual adjustment. With multiple regions enabled, it first builds this round’s stitched board, then searches, positions and verifies in-game HEX. Press **F9** to stop.

**Single-region tip:** Exact mode prioritizes an identical HEX during the main search phase, about 60 seconds after board detection. If no exact match is found, the tool attempts to position the best measured compromise; finalization may take a few extra seconds. Similar mode stops after two consecutive readings meet the configured tolerance. Search uses limited translation and measured zoom steps. Unverified zoom responses end that route, and scale limits are not repeatedly pressed. The remaining game time is available for manual adjustment. If no target is met, the overlay labels the result “Target not reached · Compromise.” This is the closest verified result from the search, not a tool failure.

Auto-detection accepts spacing variations in the title and recognizes the game executable. Select manually if multiple candidates exist; select again if that window closes. Borderless fullscreen is supported. Keep the game in the foreground and its geometry unchanged during active searching.

After positioning, the tool shows the in-game HEX. Check the result in the game before applying the dye manually.

With one region enabled, Exact and Similar modes skip full-board stitching and explore the board directly using translation and limited zoom. With multiple regions enabled, they use this round’s stitched board and calculate rotation, zoom and translation for each candidate. Avoid moving the mouse during automatic operation. Moving or resizing the game window during a search stops it; press F8 to detect the new layout.

Choose Simplified Chinese, Traditional Chinese or English in the upper-right selector. The main window, overlay and open information dialogs switch immediately without restarting. The main layout adapts from three columns to two or one; the help button opens the tutorial, and Support offers Afdian and Patreon.

## Preview and history

- Click the ordered color overview to open the complete allowed-color atlas.
- Use +/− to zoom, drag to pan, and hover to inspect individual HEX values without pagination.
- The last 50 results retain the three colors, per-region ΔE, maximum and mean differences.
- The normal search workflow verifies the in-game HEX values and shows the result in the overlay. Exact mode disables the tolerance slider.
- Settings, results and diagnostic screenshots are stored in the adjacent `data` folder by default. If the install directory is not writable, the tool uses `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`, then the system temporary directory as a last resort.
- Diagnostic records are cleaned automatically in the background, retaining the latest three runs. Active records and records updated within the last five minutes are temporarily protected. Cleanup has no aggregate size cap. Data in the system temporary directory may be removed by the operating system.

## Development

Windows 10/11 and Python 3.12. Sources are in `work/studio`.

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python run_tests.py
```

The default profile covers current production behavior. Use `python run_tests.py --profile all` for the complete suite; diagnostics, legacy paths and private fixtures have separate profiles. See [test scopes](work/studio/TESTING.md).

Install Tesseract OCR with `eng.traineddata` to run from source or build. Default location: `C:/Program Files/Tesseract-OCR`. Set `TESSERACT_HOME` for a different build location.

```powershell
python work/studio/build_release.py
```

Output: `outputs/release/ColorStudio`. Previous release data is backed up locally to `work/studio/release-test-data`. Private game captures and personal settings are not published; capture-based tests are skipped when their fixtures are absent.

## Validation

A timed search cannot guarantee an exact match, satisfaction of every tolerance or a global optimum. The layout calculation matrix covers 1024×768, 1920×1080, 3840×2160 and 5120×2880 at 100%, 125%, 150%, 200% and 250% DPI. Separate tests cover physical-pixel coordinate mapping and monitors with negative desktop coordinates. These checks do not establish real-game validation for every 4K, multi-monitor or mixed-DPI configuration.

The main window, overlay, tutorial, support dialog and runtime messages switch between all three languages immediately. OCR uses fixed `eng` data independently of the interface language and handles non-UTF-8 output from Windows installation paths. Tool windows size to the monitor work area. On a 4K display, keep the game in 1280 × 960 windowed mode; the desktop resolution does not need to change.

After starting, keep the game in the foreground and wait on the timed dye screen until the tool finishes. Press F9 to stop. If the game window is moved or resized, stop and start again. If Windows prevents game activation, activate the game window manually and let detection continue. Hotkey registration status appears at the bottom; close other tool copies or use the buttons if a key is unavailable.

The color cards retain fixed dimensions and rearrange into columns as the window width changes. Enabled cards have a teal border and background; disabled cards show an explicit label. The overlay can be moved, collapsed and adjusted for opacity while showing the current step and elapsed time. Long content scrolls while the title and F9 stop button remain visible. Click or drag to adjust color values. If positioning or color reading remains incomplete, the overlay shows a recovery status and any result currently available.

Screenshot color predictions can still differ from actual in-game HEX values. The tool reads and displays those values after positioning; applying the dye remains a manual action in the game. See the [validation report](work/studio/VERIFICATION.md) for the current scope, results and limitations. Version changes are documented on the release page.

In a source environment, `run_preflight.bat` performs a read-only check of game capture, physical client size and DPI. Protection checks are simulated and send no game input. This script requires the source environment and is not a prerequisite for the release ZIP.
