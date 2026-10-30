# 更新指南

[简体中文](automatic-updates.md) · [繁體中文](automatic-updates.zh-TW.md) · [English](automatic-updates.en.md) · [日本語](automatic-updates.ja.md) · [한국어](automatic-updates.ko.md)

## 选择正确的文件

首次安装或手动升级，请从 [GitHub Releases](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases) 下载完整包 `ColorStudio-v<版本>-Windows-x64.zip`，完整解压后运行。已安装的工具使用下方的在线更新，无需手动下载发布页的 `blob-` 文件或清单。

## 在线更新

> 工具会先通过镜像站 `v6.gh-proxy.org` 下载官方发布文件，镜像不可用时自动改为直连 GitHub。镜像只负责传输：清单必须通过内置公钥的签名验证，每个文件都会核对 SHA-256，被篡改的内容会被拒绝。

1. 在主界面点击**检查更新**。检查本身不会下载或安装。
2. 发现新版本后点击**下载更新**。工具只下载需要替换或补充的文件。
3. 下载完成后点击**安装并重启**。先结束寻色、吸管或窗口选择操作。
4. 工具会重新打开，设置、方案、历史和截图保留。

可在更新窗口关闭启动后的自动检查，或允许检查候选版本。下载可取消，之后可继续。

## 手动升级与保留设置

无法在线更新时，退出旧工具，将完整安装包解压到新的可写本地目录，再复制旧工具**实际使用的数据目录**到新目录的 `data`。数据通常位于程序旁；不可写时可能位于 `%LOCALAPPDATA%\MabinogiMobileColorStudio\data` 或临时目录。

保留旧目录，确认新工具正常启动和设置正确后再整理。不要只复制一个 EXE，`_internal` 和独立更新程序也需要保留。

## 更新遇到问题

- **无法联网**：镜像与 GitHub 都无法连接时稍后重试，或按上方方法手动升级。
- **文件被占用或权限不足**：退出同目录的工具副本；必要时把完整包解压到可写本地目录。
- **更新验证失败**：重新获取官方包；保留日志，不要手动修改签名或程序文件。
- **旧版 安装超时**：旧更新器可能误判程序仍在运行。若已下载且尚未替换文件，可使用 [0.4.4 发布页](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/tag/v0.4.4) 的 `ColorStudio-Update-Recovery-v0.4.4.zip`，关闭工具后运行 `Recover-Update.cmd` 并选择原安装目录。无适用更新记录时，使用完整包手动升级并保留数据。

安装失败时先查看当前版本和更新记录；需要协助可在 [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) 附日志。

[返回使用说明](../README.md) · [0.4.9 更新内容](release-notes-0.4.9.md)
