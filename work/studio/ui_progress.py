"""Presentation-only progress: counts describe actual work, never fake percentages."""
STAGES={
    'waiting':'等待染色界面','zoom':'识别与缩放','capture':'采集颜色板',
    'align':'对齐采集画面','period':'测量色板周期','stitch':'拼接全局颜色板',
    'export':'保存颜色板','validate':'检查拼图质量','search':'搜索目标颜色',
    'similarity':'计算旋转与缩放','ready':'准备候选方案','position':'移动到目标位置','verify':'复核游戏色码',
    'observe':'读取当前游戏色码','restore':'恢复已测最佳颜色',
}


def progress_text(data):
    title=STAGES.get(data.get('stage'),'正在按目标计算，请稍候。')
    if data.get('total'):title+=f"  {data.get('current',0)}/{data['total']}"
    body=data.get('message') or (
        '等待手动进入染色倒计时；F9 可停止。' if data.get('stage')=='waiting' else
        '图像处理中，鼠标暂时不动是正常现象。' if data.get('stage') in ('align','period','stitch','export','validate','search','similarity','ready') else
        '根据图像实测位移校正；F9随时停止。')
    return title,body


def single_result_presentation(data):
    """Explain single-region outcomes without treating a miss as a failure.

    Only a color read back and verified in-game may be called a compromise.
    If the best historical measurement could not be restored, make that
    recovery limitation explicit instead of presenting the current color as
    the best result.
    """
    outcome=data.get('outcome')
    if not data.get('verified') or outcome=='unverified':
        return ('单区域寻色已结束', '当前色码未完成复核，请以游戏内显示为准。')
    if outcome=='matched' or (outcome not in ('matched','compromise','unverified') and data.get('accepted')):
        return ('单区域目标已达标', '自动移动已结束，可继续在游戏内手动调整。')
    if data.get('historical_best_unrestored') or data.get('best_current') is False:
        return ('未命中目标 · 妥协方案',
                '未找到满足目标的颜色。此前最佳实测结果未能恢复；下方显示当前已复核的妥协结果，请以游戏内当前颜色为准。')
    return ('未命中目标 · 妥协方案',
            '未找到满足目标的颜色；下方显示本轮已实测确认的妥协结果。这是寻色未命中后的正常结束状态，并非程序故障。请查看色差，并在游戏内手动确认是否采用。')
