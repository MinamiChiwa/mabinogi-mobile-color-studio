# 染色工坊 0.3.0 / Color Studio 0.3.0

## 简体中文

本工具由AI辅助完成。

### 更新内容

- 增加滚轮档位残差修正：当目标位置位于两个滚轮档位之间，且三个取色点仍处于安全定位范围内时，程序会通过受限平移完成修正。
- 保留游戏内 HEX 复核流程；完成定位后请在游戏中确认结果，再手动套用。
- 增加历史会话清理：仅保留最近 20 次会话；超过 30 天、超过 512 MiB 或超过保留数量的旧会话可被清理；正在进行和最近 5 分钟内的会话受到保护。
- 正式发布包不包含本地配置、截图、诊断记录和历史搜索数据。
- 同步更新简体中文、繁体中文和英文界面及说明文档。

### 已知限制

当前版本可以准确定位色板，但截图颜色预测仍可能与游戏实际 HEX 存在偏差。程序会显示游戏内复核结果；未达到目标时不会自动套用。详细测量结果见验证报告。

### 使用说明

下载完整 Windows 压缩包，解压后保留 `ColorStudio.exe` 与 `_internal` 文件夹在同一目录。将游戏窗口设置为 1280 × 960，按 F8 或点击启动，待浮窗出现后手动进入游戏内限时染色界面；按 F9 可停止操作。

## 繁體中文

本工具由AI協助完成。

### 更新內容

- 新增滾輪檔位殘差修正：當目標位置位於兩個滾輪檔位之間，且三個取色點仍處於安全定位範圍內時，程式會透過受限平移完成修正。
- 保留遊戲內 HEX 複核流程；完成定位後請在遊戲中確認結果，再手動套用。
- 新增歷史工作階段清理：僅保留最近 20 次工作階段；超過 30 天、超過 512 MiB 或超過保留數量的舊工作階段可被清理；進行中及最近 5 分鐘內的工作階段受到保護。
- 正式發布包不包含本機設定、截圖、診斷記錄及歷史搜尋資料。
- 同步更新繁體中文、簡體中文及英文介面與說明文件。

### 已知限制

目前版本可以準確定位色板，但截圖顏色預測仍可能與遊戲實際 HEX 存在偏差。程式會顯示遊戲內複核結果；未達到目標時不會自動套用。詳細測量結果請參閱驗證報告。

### 使用說明

下載完整 Windows 壓縮包，解壓後將 `ColorStudio.exe` 與 `_internal` 資料夾保留在同一目錄。將遊戲視窗設定為 1280 × 960，按 F8 或點選啟動；浮窗出現後，手動進入遊戲內限時染色介面；按 F9 可停止操作。

## English

This tool was developed with AI assistance.

### Updates

- Added measured wheel-detent residual correction. When a target lies between two wheel detents and all three markers remain within the safe positioning gate, a bounded translation completes the correction.
- Preserved in-game HEX verification; review the result in the game and apply it manually after positioning.
- Added bounded session cleanup. The latest 20 sessions are retained; sessions older than 30 days, beyond 512 MiB or beyond the retention count may be removed. Active sessions and sessions from the last five minutes are protected.
- Release packages exclude local settings, screenshots, diagnostic traces and search history.
- Synchronized the Simplified Chinese, Traditional Chinese and English interface text and documentation.

### Known limitation

This version can position the board accurately, while screenshot color predictions may still differ from the game’s actual HEX values. The tool displays the verified in-game result and never applies a result that misses the target. See the validation report for measured evidence.

### Usage

Download the complete Windows archive and keep `ColorStudio.exe` beside the `_internal` folder. Set the game window to 1280 × 960, press F8 or click Start, then open the timed dye screen manually after the overlay appears. Press F9 to stop input.
