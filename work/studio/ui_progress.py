"""Presentation-only progress: counts describe actual work, never fake percentages."""
STAGES={
    'native_validate':'检查当前色板',
    'discovery':'准备寻色',
    'waiting':'等待染色界面','zoom':'识别与缩放','capture':'采集颜色板',
    'binding':'识别本局色板',
    'align':'对齐采集画面','period':'测量色板周期','stitch':'拼接全局颜色板',
    'export':'保存颜色板','validate':'检查拼图质量','search':'搜索目标颜色',
    'similarity':'计算旋转与缩放','ready':'准备候选方案','position':'移动到目标位置','verify':'复核游戏色码',
    'observe':'读取当前游戏色码','restore':'正在尝试返回本轮最好颜色',
    'retry':'重新搜索目标颜色',
}


def progress_text(data):
    if data.get('stage')=='refinement':
        title='正在优化当前配色'
        lines=[]
        colors=data.get('current_colors') or []
        deltas=data.get('current_deltas') or []
        if data.get('verified') and data.get('screenshot_verified') and len(colors) in (2,3) and len(colors)==len(deltas):
            lines.append('当前配色 · 游戏实测')
            for i,(color,delta) in enumerate(zip(colors,deltas)):
                lines.append(f'区域 {i+1}  {color or "—"} · '+(f'ΔE {delta:.2f}' if delta is not None else '未参与匹配'))
            lines.append('')
        guidance=('可查看下方已确认的颜色；满意时按 F9 停止。' if lines else
            '正在寻找目标颜色。可按 F9 停止，再查看游戏当前结果。')
        lines.extend(('正在计算更好的配色，计算期间色板可能暂时不动。','',guidance))
        return title,'\n'.join(lines)
    title=STAGES.get(data.get('stage'),'正在按目标计算，请稍候。')
    if data.get('total'):title+=f"  {data.get('current',0)}/{data['total']}"
    body=data.get('message') or (
        '正在准备寻色，请保持游戏窗口可见。F9 可停止。' if data.get('stage')=='discovery' else
        '请按提示进入染色；已经打开色板时无需重新进入。F9 可停止。' if data.get('stage')=='waiting' else
        '正在计算目标位置，色板暂时不动。F9 可停止。' if data.get('stage') in ('align','period','stitch','export','validate','search','similarity','ready') else
        '正在调整色板，请保持游戏在前台。F9 可停止。')
    return title,body


def single_result_presentation(data):
    """Explain single-region outcomes without treating a miss as a failure.

    Only a color read back and verified in-game may be called a compromise.
    If the best historical measurement could not be restored, make that
    recovery limitation explicit instead of presenting the current color as
    the best result.
    """
    if data.get('stop_reason') in ('interrupted','palette_ended'):
        return ('自动操作已停止','请在游戏中查看当前颜色，并手动决定是否套用。')
    outcome=data.get('outcome')
    if not data.get('verified') or outcome=='unverified':
        return ('单区域寻色已结束', '当前色码未完成复核，请以游戏内显示为准。')
    if outcome=='matched' or (outcome not in ('matched','compromise','unverified') and data.get('accepted')):
        return ('单区域目标已达标', '自动移动已结束，可继续在游戏内手动调整。')
    if data.get('best_current') is False:
        return ('未命中目标 · 妥协方案',
                '未找到满足目标的颜色。此前最佳实测结果未能恢复；下方显示当前已复核的妥协结果，请以游戏内当前颜色为准。')
    return ('未命中目标 · 妥协方案',
            '查看各区域的实测色码与色差，再在游戏内决定是否套用。')
