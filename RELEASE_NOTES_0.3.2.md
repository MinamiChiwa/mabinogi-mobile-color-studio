# 染色工坊 0.3.2 / Color Studio 0.3.2

## 简体中文

本工具由AI辅助完成。

### 更新内容

- 修复游戏原生缩放到达边界、图像配准失败或单次动作未能确认时直接弹出错误并结束流程的问题。程序会优先复查当前画面并尝试可安全执行的备用方案；无法可靠确认时停止继续输入并保留当前画面。
- 修复恢复状态数据不完整导致浮窗再次报错的问题。浮窗会显示当前已读取的游戏色码和处理状态。
- 保留 F9、游戏失去焦点、窗口位置或尺寸变化及游戏倒计时安全截止保护；这些情况下会释放鼠标并停止输入。
- 主窗口标题和品牌区域增加版本号 `v0.3.2`。
- 补齐本轮新增状态提示的简体中文、繁體中文和 English 文案。

### 使用与注意事项

1. 下载 `ColorStudio-v0.3.2.zip`，退出旧版本并解压到独立文件夹。保留 `ColorStudio.exe` 与 `_internal` 文件夹在同一目录。
2. 使用 1280 × 960 窗口模式进入游戏染色界面，按 F8 或点击开始。浮窗出现后手动进入限时染色界面。
3. 自动移动期间请勿操作鼠标。程序遇到无法确认的动作会保留游戏当前画面；请根据浮窗显示的色码在游戏内确认是否套用。
4. 截图预测仍可能与游戏实际 HEX 存在偏差，最终结果以游戏 HEX 复核为准。程序不会自动点击套用、确认或取消。

### 验证范围

本版本回归测试共 425 项：全部通过，其中 17 项因缺少本地游戏素材而跳过。自动化测试覆盖恢复路径、备用候选、滚轮边界、F9 保护、三语运行提示、高 DPI 布局和数据清理。自动化验证不代表所有 4K、多屏及混合 DPI 环境均已完成实机游戏验证。

## 繁體中文

本工具由AI協助完成。

### 更新內容

- 修正遊戲原生縮放到達邊界、影像對齊失敗或單次操作無法確認時直接顯示錯誤並結束流程的問題。程式會先複核目前畫面並嘗試可安全執行的備用方案；無法可靠確認時停止後續輸入並保留目前畫面。
- 修正復原狀態資料不完整導致浮窗再次報錯的問題。浮窗會顯示目前已讀取的遊戲色碼與處理狀態。
- 保留 F9、遊戲失去焦點、視窗位置或尺寸變更及遊戲倒數安全期限保護；這些情況會釋放滑鼠並停止輸入。
- 主視窗標題與品牌區域新增版本號 `v0.3.2`。
- 補齊本輪新增狀態提示的簡體中文、繁體中文與 English 文案。

### 使用與注意事項

1. 下載 `ColorStudio-v0.3.2.zip`，結束舊版本後解壓縮至獨立資料夾。請將 `ColorStudio.exe` 與 `_internal` 資料夾保留在同一目錄。
2. 使用 1280 × 960 視窗模式進入遊戲染色介面，按 F8 或點選開始。浮窗出現後手動進入限時染色介面。
3. 自動移動期間請勿操作滑鼠。程式遇到無法確認的操作時會保留遊戲目前畫面；請依浮窗顯示的色碼在遊戲內確認是否套用。
4. 截圖預測仍可能與遊戲實際 HEX 有差異，最終結果以遊戲 HEX 複核為準。程式不會自動點擊套用、確認或取消。

### 驗證範圍

本版本回歸測試共 425 項：全部通過，其中 17 項因缺少本機遊戲素材而略過。自動化測試涵蓋復原流程、備用候選、滾輪邊界、F9 保護、三語執行提示、高 DPI 版面與資料清理。自動化驗證不代表所有 4K、多螢幕及混合 DPI 環境均已完成實機遊戲驗證。

## English

This tool was developed with AI assistance.

### Changes

- Fixed a workflow failure where reaching the game's native zoom boundary, image registration failure or an unverified gesture opened an error and ended the run. The tool now rechecks the current frame and tries a safe fallback candidate; when the pose cannot be verified, it stops sending input and keeps the current frame.
- Fixed incomplete recovery data that could cause the overlay to fail while displaying the recovery state. The overlay now shows the game HEX values that were read and the current handling state.
- Retained F9, focus loss, window geometry changes and the game countdown safety deadline as input protections. These conditions release the mouse and stop further input.
- Added version `v0.3.2` to the main window title and brand area.
- Added Simplified Chinese, Traditional Chinese and English text for the new recovery states.

### Usage and notes

1. Download `ColorStudio-v0.3.2.zip`, close the previous version and extract it into a separate folder. Keep `ColorStudio.exe` beside the `_internal` folder.
2. Use 1280 × 960 windowed mode in the game, press F8 or click Start, then open the timed dye screen manually after the overlay appears.
3. Do not operate the mouse during automatic movement. If an action cannot be verified, the tool keeps the current game frame; use the HEX values shown in the overlay to decide whether to apply the result in the game.
4. Screenshot predictions may differ from actual in-game HEX values. In-game HEX verification is authoritative. The tool does not click Apply, Confirm or Cancel automatically.

### Validation scope

This release passed all 425 regression tests; 17 tests were skipped because local game fixtures were unavailable. Automated coverage includes recovery paths, fallback candidates, native wheel boundaries, F9 protection, three-language runtime messages, high-DPI layout and data cleanup. Automated checks do not establish real-game validation for every 4K, multi-monitor or mixed-DPI environment.
