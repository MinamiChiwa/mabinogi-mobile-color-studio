# 0.4.2rc11 — 搜索计算提速、重试连续缩小与本地更新

## 简体中文

- 复用相同颜色的距离计算，减少路线模拟中重复的 float32 数据转换；保留原来的颜色算法、事件顺序、搜索范围和实际核验。未命中时仍会使用剩余搜索时间，以检查更多候选。

- 重试缩小改为同一锚点连续滚动，去掉分组间的完整回读和重复准备；结束后核对实际缩放与颜色，漏收滚轮时按实际位置补齐。保留逐格滚轮节奏、F9 和最终核验，不减少搜索范围或放宽精准标准。

- 主窗接入用户决定的 GitHub 文件更新与离线导入，保留全部 data；具备正式公钥与签名清单的引导版本才支持正式更新。独立更新器具备健康检查与失败恢复，本轮仅本地验证，未发布。
- 重试前恢复已绑定游戏的焦点，激活失败时允许再次点击；记录未知客户端构建指纹，并制定韩服及其他服务器适配计划。韩服尚未实测支持。

- 扩大细化搜索期间展示当前游戏实测颜色及各区域色差，并说明计算期间色板可能保持不动。找到更好的可执行方案才继续移动；满意当前效果可按 F9 停止搜索，再到游戏内确认染色。不显示预测候选或递增路线计数，不改变寻色策略与时间预算。

- 加速启动及等待阶段的色板检查，大块数据改为对齐地址批量比较，仍覆盖所有候选并在结束时复验。准备时间随游戏状态和电脑性能变化。

- 修复两步细化中第一步已取得双白、第二步却将其覆盖的问题。中途落点优于保留结果且剩余路线预测更差时，追加一次实际色码确认，保留该落点，并从新基准继续细化；不增加逐动作截图或缩短时限。

- 修复已找到的旋转与滚轮路线被拦截、转而在初始位置不断细化的问题。移除细化约 4 秒的阶段硬截止，读取与恢复可使用真实剩余时间；持续读色超时进入实际落点恢复。

- 精简日常与发布回归，历史搜索矩阵移至研究集合；发布检查不会将必要样本缺失后的跳过误报为完整通过。
- 输入后端接受经过 HWND DPI 像素映射验证的非 1:1 视口，继续检查会话绑定、窗口和坐标证据。

- 尾部统一最多预留 3 秒，取消重复的 8／10 秒空闲预留；实际输入、回读、回程和会话检查仍按真实耗时保护。倒计时仍保留首次 30 秒宽限。
- 全局大角度色板路线允许受控的最多 90°平滑旋转，同时保留 12°与微调候选；数学近似目标需完整动作回放和实际色码复核，不能据此宣称精准命中。
- 已完成的实测候选不会因后续有限 CPU 搜索耗尽而被清除；全局路线只核算实际前进与回读成本，不再为假设失败预扣完整回程；局部细化只保留一次实测恢复成本。
- 修正剩余约 50 秒却拒绝本局重试的预算门槛。按实际缩小路线及颜色复核预留时间，新搜索使用本局剩余余量；按钮与点击后的预算判断一致，实际目标路线仍单独复核。
- 重试不可用时分别说明时间、操作额度、搜索次数和缩小路线原因，避免统一误报为时间不足。
- 精准模式移除预测候选列表，改为浮窗「重新寻色」和 F7。停止当前搜索、释放鼠标并缩小画板至最大可见范围后，在同局重新搜索。
- 修复屏幕吸管的 DPI/多屏坐标混用；冻结截图与物理鼠标坐标逐像素对应，去除全屏及强制前台，禁止定位非本工具窗口。
- 修复100px色码卡识别和强字模色块边界，提高原失败截图复核速度。计时证据可靠时，仅对已打开色板的保守截止最多校正27秒。
- 修复释放左键失败后漏释放右键，以及最终无法重新读取时保留旧达标状态的问题。三语界面和教程同步更新。
- 加速完整色板扫描并复用读取缓冲区，仍保留全量检查、唯一性确认和最终重验。
- 倒计时宽限从首次发现本局色板开始计算；仅用宽限后的可靠递减读数调整执行截止，早期误读不会直接停止路线。
- 分别记录色板关闭、会话变化和暂时读取不一致。当前无法确认时，显示「上次实测（当前未确认）」，不会将历史颜色记成当前达标。

重试不增加游戏时间、不消耗新道具，不自动开启或套用染色。预测和有限搜索不能保证多色精准成功。该本地候选版尚未完成新一局实机验收。

