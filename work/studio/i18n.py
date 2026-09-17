"""Local, offline UI translations. Profile mode identifiers stay stable."""
import re
from opencc import OpenCC
language='简体中文'
traditional=OpenCC('s2twp')
EN={
'请点击游戏窗口':'Click the game window',
'画面变化暂不明显，正在等待更新并复查；按 F9 可接管。':'Waiting for a fresh frame to recheck movement. Press F9 to take over.',
'正在复查画面变化':'Rechecking board response',
'尚未确认输入失败，请稍候。\n满意当前颜色时仍可按 F9 接管。':'Input failure is not confirmed. Please wait.\nPress F9 to keep colors you like.',
'多次不同方向操作并延迟复查后，仍未检测到色板或色码变化，已停止。请确认鼠标是否实际拖动色板；这不一定代表游戏拒绝输入。':'Stopped after repeated moves in different directions and a delayed recheck showed no board or color-code change. Check whether the board actually moves; this does not prove the game rejected input.',

'等待染色界面':'Waiting for dye screen',
'可从任意游戏界面进入普通染色并完成教学。\n识别成功后自动寻色；F9 取消等待。':'Open regular dye from any game screen and finish the tutorial.\nSearch starts automatically. F9 cancels waiting.',
'满意当前颜色？停止接管 F9':'Keep current colors · Stop with F9',
'正在回退 · 随时可按 F9 接管':'Restoring · F9 to take over',
'正在恢复本轮最佳组合，结束前提前停止微调。\n满意当前颜色时，按 F9 保留当前画面。':'Restoring the best combination with time to spare.\nPress F9 to stop on colors you like.',
'当前组合已达标 · 仍在优化':'Current colors meet targets · Optimizing',
'持续搜索最佳颜色组合':'Searching for the best combination',
'剩余约 30 秒回退最佳方案。\n满意当前颜色时请按 F9 停止，由你确认使用。':'At about 30 seconds remaining, restore the best.\nLike these colors? Press F9 and confirm in game.',
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
'精准色更难寻找  ·  推荐从相似模式 ΔE 8–12 开始，数值越小越接近目标':'Exact colors are harder to find · Try Similar with ΔE 8–12; lower means closer',
'开始寻色   F8':'Start   F8','停止   F9':'Stop   F9','达标后自动复核并套用':'Verify & apply automatically',
'诊断':'Diagnostics','取当前色 F7':'Read colors F7',
'就绪 · 支持横屏与竖屏识别':'Ready · Landscape and portrait supported',
'持续寻找更接近的颜色，剩余约 30 秒返回本轮最佳组合，由你确认是否使用。':'Keeps improving colors, then returns to the best observed set with about 30 seconds left.',
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
' 当前颜色已达到目标。':' Current colors meet your targets.',
' 当前为妥协颜色，未达到设定目标。':' This is a closest result; your targets were not met.',
' 未自动套用，请返回游戏决定使用或取消。':' Not applied. Choose Use or Cancel in the game.',
'染色完成：目标色已通过结果页复核并套用。':'Dye completed: result colors verified and applied.',
'已停止，鼠标已释放。':'Stopped. Mouse released.',
'已暂停：游戏失去焦点。返回游戏按 F8 重新开始。':'Game lost focus. Return to the game and press F8.',
'窗口位置或尺寸已变化，已停止。请按 F8 重新识别。':'Game window changed. Press F8 to detect it again.',
'未找到瑪奇 Mobile，请先打开台服游戏。':'Mabinogi Mobile not found. Open the Hong Kong/Macau/Taiwan client.',
'未能可靠读取倒计时，已停止。请在教学结束后再按 F8。':'Timer unreadable. Press F8 after the tutorial ends.',
'正在等待染色色板显示……':'Waiting for the dye board…',
'当前在结果页，颜色未满足目标或自动套用已关闭，未操作。':'Result screen detected. Automatic apply is off or targets are not met.',
'已读取当前色码。':'Current colors read.',
'已将当前三色设为目标，保留各区匹配模式与容差。':'Current colors set as targets. Match modes and tolerances preserved.',
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
'使用提示':'Usage notice','适用于港澳台服瑪奇Mobile。游戏中使用本程序存在风险，请自行斟酌。':'For the Hong Kong/Macau/Taiwan service of Mabinogi Mobile. Using this tool in-game carries risks; use your own judgment.',
}

