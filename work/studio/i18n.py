"""Local, offline UI translations. Profile mode identifiers stay stable."""
import re
import weakref
from functools import lru_cache
from opencc import OpenCC
language='简体中文'
traditional=OpenCC('s2twp')
EN={
'读取当前游戏色码':'Reading current game HEX',
'恢复已测最佳颜色':'Restoring the best measured color',
'单区域目标已达标':'Single-region target matched',
'单区域寻色完成':'Single-region search complete',
'单区域寻色已结束':'Single-region search ended',
'自动移动已结束，可继续在游戏内手动调整。':'Automatic movement has ended. Manual adjustment is available in the game.',
'当前色码未完成复核，请以游戏内显示为准。':'Current HEX could not be verified. Refer to the colors shown in the game.',
'无法为所选方案预留可靠的返回与复核时间，已保留当前实测结果。':'The selected option does not allow a reliable return and verification within the remaining time. The current measured result has been kept.',
'所选方案无法完成路线复核，已保留当前实测结果。':'The selected route could not be verified. The current measured result has been kept.',
'所选方案的返回路线尚未完成验证，已保留当前实测结果。':'The selected option has no verified return route. The current measured result has been kept.',
'剩余时间不足以完成切换、返回与颜色复核，已保留当前实测结果。':'There is insufficient time to switch, return and verify the colors. The current measured result has been kept.',
'本轮候选实测未达标；当前颜色如下，尚不能判断色板无解。':'The tested candidates did not meet the targets. Current colors are shown below; this does not prove the board has no solution.',
'当前候选实测未达标':'The current candidate did not meet the targets',
'正在检查剩余候选和游戏时间；F9随时停止。':'Checking other candidates and remaining game time. F9 stops at any time.',
'正在定位预测达标且剩余时间允许的方案。\n完成后仍可选择其他方案，实际染色须在游戏内手动确认。':'Positioning a predicted match that fits the remaining game time.\nYou can choose another option afterward and confirm application manually in the game.',
'当前候选实测未达标，正在定位并复核下一候选。':'The current candidate did not meet the targets. Positioning and checking the next candidate.',
'自动定位最接近方案':'Positioning the closest available combination',
'已到达最接近方案':'Closest available combination reached',
'这是当前可测量的妥协方案；可选择其他方案，实际染色须在游戏内手动确认。':'This is the closest measurable compromise. You may choose another option and confirm application manually in the game.',
'缺少当前姿态测量，未执行切换，保持当前颜色。':'Current pose measurement is missing. No switch was made; current colors are kept.',
'已停止自动染色，可重新开始。':'Automatic dyeing stopped. You can start again.',
'快捷键已就绪：F8 开始 / F9 停止':'Hotkeys ready: F8 starts and F9 stops.',
'全局注册不可用：':'Some hotkeys failed to register; ',
'；F9 仍通过轮询停止，其他操作请使用按钮。':'F9 polling remains available. Use the buttons for the other actions.',
'大图重建校验未通过':'Atlas reconstruction validation failed',
'大图重建校验未通过：':'Atlas reconstruction validation failed: ',
'区域 ':'Region ',
' 留出 RGB RMSE ':' held-out RGB RMSE ',
'（上限 ':' (limit ',
'）。尚未搜索目标组合，不能据此判断没有满足目标的方案。':'). The target colors have not been searched, so this does not mean that no matching combination exists.',
'当前搜索未得到可执行方案':'The current search found no executable plan',
'本轮没有预测达标方案；以下结果仅供参考，实际复核未达标时会停止。':'No predicted match was found this round. The entries below are for reference; execution stops if verification misses the targets.',
'请先启动工具，再手动进入染色倒计时界面；识别成功后自动采样和定位，结果须在游戏内手动确认。':'Start the tool, then manually enter the timed dye screen. Sampling and positioning begin after recognition; the result must be confirmed in the game.',
'旧版策略':'Legacy strategy',
'周期图板实验':'Periodic atlas experiment',
'设置染色入口位置':'Set dye-entry point',
'入口点':'Entry point',
'染色入口已记录；启动实验会消耗一瓶染色剂，不会自动确认或套用。':'Dye entry saved. Starting the experiment uses one dye; it will not confirm or apply the result.',
'请先设置染色入口位置。':'Set the dye-entry point first.',
'目标游戏窗口已变化，请重新设置染色入口位置。':'The game window changed. Set the dye-entry point again.',
'游戏窗口尺寸已变化，请重新设置染色入口位置。':'The game window size changed. Set the dye-entry point again.',
'游戏窗口位置或尺寸已变化，请重新设置染色入口位置。':'The game window moved or changed size. Set the dye-entry point again.',
'染色入口位置已超出游戏窗口，请重新设置。':'The dye-entry point is outside the game window. Set it again.',
'周期图板实验会开始一局普通染色并消耗染色剂；只采集和定位，不会自动确认或套用。':'The periodic-atlas experiment starts a regular dye round and uses one dye. It only captures and positions colors; it will not confirm or apply them.',
'冻结画面：单击普通染色入口位置；Esc 取消':'Frozen screenshot: click the regular-dye entry point; Esc cancels',
'客户区坐标 (':'Client point (',
') · 单击设置 / Esc 取消':') · Click to set / Esc to cancel',
'请在游戏窗口内选择 · Esc 取消':'Select inside the game window · Esc cancels',
'染色入口选择失败：':'Could not set dye-entry point: ',
'周期图板实验 · 正在采集本局颜色板':'Periodic-atlas experiment · Capturing this round',
'本局颜色板质量门槛通过，正在准备自动最佳方案。':'Board quality checks passed. Preparing the automatic best combination.',
'自动最佳方案已复核，请查看浮窗，并在游戏内手动确认是否套用。':'The automatic best combination is verified. Review the overlay and confirm application manually in the game.',
'剩余时间不足，未发送定位操作。':'Not enough time; no positioning input was sent.',
'颜色板质量未达标，未发布候选。':'Board quality checks failed; no candidates were published.',
'剩余时间不足，保持自动最佳方案。':'Not enough time; keeping the automatic best combination.',
'未选择其他方案，保持自动最佳方案。':'No other combination selected; keeping the automatic best combination.',
'自动方案实测色码':'Measured game HEX for the automatic combination',
'最大实测色差':'Maximum measured color difference',
'已停止，请查看游戏当前颜色。':'Stopped. Check the current colors in-game.',
'候选选择已结束。':'Candidate selection has ended.',
'游戏色码已复核':'Game HEX verified',
'全部目标达标，请在游戏内手动确认是否套用。':'All targets meet the configured criteria. Confirm application manually in the game.',
'当前为妥协结果，请先检查实测色差；是否套用请在游戏内手动确认。':'Compromise result. Review measured differences before deciding.',
'正在定位所选方案':'Positioning selected combination',
'根据图像实测位移校正；F9随时停止。':'Correcting measured texture motion. F9 stops at any time.',
'预测 ':'Predicted ',
'实测 ':'Measured ',
'选择颜色方案 · 尚未执行':'Choose a color combination · Not executed',
'自动定位最佳方案':'Positioning the automatic best combination',
'正在先移动到预测色差最小的方案。\n完成后仍可选择其他方案，实际染色须在游戏内手动确认。':'Moving to the predicted lowest-difference combination first.\nYou can still choose another option afterward. Application must be confirmed manually in the game.',
'自动方案（当前）':'Automatic combination (current)',
'已到达自动最佳方案':'Automatic best combination reached',
'可选择其他方案；剩余时间不足时将保持当前自动方案。':'You may choose another option; if time is insufficient, the automatic combination is kept.',
'已保持自动最佳方案':'Automatic best combination kept',
'剩余时间不足，未移动到所选方案。':'Not enough time to move to the selected combination.',
'剩余时间不足':'Not enough time',
'无法安全定位并复核自动最佳方案。':'Not enough time to safely position and verify the automatic best combination.',
'未选择其他方案':'No other option selected',
'已保持自动最佳方案。':'The automatic best combination was kept.',
'以下为截图预测，ΔE 76 越小越接近。\n选择后仍需游戏色码复核，实际染色须在游戏内手动确认。':'Screenshot predictions; lower Delta E 76 is closer.\nGame HEX verification is still required. Application must be confirmed manually in the game.',
'有效覆盖不足，暂无可计算方案。':'Insufficient valid coverage; no candidates available.',
'预测达标':'Predicted within tolerance',
'妥协方案':'Compromise',
'选择此方案':'Select this combination',
'颜色方案已失效':'Color combinations expired',
'最大 ':'Maximum ',
' / 平均 ':' / Mean ',
'请点击游戏窗口':'Click the game window',
'画面变化暂不明显，正在等待更新并复查；按 F9 可接管。':'Waiting for a fresh frame to recheck movement. Press F9 to take over.',
'正在复查画面变化':'Rechecking board response',
'尚未确认输入失败，请稍候。\n如需保留当前颜色，仍可按 F9 接管。':'Input failure is not confirmed. Please wait.\nPress F9 to retain the current colors.',
'多次不同方向操作并延迟复查后，仍未检测到色板或色码变化，已停止。请确认鼠标是否实际拖动色板；这不一定代表游戏拒绝输入。':'Stopped after repeated moves in different directions and a delayed recheck showed no board or color-code change. Check whether the board actually moves; this does not prove the game rejected input.',

'等待染色界面':'Waiting for dye screen',
'可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。':'Open regular dye from any game screen and finish the tutorial.\nSearch starts automatically. F9 cancels waiting.',
'满意当前颜色？停止接管 F9':'Keep current colors · Stop with F9',
'正在回退 · 随时可按 F9 接管':'Restoring · F9 to take over',
'正在恢复本轮最佳组合，结束前提前停止微调。\n如需保留当前画面，请按 F9 停止。':'Restoring the best combination with time to spare.\nPress F9 to retain the current colors.',
'当前组合已达标 · 仍在优化':'Current colors meet targets · Optimizing',
'持续搜索最佳颜色组合':'Searching for the best combination',
'剩余约 30 秒回退最佳方案。\n如需保留当前颜色，请按 F9 停止，并在游戏内手动确认是否套用。':'At about 30 seconds remaining, restore the best.\nLike these colors? Press F9 and confirm in game.',
'寻色完成：已保留接近最佳的组合，停止微调，未精确复现最佳记录。':'Stopped on a combination close to the best; the saved best was not reproduced exactly.',
'正在停止并释放鼠标…':'Stopping and releasing the mouse…',

'最佳位置暂无法恢复，正在尝试已记录的备用方案。':'Trying a recorded alternative because the best position could not be restored.',
'寻色完成：已恢复备用方案，未回到最佳组合。':'Search complete: an alternative was restored, not the best combination.',
'流程已中断':'Process interrupted',
'已启用':'Enabled',
'未启用':'Disabled',
'等待染色界面 · 剩余 ':'Waiting for dye screen · Time left: ',
'等待超时':'Waiting timed out',
'正在等待染色界面，请打开普通染色并完成教学。按 F9 可取消。':'Open regular dye and finish the tutorial. Press F9 to cancel waiting.',
'等待染色界面超时，尚未开始寻色。请打开染色界面、完成教学后再按 F8。':'Waiting timed out; color search has not started. Open the dye screen, finish the tutorial, then press F8 again.',
'局部多次未命中，正在缩小色板并重新探索。':'No match after several local attempts. Zooming out to explore a new area.',
'染色工坊':'Color Studio','瑪奇 Mobile':'Mabinogi Mobile','南千和':'南千和',
'精准 HEX':'Exact HEX','相似颜色':'Similar',
'颜色区域':'Color region','匹配此区域':'Match this region','点击选色':'Choose color','屏幕吸管':'Eyedropper',
'当前颜色':'Current','最佳结果':'Best result','未参与匹配':'Not matched','读取失败':'Unreadable',
'目标色集合':'Allowed colors','点击查看全部':'View all colors',' 色':' colors',
'替代颜色 · 多个颜色用逗号分隔':'Alternatives · separate HEX codes with commas',
'六位色码必须完全一致':'Requires an exact six-digit HEX match',
'感知色差':'Color difference','数值越小越严格':'Lower = closer',
'请输入有效 HEX':'Enter a valid HEX code','颜色未设置完整':'Finish entering a color',
'正在计算允许的颜色…':'Calculating allowed colors…','正在准备颜色预览…':'Preparing preview…',
'预览计算失败，请重新选择颜色':'Preview unavailable. Please choose again.',
'选择目标颜色':'Choose target color','区域':'Region',
'保存方案':'Save preset','寻色记录':'Results','♥  支持作者':'♥  Support',
'① 设置目标颜色    →    ② 游戏内打开普通染色    →    ③ 教学结束后按 F8':'1 Set colors   →   2 Open regular dye in game   →   3 Press F8 after the tutorial',
'开始寻色   F8':'Start   F8','停止   F9':'Stop   F9','达标后自动复核并套用':'Verify & apply automatically',
'诊断':'Diagnostics',
'就绪 · 支持横屏与竖屏识别':'Ready · Landscape and portrait supported',
'持续寻找更接近的颜色，剩余约 30 秒返回本轮最佳组合；是否套用请在游戏内手动确认。':'Keeps improving colors, then returns to the best observed set with about 30 seconds left.',
'F9 随时停止并释放鼠标  ·  切换窗口停止寻色  ·  不自动开启下一瓶染色剂':'F9 stops input · Switching windows stops search · One dye per session',
'记录最近 50 次结果 · ΔE 越小越接近目标，0 表示目标原色':'Last 50 results · Lower ΔE is closer; 0 is the target color',
'完成一次寻色后，颜色组合会自动保存在这里。':'Completed color sets will be saved here.',
'目标达标':'Target matched','妥协结果':'Closest result','已套用':'Applied','寻色结果':'Search result',
'最大色差':'Maximum difference','最佳组合':'Best set','本次结果':'Final set','最大':'Max','平均':'Mean',
'色差越小越接近目标':'Lower difference means closer to target','色差':'Difference',
'未识别':'Unreadable','方案已保存，下次启动自动恢复。':'Preset saved for the next launch.',
'请至少启用一个颜色区域。':'Enable at least one region.',
'正在识别游戏界面…':'Detecting game screen…','正在停止并释放鼠标…':'Stopping and releasing mouse…',
'快捷键被其他程序占用，请使用界面按钮。':'Hotkey unavailable. Use the on-screen buttons.',
'正在寻色 · 游戏剩余 ':'Searching · Time left: ','正在恢复最佳颜色 · 游戏剩余 ':'Returning to best colors · Time left: ',
' 秒':' s','正在调整色板，持续寻找更接近的颜色…':'Adjusting the board to find closer colors…',
'本轮结果未能保存，请检查程序文件夹是否可写。':'Could not save the result. Check folder write access.',
'流程完成 · ':'Finished · ','当前颜色：':'Current colors: ',
'允许颜色 · 完整色图':'Allowed colors · Full atlas',' 种允许颜色':' allowed colors',
'适合窗口':'Fit','原始尺寸':'Actual size','正在生成完整色图…':'Generating full color atlas…',
'色图生成失败，请关闭后重试。':'Could not generate atlas. Close and retry.',
'色差由中心向外增加 · 放大查看每个颜色，拖动或滚动浏览，悬停查看 HEX':'Difference increases outward · Zoom to inspect, drag or scroll to browse, hover for HEX',
'当前色块':'Color','拖动浏览 / ＋ 放大 / － 缩小':'Drag to browse / ＋ Zoom in / － Zoom out',
'屏幕吸管 · 单击取色 / Esc 取消':'Eyedropper · Click to pick / Esc to cancel',
'移动预览 · 单击取色 · Esc 取消':'Move to preview · Click to pick · Esc to cancel',
'单击取色 · Esc 取消':'Click to pick · Esc to cancel','屏幕取色失败：':'Eyedropper failed: ',
'输入诊断':'Input diagnostics',
'请先进入游戏限时染色界面。\n将依次测试左键平移、右键圆弧和滚轮缩放，记录前后色码与截图，不套用结果。\n\n是否开始？':'Open the timed dye screen first.\nTests dragging, right-button rotation and wheel zoom without applying colors.\n\nStart diagnostics?',
'发现区域 ':'Found a nearby color in region ',' 的接近颜色，正在放大寻找纯色。':'. Enlarging to find an exact color.',
'当前范围没有合适候选，正在拖动色板探索新颜色。':'No suitable candidate in view. Exploring another area.',
'剩余约 30 秒，正在回到本轮最接近的已观察颜色。':'About 30 seconds left. Returning to the best observed colors.',
'寻色完成：全部目标已匹配并复核。请返回游戏确认使用。':'All enabled targets matched and verified. Confirm use in the game.',
'寻色完成：已回到本轮最接近结果。':'Returned to the best observed result.',
'寻色结束：未能可靠恢复本轮最佳颜色，已停止操作。':'Search stopped. Could not reliably restore the best colors.',
' 当前颜色已达到目标。':' Current colors meet the configured targets.',
' 当前为妥协颜色，未达到设定目标。':' This is the closest result; the configured targets were not met.',
' 未自动套用，请返回游戏决定使用或取消。':' Not applied. Choose Use or Cancel in the game.',
'染色完成：目标色已通过结果页复核并套用。':'Dye completed: result colors verified and applied.',
'已停止，鼠标已释放。':'Stopped. Mouse released.',
'已暂停：游戏失去焦点。返回游戏按 F8 重新开始。':'Game lost focus. Return to the game and press F8.',
'窗口位置或尺寸已变化，已停止。请按 F8 重新识别。':'Game window changed. Press F8 to detect it again.',
'未找到瑪奇 Mobile，请先打开台服游戏。':'Mabinogi Mobile not found. Open the Hong Kong/Macau/Taiwan client.',
'未能可靠读取倒计时，已停止。请在教学结束后再按 F8。':'Timer unreadable. Press F8 after the tutorial ends.',
'正在等待染色色板显示……':'Waiting for the dye board…',
'当前在结果页，颜色未满足目标或自动套用已关闭，未操作。':'Result screen detected. Automatic apply is off or targets are not met.',
'三个色码尚未完整识别，未替换目标。':'Could not read all three colors. Targets unchanged.',
'色码复核不一致，未替换目标。':'Color verification differed. Targets unchanged.',
'颜色请输入六位 HEX，例如 #202020':'Enter a six-digit HEX color, e.g. #202020',
'文字识别组件缺失，请使用完整安装包。':'OCR component missing. Use the complete download.',
'未识别染色小游戏的三个色码卡片，请先进入限时染色界面。':'Open the timed dye screen before starting.',
'色板定位超出窗口，已停止以避免误操作。':'Dye board lies outside the window. Search stopped.',
'色码卡片下方定位线不可见，可能仍在显示教学或结果窗口。':'Marker lines not visible. Wait for the tutorial or close the result screen.',
'无法可靠识别取色点位，请放大游戏窗口后重试。':'Could not locate markers. Enlarge the game window and retry.',
'游戏窗口已关闭。':'Game window closed.','游戏窗口已最小化，请恢复后再试。':'Restore the minimized game window.',
'无法激活游戏，请在游戏按 F8。':'Could not focus game. Press F8 from the game.',
'连续两次输入后色板未变化。已停止，请检查游戏是否接受模拟鼠标输入。':'Board did not respond to input. Check whether the game accepts mouse input.',
'使用提示':'Usage notice','适用于港澳台服瑪奇Mobile。游戏中使用本工具可能存在风险，建议谨慎使用。':'For the Hong Kong/Macau/Taiwan service of Mabinogi Mobile. Please note that using this tool in-game may carry some risk.',
}