## 繁體中文

- 重用相同顏色的距離計算，減少路線模擬中重複的 float32 資料轉換；保留原本的顏色算法、事件順序、搜尋範圍及實際核驗。未命中時仍會使用剩餘搜尋時間，以檢查更多候選。

- 重試縮小改為同一錨點連續滾動，移除分組間的完整回讀與重複準備；結束後核對實際縮放與顏色，漏收滾輪時依實際位置補齊。保留逐格滾輪節奏、F9 與最終核驗，不縮減搜尋範圍或放寬精準標準。

- 主畫面接入由使用者決定的 GitHub 檔案更新與離線匯入，保留全部 data；具備正式公鑰與簽名清單的引導版本才支援正式更新。獨立更新器具備健康檢查與失敗恢復，本次僅本機驗證，未發布。
- 重試前恢復已綁定遊戲的焦點，啟用失敗時可再次點擊；記錄未知客戶端版本指紋，並制定韓服與其他伺服器適配計畫。韓服尚未實測支援。

- 擴大細化搜尋期間顯示目前遊戲實測顏色及各區域色差，並說明計算期間色板可能保持不動。找到更好的可執行方案才繼續移動；滿意目前效果可按 F9 停止搜尋，再到遊戲內確認染色。不顯示預測候選或遞增路線計數，不變更尋色策略與時間預算。

- 加速啟動及等待階段的色板檢查，大塊資料改為對齊位址批次比較，仍涵蓋所有候選並在結束時複驗。準備時間會隨遊戲狀態及電腦效能變化。

- 修正兩步細化中第一步已取得雙白、第二步卻將其覆蓋的問題。中途落點優於保留結果且剩餘路線預測更差時，追加一次實際色碼確認，保留該落點，並從新基準繼續細化；不增加逐動作截圖或縮短時限。

- 修正已找到的旋轉與滾輪路線被攔截、轉而在初始位置持續細化的問題。移除細化約 4 秒的階段硬截止，讀取與恢復可使用實際剩餘時間；持續讀色逾時會進入實際落點恢復。

- 精簡日常與發布回歸，歷史搜尋矩陣移至研究集合；發布檢查不會將必要樣本缺失後的跳過誤報為完整通過。
- 輸入後端接受經過 HWND DPI 像素映射驗證的非 1:1 視口，繼續檢查會話綁定、視窗與座標證據。

- 尾部統一最多預留 3 秒，移除重複的 8／10 秒空閒預留；實際輸入、回讀、回程與會話檢查仍依真實耗時保護。倒數計時仍保留首次 30 秒寬限。
- 全域大角度色板路線允許受控的最多 90°平滑旋轉，同時保留 12°與微調候選；數學近似目標仍須完整動作重播與實際色碼複核，不能宣稱精準命中。
- 已完成的實測候選不會因後續有限 CPU 搜尋耗盡而被清除；全域路線只計算實際前進與回讀成本，不再為假設失敗預扣完整回程；局部細化只保留一次實測恢復成本。
- 修正剩餘約 50 秒仍拒絕本局重試的預算門檻。依實際縮小路線與顏色複核預留時間，新搜尋使用本局剩餘餘量；按鈕與點擊後的預算判斷一致，實際目標路線仍單獨複核。
- 重試無法使用時分別說明時間、操作額度、搜尋次數與縮小路線原因，避免統一誤報為時間不足。
- 精準模式移除預測候選清單，改為浮窗「重新尋色」與 F7。停止目前搜尋、釋放滑鼠並縮小色板至最大可見範圍後，在同局重新搜尋。
- 修復螢幕吸管的 DPI／多螢幕座標混用；凍結截圖與實體滑鼠座標逐像素對應，移除全螢幕與強制前景，禁止定位非本工具視窗。
- 修復100px色碼卡辨識與強字模色塊邊界，提高原失敗截圖複核速度。計時證據可靠時，僅對已開啟色板的保守截止最多校正27秒。
- 修復左鍵釋放失敗後漏釋放右鍵，以及最後無法重新讀取時保留舊達標狀態的問題。三語介面與教學同步更新。
- 加速完整色板掃描並重用讀取緩衝區，仍保留全量檢查、唯一性確認與最終重驗。
- 倒數計時寬限從首次發現本局色板開始計算；僅使用寬限後可靠的遞減讀數調整執行截止，早期誤讀不會直接停止路線。
- 分別記錄色板關閉、會話變化與暫時讀取不一致。無法確認目前狀態時，顯示「上次實測（目前未確認）」，不會將歷史顏色記為目前達標。

