# Update guide

[简体中文](automatic-updates.md) · [繁體中文](automatic-updates.zh-TW.md) · [English](automatic-updates.en.md) · [日本語](automatic-updates.ja.md) · [한국어](automatic-updates.ko.md)

## Choose the right file

For a first install or a manual upgrade, download the full package `ColorStudio-v<version>-Windows-x64.zip` from [GitHub Releases](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases), extract all of it and run the app. Installed copies use the online update below; you never need to download `blob-` files or the manifest yourself.

## Online update

> The app downloads official release files through the mirror `v6.gh-proxy.org` first and switches to GitHub directly when the mirror is unavailable. The mirror only carries the bytes: the manifest must pass the signature check against the built-in public key and every file is checked by SHA-256, so altered content is rejected.

1. Choose **Check for updates** in the main window. Checking does not download or install anything.
2. Choose **Download update** when a new version is available. Only needed replacement or missing files are downloaded.
3. Once downloaded, choose **Install and restart**. Finish searching, picking a color or selecting a window first.
4. The app reopens with settings, presets, history and screenshots kept.

The update window lets you disable automatic startup checks or include prereleases. Downloads can be cancelled and resumed later.

## Manual upgrade and data

If online update is not possible, close the old app and extract the full installation package to a new writable local folder. Copy the old app's **actual data folder** into the new folder as `data`. It is usually beside the app, but may be at `%LOCALAPPDATA%\MabinogiMobileColorStudio\data` or in a temporary folder when the original location is not writable.

Keep the old folder until the new app starts and your settings are correct. Do not copy only the EXE; keep `_internal` and the separate updater too.

## Troubleshooting updates

- **Cannot connect:** if neither the mirror nor GitHub is reachable, retry later or upgrade manually as described above.
- **Files in use or access denied:** close other copies from the same folder, or extract the full package to a writable local folder.
- **Verification failed:** obtain the official package again and keep the logs. Do not edit signatures or program files manually.
- **Installation times out on older versions:** the old updater may think the app is still running. If the update was downloaded but files have not been replaced, use `ColorStudio-Update-Recovery-v0.4.4.zip` from the [0.4.4 release](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/tag/v0.4.4). Close the app, run `Recover-Update.cmd` and select the original installation folder. If there is no suitable pending update, upgrade manually with the full package and keep your data.

Check the current version and update records after a failed installation. Attach logs to [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) if you need help.

[Back to the user guide](../README.en.md) · [What's new in 0.4.9](release-notes-0.4.9.md)