EN.update({'请先停止寻色再切换语言。': 'Stop the search before switching language.', 'Windows 未接受鼠标输入。请检查游戏与工具是否使用相同权限运行。': 'Windows rejected mouse input. Run game and tool with matching privileges.', '候选已接近，逐点读取三个实际色码进行微调。': 'Refining a nearby candidate using actual game colors.', '剩余时间不足，停止输入校准。': 'Not enough time for input diagnostics.', '取消确认窗口未能可靠识别，请手动取消。': 'Cancel dialog unreadable. Please cancel manually.', '右键动作未能证实色板旋转，不能判定旋转校准通过。': 'Could not verify right-button rotation.', '已匹配，但未识别到游戏确认按钮。请手动确认。': 'Colors matched. Confirm manually; the button was not detected.', '已提交，但结果页未能可靠识别，未点击套用。请在游戏中确认。': 'Submitted, but the result is unreadable. Confirm in the game.', '已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。': 'Game lost focus. Return and press F8 to restart.', '平移候选已接近，保留当前范围并验证邻近色码。': 'Checking nearby colors around the candidate.', '旋转按下点距离色板边缘太近。': 'Rotation pivot is too close to the board edge.', '无法可靠识别颜色点位。请放大游戏窗口后重试。': 'Cannot detect color markers. Enlarge the game window and retry.', '无法激活游戏。请点击游戏后按 F8。': 'Click the game and press F8.', '未找到瑪奇 Mobile。请先启动台服游戏。': 'Open the Hong Kong/Macau/Taiwan client of Mabinogi Mobile first.', '未找到目标且无法定位结束按钮，请手动选择不使用。': 'Target not found. Please select Cancel in the game.', '未测得明确缩放倍率，不能判定缩放校准通过。': 'Could not verify the zoom scale.', '未识别到染色小游戏的三张色码卡片。请先进入限时染色界面。': 'Open the timed dye screen before starting.', '未识别到结果页，请手动选择不使用本次染色。': 'Result page unreadable. Please cancel this dye manually.', '本次右键动作未能证实有效旋转，继续平移搜索。': 'Rotation unverified. Continuing with translation.', '本轮未找到全部目标，已取消结果并保留原色。本次消耗 1 个染色剂。': 'Targets not found. Result canceled; original colors kept. One dye consumed.', '游戏窗口已最小化，请恢复后重试。': 'Restore the game window and retry.', '确认点击后结果页仍在，未确认套用成功。': 'Result page is still visible. Apply could not be confirmed.', '窗口位置或尺寸已变化。已停止，请按 F8 重新识别。': 'Game window changed. Press F8 to detect it again.', '结果色码与目标不符，已停止套用。请取消本次结果。': 'Result does not meet the targets. Please cancel it.', '结果页按钮在等待后仍无法可靠定位，未套用。': 'Apply button unreadable. No colors applied.', '缩放中心必须位于色板内。': 'Zoom pivot must be inside the board.', '色板定位不完整，已停止以避免误操作。': 'Board detection incomplete. Search stopped.', '色码卡片下方点位尚不可见，可能正在显示教学或结果窗口。': 'Markers not visible. Wait for the tutorial or close the result screen.', '输入校准完成：平移、旋转、缩放均引起画面变化；未套用颜色。': 'Diagnostics complete: drag, rotate and zoom changed the board. Nothing applied.', '键盘输入被 Windows 拒绝。': 'Windows rejected keyboard input.', ' 输入后色板没有可确认的变化，校准未通过。': ' input produced no verified change. Diagnostics failed.'})

