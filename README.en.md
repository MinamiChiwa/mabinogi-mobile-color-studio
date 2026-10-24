# Color Studio · Mabinogi Mobile

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**ColorStudio 0.4.9** is a Windows color search tool for the Taiwan server of Mabinogi Mobile. Korean and Japanese support is in testing. It adjusts the palette for your selected targets; you decide whether to apply the result in the game.

## 1. Install

Download **`ColorStudio-v0.4.9-Windows-x64.zip`** from [GitHub Releases](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases), extract the whole archive, and run `ColorStudio.exe`. Keep `_internal` beside the executable. No separate Python or Tesseract installation is needed.

**`UPDATE-ONLY` packages are for updating an existing installation. They are not first-install packages and cannot be extracted and run directly.** See Updates below.

## 2. Start searching

1. Select the **server and game window**. No fixed resolution is required; adjust the window before starting.
2. Enable the **color regions** you want to match, then set targets, matching requirements and priorities. Use HEX input, the color picker or the eyedropper. Alternative colors are also accepted targets. Priority 1 is highest.
3. Press **F8 / Start search**, then follow the prompt to open dyeing in the game. You can also start with the palette already open.
4. Keep the game in the foreground and avoid moving the mouse or changing the game window during automatic input. Apply the result manually in the game.

The **search method** and each region's **matching requirement** are separate settings:

| Setting | Option | Purpose |
|---|---|---|
| Search method | Screenshot Search (default) | Uses screenshots and mouse input without reading game memory |
| Search method | Precise Search | Reads game memory to plan palette movements |
| Matching requirement | Exact HEX | Requires an identical six-digit color code |
| Matching requirement | Similar | Uses the region's color-difference tolerance; lower values require a closer match |

Screenshot Search has relatively lower risk. Precise Search reads game memory and carries higher risk, including detection or account penalties. Screenshots and automated mouse input do not guarantee account safety either.

The tool first looks for a combination that meets all enabled targets. Otherwise it compares results in your priority order. Two-region palettes automatically exclude the absent third region without changing its saved settings.

## 3. Read the result

- **Targets met:** review the actual game HEX values and decide whether to apply them in the game.
- **Not all targets met:** review current colors and each region's difference, then adjust, retry or use the result.
- **Last measured colors (current state unconfirmed):** these are earlier readings; check the current game view.

When not all targets are met, compromise selection follows your region priorities and considers overall color difference, hue and saturation to better preserve the character of your target colors. Displayed differences, Similar tolerances and Exact HEX requirements remain unchanged.

The palette may remain still during calculation. The overlay shows the current stage and colors already read.

Colors, matching requirements and priorities save automatically. **Save preset** stores named settings that you can edit, load or delete. Load an edited preset to use it for the current search. Search history and presets are stored separately.

## 4. Stop or retry

- **F9 / Stop:** ends automatic input. Check the current colors in the game.
- **F7 / Retry search (Testing only):** zooms out and searches again in the same round, using its remaining time and target settings. It does not reset the countdown or use another dye item.

The tool does not open dyeing, confirm, apply or cancel a result automatically.

## 5. Update

Choose **Check for updates** in the main window, then **Download update** when a new version is available. Once downloaded, choose **Install and restart**. Settings, presets and records are kept.

If you cannot reach GitHub, obtain `UPDATE-ONLY-ColorStudio-0.4.9-win-x64.zip` and choose **Import offline update** in the app. Use the full installation package for a first install.

[Online, offline and manual updates](docs/automatic-updates.en.md) · [What's new in 0.4.9](docs/release-notes-0.4.9.md)

## Help and feedback

- **Game window missing:** open the game, select its server and refresh the window list.
- **Access denied:** use the same privilege level for the tool and game. If the game runs as administrator, reopen the tool as administrator.
- **Window moved or resized:** stop with F9, then start with F8 to detect the current window again.
- **Report a problem:** attach the session log to [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues). You do not need another dye round just to report it.

Data normally lives in `data` beside the app. If that folder is not writable, the app uses `%LOCALAPPDATA%\MabinogiMobileColorStudio\data`, or a temporary folder when necessary. For a manual move, copy the data folder actually in use.

[Server guide](docs/server-adaptation/server-selection.md) · [Development and tests](TESTING.md)

By **MinamiChiwa** · [Afdian](https://afdian.com/a/minamichiwa) · [Patreon](https://patreon.com/chiwaminami). Donations are optional and do not affect features. Developed with AI assistance.