EN.update({'请先停止寻色再切换语言。': 'Stop the search before switching language.', 'Windows 未接受鼠标输入。请检查游戏与工具是否使用相同权限运行。': 'Windows rejected mouse input. Run game and tool with matching privileges.', '候选已接近，逐点读取三个实际色码进行微调。': 'Refining a nearby candidate using actual game colors.', '剩余时间不足，停止输入校准。': 'Not enough time for input diagnostics.', '取消确认窗口未能可靠识别，请手动取消。': 'Cancel dialog unreadable. Please cancel manually.', '右键动作未能证实色板旋转，不能判定旋转校准通过。': 'Could not verify right-button rotation.', '已匹配，但未识别到游戏确认按钮。请手动确认。': 'Colors matched. Confirm manually; the button was not detected.', '已提交，但结果页未能可靠识别，未点击套用。请在游戏中确认。': 'Submitted, but the result is unreadable. Confirm in the game.', '已暂停：游戏失去焦点。返回游戏后按 F8 重新开始。': 'Game lost focus. Return and press F8 to restart.', '平移候选已接近，保留当前范围并验证邻近色码。': 'Checking nearby colors around the candidate.', '旋转按下点距离色板边缘太近。': 'Rotation pivot is too close to the board edge.', '无法可靠识别颜色点位。请放大游戏窗口后重试。': 'Cannot detect color markers. Enlarge the game window and retry.', '无法激活游戏。请点击游戏后按 F8。': 'Click the game and press F8.', '未找到瑪奇 Mobile。请先启动台服游戏。': 'Open the Hong Kong/Macau/Taiwan client of Mabinogi Mobile first.', '未找到目标且无法定位结束按钮，请手动选择不使用。': 'Target not found. Please select Cancel in the game.', '未测得明确缩放倍率，不能判定缩放校准通过。': 'Could not verify the zoom scale.', '未识别到染色小游戏的三张色码卡片。请先进入限时染色界面。': 'Open the timed dye screen before starting.', '未识别到结果页，请手动选择不使用本次染色。': 'Result page unreadable. Please cancel this dye manually.', '本次右键动作未能证实有效旋转，继续平移搜索。': 'Rotation unverified. Continuing with translation.', '本轮未找到全部目标，已取消结果并保留原色。本次消耗 1 个染色剂。': 'Targets not found. Result canceled; original colors kept. One dye consumed.', '游戏窗口已最小化，请恢复后重试。': 'Restore the game window and retry.', '确认点击后结果页仍在，未确认套用成功。': 'Result page is still visible. Apply could not be confirmed.', '窗口位置或尺寸已变化。已停止，请按 F8 重新识别。': 'Game window changed. Press F8 to detect it again.', '结果色码与目标不符，已停止套用。请取消本次结果。': 'Result does not meet the targets. Please cancel it.', '结果页按钮在等待后仍无法可靠定位，未套用。': 'Apply button unreadable. No colors applied.', '缩放中心必须位于色板内。': 'Zoom pivot must be inside the board.', '色板定位不完整，已停止以避免误操作。': 'Board detection incomplete. Search stopped.', '色码卡片下方点位尚不可见，可能正在显示教学或结果窗口。': 'Markers not visible. Wait for the tutorial or close the result screen.', '输入校准完成：平移、旋转、缩放均引起画面变化；未套用颜色。': 'Diagnostics complete: drag, rotate and zoom changed the board. Nothing applied.', '键盘输入被 Windows 拒绝。': 'Windows rejected keyboard input.', ' 输入后色板没有可确认的变化，校准未通过。': ' input produced no verified change. Diagnostics failed.'})

