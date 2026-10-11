# 0.4.2rc2 — 本局重试与跨电脑修复

## 简体中文

- 精准模式移除预测候选列表，改为浮窗「重新寻色」和 F7。停止当前搜索、释放鼠标并缩小画板至最大可见范围后，在同局重新搜索。
- 修复屏幕吸管的 DPI/多屏坐标混用；冻结截图与物理鼠标坐标逐像素对应，去除全屏及强制前台，禁止定位非本工具窗口。
- 修复100px色码卡识别和强字模色块边界，提高原失败截图复核速度。计时证据可靠时，仅对已打开色板的保守截止最多校正20秒。
- 修复释放左键失败后漏释放右键，以及最终无法重新读取时保留旧达标状态的问题。三语界面和教程同步更新。
- 加速完整色板扫描并复用读取缓冲区，仍保留全量检查、唯一性确认和最终重验。
- 倒计时宽限从首次发现本局色板开始计算；仅用宽限后的可靠递减读数调整执行截止，早期误读不会直接停止路线。
- 分别记录色板关闭、会话变化和暂时读取不一致。当前无法确认时，显示「上次实测（当前未确认）」，不会将历史颜色记成当前达标。

重试不增加游戏时间、不消耗新道具，不自动开启或套用染色。预测和有限搜索不能保证多色精准成功。该本地候选版尚未完成新一局实机验收。

## 繁體中文

- 精準模式移除預測候選清單，改為浮窗「重新尋色」與 F7。停止目前搜尋、釋放滑鼠並縮小色板至最大可見範圍後，在同局重新搜尋。
- 修復螢幕吸管的 DPI／多螢幕座標混用；凍結截圖與實體滑鼠座標逐像素對應，移除全螢幕與強制前景，禁止定位非本工具視窗。
- 修復100px色碼卡辨識與強字模色塊邊界，提高原失敗截圖複核速度。計時證據可靠時，僅對已開啟色板的保守截止最多校正20秒。
- 修復左鍵釋放失敗後漏釋放右鍵，以及最後無法重新讀取時保留舊達標狀態的問題。三語介面與教學同步更新。
- 加速完整色板掃描並重用讀取緩衝區，仍保留全量檢查、唯一性確認與最終重驗。
- 倒數計時寬限從首次發現本局色板開始計算；僅使用寬限後可靠的遞減讀數調整執行截止，早期誤讀不會直接停止路線。
- 分別記錄色板關閉、會話變化與暫時讀取不一致。無法確認目前狀態時，顯示「上次實測（目前未確認）」，不會將歷史顏色記為目前達標。

重試不增加遊戲時間、不消耗新道具，不自動開啟或套用染色。有限搜尋無法保證多色精準成功。本機候選版尚未完成新一局實機驗收。

## English

- Precise Search replaces predicted alternatives with Retry in the overlay and F7. It ends the current search, releases the mouse, zooms out to the maximum visible area and searches again in the same round.
- Fixes mixed DPI and multi-monitor eyedropper coordinates. Physical cursor pixels map directly to the frozen screenshot. Fullscreen and forced focus are removed, and foreign windows cannot be repositioned.
- Improves 100px HEX-card decoding and strong-glyph swatch validation. Reliable timer evidence can correct the conservative cap of an already-open board by at most 20 seconds.
- Attempts both mouse-button releases even if one fails, and clears stale matches when final readback is unavailable. UI and tutorials are updated in all three languages.
- Speeds up complete palette discovery and reuses read buffers while retaining full coverage, uniqueness checks and final revalidation.
- Starts the countdown advisory interval at the first observation of this round's board. Only reliable decreasing readings after that interval can adjust the execution deadline; early misreads do not directly stop a route.
- Separately records a closed board, changed session and inconsistent observation. When the current state is unconfirmed, the UI labels earlier colors as "Last measured colors (current state unconfirmed)" and does not report them as a current match.

A retry does not add game time, use a new dye item, open dyeing or apply a result. Multiple exact matches are not guaranteed. This local candidate has not completed a new live dye-round validation.
