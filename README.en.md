# Color Studio · Mabinogi Mobile

By **MinamiChiwa** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami)

A Windows color search tool for the Hong Kong/Macau/Taiwan service of Mabinogi Mobile. Precise Search reads the current round’s palette, plans translation, zoom and rotation, and verifies game HEX values. Visual Search is a fallback if Precise Search fails.

Using tools in-game may carry risk; use with care. Donations are optional and do not affect features. Developed with AI assistance.

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## Use

Extract the entire release and run `ColorStudio.exe`. Keep `_internal` beside it. Python and Tesseract do not need separate installation. Exit the old app before upgrading into a new folder; copy its `data` folder to retain settings.

1. Select the game window, or use automatic detection for a single window. No fixed game resolution is required; window sizes and Windows scaling have explicit coordinate mapping.
2. Enable the regions to match. Enter HEX codes, choose colors, or use the eyedropper. Alternative colors are also accepted targets.
3. Choose Exact HEX or Similar per region. Exact requires the identical six-digit code; Similar uses the region’s ΔE tolerance.
4. Set priorities; 1 is highest. Meeting all enabled targets always comes first. Otherwise, targets are favored in priority order, followed by color differences. Changing a priority swaps it with the other region.
5. Press **F8** or Start, then open dyeing after the waiting message. Starting after opening the dye screen is also supported. Use Precise Search by default; Visual Search is for failures of Precise Search.
6. Keep the game in front. Avoid mouse use or moving/resizing the game window during execution. **F9** stops and releases the mouse. Confirm application manually in the game.

Each palette is bound to its game session. Regions share transformations; mathematical palette candidates still need an executable route and game HEX verification. Predicted colors do not prove a match. If all targets cannot be met, the tool tries to retain the best measured compromise in priority order.

Precise Search does not display predicted alternatives. Click Retry in the overlay or press **F7** to end the current search, zoom out to the maximum visible board area, and search again in the same round. A retry keeps the remaining time and target settings, with no new dye item used. Current colors are kept if there is insufficient time to reset and search again. **F9** still stops all actions.

Countdown readings are advisory for about 30 seconds after this round's board is first observed. Afterward, only reliable, decreasing screenshot readings can adjust the execution deadline. Retrying does not reset that interval or the round's time. If the current state cannot be verified, earlier colors are labeled "Last measured colors (current state unconfirmed)"; use the current colors in the game.

Two- and three-region boards are detected automatically. A two-region round uses its actual left and right regions; the third UI card is marked unavailable without changing saved settings or priorities. If only the absent third region is enabled, no input is sent and the tool asks you to enable Region 1 or 2.

When leather, wood or another material’s base palette lacks pure black or white, `#000000` or `#FFFFFF` cannot be matched exactly. Refer to the game’s actual HEX values. Multiple exact matches and finding a globally optimal result within the time limit are not guaranteed.

## Settings and presets

- Current colors, alternatives, enabled regions, matching modes, tolerances, priorities and search strategy save automatically and restore next time.
- The eyedropper maps physical cursor coordinates directly to a frozen screenshot, including negative virtual-desktop origins. It does not reposition the game window or force game focus.
- Save preset manages named configurations: save current settings, edit or rename independently, load, and delete. Editing a preset changes the main configuration only when loaded.
- Results retain the last 50 color combinations and their measured ΔE. Presets and result history are stored separately.
- Simplified Chinese, Traditional Chinese and English are supported. The resizable window rearranges cards into one, two or three columns. The topmost overlay supports clicks and dragging without taking game focus. It briefly hides while sending a game gesture, then returns.
- Data defaults to `data` beside the app. A nonwritable folder falls back to `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`, then to the temporary directory.
- Diagnostics retain the latest three sessions while protecting active records. Temporary data may be cleared by Windows.

## Diagnostics

`native-window-check.ps1` performs a passive preflight on an ordinary game screen, with no input or dye item required. The accompanying `WINDOW_CHECK.en.md` provides instructions.

Preflight checks the current build, modules, physical client area and game coordinates. A passing preflight does not prove live dye accuracy. Several display/scaling configurations were tested; universal size, mixed-DPI or game-version support is not claimed. Stop and restart after changing the game window during a run.

If process access is denied, run the tool and game at the same privilege level. When the game runs as administrator, right-click the tool and choose Run as administrator. Retry preflight on an ordinary game screen without starting a new dye round. The tool never elevates itself automatically.

Report problems at [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) with the session log. Extra dye items are not needed just to report a problem. The game’s current HEX values determine the final result.

## Development and tests

Windows 10/11, Python 3.12; production source is in `work/studio`.

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python scripts/run_tests.py
python scripts/run_tests.py --suite release
```

The default quick profile covers current product contracts. Release adds recorded palette search and recovery checks. Historical experiments and large search matrices remain available with `--suite research` or `--suite full`. See [TESTING.md](TESTING.md) for counts, timings and skipped-fixture limits. Test profiles do not change production search capability or game budgets.

Source and packaging require Tesseract with `eng.traineddata`, normally in `C:/Program Files/Tesseract-OCR`; override with `TESSERACT_HOME`. OCR language is independent of the interface language.

```powershell
python work/studio/build_release.py
```

Distribute the entire `outputs/release/ColorStudio` directory. Personal profiles, sessions and screenshots are excluded from releases and Git. Current scope is in [VERIFICATION.md](work/studio/VERIFICATION.md); changes are described on GitHub Releases.

## Updates

Bootstrap versions can check GitHub from the main window. You decide when to download and install. File updates keep settings, presets and all data. A full offline update can be imported when GitHub is unreachable. Older releases need one manual bootstrap upgrade. Development candidates have no production update key and are not an official update source.
