# 更新指南

[简体中文](automatic-updates.md) · [繁體中文](automatic-updates.zh-TW.md) · [English](automatic-updates.en.md) · [日本語](automatic-updates.ja.md) · [한국어](automatic-updates.ko.md)

## 選擇正確的檔案

| 用途 | 檔案 | 操作 |
|---|---|---|
| 首次安裝或手動升級 | `ColorStudio-v0.4.6-Windows-x64.zip` | 完整解壓縮後執行 |
| 完整離線更新 | `UPDATE-ONLY-ColorStudio-0.4.6-win-x64.zip` | 在已安裝的工具內匯入 |
| 從官方 0.4.5 更新 | `UPDATE-ONLY-ColorStudio-from-0.4.5-to-0.4.6-win-x64.zip` | 僅適用於檔案相符的官方 0.4.5 |
| 從官方 0.4.4 更新 | `UPDATE-ONLY-ColorStudio-from-0.4.4-to-0.4.6-win-x64.zip` | 僅適用於檔案相符的官方最終修訂版 0.4.4 |

**UPDATE-ONLY 不能用於首次安裝，也不能直接解壓縮執行。** 小型差異套件不適用時，請用完整離線更新套件。不必手動下載發布頁的 `blob-` 檔案。

## 線上更新

1. 在主畫面點選**檢查更新**。檢查本身不會下載或安裝。
2. 發現新版本後選擇**下載更新**。工具只下載需要替換或補充的檔案。
3. 完成後按**安裝並重新啟動**。請先結束尋色、滴管或視窗選擇操作。
4. 工具會重新開啟，設定、方案、歷史及截圖會保留。

可在更新視窗關閉啟動後的自動檢查，或允許檢查候選版本。下載可取消，之後可繼續。

## 離線更新

無法連線至 GitHub 時，可用另一台電腦下載完整離線更新套件，再複製過來。在工具內選擇**匯入離線更新**，選取 ZIP；驗證完成後按**安裝並重新啟動**。

完整離線套件適用於已有更新功能的工具。沒有更新功能的舊版，請使用下方手動升級方式。

## 手動升級與保留設定

關閉舊工具，將完整安裝套件解壓縮到新的可寫本機目錄，再把舊工具**實際使用的資料目錄**複製到新目錄的 `data`。資料通常存在程式旁；無法寫入時可能存在 `%LOCALAPPDATA%\MabinogiMobileColorStudio\data` 或暫存目錄。

請保留舊目錄，確認新工具正常啟動、設定正確後再整理。不要只複製 EXE，`_internal` 與獨立更新程式也需要保留。

## 更新遇到問題

- **無法連線**：稍後重試或使用完整離線更新套件。
- **差異套件不相符**：改用完整離線更新套件。
- **檔案被占用或權限不足**：關閉同目錄的工具副本；必要時將完整套件解壓縮到可寫本機目錄。
- **更新驗證失敗**：重新取得官方套件並保留紀錄，不要手動修改簽名或程式檔案。
- **0.4.3 或早期 0.4.4 安裝逾時**：舊更新器可能誤判程式仍在執行。若已下載且尚未替換檔案，可使用 [0.4.4 發布頁](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/tag/v0.4.4) 的 `ColorStudio-Update-Recovery-v0.4.4.zip`，關閉工具後執行 `Recover-Update.cmd` 並選取原安裝目錄。沒有適用更新紀錄時，請手動升級完整套件並保留資料。

安裝失敗時先確認目前版本及更新紀錄；需要協助可在 [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) 附上紀錄。

[返回使用說明](../README.zh-TW.md) · [0.4.6 更新內容](release-notes-0.4.6.md)
