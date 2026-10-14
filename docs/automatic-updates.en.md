# Update guide

[简体中文](automatic-updates.md) · [繁體中文](automatic-updates.zh-TW.md) · [English](automatic-updates.en.md) · [日本語](automatic-updates.ja.md) · [한국어](automatic-updates.ko.md)

## Choose the right file

| Purpose | File | How to use it |
|---|---|---|
| First install or manual upgrade | `ColorStudio-v0.4.6-Windows-x64.zip` | Extract the entire package and run the app |
| Full offline update | `UPDATE-ONLY-ColorStudio-0.4.6-win-x64.zip` | Import in an existing installation |
| Update from official 0.4.5 | `UPDATE-ONLY-ColorStudio-from-0.4.5-to-0.4.6-win-x64.zip` | Only for matching files from official 0.4.5 |
| Update from official 0.4.4 | `UPDATE-ONLY-ColorStudio-from-0.4.4-to-0.4.6-win-x64.zip` | Only for matching files from the final corrected official 0.4.4 |

**UPDATE-ONLY packages are not for first installs and cannot be extracted and run directly.** If the smaller delta does not match, use the full offline update. You do not need to download individual `blob-` files from the release page.

## Online update

1. Choose **Check for updates** in the main window. Checking does not download or install anything.
2. Choose **Download update** when a new version is available. Only needed replacement or missing files are downloaded.
3. Once downloaded, choose **Install and restart**. Finish searching, picking a color or selecting a window first.
4. The app reopens with settings, presets, history and screenshots kept.

The update window lets you disable automatic startup checks or include prereleases. Downloads can be cancelled and resumed later.

## Offline update

If GitHub is unavailable, download a full offline update on another computer and copy it over. Choose **Import offline update**, select the ZIP, then choose **Install and restart** after verification.

Offline updates need an existing app with the updater. For older versions without it, follow the manual upgrade below.

## Manual upgrade and data

Close the old app and extract the full installation package to a new writable local folder. Copy the old app's **actual data folder** into the new folder as `data`. It is usually beside the app, but may be at `%LOCALAPPDATA%\MabinogiMobileColorStudio\data` or in a temporary folder when the original location is not writable.

Keep the old folder until the new app starts and your settings are correct. Do not copy only the EXE; keep `_internal` and the separate updater too.

## Troubleshooting updates

- **Cannot connect:** retry later or use a full offline update.
- **Delta package does not match:** use a full offline update.
- **Files in use or access denied:** close other copies from the same folder, or extract the full package to a writable local folder.
- **Verification failed:** obtain the official package again and keep the logs. Do not edit signatures or program files manually.
- **Installation times out on 0.4.3 or early 0.4.4:** the old updater may think the app is still running. If the update was downloaded but files have not been replaced, use `ColorStudio-Update-Recovery-v0.4.4.zip` from the [0.4.4 release](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/tag/v0.4.4). Close the app, run `Recover-Update.cmd` and select the original installation folder. If there is no suitable pending update, upgrade manually with the full package and keep your data.

Check the current version and update records after a failed installation. Attach logs to [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) if you need help.

[Back to the user guide](../README.en.md) · [What's new in 0.4.6](release-notes-0.4.6.md)
