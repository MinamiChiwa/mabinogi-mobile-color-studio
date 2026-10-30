# 更新指南

[简体中文](automatic-updates.md) · [繁體中文](automatic-updates.zh-TW.md) · [English](automatic-updates.en.md) · [日本語](automatic-updates.ja.md) · [한국어](automatic-updates.ko.md)

## 選擇正確的檔案

首次安裝或手動升級，請從 [GitHub Releases](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases) 下載完整套件 `ColorStudio-v<版本>-Windows-x64.zip`，完整解壓縮後執行。已安裝的工具請使用下方的線上更新，不必手動下載發布頁的 `blob-` 檔案或清單。

## 線上更新

> 工具會先透過鏡像站 `v6.gh-proxy.org` 下載官方發布檔案，鏡像無法使用時自動改為直連 GitHub。鏡像只負責傳輸：清單必須通過內建公鑰的簽章驗證，每個檔案都會核對 SHA-256，遭竄改的內容會被拒絕。

1. 在主畫面點選**檢查更新**。檢查本身不會下載或安裝。
2. 發現新版本後選擇**下載更新**。工具只下載需要替換或補充的檔案。
3. 完成後按**安裝並重新啟動**。請先結束尋色、滴管或視窗選擇操作。
4. 工具會重新開啟，設定、方案、歷史及截圖會保留。

可在更新視窗關閉啟動後的自動檢查，或允許檢查候選版本。下載可取消，之後可繼續。

## 手動升級與保留設定

無法線上更新時，關閉舊工具，將完整安裝套件解壓縮到新的可寫本機目錄，再把舊工具**實際使用的資料目錄**複製到新目錄的 `data`。資料通常存在程式旁；無法寫入時可能存在 `%LOCALAPPDATA%\MabinogiMobileColorStudio\data` 或暫存目錄。

請保留舊目錄，確認新工具正常啟動、設定正確後再整理。不要只複製 EXE，`_internal` 與獨立更新程式也需要保留。

## 更新遇到問題

- **無法連線**：鏡像與 GitHub 都無法連線時請稍後重試，或依上方方式手動升級。
- **檔案被占用或權限不足**：關閉同目錄的工具副本；必要時將完整套件解壓縮到可寫本機目錄。
- **更新驗證失敗**：重新取得官方套件並保留紀錄，不要手動修改簽名或程式檔案。
- **舊版 安裝逾時**：舊更新器可能誤判程式仍在執行。若已下載且尚未替換檔案，可使用 [0.4.4 發布頁](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/releases/tag/v0.4.4) 的 `ColorStudio-Update-Recovery-v0.4.4.zip`，關閉工具後執行 `Recover-Update.cmd` 並選取原安裝目錄。沒有適用更新紀錄時，請手動升級完整套件並保留資料。

安裝失敗時先確認目前版本及更新紀錄；需要協助可在 [GitHub Issues](https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/issues) 附上紀錄。

[返回使用說明](../README.zh-TW.md) · [0.4.9 更新內容](release-notes-0.4.9.md)
