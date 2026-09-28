# 染色工坊 0.3.1 / Color Studio 0.3.1

## 简体中文

本工具由AI辅助完成。

### 更新内容

- 修复部分 Windows 语言环境或中文路径下，点击开始后出现编码错误并停止的问题。正式包内置 OCR 及英文识别数据，无需另行安装。
- 改善启动等待：等待游戏窗口或染色倒计时不再因固定等待时限结束；无法自动切回游戏时，可手动激活游戏窗口继续识别。临时识别失败会重试，避免一次异常导致整局识别不可用。
- 补齐简体中文、繁體中文和 English 的运行进度、候选执行及异常提示。主窗口、浮窗和已打开的信息窗口支持即时切换语言，无需重启。
- 改善高 DPI 下的窗口尺寸、屏幕取色坐标和多屏位置计算，修复部分信息窗口初次打开过小的问题。浮窗内容可滚动，标题和 F9 停止按钮保持可见。
- 旧会话清理改为后台执行，避免开始时阻塞界面；增加会话名称冲突保护。安装目录不可写时，依次尝试用户本地数据目录和系统临时目录。
- 同步整理三语说明文档、赞助说明和验证范围。正式包不包含本地配置、截图、诊断记录或历史会话。

### 使用与注意事项

1. 下载 `ColorStudio-v0.3.1.zip`，退出旧版本并解压到独立文件夹。保留 `ColorStudio.exe` 与 `_internal` 文件夹在同一目录。
2. 游戏使用 **1280 × 960 窗口模式**。4K 显示器也使用相同游戏设置，无需修改桌面分辨率。选择目标窗口与颜色后，按 F8 或点击开始；浮窗出现后手动进入游戏染色倒计时界面。
3. 启动后请保持游戏处于前台，并在染色倒计时界面等待程序完成。需要中止时按 F9；如果游戏窗口位置或大小发生变化，请停止后重新开始。程序完成定位后会显示游戏内 HEX，请在游戏中确认结果并手动套用。
4. 候选先按精准命中区域数排序，命中数相同时依次比较所有启用区域的最大色差和平均色差。相似模式使用各区设定的容差；没有全部达标的候选时仍会定位最接近的可执行妥协方案。
5. 截图预测仍可能与实际游戏 HEX 不同，最终结果以游戏 HEX 复核为准。搜索不保证每次精准命中、满足全部容差或获得全局最优组合。

### 验证范围

回归测试共 420 项：403 项通过，17 项因缺少本地测试素材而跳过，0 项失败。布局计算矩阵覆盖 1024×768、1920×1080、3840×2160、5120×2880，以及 100%、125%、150%、200%、250% DPI；另有物理像素坐标、负坐标多屏和三语测试。这些检查不代表所有 4K、多屏及混合 DPI 配置均已完成实机游戏验证。

## 繁體中文

本工具由AI協助完成。

### 更新內容

- 修正部分 Windows 語言環境或中文路徑下，點選開始後發生編碼錯誤並停止的問題。正式版內含 OCR 與英文辨識資料，不必另行安裝。
- 改善啟動等待：等待遊戲視窗或染色倒數時，不再因固定等待時限而結束；無法自動切回遊戲時，可手動將遊戲視窗切至前景以繼續辨識。暫時辨識失敗會重試，避免單次異常使整局無法辨識。
- 補齊簡體中文、繁體中文與 English 的執行進度、候選執行及異常提示。主視窗、浮窗與已開啟的資訊視窗支援即時切換語言，不必重新啟動。
- 改善高 DPI 下的視窗尺寸、螢幕取色座標與多螢幕位置計算，修正部分資訊視窗初次開啟過小的問題。浮窗內容可捲動，標題與 F9 停止按鈕保持可見。
- 舊工作階段清理改為背景執行，避免開始時介面停頓；新增工作階段名稱衝突保護。安裝目錄無法寫入時，依序嘗試使用者本機資料目錄與系統暫存目錄。
- 同步整理三語說明文件、贊助說明與驗證範圍。正式版壓縮包不包含本機設定、截圖、診斷記錄或歷史工作階段。

### 使用與注意事項