EN.update({'未检测到唯一窗口': 'No unique window found', '① 设置颜色与窗口    →    ② 点击开始或按 F8    →    ③ 进入普通染色，教学后自动寻色': '1 Set colors and window   →   2 Start / F8   →   3 Open regular dye; search begins after the tutorial', '任务已启动，正在等待或寻色；按 F9 停止。': 'Already waiting or searching. Press F9 to stop.', '快捷键不可用：': 'Unavailable hotkeys: ', '快捷键已就绪：F8 开始 / F9 停止': 'Hotkeys ready: F8 Start / F9 Stop', '正在识别窗口：': 'Detecting window: ', '浮窗暂不可用，寻色状态请查看主窗口。': 'Overlay unavailable. Follow progress in the main window.', '游戏窗口 · ': 'Game window · ', '窗口选择已更新，下次开始时生效。': 'Window selection updated for the next start.', '自动检测': 'Auto-detect', '请先按 F9 停止，再更换游戏窗口。': 'Press F9 to stop before changing the game window.', '；请关闭其他工具副本或使用按钮。': '. Close other copies of this tool or use its buttons.', '未能自动切回游戏。请点击游戏窗口，程序会继续等待识别，无需再次开始。': 'Could not focus the game. Click the game window; detection will continue without restarting.', '选择游戏窗口': 'Select game window', '默认自动识别瑪奇Mobile，也可选择标题不同的游戏窗口。': 'Automatically finds Mabinogi Mobile. Choose a window manually if its title differs.', '刷新窗口': 'Refresh list', '使用此窗口': 'Use selection', '自动检测到：': 'Detected: ', '确认后仅对所选窗口识别；窗口关闭后需重新选择。': 'Only the selected window will be used. Select it again if it closes.', '发现多个游戏窗口，请手动选择目标窗口。': 'Multiple game windows found. Select the intended window manually.', '所选窗口已关闭，请重新选择游戏窗口。': 'The selected window closed. Select the game window again.', '无法读取窗口列表，请重试。': 'Could not list windows. Try again.', '未找到游戏窗口。请启动游戏，或手动选择窗口。': 'Game window not found. Open the game or select a window manually.', '感知色差 ΔE ≤ ': 'Color difference ΔE ≤ ', ' · 数值越小越严格': ' · Lower is stricter', '色差由中心向外增加 · 放大查看每个颜色，拖动或滚动浏览，悬停查看 HEX': 'Difference increases outward · Use +/− to zoom, drag to browse, hover for HEX', '色差由中心向外增加 · ＋／－缩放，拖动浏览，悬停查看 HEX': 'Difference increases outward · Use +/− to zoom, drag to browse, hover for HEX'})

