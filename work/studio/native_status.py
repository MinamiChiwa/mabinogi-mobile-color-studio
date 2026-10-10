"""User-facing native results, separate from predicted candidate acceptance."""


def candidate_reason_text(reason):
    """Explain selection rejections without displaying internal exception text."""
    if reason in ('insufficient_protected_time','candidate_compile_timeout'):
        return '剩余时间不足以完成切换、返回与颜色复核，已保留当前实测结果。'
    if reason=='insufficient_protected_actions':
        return '完整切换与返回路线超过剩余操作额度，已保留当前实测结果。'
    if reason=='candidate_return_not_proven':
        return '所选方案的返回路线尚未完成验证，已保留当前实测结果。'
    if reason=='candidate_endpoint_not_reproduced':
        return '所选方案无法完成路线复核，已保留当前实测结果。'
    if reason=='reference_changed':
        return '当前色板位置或颜色已变化，已重新读取；请选择当前候选。'
    if reason=='stale_or_unknown_candidate':
        return '所选候选已失效，已保留当前颜色。'
    return '所选方案暂时无法安全切换，已保留当前实测结果。'


def result_text(data):
    reason=data.get('stop_reason')
    if reason=='initial_validation_timeout':
        return ('游戏初始化检查超时','进程或窗口检查尚未完成。请在游戏普通界面重试，并附上本次诊断记录。')
    if reason=='discovery_read_failure':
        return ('色板候选读取未完成','有候选或内存区域未能可靠读取，本次已停止扫描并保存详情。请在游戏普通界面重试，无需消耗染色道具。')
    if reason in ('initial_discovery_timeout','discovery_incomplete_timeout'):
        return ('色板扫描尚未完成','本次扫描未能完成候选和唯一性检查，不能据此判断没有染色板。请在游戏普通界面重新准备，等提示就绪后再进入染色。')
    if reason=='ambiguous_active_palette_timeout':
        return ('未能唯一绑定染色板','检测到多个活动色板候选。请确认只打开了一个染色板，并附上诊断记录。')
    if reason=='no_active_palette_timeout':
        return ('等待染色界面超时','等待期间未找到已验证的活动染色板，本轮没有发送操作。')
    if reason=='user_candidate_observed' and data.get('verified'):
        return ('所选方案已复核','已保留您选择的方案。请查看各区域实测色差，在游戏内手动确认是否套用。')
    if reason=='candidate_recovery_unconfirmed':
        return ('所选方案返回未完成复核','切换后的恢复结果尚未确认。请以游戏当前颜色为准，详细记录已保存。')
    if reason=='no_available_regions':return ('本局没有已启用的可用区域','本局没有已启用的可用区域，请启用区域 1 或 2。')
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
        if category=='process_access':
            return ('无法读取游戏进程（权限被拒绝）','请让工具与游戏使用相同权限级别；若游戏以管理员运行，请右键工具选择「以管理员身份运行」后重开。先在游戏普通界面重试，确认权限检查通过后再开始新一局染色。')
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
