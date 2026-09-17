# 染色工坊 · 瑪奇 Mobile

作者：**南千和** · [愛發電支援作者](https://afdian.com/a/minamichiwa)

適用於**港澳臺服瑪奇Mobile**的自動染色工具。於 Windows 執行，透過遊戲畫面識別與滑鼠操作，尋找三個染色區域的目標顏色。

> 在遊戲中使用本程式存在風險，請使用者自行斟酌。

[簡體中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

## 使用

從 Releases 下載完整壓縮包，解壓後執行 `ColorStudio.exe`，保留旁邊的 `_internal` 資料夾。

1. 啟用需要匹配的區域，輸入 HEX 或使用選色器、螢幕吸管；可以填寫替代顏色。
2. 選擇精準模式或相似模式。推薦先從相似模式 ΔE 8–12 開始，色差越小越接近目標。
3. 在遊戲中使用普通染色劑，教學結束後按 **F8** 開始；**F9** 停止。

相似模式進入容差範圍後仍繼續尋找更接近的組合。除所有啟用區域命中目標原色外，剩餘約 30 秒返回本輪最佳組合。工具會複核遊戲色碼，完成後彈窗提示，由玩家決定是否使用妥協顏色。

精準模式遇到接近顏色會以該色塊為縮放中心分批放大。旋轉以右鍵按下處為圓心，縮放以滑鼠位置為支點。視窗位置或大小在執行期間改變會停止尋色，需要重新按 F8。

介面右上角可選擇簡體中文、繁體中文或 English；切換時儲存方案並重新開啟程式。

## 預覽與記錄

- 主介面顯示有序色塊概覽，點選開啟完整允許顏色集合。
- 大圖支援縮放、拖動、滾動及懸停檢視 HEX，不需要翻頁。
- 尋色記錄儲存最近 50 次結果，包含三色組合、各區 ΔE、最大和平均色差。
- 自動複核套用預設關閉。精準模式的色差滑條不可用。
- 本機配置、記錄及診斷截圖存放在程式旁的 `data` 資料夾。

## 開發

Windows 10/11，Python 3.12。原始碼位於 `work/studio`。

```powershell
python -m pip install -r requirements-build.txt
python work/studio/app.py
python -m unittest discover -s work/studio -p "test_*.py"
```

原始碼執行與構建還需要安裝 Tesseract OCR（含 `eng.traineddata`）。預設位置為 `C:/Program Files/Tesseract-OCR`；構建時可設定 `TESSERACT_HOME`。

```powershell
python work/studio/build_release.py
```

產物在 `outputs/release/ColorStudio`。現有釋出目錄的個人資料會備份到 `work/studio/release-test-data`，不會提交到倉庫。遊戲實拍迴歸素材屬於本機測試資料，未隨倉庫分發；缺少這些素材時相關測試會顯示跳過。

## 驗證範圍

見 [VALIDATION.md](VALIDATION.md)。有限時間內的搜尋不保證每次找到精準顏色或全域性最優組合；當前實機驗證不覆蓋所有 DPI 與顯示器組合。
