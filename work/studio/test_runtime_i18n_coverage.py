import ast
import re
from pathlib import Path
import unittest

import i18n

_CJK = re.compile(r'[\u4e00-\u9fff]')
_RUNTIME_MODULES = (
    'engine.py',
    'atlas_service.py',
    'atlas_runner.py',
    'ui_progress.py',
    'search_overlay.py',
    'atlas_execution.py',
    'live_atlas_capture.py',
    'vision.py',
    'atlas_live_adapter.py',
    'platform_win.py',
)


class RuntimeLanguageCoverageTests(unittest.TestCase):
    def test_internal_runtime_errors_have_complete_display_translations(self):
        from runtime_messages import ERROR_SOURCE
        original = i18n.language
        try:
            for language in ('简体中文', '繁體中文', 'English'):
                i18n.set_language(language)
                for technical, source in ERROR_SOURCE.items():
                    with self.subTest(language=language, message=technical):
                        translated = str(i18n.tr(technical))
                        self.assertNotEqual(translated, technical)
                        self.assertEqual(translated, str(i18n.tr(source)))
                        if language == 'English':
                            self.assertFalse(_CJK.search(translated), translated)
                        else:
                            self.assertTrue(_CJK.search(translated), translated)
        finally:
            i18n.set_language(original)

    def test_registration_reasons_translate_as_complete_clauses(self):
        from atlas_execution import _measured_motion, CandidateExpired
        from types import SimpleNamespace
        original = i18n.language
        try:
            for reason in ('insufficient_features', 'insufficient_matches',
                           'invalid_transform', 'insufficient_inliers',
                           'insufficient_material_overlap', 'insufficient_region_overlap',
                           'material_rgb_mismatch', 'unknown'):
                adapter = SimpleNamespace(motion=lambda *_: None,
                    last_motion_diagnostics={'reason': reason})
                with self.assertRaises(CandidateExpired) as caught:
                    _measured_motion(adapter, None, None, lambda *_: None, 'reference')
                for language in ('简体中文', '繁體中文', 'English'):
                    i18n.set_language(language)
                    message = str(i18n.tr(str(caught.exception)))
                    if language == 'English':
                        self.assertFalse(_CJK.search(message), message)
                        self.assertIn('Automatic movement stopped.', message)
                    else:
                        self.assertNotIn('Region', message)
        finally:
            i18n.set_language(original)

    def test_english_covers_runtime_status_literals(self):
        root = Path(__file__).parent
        missing = []
        original = i18n.language
        try:
            i18n.set_language('English')
            for name in _RUNTIME_MODULES:
                tree = ast.parse((root / name).read_text(encoding='utf-8'))
                for node in ast.walk(tree):
                    value = node.value if isinstance(node, ast.Constant) else None
                    if not isinstance(value, str) or not _CJK.search(value):
                        continue
                    translated = str(i18n.tr(value))
                    if _CJK.search(translated):
                        missing.append(f'{name}: {value}')
        finally:
            i18n.set_language(original)
        self.assertEqual(missing, [], 'English runtime strings are not fully translated: ' + repr(missing))

    def test_formal_atlas_fallback_messages_are_localized(self):
        messages = (
            '游戏倒计时已截止，未发布候选。',
            '剩余时间不足以安全定位并复核自动最佳方案，未发送定位操作。',
            '候选已失效，保持自动最佳方案。',
            '已停止，保留自动最佳方案。',
        )
        original = i18n.language
        try:
            i18n.set_language('English')
            for message in messages:
                self.assertFalse(_CJK.search(str(i18n.tr(message))), message)
            i18n.set_language('繁體中文')
            for message in messages:
                translated = str(i18n.tr(message))
                self.assertNotIn('倒计时', translated)
                self.assertNotIn('候选', translated)
        finally:
            i18n.set_language(original)


if __name__ == '__main__':
    unittest.main()
