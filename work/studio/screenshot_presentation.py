"""Actual screenshot results and their explicit historical/current distinction."""
def result_text(data):
    if data.get('stop_reason')=='interrupted':
        from native_status import result_text as native_result_text
        cause=data.get('interruption_reason')
        if cause in ('focus_lost','window_changed','activation_failed'):
            return native_result_text(data)
        if data.get('verified'):
            return '截图寻色已停止','游戏实际色码已复核，请在游戏内手动确认是否套用。'
    if data.get('stop_reason') in ('palette_ended','interrupted'):
        return '截图寻色已停止','自动操作已停止；请以游戏当前颜色为准。'
    if data.get('stop_reason')=='processing_error':
        if not data.get('verified'):
            detail='错误记录已保存，当前色码未完成复核；请以游戏当前颜色为准。'
        elif data.get('best_current') is False:
            detail='错误记录已保存，当前颜色已复核，但未能恢复此前较好的结果；请以游戏当前颜色为准。'
        else:
            detail='已保留或恢复本轮较好的实测颜色，错误记录已保存；请查看当前色差后再决定是否套用。'
        return '截图寻色处理异常',detail
    if not data.get('verified'):
        return '截图寻色已结束','当前色码未完成复核，请以游戏内显示为准。'
    if data.get('accepted'):
        if data.get('best_current') is False:
            return '截图寻色目标已达标','当前颜色符合目标要求，但未回到此前保留的配色；请以游戏当前颜色为准。'
        return '截图寻色目标已达标','游戏实际色码已复核，请在游戏内手动确认是否套用。'
    if data.get('best_current') is False:
        return '截图寻色 · 当前妥协结果','当前颜色已经复核；此前更好的实测结果未完全恢复，请查看当前色差后再决定是否套用。'
    return '截图寻色 · 妥协结果','本轮未命中全部目标。妥协选色兼顾色相与饱和度，色差仍按原有 ΔE 显示；请在游戏内决定是否套用。'
