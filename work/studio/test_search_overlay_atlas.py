import unittest
from unittest.mock import Mock,patch

from search_overlay import SearchOverlay, candidate_display, update_candidate_display


class Label:
    def __init__(self):self.values=[]
    def configure(self,**values):self.values.append(values)


class Button:
    def __init__(self):self.states=[]
    def configure(self,**values):self.states.append(values)


class SearchOverlayAtlasTests(unittest.TestCase):
    def test_alignment_failure_switches_overlay_from_capture_count_to_recovery(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='computing';overlay.update_activity=Mock();overlay.render=Mock()
        overlay.handle('atlas_status',{'message':'配准失败，已停止继续移动，正在读取当前游戏颜色。'})
        self.assertEqual(overlay.phase,'computing')
        overlay.update_activity.assert_called_once_with({
            'stage':'recover',
            'message':'配准失败，已停止继续移动，正在读取当前游戏颜色。'})
        self.assertEqual(overlay.render.call_args.args,
                         ('停止采集并读取当前颜色',
                          '配准失败，已停止继续移动，正在读取当前游戏颜色。'))

    def test_single_region_compromise_result_is_labeled_as_expected_outcome(self):
        import i18n
        original=i18n.language
        try:
            overlay=SearchOverlay.__new__(SearchOverlay)
            overlay.rules=[dict(enabled=True),dict(enabled=False),dict(enabled=False)]
            overlay.clear_candidates=Mock();overlay.results=Mock();overlay.copy=Mock()
            overlay.activity=Mock();overlay.collapse=Mock();overlay.resize_surface=Mock()
            overlay.render=Mock()
            data=dict(verified=True,accepted=False,best_verified=True,best_current=True,
                      outcome='compromise',actual_colors=['#888888',None,None],
                      actual_deltas=[12.,None,None])
            with patch('search_overlay.ct.CTkLabel'):
                overlay.show_single_result(data)
            self.assertEqual(overlay.render.call_args.args,
                             ('未命中目标 · 妥协方案',
                              '未找到满足目标的颜色；下方显示本轮已实测确认的妥协结果。这是寻色未命中后的正常结束状态，并非程序故障。请查看色差，并在游戏内手动确认是否采用。'))
            i18n.set_language('English')
            self.assertIn('Compromise',str(i18n.tr(overlay.render.call_args.args[0])))
            self.assertIn('normal outcome',str(i18n.tr(overlay.render.call_args.args[1])))
        finally:i18n.set_language(original)

    def test_multi_region_compromise_notice_is_translated_in_three_languages(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
                    setattr(overlay,name,Mock())
                overlay.candidate_rows={}
                data=dict(batch_id='batch',default_id=0,compromise_only=True,
                    candidates=[dict(id=0,colors=['#000000']*3,deltas=[20]*3,
                                     maximum=20,average=20,accepted=False)])
                with patch('search_overlay.ct.CTkFrame'),patch('search_overlay.ct.CTkButton'), \
                     patch('search_overlay.ct.CTkLabel') as labels:
                    overlay.show_candidates(data)
                texts=' '.join(str(i18n.tr(c.kwargs.get('text',''))) for c in labels.call_args_list)
                expected=str(i18n.tr('本轮没有预测达标方案；以下结果仅供参考，实际复核未达标时会停止。'))
                self.assertIn(expected,texts)
        finally:i18n.set_language(original)

    def test_multi_region_exact_miss_notice_promises_measured_near_match(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
                    setattr(overlay,name,Mock())
                overlay.candidate_rows={}
                data=dict(batch_id='batch',default_id=0,compromise_only=True,
                    compromise_fallback=True,
                    candidates=[dict(id=0,colors=['#FFFEFE']*3,deltas=[.44,.8,1.2],
                                     maximum=1.2,average=.81,accepted=False)])
                with patch('search_overlay.ct.CTkFrame'),patch('search_overlay.ct.CTkButton'), \
                     patch('search_overlay.ct.CTkLabel') as labels:
                    overlay.show_candidates(data)
                texts=' '.join(str(i18n.tr(c.kwargs.get('text',''))) for c in labels.call_args_list)
                expected=str(i18n.tr('本轮没有共同精准命中；以下候选按综合色差排序，实测后保留近似结果，不会自动确认染色。'))
                self.assertIn(expected,texts)
                if language=='English':self.assertIn('measured near match',texts)
                elif language=='繁體中文':self.assertIn('實測後保留近似結果',texts)
                else:self.assertIn('实测后保留近似结果',texts)
        finally:i18n.set_language(original)

    def test_pose_only_recovery_does_not_claim_colors_were_read(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
                    setattr(overlay,name,Mock())
                with patch('search_overlay.ct.CTkLabel') as labels:
                    overlay.show_recovery(dict(verified=False,pose_reliable=True,
                        actual_colors=[None]*3,actual_deltas=[None]*3))
                self.assertEqual(overlay.render.call_args.args[1],
                                 '未能读取当前色码，请以游戏内显示为准。')
                labels.assert_not_called()
                if language=='English':
                    self.assertIn('could not be read',str(i18n.tr(overlay.render.call_args.args[1])))
        finally:i18n.set_language(original)

    def test_unrestored_history_is_labeled_separately_in_three_languages(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                overlay.show_recovery=Mock();overlay.render=Mock();overlay.results=Mock()
                data=dict(actual_colors=['#513B43',None,None],actual_deltas=[51,None,None],
                          best_result=dict(actual_colors=['#F2F2F2',None,None],actual_deltas=[17,None,None]))
                with patch('search_overlay.ct.CTkLabel') as label:
                    overlay.show_unrestored_best(data)
                overlay.show_recovery.assert_called_once_with(data)
                texts=[str(i18n.tr(c.kwargs.get('text',''))) for c in label.call_args_list]
                self.assertIn(str(i18n.tr('先前最佳实测（未恢复）')),texts)
                if language=='English':self.assertIn('not restored',' '.join(texts))
                self.assertIn('#F2F2F2',' '.join(texts))
                self.assertNotIn('None',' '.join(texts))
        finally:i18n.set_language(original)

    def test_current_alternate_is_first_and_swatches_use_game_hex_without_changing_targets(self):
        import copy
        data=dict(batch_id='batch',default_id=0,candidates=[
            dict(id=0,colors=['#9369A7','#7E5F9D','#304592'],deltas=[61.7,60.,49.6],
                 maximum=61.7,average=57.1,accepted=False),
            dict(id=6,colors=['#083D8F','#414693','#304592'],deltas=[46.9,49.1,49.6],
                 maximum=49.6,average=48.5,accepted=False)])
        original=copy.deepcopy(data)
        result=dict(candidate_id=6,verified=True,actual_colors=['#073E90','#414493','#304591'],
                    actual_deltas=[46.95,47.84,50.20],maximum=50.20,average=48.33,
                    accepted=False,exact_matches=0,exact_total=2,family_consistent=True)
        updated=update_candidate_display(data,6,result=result,current=True)
        self.assertEqual(data,original)
        self.assertEqual(updated['default_id'],6)
        self.assertEqual([row['id'] for row in updated['candidates']],[6,0])
        shown=candidate_display(updated['candidates'][0],updated['observations'][6])
        self.assertEqual(shown['colors'],result['actual_colors'])
        self.assertEqual(shown['deltas'],result['actual_deltas'])
        self.assertEqual(shown['maximum'],50.20)
        self.assertTrue(shown['measured'])
        self.assertFalse(candidate_display(updated['candidates'][1])['measured'])
        # Execution data remains a prediction, never silently replaced by HEX.
        self.assertEqual(updated['candidates'][0]['colors'],original['candidates'][1]['colors'])

    def test_changed_route_invalidates_old_observation_only_for_that_candidate(self):
        data=dict(candidates=[dict(id=0,colors=['#111111']*3),dict(id=6,colors=['#222222']*3)],
                  observations={0:dict(verified=True),6:dict(verified=True)},default_id=0)
        updated=update_candidate_display(data,6,candidate=dict(id=6,colors=['#333333']*3),current=True)
        self.assertEqual(set(updated['observations']),{0})
        self.assertEqual(updated['candidates'][0]['colors'],['#333333']*3)
        self.assertEqual(set(data['observations']),{0,6})

    def test_switching_away_restores_other_buttons_published_target_forecast(self):
        original=dict(candidates=[dict(id=0,colors=['#111111']*3),dict(id=6,colors=['#222222']*3)],default_id=0)
        first=update_candidate_display(original,0,candidate=dict(id=0,colors=['#999999']*3),current=True)
        second=update_candidate_display(first,6,candidate=dict(id=6,colors=['#333333']*3),current=True)
        self.assertEqual(second['candidates'],[dict(id=6,colors=['#333333']*3),dict(id=0,colors=['#111111']*3)])

    def test_final_event_reorders_and_keeps_selection_callbacks_on_correct_ids(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay._candidate_data=dict(batch_id='batch',default_id=0,candidates=[
            dict(id=0,colors=['#9369A7']*3),dict(id=6,colors=['#083D8F']*3)])
        overlay.default_candidate_id=0;overlay.activity=Mock();overlay.render=Mock()
        overlay.candidate_rows={0:Button(),6:Button()};overlay.select_candidate=Mock()
        overlay.show_default_verification=Mock();overlay.show_candidates=Mock()
        result=dict(candidate_id=6,verified=True,actual_colors=['#073E90','#414493','#304591'],
                    actual_deltas=[46.95,47.84,50.20],accepted=False)
        overlay.handle('atlas_default_verified',result)
        display=overlay.show_candidates.call_args.args[0]
        self.assertEqual([row['id'] for row in display['candidates']],[6,0])
        self.assertEqual(display['observations'][6],result)
        self.assertEqual(overlay.default_candidate_id,6)
        self.assertEqual(overlay.phase,'choosing')
        self.assertEqual(overlay.candidate_rows[6].states[-1]['state'],'disabled')
        self.assertEqual(overlay.candidate_rows[0].states[-1]['state'],'normal')
        overlay.select_candidate.assert_not_called()

    def test_candidate_widgets_display_measured_swatches_and_source_labels_in_three_languages(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
                    setattr(overlay,name,Mock())
                overlay.candidate_rows={}
                data=dict(batch_id='batch',default_id=6,candidates=[
                    dict(id=6,colors=['#FFFFFF']*3,deltas=[0]*3,maximum=0,average=0,accepted=True)],
                    observations={6:dict(verified=True,actual_colors=['#073E90','#414493',None],
                        actual_deltas=[46.95,47.84,None],maximum=47.84,average=47.395,accepted=False)})
                with patch('search_overlay.ct.CTkFrame'),patch('search_overlay.ct.CTkButton'), \
                     patch('search_overlay.ct.CTkLabel') as labels:
                    overlay.show_candidates(data)
                colors=[c.kwargs['fg_color'] for c in labels.call_args_list if 'fg_color' in c.kwargs]
                self.assertEqual(colors,['#073E90','#414493','#333333'])
                texts=[str(i18n.tr(c.kwargs.get('text',''))) for c in labels.call_args_list]
                self.assertIn(str(i18n.tr('当前方案 · 游戏实测')),texts)
                self.assertNotIn('#FFFFFF',' '.join(texts))
                self.assertNotIn('None',' '.join(texts))
                if language=='English':self.assertIn('Measured in game',' '.join(texts))
        finally:i18n.set_language(original)

    def test_bound_route_prediction_replaces_old_candidate_colours(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay._candidate_data={'candidates':[{'id':7,'colors':['#FFFFFF']*3}]}
        overlay.show_candidates=Mock()
        replacement={'id':7,'colors':['#FAFAFA']*3,'prediction_pose_source':'bound_integer_route_forecast'}
        overlay.handle('atlas_prediction_updated',{'candidate_id':7,'candidate':replacement})
        self.assertEqual(overlay.show_candidates.call_args.args[0]['candidates'],[replacement])

    def test_verified_result_without_atlas_prediction_renders_in_all_languages(self):
        import i18n
        original=i18n.language
        try:
            for language in ('简体中文','繁體中文','English'):
                i18n.set_language(language)
                overlay=SearchOverlay.__new__(SearchOverlay)
                for name in ('clear_candidates','results','copy','activity','collapse','resize_surface','render'):
                    setattr(overlay,name,Mock())
                data=dict(accepted=True,actual_colors=['#FFFFFF',None,None],
                          actual_deltas=[0,None,None],predicted_colors=[None]*3,
                          predicted_deltas=[None]*3,maximum=0,average=0)
                with patch('search_overlay.ct.CTkLabel') as label:
                    overlay.show_verification(data)
                    text=str(label.call_args_list[0].kwargs['text'])
                self.assertIn('#FFFFFF',text)
                self.assertNotIn('None',text)
                if language=='English':
                    self.assertIn('Measured',text)
                    self.assertNotIn('实测',text)
        finally:i18n.set_language(original)

    def test_f9_dismisses_all_phases_and_late_events_cannot_restore_overlay(self):
        for phase in ('waiting','positioning','choosing','verified','invalidated','unavailable'):
            with self.subTest(phase=phase):
                overlay=SearchOverlay.__new__(SearchOverlay)
                overlay.phase=phase;overlay.batch_id='batch';overlay.candidate_rows={7:Button()}
                overlay.withdraw=Mock();overlay.render=Mock();overlay.show_candidates=Mock()
                overlay.select_candidate=Mock()
                overlay.dismiss()
                for kind in ('atlas_candidates','atlas_default_verified','atlas_invalidated','interrupted','finished'):
                    overlay.handle(kind,{})
                overlay.choose('batch',7)
                self.assertEqual(overlay.phase,'stopped');self.assertIsNone(overlay.batch_id)
                overlay.withdraw.assert_called_once();overlay.render.assert_not_called()
                overlay.show_candidates.assert_not_called();overlay.select_candidate.assert_not_called()

    def test_expired_choice_disables_candidates_and_rejects_late_clicks(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='choosing';overlay._text=None;overlay.batch_id='batch-1'
        overlay.selection_sent=False;overlay.candidate_rows={7:Button()}
        overlay.heading=Label();overlay.copy=Label()
        overlay.select_candidate=Mock()

        overlay.handle('atlas_selection_expired',{})
        overlay.choose('batch-1',7)

        self.assertEqual(overlay.phase,'verified')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)
        overlay.select_candidate.assert_not_called()

    def test_choice_rejection_keeps_automatic_result_and_disables_rows(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='positioning';overlay._text=None;overlay.batch_id='batch-1'
        overlay.candidate_rows={7:Button()};overlay.heading=Label();overlay.copy=Label()
        overlay.handle('atlas_choice_rejected',{'message':'Not enough time.'})
        self.assertEqual(overlay.phase,'verified')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)

    def test_no_joint_candidate_shows_explicit_read_only_title(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='positioning';overlay._text=None;overlay.batch_id='batch-1'
        overlay.candidate_rows={7:Button()};overlay.heading=Label();overlay.copy=Label()
        overlay.clear_candidates=Mock();overlay.render=Mock()
        overlay.handle('atlas_invalidated',{
            'reason':'no_joint_candidate',
            'message':'未找到所有启用区域共同满足目标的候选，已停止自动移动并读取当前游戏色码。'})
        self.assertEqual(overlay.phase,'invalidated')
        self.assertEqual(overlay.render.call_args.args,
                         ('未找到共同方案',
                          '未找到所有启用区域共同满足目标的候选，已停止自动移动并读取当前游戏色码。'))

    def test_stop_invalidates_visible_choices_and_finished_event_keeps_overlay(self):
        overlay=SearchOverlay.__new__(SearchOverlay)
        overlay.phase='choosing';overlay._text=None;overlay.batch_id='batch-1'
        overlay.candidate_rows={7:Button()};overlay.heading=Label();overlay.copy=Label()
        overlay.select_candidate=Mock()
        overlay.handle('interrupted',{'message':'Stopped.'})
        overlay.handle('finished',{})
        overlay.choose('batch-1',7)
        self.assertEqual(overlay.phase,'interrupted')
        self.assertIsNone(overlay.batch_id)
        self.assertIn({'state':'disabled'},overlay.candidate_rows[7].states)
        overlay.select_candidate.assert_not_called()


if __name__=='__main__':unittest.main()
