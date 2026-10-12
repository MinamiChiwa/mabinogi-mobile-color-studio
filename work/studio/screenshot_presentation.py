"""Actual screenshot results and their explicit historical/current distinction."""
def result_text(data):
    if data.get('stop_reason') in ('palette_ended','interrupted'):
        return '截图寻色已停止','自动操作已停止；请以游戏当前颜色为准。'
    if not data.get('verified'):
        return '截图寻色已结束','当前色码未完成复核，请以游戏内显示为准。'
    if data.get('accepted'):
        return '截图寻色目标已达标','游戏实际色码已复核，请在游戏内手动确认是否套用。'
    if data.get('best_current') is False:
        return '截图寻色 · 当前妥协结果','当前颜色已经复核；此前更好的实测结果未完全恢复，请查看当前色差后再决定是否套用。'
    return '截图寻色 · 妥协结果','本轮未命中全部目标。下方为游戏实际色码与色差；可重试或在游戏内手动调整。'