EN.update({'未检测到唯一窗口': 'No unique window found', '① 设置颜色与窗口    →    ② 点击开始或按 F8    →    ③ 进入普通染色，教学后自动寻色': '1 Set colors and window   →   2 Start / F8   →   3 Open regular dye; search begins after the tutorial', '任务已启动，正在等待或寻色；按 F9 停止。': 'Already waiting or searching. Press F9 to stop.', '快捷键不可用：': 'Unavailable hotkeys: ', '快捷键已就绪：F8 开始 / F9 停止': 'Hotkeys ready: F8 Start / F9 Stop', '正在识别窗口：': 'Detecting window: ', '浮窗暂不可用，寻色状态请查看主窗口。': 'Overlay unavailable. Follow progress in the main window.', '游戏窗口 · ': 'Game window · ', '窗口选择已更新，下次开始时生效。': 'Window selection updated for the next start.', '自动检测': 'Auto-detect', '请先按 F9 停止，再更换游戏窗口。': 'Press F9 to stop before changing the game window.', '；请关闭其他工具副本或使用按钮。': '. Close other copies of this tool or use its buttons.', '未能自动切回游戏。请点击游戏窗口，程序会继续等待识别，无需再次开始。': 'Could not focus the game. Click the game window; detection will continue without restarting.', '选择游戏窗口': 'Select game window', '默认自动识别瑪奇Mobile，也可选择标题不同的游戏窗口。': 'Automatically finds Mabinogi Mobile. Choose a window manually if its title differs.', '刷新窗口': 'Refresh list', '使用此窗口': 'Use selection', '自动检测到：': 'Detected: ', '确认后仅对所选窗口识别；窗口关闭后需重新选择。': 'Only the selected window will be used. Select it again if it closes.', '发现多个游戏窗口，请手动选择目标窗口。': 'Multiple game windows found. Select the intended window manually.', '所选窗口已关闭，请重新选择游戏窗口。': 'The selected window closed. Select the game window again.', '无法读取窗口列表，请重试。': 'Could not list windows. Try again.', '未找到游戏窗口。请启动游戏，或手动选择窗口。': 'Game window not found. Open the game or select a window manually.', '感知色差 ΔE ≤ ': 'Color difference ΔE ≤ ', ' · 数值越小越严格': ' · Lower is stricter', '色差由中心向外增加 · 放大查看每个颜色，拖动或滚动浏览，悬停查看 HEX': 'Difference increases outward · Use +/− to zoom, drag to browse, hover for HEX', '色差由中心向外增加 · ＋／－缩放，拖动浏览，悬停查看 HEX': 'Difference increases outward · Use +/− to zoom, drag to browse, hover for HEX'})

TW={
'确认后仅对所选窗口识别；窗口关闭后需重新选择。':'確認後僅辨識所選視窗；視窗關閉後請重新選擇。',
'默认自动识别瑪奇Mobile，也可选择标题不同的游戏窗口。':'預設自動辨識瑪奇Mobile，也可選擇標題不同的遊戲視窗。',
}

def tr(text):
    if not isinstance(text,str) or language=='简体中文':return text
    if language=='繁體中文':return TW.get(text,traditional.convert(text).replace('玛奇','瑪奇'))
    if text in EN:return EN[text]
    for source in sorted(EN,key=len,reverse=True):text=text.replace(source,EN[source])
    return text

def install_widgets(ct):
    """Translate display text only; identifiers and HEX values are never changed."""
    for cls in (ct.CTkLabel,ct.CTkButton,ct.CTkCheckBox,ct.CTkSwitch):
        original_init=cls.__init__;original_config=cls.configure
        def init(self,*args,_original=original_init,**kwargs):
            if 'text' in kwargs:kwargs['text']=tr(kwargs['text'])
            _original(self,*args,**kwargs)
        def configure(self,*args,_original=original_config,**kwargs):
            if 'text' in kwargs:kwargs['text']=tr(kwargs['text'])
            return _original(self,*args,**kwargs)
        cls.__init__=init;cls.configure=configure
