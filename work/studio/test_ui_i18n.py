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
        self.assertIn('精准区域优先于相似区域',tips['Tips 1 · 匹配方式'])
        self.assertIn('浮窗会显示进度',tips['Tips 2 · 等待与候选'])
        self.assertNotIn('ΔE≤8',section)
        self.assertEqual(EN[section],'Choose Exact or Similar for each region.')
        self.assertEqual(TW[section],'為每個區域選擇精準或相似模式。')
        self.assertIn('Exact regions take priority',EN[tips['Tips 1 · 匹配方式']])

    def test_short_tutorial_copy_has_natural_english_and_traditional_versions(self):
        source='每个区域都可单独选择精准或相似。精准区优先于相似区：先比较精准命中数，再比较精准区色差，最后比较相似区色差。'
        original=i18n.language
        try:
            i18n.set_language('English')
            self.assertEqual(str(i18n.tr(source)),EN[source])
            self.assertIn('Exact regions take priority',EN[source])
            i18n.set_language('繁體中文')
            self.assertEqual(str(i18n.tr(source)),TW[source])
            self.assertIn('精準區優先於相似區',TW[source])
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
            i18n.set_language('English')
            self.assertEqual(str(label.text),'How to use Color Studio')
            self.assertEqual(str(dialog.window_title),'Support the creator')
            i18n.set_language('繁體中文')
            self.assertEqual(str(label.text),'使用教學')
        finally:i18n.set_language(original)

    def test_selected_similar_tolerance_is_translated_without_fixed_ceiling(self):
        original=i18n.language
        try:
            i18n.set_language('English')
            hint=i18n.tr('目标色差 ΔE ≤ 12 · 数值越小越接近目标')
            self.assertEqual(str(hint),'Target color difference ΔE ≤ 12 · Lower values are closer to the target')
        finally:i18n.set_language(original)


if __name__=='__main__':unittest.main()