1. 下載 `ColorStudio-v0.3.1.zip`，結束舊版本後解壓縮至獨立資料夾。請將 `ColorStudio.exe` 與 `_internal` 資料夾保留在同一目錄。
2. 遊戲使用 **1280 × 960 視窗模式**。4K 螢幕亦使用相同遊戲設定，不必修改桌面解析度。選擇目標視窗與顏色後，按 F8 或點選開始；浮窗出現後手動進入遊戲染色倒數介面。
3. 啟動後請保持遊戲在前景，並在染色倒數介面等待程式完成。需要中止時按 F9；若遊戲視窗位置或大小發生變更，請停止後重新開始。程式完成定位後會顯示遊戲內 HEX，請在遊戲中確認結果並手動套用。
4. 候選先依精準命中區域數排序，命中數相同時依序比較所有啟用區域的最大色差與平均色差。相似模式使用各區設定的容差；沒有全部達標的候選時，仍會定位最接近且可執行的折衷方案。
5. 截圖預測仍可能與遊戲實際 HEX 不同，最終結果以遊戲 HEX 複核為準。搜尋不保證每次精準命中、符合所有容差或取得全域最佳組合。

### 驗證範圍

迴歸測試共 420 項：403 項通過，17 項因缺少本機測試素材而略過，0 項失敗。版面計算矩陣涵蓋 1024×768、1920×1080、3840×2160、5120×2880，以及 100%、125%、150%、200%、250% DPI；另有實體像素座標、負座標多螢幕與三語測試。這些檢查不代表所有 4K、多螢幕及混合 DPI 設定均已完成實機遊戲驗證。

## English

This tool was developed with AI assistance.

### Changes

- Fixed a startup encoding error affecting some Windows language settings and installation paths containing Chinese characters. OCR and English recognition data are included; no separate installation is required.
- Improved startup waiting. Waiting for the game window or dye countdown no longer ends after a fixed timeout. If automatic activation fails, bringing the game to the foreground manually allows detection to continue. Temporary recognition failures are retried without disabling OCR for the rest of the run.
- Completed Simplified Chinese, Traditional Chinese and English messages for progress, candidate execution and errors. The main window, overlay and open information dialogs switch languages without restarting.
- Improved high-DPI window sizing, screen color-picking coordinates and multi-monitor positioning. Fixed information dialogs opening too small. Overlay content scrolls while the title and F9 stop button remain visible.
- Moved old-session cleanup to the background to avoid blocking the interface at startup, and prevented session-name collisions. If the installation directory is not writable, the tool tries the user's local data directory, then the system temporary directory.
- Updated all three user guides, sponsorship information and validation scope. Release archives exclude local settings, captures, diagnostic records and session history.

### Usage and notes

1. Download `ColorStudio-v0.3.1.zip`, close the previous version and extract into a separate folder. Keep `ColorStudio.exe` beside the `_internal` folder.
2. Use **1280 × 960 windowed mode** in the game, including on a 4K display. The desktop resolution does not need to change. Select the game window and target colors, then press F8 or click Start. Open the timed dye screen manually after the overlay appears.
3. After starting, keep the game in the foreground and wait on the timed dye screen until the tool finishes. Press F9 to stop. If the game window is moved or resized, stop and start again. After positioning, the tool shows the in-game HEX; review the result in the game and apply it manually.
4. Candidates rank first by exact-match count, then by maximum and average color difference across all enabled regions. Similar mode uses each region's configured tolerance. If no candidate meets every setting, the tool still positions the closest executable compromise.
5. Screenshot predictions may still differ from actual in-game HEX values. In-game HEX verification determines the reported result. Searches cannot guarantee an exact match, satisfaction of every tolerance or a global optimum.

### Validation scope

The regression suite contains 420 tests: 403 passed, 17 were skipped because local fixtures were unavailable, and none failed. The layout calculation matrix covers 1024×768, 1920×1080, 3840×2160 and 5120×2880 at 100%, 125%, 150%, 200% and 250% DPI. Separate tests cover physical-pixel coordinates, monitors with negative coordinates and all three interface languages. These checks do not establish real-game validation for every 4K, multi-monitor or mixed-DPI setup.