TW={
'本轮没有预测达标方案；以下结果仅供参考，实际复核未达标时会停止。':'本輪沒有預測達標方案；以下結果僅供參考，實際複核未達標時會停止。',
'确认后仅对所选窗口识别；窗口关闭后需重新选择。':'確認後僅辨識所選視窗；視窗關閉後請重新選擇。',
'默认自动识别瑪奇Mobile，也可选择标题不同的游戏窗口。':'預設自動辨識瑪奇Mobile，也可選擇標題不同的遊戲視窗。',
}

from ui_strings import EN as UI_EN, TW as UI_TW
EN.update(UI_EN);TW.update(UI_TW)
from runtime_messages import EN as RUNTIME_EN, TW as RUNTIME_TW, ERROR_SOURCE
EN.update(RUNTIME_EN);TW.update(RUNTIME_TW)

# Complete messages emitted by the formal atlas service.  These entries are
# intentionally keyed by the full sentence: translating only a shorter
# substring would leave the remainder of a status message in Chinese.
EN.update({
    '候选选择未能完成，已保持自动方案。': 'Candidate selection could not be completed. The automatic combination was kept.',
    '渐进候选搜索未完成，回退完整颜色板候选。': 'Progressive candidate search did not complete. Falling back to full-board candidates.',
    '未选择其他方案，保持自动最佳方案。': 'No other combination was selected. The automatic best combination was kept.',
    '。尚未搜索目标组合，不能据此判断没有满足目标的方案。': '. The target combinations have not been searched, so this does not show that no match exists.',
    '请进入普通染色；教学结束后自动验证颜色板。F9停止。': 'Open regular dyeing; the board is verified automatically after the tutorial. F9 stops.',
    '游戏倒计时已截止，未发布候选。': 'The game countdown has expired. No candidates were published.',
    '剩余时间不足以安全定位并复核自动最佳方案，未发送定位操作。': 'Not enough time to safely position and verify the automatic best combination. No positioning input was sent.',
    '候选已失效，保持自动最佳方案。': 'The candidate expired. The automatic best combination is kept.',
    '已停止，保留自动最佳方案。': 'Stopped. The automatic best combination is kept.',
    '倒计时复核暂时不可用，沿用首次识别结果；未延长安全截止时间。': 'The countdown could not be rechecked temporarily. The first reading is being used; the safe deadline was not extended.',
    '倒计时复核暂时不可用，沿用首次识别结果': 'The countdown could not be rechecked temporarily. The first reading is being used.',
})
TW.update({
    '渐进候选搜索未完成，回退完整颜色板候选。': '漸進候選搜尋未完成，改用完整色板候選。',
    '。尚未搜索目标组合，不能据此判断没有满足目标的方案。': '。尚未搜尋目標組合，無法據此判斷沒有符合目標的方案。',
    '请进入普通染色；教学结束后自动验证颜色板。F9停止。': '請進入普通染色；教學結束後會自動驗證顏色板。F9 停止。',
    '游戏倒计时已截止，未发布候选。': '遊戲倒數已結束，未發布候選方案。',
    '剩余时间不足以安全定位并复核自动最佳方案，未发送定位操作。': '剩餘時間不足以安全定位並複核自動最佳方案，未傳送定位操作。',
    '候选已失效，保持自动最佳方案。': '候選方案已失效，保留自動最佳方案。',
    '已停止，保留自动最佳方案。': '已停止，保留自動最佳方案。',
    '倒计时复核暂时不可用，沿用首次识别结果；未延长安全截止时间。': '倒數暫時無法複核，沿用首次辨識結果；未延長安全操作期限。',
    '倒计时复核暂时不可用，沿用首次识别结果': '倒數暫時無法複核，沿用首次辨識結果。',
})
_english_parts=sorted(EN,key=len,reverse=True)
_widgets=weakref.WeakSet()
_refreshers=weakref.WeakKeyDictionary()


