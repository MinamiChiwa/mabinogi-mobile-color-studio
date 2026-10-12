import unittest
from updater.ui_update import update_copy

class UpdateUITests(unittest.TestCase):
    def test_copy_has_three_languages_and_true_size(self):
        for language in ('简体中文','繁體中文','English','日本語','한국어'):
            copy=update_copy(language,'0.4.2',123456)
            self.assertIn('0.4.2',copy['title']);self.assertIn('KiB',copy['detail'])

    def test_japanese_and_korean_update_states_have_no_chinese_fallback(self):
        from updater.ui_update import TEXTS,text
        from locale_ja import UPDATER_JA
        from locale_ko import UPDATER_KO
        for language,words in (('日本語',UPDATER_JA),('한국어',UPDATER_KO)):
            self.assertEqual(set(words),set(TEXTS))
            for key in TEXTS:
                self.assertEqual(text(key,language),words[key])
                self.assertNotEqual(text(key,language),TEXTS[key][0])

if __name__=='__main__':unittest.main()