重試不增加遊戲時間、不消耗新道具，不自動開啟或套用染色。有限搜尋無法保證多色精準成功。本機候選版尚未完成新一局實機驗收。

## English

- Reuses identical colour-distance calculations and avoids redundant float32 conversions during route simulation. Colour arithmetic, event order, search coverage and actual verification are preserved. Searches without a hit still use the remaining allowance to examine more candidates.

- Retry now zooms out continuously at one anchor, without full readback and repeated preparation between groups. Actual scale and colors are verified at the end; missed wheel events are corrected from the measured position. Per-notch pacing, F9, search coverage and exact-match requirements are preserved.

- Adds user-controlled GitHub file updates and offline imports while keeping all data. Official updates require a bootstrap with a production public key and signed ownership manifest. The independent updater supports health checks and recovery; this candidate is locally verified and unpublished.
- Retry restores focus to the bound game and stays available when activation fails. Unknown client build fingerprints and a multi-server adaptation plan are added; Korean native search is not yet validated.

- Shows the current measured game colors and each region's color difference during extended refinement. Explains why the board may remain still while a better executable route is calculated. Press F9 when satisfied, then confirm dyeing in the game. No predicted alternatives or growing route counts are shown; search behavior and time budgets are unchanged.

- Speeds up startup and waiting checks with aligned full-pointer comparisons for large blocks, retaining full candidate coverage and final revalidation. Preparation time still depends on game state and computer performance.

- Keeps a better intermediate result instead of overwriting it with a worse route endpoint. If live feedback beats the retained result and the predicted remaining route, one visual confirmation promotes that landing as the next refinement anchor. No screenshot is added to every action and time limits are unchanged.

- Fixes a blocked rotation/wheel route that caused repeated refinement at the initial position. Removes the roughly four-second refinement phase deadline: reads and recovery use the actual remaining allowance. Persistent color-read timeouts enter endpoint recovery.

- Trims daily and release regression profiles while keeping historical search matrices in research. Missing required evidence can no longer produce a complete release verdict.
- Accepts non-1:1 input viewports backed by verified HWND DPI pixel mapping, retaining session, window and coordinate checks.

- Uses a single three-second game-tail reserve and removes duplicate eight/ten-second idle padding. Real input, readback, return and session checks remain charged by their measured cost. The initial 30-second countdown grace remains.
- Global palette approaches may use controlled smooth rotations up to 90 degrees while retaining 12-degree and micro-adjustment proposals. Mathematical near targets still require full route replay and actual HEX verification; they never prove an exact match.
- Completed measured candidates are retained when later bounded CPU search is exhausted. Global routes are admitted by their actual forward and readback cost without a hypothetical full return. Local refinement reserves one measured recovery.
- Fixes overly conservative retry admission with about 50 seconds left. It reserves the actual zoom-out route and color verification, then searches within the round's remaining allowance. Button availability and retry admission use the same budget; real target routes still require independent approval.
- Unavailable retries now distinguish time, action allowance, search count and zoom-out route causes instead of reporting every refusal as insufficient time.
- Precise Search replaces predicted alternatives with Retry in the overlay and F7. It ends the current search, releases the mouse, zooms out to the maximum visible area and searches again in the same round.
- Fixes mixed DPI and multi-monitor eyedropper coordinates. Physical cursor pixels map directly to the frozen screenshot. Fullscreen and forced focus are removed, and foreign windows cannot be repositioned.
- Improves 100px HEX-card decoding and strong-glyph swatch validation. Reliable timer evidence can correct the conservative cap of an already-open board by at most 27 seconds.
- Attempts both mouse-button releases even if one fails, and clears stale matches when final readback is unavailable. UI and tutorials are updated in all three languages.
- Speeds up complete palette discovery and reuses read buffers while retaining full coverage, uniqueness checks and final revalidation.
- Starts the countdown advisory interval at the first observation of this round's board. Only reliable decreasing readings after that interval can adjust the execution deadline; early misreads do not directly stop a route.
- Separately records a closed board, changed session and inconsistent observation. When the current state is unconfirmed, the UI labels earlier colors as "Last measured colors (current state unconfirmed)" and does not report them as a current match.

A retry does not add game time, use a new dye item, open dyeing or apply a result. Multiple exact matches are not guaranteed. This local candidate has not completed a new live dye-round validation.
