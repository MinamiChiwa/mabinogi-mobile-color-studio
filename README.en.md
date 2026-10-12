# Color Studio · Mabinogi Mobile

By **MinamiChiwa** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami)

A Windows color search tool for supported Taiwan, Korean and Japanese builds of Mabinogi Mobile. Korean and Japanese support is still in testing. Precise Search reads the current round’s palette, plans translation, zoom and rotation, and verifies game HEX values. Screenshot Search replaces the old visual strategy using captured pixels, image registration and actual HEX verification, without reading game memory. See the [server guide](docs/server-adaptation/server-selection.md) for validation status.

Using tools in-game may carry risk; use with care. Donations are optional and do not affect features. Developed with AI assistance.

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

## Use

Extract the entire release and run `ColorStudio.exe`. Keep `_internal` beside it. Python and Tesseract do not need separate installation. Exit the old app before upgrading into a new folder; copy its `data` folder to retain settings.

1. Select Taiwan, Korea or Japan beside the game-window selector; detection updates for that server. Select its window or use automatic detection. No separate preflight or fixed game resolution is required; window sizes and Windows scaling have explicit coordinate mapping.
2. Enable the regions to match. Enter HEX codes, choose colors, or use the eyedropper. Alternative colors are also accepted targets.
3. Choose Exact HEX or Similar per region. Exact requires the identical six-digit code; Similar uses the region’s ΔE tolerance.
4. Set priorities; 1 is highest. Meeting all enabled targets always comes first. Otherwise, each region is compared in priority order using its match status and color difference. Differences are grouped in ΔE 0.5 steps so tiny gains in a higher-priority region do not hide substantial improvements elsewhere. Exact matches still require identical HEX codes. Changing a priority swaps it with the other region.
5. Press **F8** or Start, then open dyeing after the waiting message. Starting after opening the dye screen is also supported. Precise Search remains the default; use Screenshot Search if Precise Search is unavailable.
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
- Simplified Chinese, Traditional Chinese, English, Japanese and Korean are supported. The resizable window rearranges cards into one, two or three columns. The topmost overlay supports clicks and dragging without taking game focus. It briefly hides while sending a game gesture, then returns.
- Data defaults to `data` beside the app. A nonwritable folder falls back to `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`, then to the temporary directory.
- Diagnostics retain the latest three sessions while protecting active records. Temporary data may be cleared by Windows.

## Diagnostics

Select the server and game window in the app; no separate preflight script is required. Several display and scaling configurations have been tested. Stop and restart after moving or resizing the game during a run. Client updates may require a new adapter.

If process access is denied, run the tool and game at the same privilege level. If the game runs as administrator, right-click the tool and choose Run as administrator. The tool never elevates itself automatically.

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

Bootstrap versions can check GitHub from the main window. You decide when to download and install. File updates keep settings, presets and all data. A full offline update can be imported when GitHub is unreachable. Older releases need one manual bootstrap upgrade. The official 0.4.2 package includes update signature verification. Retry search is labeled Testing only.

For a first installation, download `ColorStudio-v0.4.3-Windows-x64.zip`. `UPDATE-ONLY-ColorStudio-0.4.3-win-x64.zip` is only for Import offline update inside the app; it is not a runnable installation. `UPDATE-ONLY-ColorStudio-from-0.4.2-to-0.4.3-win-x64.zip` requires the official 0.4.2 baseline.
