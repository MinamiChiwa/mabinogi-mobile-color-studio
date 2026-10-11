import importlib,importlib.util,unittest


class NativePresentationTests(unittest.TestCase):
    def module(self):
        self.assertIsNotNone(importlib.util.find_spec('native_status'),'Native presentation missing')
        return importlib.import_module('native_status')
    def test_predicted_or_unknown_result_never_claims_actual_success(self):
        m=self.module();data=dict(verified=False,accepted=True,stop_reason='target_observed')
        title,body=m.result_text(data)
        self.assertNotIn('已达标',title);self.assertIn('未完成复核',body)
    def test_no_candidate_is_not_presented_as_unreachable(self):
        m=self.module();title,body=m.result_text(dict(verified=True,accepted=False,stop_reason='not_found_in_budget'))
        self.assertIn('未找到',title);self.assertIn('不能据此判断',body)
    def test_exact_and_user_tolerance_have_distinct_result_titles(self):
        m=self.module()
        for exact,expected in ((True,'精确'),(False,'容差')):
            title,body=m.result_text(dict(verified=True,accepted=True,target_exact=exact,stop_reason='target_observed'))
            self.assertIn(expected,title);self.assertIn('手动确认',body)
    def test_verified_unaccepted_compromise_is_labeled_as_unmatched(self):
        m=self.module();title,body=m.result_text(dict(verified=True,accepted=False,
            stop_reason='compromise_observed',outcome='compromise',best_current=True))
        self.assertIn('妥协',title);self.assertIn('未命中',title)
        self.assertIn('手动确认',body)
    def test_a_predicted_compromise_is_not_presented_as_verified(self):
        title,body=self.module().result_text(dict(verified=False,accepted=False,stop_reason='compromise_observed',outcome='compromise'))
        self.assertNotIn('妥协方案',title);self.assertIn('未完成复核',body)
    def test_an_unrestored_better_observation_is_not_labeled_current_best(self):
        title,body=self.module().result_text(dict(verified=True,accepted=False,stop_reason='compromise_observed',
            outcome='compromise',best_current=False))
        self.assertIn('未恢复',body)

    def test_active_palette_error_does_not_tell_user_to_exit_palette(self):
        title,body=self.module().result_text(dict(verified=False,stop_reason='already_active_palette'))
        self.assertIn('绑定',title)
        self.assertNotIn('退出当前染色界面',body)

    def test_internal_error_is_presented_as_diagnostic_failure(self):
        title,body=self.module().result_text(dict(verified=False,stop_reason='internal_error'))
        self.assertIn('内部',title);self.assertIn('诊断',body)

    def test_ended_palette_and_changed_binding_have_distinct_user_messages(self):
        ended=self.module().result_text(dict(stop_reason='palette_ended',verified=False))
        changed=self.module().result_text(dict(stop_reason='session_binding_changed',verified=False))
        self.assertIn('结束',ended[0]);self.assertIn('变化',changed[0])
        self.assertNotEqual(ended,changed)
        self.assertNotIn('时间不足',ended[0])

    def test_unstable_session_is_distinct_from_closed_or_changed_session(self):
        module=self.module()
        ended=module.result_text(dict(stop_reason='palette_ended',verified=False))
        changed=module.result_text(dict(stop_reason='session_binding_changed',verified=False))
        for reason in ('session_probe_unstable','session_observation_unstable'):
            with self.subTest(reason=reason):
                title,body=module.result_text(dict(stop_reason=reason,verified=False))
                self.assertIn('不稳定',title)
                self.assertIn('诊断',body)
                self.assertNotEqual((title,body),ended)
                self.assertNotEqual((title,body),changed)
                self.assertNotIn('时间不足',title)

    def test_last_verified_colors_are_historical_not_current_success(self):
        module=self.module();helper=getattr(module,'last_verified_display',None)
        self.assertTrue(callable(helper),'The UI needs a separate historical observation model')
        data=dict(stop_reason='palette_ended',verified=False,accepted=False,
            actual_colors=[None,None],last_verified_colors=['#EBEFE1','#838586'],
            last_verified_deltas=[2.8,40.1],last_verified_screenshot=True)
        shown=helper(data)
        self.assertEqual(shown['colors'],['#EBEFE1','#838586'])
        self.assertIn('未确认',shown['label'])
        self.assertFalse(shown['current']);self.assertFalse(shown['accepted'])
        data['last_verified_screenshot']=False
        self.assertIsNone(helper(data))

    def test_incomplete_initial_scan_is_not_reported_as_no_palette(self):
        for reason in ('initial_discovery_timeout','discovery_incomplete_timeout'):
            with self.subTest(reason=reason):
                title,body=self.module().result_text(dict(verified=False,stop_reason=reason))
                self.assertIn('扫描',title)
                self.assertIn('普通界面',body)
                self.assertNotIn('未检测到',title)

    def test_initial_context_timeout_and_ambiguous_candidates_are_distinct(self):
        title,_=self.module().result_text(dict(verified=False,stop_reason='initial_validation_timeout'))
        self.assertIn('初始化',title)
        title,body=self.module().result_text(dict(verified=False,stop_reason='ambiguous_active_palette_timeout'))
        self.assertIn('唯一',title);self.assertIn('多个',body)

    def test_discovery_progress_does_not_invite_entering_before_armed(self):
        from ui_progress import progress_text
        title,body=progress_text(dict(stage='discovery'))
        self.assertIn('准备',title)
        self.assertIn('暂时不要进入',body)

    def test_refinement_explains_stationary_board_and_shows_only_measured_results(self):
        from ui_progress import progress_text
        import i18n
        data=dict(stage='refinement',verified=True,screenshot_verified=True,
            current_colors=['#FFFFFF','#FFFFFF','#EBEEDC'],current_deltas=[0.,0.,11.4525766],
            checked_routes=14527)
        title,body=progress_text(data)
        self.assertIn('已保留当前配色',title)
        self.assertIn('数十秒',body);self.assertIn('F9',body)
        self.assertIn('区域 3  #EBEEDC · ΔE 11.45',body)
        self.assertNotIn('14527',body)
        for count in (2,3):
            _,text=progress_text(dict(data,current_colors=data['current_colors'][:count],
                current_deltas=[0.,None,11.45][:count]))
            self.assertIn('未参与匹配',text)
            self.assertEqual('区域 3' in text,count==3)
        _,unverified=progress_text(dict(data,screenshot_verified=False))
        self.assertNotIn('#FFFFFF',unverified)
        original=i18n.language
        try:
            i18n.set_language('English')
            translated=str(i18n.tr(title+'\n'+body))
            self.assertFalse(any('\u4e00'<=c<='\u9fff' for c in translated),translated)
        finally:i18n.set_language(original)

    def test_discovery_keeps_memory_reading_details_out_of_user_status(self):
        from ui_progress import progress_text
        title,body=progress_text(dict(stage='discovery',discovery=dict(bytes_scanned=33554432,
            regions_visited=256,eligible_addresses=['0x10000'],candidate_read_failures=2)))
        self.assertEqual((title,body),progress_text(dict(stage='discovery')))
        self.assertNotIn('MiB',body);self.assertNotIn('0x10000',body)

    def test_discovery_read_failure_is_explicit_and_fully_localized(self):
        import i18n
        original=i18n.language
        try:
            title,body=self.module().result_text(dict(verified=False,stop_reason='discovery_read_failure'))
            self.assertIn('准备',title)
            self.assertIn('普通界面',body)
            self.assertNotIn('未检测到',title)
            i18n.set_language('English')
            for text in (title,body):
                self.assertFalse(any('\u4e00'<=c<='\u9fff' for c in str(i18n.tr(text))))
        finally:i18n.set_language(original)

    def test_explicit_measured_choice_is_not_presented_as_failed_restoration(self):
        title,body=self.module().result_text(dict(verified=True,accepted=False,
            stop_reason='user_candidate_observed',best_current=False))
        self.assertIn('所选',title)
        self.assertIn('实测色差',body)
        self.assertNotIn('未恢复',body)

    def test_candidate_rejections_are_localized_without_technical_error_text(self):
        import i18n
        from native_status import candidate_reason_text
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                for reason in ('insufficient_protected_time','candidate_compile_timeout',
                        'insufficient_protected_actions','candidate_return_not_proven',
                        'candidate_endpoint_not_reproduced','reference_changed',
                        'stale_or_unknown_candidate','RuntimeError: implementation detail'):
                    with self.subTest(language=language,reason=reason):
                        source=candidate_reason_text(reason);text=str(i18n.tr(source))
                        self.assertNotIn(reason,text)
                        if language=='English':
                            self.assertFalse(any('\u4e00'<=char<='\u9fff' for char in text),text)
        finally:i18n.set_language(original)

    def test_retry_reasons_distinguish_time_limits_from_actions_and_reset_state(self):
        helper=getattr(self.module(),'retry_reason_text',None)
        self.assertTrue(callable(helper),'Retry availability needs its actual reason')
        self.assertEqual(helper('insufficient_retry_time'),'剩余时间不足以完成重试，已保留当前颜色。')
        for reason,expected in (('insufficient_retry_actions','操作'),('action_limit','操作'),
                ('round_limit','搜索'),('unsupported_retry_settings','缩小'),
                ('retry_resetting','动作'),('session_closing','结束')):
            with self.subTest(reason=reason):
                body=helper(reason)
                self.assertIn(expected,body)
                self.assertNotIn('时间不足',body)
                self.assertNotIn(reason,body)

    def test_retry_reasons_are_fully_translated_without_raw_exception_text(self):
        import i18n
        helper=getattr(self.module(),'retry_reason_text',None)
        self.assertTrue(callable(helper))
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                for reason in ('insufficient_retry_time','insufficient_retry_actions','action_limit',
                        'round_limit','unsupported_retry_settings','retry_resetting','session_closing',
                        'RuntimeError: implementation detail'):
                    with self.subTest(language=language,reason=reason):
                        text=str(i18n.tr(helper(reason)))
                        self.assertNotIn(reason,text)
                        if language=='English':
                            self.assertFalse(any('\u4e00'<=char<='\u9fff' for char in text),text)
        finally:i18n.set_language(original)


if __name__=='__main__':unittest.main()
