import unittest
from updater.ui_update import update_copy

class UpdateUITests(unittest.TestCase):
    def test_copy_has_three_languages_and_true_size(self):
        for language in ('简体中文','繁體中文','English'):
            copy=update_copy(language,'0.4.2',123456)
            self.assertIn('0.4.2',copy['title']);self.assertIn('KiB',copy['detail'])

if __name__=='__main__':unittest.main()
