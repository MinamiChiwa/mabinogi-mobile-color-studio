import unittest
from types import SimpleNamespace

import i18n
from ui_dialogs import TUTORIAL
from ui_strings import EN, TW


class FakeWidget:
    def __init__(self,*args,text='',**kwargs):
        self.text=text;self.exists=True
    def configure(self,**kwargs):
        if 'text' in kwargs:self.text=kwargs['text']
    def winfo_exists(self):return self.exists
    def title(self,value=None):
        if value is not None:self.window_title=value
        return getattr(self,'window_title','')


def fake_class(name):
    return type(name,(FakeWidget,),{})


class UiLanguageTests(unittest.TestCase):
    def test_best_result_protection_messages_are_fully_translated(self):
        from runtime_messages import EN as runtime_en,TW as runtime_tw
        messages=['正在恢复本轮已实测的最佳方案。','先前最佳实测（未恢复）',
                  '未能恢复先前最佳结果，请以游戏当前颜色为准。']
        original=i18n.language
        try:
            for language,translations in [('English',runtime_en),('繁體中文',runtime_tw)]:
                i18n.set_language(language)
                for message in messages:self.assertEqual(str(i18n.tr(message)),translations[message])
        finally:i18n.set_language(original)

    def test_unreachable_choice_message_has_complete_runtime_translations(self):
        from runtime_messages import EN as runtime_en,TW as runtime_tw
        message='所选方案无法从当前位置可靠到达，已保留当前颜色。'
        original=i18n.language
        try:
            for language,translations in [('English',runtime_en),('繁體中文',runtime_tw)]:
                i18n.set_language(language)
                self.assertEqual(str(i18n.tr(message)),translations[message])
        finally:i18n.set_language(original)

    def test_family_mismatch_messages_switch_without_missing_translations(self):
        messages=['存在色系偏离','部分区域与目标色系不符。',
                  '本轮可执行方案均有区域偏离目标色系，以下按综合色差与落点稳定性排序。']
        original=i18n.language
        try:
            for language,translations in [('English',EN),('繁體中文',TW)]:
                i18n.set_language(language)
                for message in messages:
                    self.assertEqual(str(i18n.tr(message)),translations[message])
        finally:i18n.set_language(original)

    def test_main_screen_does_not_show_removed_explanatory_copy(self):
        from pathlib import Path
        source=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
        self.assertNotIn('即使只将一个或两个区域设为精准 HEX',source)
        self.assertNotIn('设置颜色与窗口 → 开始 / F8 → 手动进入染色倒计时',source)
        self.assertNotIn('先拼接本局色板，再搜索并定位；最终是否染色由你确认。',source)

    def test_tutorial_step_is_short_and_tips_cover_matching_behavior(self):
        section=dict(TUTORIAL)['4. 选择匹配模式']
        self.assertEqual(section,'为每个区域选择精准或相似模式。')
        self.assertEqual(len([heading for heading,_ in TUTORIAL if heading.startswith('Tips ')]),2)
        tips=dict(TUTORIAL)
        self.assertIn('设定的色差范围',tips['Tips 1 · 匹配方式'])
        self.assertIn('稳定、均衡',tips['Tips 1 · 匹配方式'])
        self.assertIn('整体质量相同时优先精准命中',tips['Tips 1 · 匹配方式'])
        self.assertIn('浮窗会显示进度',tips['Tips 2 · 等待与候选'])
        self.assertNotIn('ΔE≤8',section)
        self.assertEqual(EN[section],'Choose Exact or Similar for each region.')
        self.assertEqual(TW[section],'為每個區域選擇精準或相似模式。')
        self.assertIn('stable, balanced results',EN[tips['Tips 1 · 匹配方式']])

    def test_short_tutorial_copy_has_natural_english_and_traditional_versions(self):
        source=dict(TUTORIAL)['Tips 1 · 匹配方式']
        original=i18n.language
        try:
            i18n.set_language('English')
            self.assertEqual(str(i18n.tr(source)),EN[source])
            self.assertIn('stable, balanced results',EN[source])
            i18n.set_language('繁體中文')
            self.assertEqual(str(i18n.tr(source)),TW[source])
            self.assertIn('穩定、均衡的結果',TW[source])
        finally:i18n.set_language(original)

    def test_risk_notice_uses_courteous_language(self):
        source='适用于港澳台服瑪奇Mobile。游戏中使用本工具可能存在风险，建议谨慎使用。'
        original=i18n.language
        try:
            i18n.set_language('English')
            self.assertEqual(str(i18n.tr(source)), 'For the Hong Kong/Macau/Taiwan service of Mabinogi Mobile. Please note that using this tool in-game may carry some risk.')
        finally:i18n.set_language(original)

    def test_language_switch_updates_existing_labels_and_dialog_titles(self):
        fake=SimpleNamespace(
            CTkLabel=fake_class('CTkLabel'),CTkButton=fake_class('CTkButton'),
            CTkCheckBox=fake_class('CTkCheckBox'),CTkSwitch=fake_class('CTkSwitch'),
            CTk=fake_class('CTk'),CTkToplevel=fake_class('CTkToplevel'))
        i18n.install_widgets(fake)
        original=i18n.language
        try:
            label=fake.CTkLabel(text='使用教程')
            dialog=fake.CTkToplevel();dialog.title('支持作者')
            waiting=fake.CTkLabel(text='等待用户手动进入倒计时染色界面')
            i18n.set_language('English')
            self.assertEqual(str(label.text),'How to use Color Studio')
            self.assertEqual(str(dialog.window_title),'Support the creator')
            self.assertEqual(str(waiting.text),'Waiting for the timed dye screen to be opened.')
            i18n.set_language('繁體中文')
            self.assertEqual(str(label.text),'使用教學')
            self.assertEqual(str(waiting.text),'等待您手動進入限時染色畫面。')
            i18n.set_language('简体中文')
            self.assertEqual(str(waiting.text),'等待用户手动进入倒计时染色界面')
        finally:i18n.set_language(original)

    def test_selected_similar_tolerance_is_translated_without_fixed_ceiling(self):
        original=i18n.language
        try:
            i18n.set_language('English')
            hint=i18n.tr('目标色差 ΔE ≤ 12 · 数值越小越接近目标')
            self.assertEqual(str(hint),'Target color difference ΔE ≤ 12 · Lower values are closer to the target')
        finally:i18n.set_language(original)

    def test_dynamic_runtime_statuses_are_translated_and_refresh_in_place(self):
        fake=SimpleNamespace(
            CTkLabel=fake_class('CTkLabel'),CTkButton=fake_class('CTkButton'),
            CTkCheckBox=fake_class('CTkCheckBox'),CTkSwitch=fake_class('CTkSwitch'),
            CTk=fake_class('CTk'),CTkToplevel=fake_class('CTkToplevel'))
        i18n.install_widgets(fake)
        original=i18n.language
        try:
            status=fake.CTkLabel(text='正在寻色 · 游戏剩余 56 秒')
            i18n.set_language('English')
            self.assertEqual(str(status.text),'Searching · game time left: 56 s')
            status.configure(text='当前颜色  #AABBCC')
            self.assertEqual(str(status.text),'Current color  #AABBCC')
            i18n.set_language('繁體中文')
            self.assertEqual(str(status.text),'當前顏色  #AABBCC')
        finally:i18n.set_language(original)

    def test_critical_capture_and_quality_failures_are_localized(self):
        from atlas_service import quality_failure_message
        timer='倒计时无法可靠识别，未开始缩放或扫描；本次入口已消耗染色剂，请检查 OCR 后再运行。'
        gate=quality_failure_message({'thresholds':{'max_rgb_rmse':8},'regions':[
            {'region':1,'passed':False,'heldout_rgb_rmse':12.4}]})
        original=i18n.language
        try:
            i18n.set_language('English')
            self.assertEqual(str(i18n.tr(timer)), 'The countdown could not be read reliably. No zoom or scan was started, but this dye was consumed. Check OCR before trying again.')
            self.assertEqual(str(i18n.tr(gate)), 'Atlas reconstruction validation failed: Region 1 held-out RGB RMSE 12.40 (limit 8.00). The target colors have not been searched, so this does not mean that no matching combination exists.')
            i18n.set_language('繁體中文')
            self.assertEqual(str(i18n.tr(timer)), '倒數計時無法可靠辨識，未開始縮放或掃描；本次染劑已消耗，請先檢查 OCR 再重新執行。')
            self.assertNotIn('倒计时',str(i18n.tr(timer)))
            self.assertNotIn('大图',str(i18n.tr(gate)))
        finally:i18n.set_language(original)

    def test_progress_event_can_report_a_specific_retry_status(self):
        from ui_progress import progress_text
        original=i18n.language
        try:
            title,body=progress_text({'stage':'zoom','message':'正在复核倒计时识别'})
            i18n.set_language('English')
            self.assertEqual(str(i18n.tr(title)),'Detecting and zooming')
            self.assertEqual(str(i18n.tr(body)),'Rechecking the countdown reading')
        finally:i18n.set_language(original)

    def test_single_region_compromise_is_explicit_and_translated(self):
        from ui_progress import single_result_presentation
        result=dict(verified=True,accepted=False,best_verified=True,best_current=True,
                    outcome='compromise')
        title,body=single_result_presentation(result)
        self.assertIn('妥协方案',title)
        self.assertIn('正常结束状态',body)
        original=i18n.language
        try:
            for language in ('English','繁體中文'):
                i18n.set_language(language)
                translated_title=str(i18n.tr(title));translated_body=str(i18n.tr(body))
                self.assertNotIn('妥协方案',translated_title if language=='English' else '')
                self.assertNotIn('正常结束状态',translated_body if language=='English' else '')
                if language=='English':
                    self.assertIn('Compromise',translated_title)
                    self.assertIn('normal outcome',translated_body)
                else:
                    self.assertIn('折衷',translated_title)
                    self.assertIn('正常結束狀態',translated_body)
        finally:i18n.set_language(original)

    def test_single_region_unrestored_best_is_separate_from_normal_compromise(self):
        from ui_progress import single_result_presentation
        title,body=single_result_presentation(dict(verified=True,accepted=False,
            best_verified=True,best_current=True,historical_best_unrestored=True,
            outcome='compromise'))
        self.assertIn('妥协方案',title)
        self.assertIn('未能恢复',body)

    def test_single_region_unverified_is_not_labeled_as_compromise(self):
        from ui_progress import single_result_presentation
        title,body=single_result_presentation(dict(verified=False,accepted=False,
            outcome='unverified'))
        self.assertNotIn('妥协',title)
        self.assertIn('未完成复核',body)


if __name__=='__main__':unittest.main()