class DisplayText(str):
    """Retain source text for live language changes, including concatenation."""
    def __new__(cls,value,source):
        obj=super().__new__(cls,value);obj.source=source;return obj
    def __add__(self,other):return tr(self.source+getattr(other,'source',str(other)))
    def __radd__(self,other):return tr(getattr(other,'source',str(other))+self.source)


@lru_cache(maxsize=4096)
def _translate(text,language):
    text=ERROR_SOURCE.get(text,text)
    if language=='简体中文':return text
    if language=='繁體中文':return TW.get(text,traditional.convert(text).replace('玛奇','瑪奇'))
    if text in EN:return EN[text]
    for source in _english_parts:text=text.replace(source,EN[source])
    return text


def tr(text):
    if not isinstance(text,str):return text
    source=getattr(text,'source',text)
    return DisplayText(_translate(source,language),source)


def on_language(widget,callback):
    _refreshers[widget]=callback.__name__


def set_language(value):
    global language
    if value not in ('简体中文','繁體中文','English'):raise ValueError('Unknown language')
    language=value
    for widget in list(_widgets):
        if not widget.winfo_exists():continue
        if hasattr(widget,'_i18n_text'):widget.configure(text=widget._i18n_text)
        if hasattr(widget,'_i18n_title'):widget.title(widget._i18n_title)
    for widget,name in list(_refreshers.items()):
        if widget.winfo_exists():getattr(widget,name)()

def install_widgets(ct):
    """Translate display text only; identifiers and HEX values are never changed."""
    if getattr(ct,'_studio_i18n',False):return
    ct._studio_i18n=True
    for cls in (ct.CTkLabel,ct.CTkButton,ct.CTkCheckBox,ct.CTkSwitch):
        original_init=cls.__init__;original_config=cls.configure
        def init(self,*args,_original=original_init,**kwargs):
            if 'text' in kwargs:
                self._i18n_text=getattr(kwargs['text'],'source',kwargs['text'])
                kwargs['text']=tr(kwargs['text'])
            _original(self,*args,**kwargs)
            _widgets.add(self)
        def configure(self,*args,_original=original_config,**kwargs):
            if 'text' in kwargs:
                self._i18n_text=getattr(kwargs['text'],'source',kwargs['text'])
                kwargs['text']=tr(kwargs['text'])
            return _original(self,*args,**kwargs)
        cls.__init__=init;cls.configure=configure
    for cls in (ct.CTk,ct.CTkToplevel):
        original=cls.title
        def title(self,string=None,_original=original):
            if string is None:return _original(self)
            self._i18n_title=getattr(string,'source',string);_widgets.add(self)
            return _original(self,tr(string))
        cls.title=title
