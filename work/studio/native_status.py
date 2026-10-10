"""User-facing native results, separate from predicted candidate acceptance."""


def result_text(data):
    reason=data.get('stop_reason')
    if data.get('verified') and data.get('accepted') and reason=='target_observed':
        return ('目标 HEX 已精确匹配' if data.get('target_exact') else '目标颜色已在容差内匹配',
                '游戏色码已复核，请在游戏内手动确认是否套用。')
    if reason=='compromise_observed' and data.get('verified'):
        if data.get('best_current') is False:
            return ('未命中目标 · 当前妥协结果','当前颜色已复核，但未恢复此前更好的实测结果，请在游戏内手动确认是否采用。')
        detail='已复核本轮色差较小的方案，请查看实测色差，在游戏内手动确认是否采用。'
        refinement=data.get('refinement_stop')
        if refinement in ('local_search_budget','local_search_timeout'):
            detail+=' 本轮细化搜索时间已用完，保留当前结果；不能据此判断无解。'
        elif refinement=='local_family_exhausted':
            detail+=' 当前局部动作组合未找到可安全执行的改善路线，不能据此判断无解。'
        elif refinement=='insufficient_protected_time':
            detail+=' 已保留恢复时间，当前余量不足以再安全试探。'
        return ('未命中目标 · 妥协方案',detail)
    if reason=='not_found_in_budget':
        return ('本轮未找到达标方案','有限搜索未找到符合目标的可执行方案，不能据此判断色板无解。')
    if reason=='insufficient_time':return ('剩余时间不足，已停止','未继续发送操作，请以游戏当前颜色为准。')
    if reason in ('insufficient_route_actions','insufficient_compromise_actions'):
        return ('剩余操作额度不足，已保留当前颜色','完整路线超过本轮剩余操作额度，未执行部分路线；请查看当前游戏颜色。')
    if reason=='observation_failed':return ('颜色复核暂未完成，已停止','已保留能够读取的游戏色码；该记录未完成截图复核，请以游戏当前颜色为准。')
    if reason=='already_active_palette':return ('无法绑定当前染色板','请确认只打开了一个染色板；关闭重叠窗口后重试。')
    if reason=='unavailable':
        category=data.get('unavailable_reason')
        if category=='module_resolution':
            return ('未能定位游戏模块','已记录目标进程及实际安装路径，请查看诊断记录。')
        if category=='game_build':
            return ('当前游戏版本尚未支持','游戏模块或数据版本与当前适配版本不同，详情已写入诊断记录。')
        if category=='coordinate_mapping':
            return ('窗口坐标映射未完成','已记录游戏内部尺寸、物理窗口尺寸及缩放信息，请查看诊断记录。')
        if category=='window_measurement':
            return ('未能读取物理窗口坐标','请恢复游戏窗口，详情已写入诊断记录。')
        return ('当前游戏或窗口条件不支持','请检查游戏版本、窗口和程序权限，详情已写入诊断记录。')
    if reason=='interrupted':return ('已停止自动染色','请以游戏当前颜色为准。')
    if reason=='model_response_mismatch':return ('实际操作响应不符，已停止','已停止后续操作，请查看当前游戏颜色。')
    if reason=='internal_error':return ('工具内部错误，已停止','本轮未继续发送操作，详细异常已写入诊断记录。')
    if not data.get('verified'):
        return ('本轮寻色已停止','当前色码未完成复核，请以游戏内显示为准。')
    return ('本轮寻色已结束','当前颜色未达到全部目标，请以游戏内显示为准。')
