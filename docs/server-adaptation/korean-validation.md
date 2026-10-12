> 历史验证记录：专用 CMD 已退出发布包。当前请使用主界面服务器选择，见 [服务器说明](server-selection.md)。

# 韩服验证启动 / 韓服驗證啟動 / Korean validation launch

只读预检 / 唯讀預檢 / Read-only preflight：保持韩服窗口可见，运行 `Korean-preflight.cmd`，结果保存到包内 `data/korean-preflight`。该入口不操作游戏，也不消耗道具；同时运行台服时仍绑定韩服窗口并核对完整构建指纹。

简体中文：关闭已运行的染色工坊，双击包内 `Korean-validation.cmd`。选择韩服游戏窗口，照常设置目标颜色、优先级后启动寻色。该入口仅允许指纹完全一致的 2026-10-12 韩服构建执行验证；拖动、缩放、旋转、F7 重试与 F9 停止沿用现有完整流程，不自动开始或确认染色。普通 `ColorStudio.exe` 仍保留已验证服务器能力。韩服接入可测试，但尚未经过真实染色板和操作响应验收，不能据此保证精准成功。发生问题时提供该包 `data/sessions` 内完整记录。进入染色前先确保工具已就绪，避免浪费有限道具。

繁體中文：關閉已執行的染色工坊，雙擊包內 `Korean-validation.cmd`。選擇韓服遊戲視窗，照常設定目標顏色與優先級後啟動尋色。此入口僅允許指紋完全相同的 2026-10-12 韓服版本執行驗證；拖動、縮放、旋轉、F7 重試與 F9 停止沿用現有完整流程，不會自動開始或確認染色。一般 `ColorStudio.exe` 保留已驗證伺服器能力。韓服已接入供測試，但尚未通過實際色板與操作響應驗收，不能保證精準成功。若發生問題，請提供該包 `data/sessions` 中的完整紀錄。進入染色前先確認工具就緒，避免浪費有限道具。

English: Close any running ColorStudio instance, then open `Korean-validation.cmd`. Select the Korean game window and configure colors and priorities normally. This launch enables test input only for the exact Korean build fingerprint investigated on 2026-10-12. Dragging, zooming, rotation, F7 Retry and F9 Stop use the existing complete workflow; dyeing is never opened or confirmed automatically. Normal `ColorStudio.exe` retains verified server capabilities. Korean input is connected for testing but has not passed live palette/response validation, so exact matches are not guaranteed. For diagnosis, keep the complete session folder under `data/sessions`. Wait until the tool is ready before consuming a dye item.
