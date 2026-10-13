"""Five-language switching and old-updater-compatible distribution contracts."""
import re
import tempfile
import unittest
import sys
from pathlib import Path

import i18n


class ReleaseLocalizationTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language('简体中文')

    def test_japanese_and_korean_switch_complete_dynamic_text_without_changing_hex(self):
        for language,word in [('日本語','部位'),('한국어','영역')]:
            with self.subTest(language=language):
                self.assertIn(language,getattr(i18n,'LANGUAGES',()))
                i18n.set_language(language)
                text=str(i18n.tr('区域 2 · 当前颜色：#FFFFFF · F9'))
                self.assertIn(word,text)
                self.assertIn('#FFFFFF',text)
                self.assertIn('F9',text)
                self.assertNotIn('当前颜色',text)
                self.assertNotIn('区域',text)

    def test_new_locales_cover_runtime_messages_and_preserve_placeholders(self):
        from locale_ja import JA
        from locale_ko import KO
        for locale in (JA,KO):
            self.assertFalse(set(i18n.EN)-set(locale))
            for source in i18n.EN:
                self.assertTrue(locale[source].strip(),source)
                self.assertEqual(source.count('\n'),locale[source].count('\n'),source)
                self.assertEqual(re.findall(r'\{[^{}]*\}',source),
                                 re.findall(r'\{[^{}]*\}',locale[source]),source)
                self.assertNotIn('\\n',locale[source],source)

    def test_saved_unknown_language_falls_back_to_simplified_chinese(self):
        normalize=getattr(i18n,'normalize_language',None)
        self.assertTrue(callable(normalize))
        self.assertEqual(normalize('unknown'),'简体中文')
        self.assertEqual(normalize('日本語'),'日本語')
        self.assertEqual(normalize(None),'简体中文')

    def test_packaged_guides_use_old_updater_paths_and_remove_development_documents(self):
        from release_documents import package_documents
        from updater.manifest import validate_relative_path
        source=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temp:
            package=Path(temp)
            stale=['Korean-validation.cmd','Korean-preflight.cmd','native-window-check.ps1',
                   'WINDOW_CHECK.zh-CN.md','WINDOW_CHECK.zh-TW.md','WINDOW_CHECK.en.md',
                   'SCREENSHOT_PREVIEW.md','docs/korean-validation.md',
                   'docs/automatic-updates.md','work/studio/VERIFICATION.md',
                   '_internal/docs/README.ja.md','_internal/docs/README.ko.md',
                   'TESTING.md','RELEASE_NOTES.md']
            for name in stale:
                path=package/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('obsolete',encoding='utf-8')
            retained=['_internal/ocr/eng.traineddata','THIRD_PARTY/tesseract/LICENSE']
            for name in retained:
                path=package/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'required runtime or license')
            package_documents(source,package)
            self.assertTrue(all(not (package/name).exists() for name in stale))
            for name in ('docs','work','_internal/docs'):
                self.assertFalse((package/name).exists())
            for name in retained:
                self.assertEqual((package/name).read_bytes(),b'required runtime or license')
            self.assertEqual({p.name for p in package.glob('*.md')},
                             {'README.md','README.zh-TW.md','README.en.md'})
            for name in ('README.ja.md','README.ko.md'):
                self.assertFalse((package/name).exists())
                self.assertFalse((package/'_internal/docs'/name).exists())
                self.assertIn('/'+name,(package/'README.md').read_text(encoding='utf-8'))
            for path in package.rglob('*.md'):
                validate_relative_path(path.relative_to(package).as_posix())
                text=path.read_text(encoding='utf-8')
                self.assertNotRegex(text,r'(?m)^## (开发与测试|開發與測試|Development and tests)$')
                self.assertNotIn('python work/studio/',text)
                for link in re.findall(r'\]\(([^)]+)\)',text):
                    if '://' in link or link.startswith('#'):continue
                    self.assertTrue((path.parent/link.split('#')[0]).exists(),(path,link))

    def test_release_guard_rejects_development_documents_including_empty_directories(self):
        from release_documents import validate_package_documents
        for name in ('docs','WORK','_internal/Docs','TESTING.md','release_notes.md'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp:
                package=Path(temp);path=package/name
                if path.suffix:path.parent.mkdir(parents=True,exist_ok=True);path.write_text('stale')
                else:path.mkdir(parents=True)
                with self.assertRaisesRegex(ValueError,'Development documents'):
                    validate_package_documents(package)


@unittest.skipUnless(sys.platform=='win32','Real Tk layout requires Windows')
class ReleaseLocalizationDesktopTests(unittest.TestCase):
    def test_five_languages_resize_and_restore_without_changing_targets(self):
        import app
        from test_native_ui_hit_testing import NativeUIHitTestingTests
        helper=NativeUIHitTestingTests();self.addCleanup(helper.doCleanups);helper.setUp()
        original=i18n.language;self.addCleanup(i18n.set_language,original)
        ui=helper.ui
        targets=[card.target.get() for card in ui.cards]
        for language in i18n.LANGUAGES:
            ui.change_language(language);helper.pump(.03)
            self.assertEqual(i18n.language,language)
            for width in (560,1120):
                ui.geometry(f'{width}x850+20+20');helper.pump(.12)
                for widget in (ui.start,ui.stop_button,ui.server_menu,ui.window_button):
                    helper.hit(widget)
                self.assertEqual([card.target.get() for card in ui.cards],targets)
                self.assertEqual(ui.server_menu.cget('values'),[str(i18n.tr(name)) for _,name in app.SERVER_OPTIONS])
        self.assertEqual(helper.errors,[])
        from ui_settings import read_settings
        self.assertEqual(read_settings(Path(helper.folder.name)/'settings.json')['language'],'한국어')


if __name__=='__main__':unittest.main()
