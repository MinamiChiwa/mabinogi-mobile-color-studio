# 0.4.1 — 候选选择、双区域适配与扫描/浮窗修复

## 简体中文

本地 rc2 修复色板扫描被无效内存匹配反复阻塞的问题。浮窗按钮和拖动恢复可用，实际游戏动作期间短暂隐藏避让，完成后恢复；取消会保留扫描诊断。

- 精准寻色找到目标后仍提供其他候选，按区域优先级与色差排序。时间允许时自动定位目标；切换前重新核对完整路线、实测色码和返回余量。
- 自动适配双区域及三区域色板，保留缺失区域的保存设置。精准、相似、替代色和区域优先级共同生效。
- 初始化扫描保留进度，准确区分未完成、多个候选和无活动色板；进程权限拒绝提供同权限启动指导。
- 完成后释放主界面操作，并支持重新查看只读候选。简中、繁中、英语文案和教程同步更新。

预测不代表游戏实测，多色精准及所有硬件环境不保证成功。程序不会自动开启染色或套用结果。

## 繁體中文

本機 rc2 修復色板掃描被無效記憶體匹配反覆阻塞的問題。浮窗按鈕與拖動恢復可用，實際遊戲動作期間短暫隱藏避讓，完成後恢復；取消會保留掃描診斷。

- 精準尋色找到目標後仍提供其他候選，依區域優先順序與色差排序。時間允許時自動定位目標；切換前重新核對完整路線、實測色碼與返回餘量。
- 自動適配雙區域與三區域色板，保留缺失區域的儲存設定。精準、相似、替代色與區域優先順序共同生效。
- 初始化掃描保留進度，正確區分未完成、多個候選與無活動色板；程序存取權限遭拒時提供相同權限執行指引。
- 完成後釋放主畫面操作，並支援重新查看唯讀候選。簡中、繁中、英文文案與教學同步更新。

預測不代表遊戲實測，多色精準與所有硬體環境不保證成功。程式不會自動開啟染色或套用結果。

## English

Local rc2 fixes repeated palette-scan blockage caused by invalid memory pattern matches. Overlay controls and dragging are usable again. It briefly hides during game gestures and returns afterward. Cancellation retains scan diagnostics.

- Precise Search retains alternatives after finding a target, ordered by region priority and color difference. It positions the target when time permits. Switching requires fresh route, game-color and return-allowance checks.
- Two- and three-region boards are detected automatically while saved settings for absent regions are retained. Exact, Similar, alternative colors and region priorities work together.
- Initialization scans retain progress and distinguish incomplete discovery, multiple candidates and no active board. Process-access denials provide guidance for matching privilege levels.
- Completion releases main-window controls and allows reopening a read-only candidate list. Simplified Chinese, Traditional Chinese and English copy and tutorials are updated together.

Predictions are not measured game results. Multiple exact matches and every hardware environment are not guaranteed. The tool never opens a dye round or applies its result automatically.
