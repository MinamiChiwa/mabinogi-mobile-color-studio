"""Real Windows Tk profile and preset integration; no game input."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import app
from profile_store import PresetStore, read_profile
import test_native_ui_hit_testing as hit_testing


@unittest.skipUnless(sys.platform=='win32','Native Tk profile UI requires Windows')
class ProfileUITests(unittest.TestCase):
    def setUp(self):
        self.helper=hit_testing.NativeUIHitTestingTests()
        self.addCleanup(self.helper.doCleanups)
        self.helper.setUp()
        self.ui=self.helper.ui
        self.root=Path(self.helper.folder.name)

    def test_current_settings_autosave_including_incomplete_input(self):
        card=self.ui.cards[0]
        card.target.set('#12')
        card.alt.set('#FFFFFF, #AABBCC')
        card.enabled.set(False)
        card.mode.set('相似颜色');card.change_mode()
        card.tolerance.set(12.)
        self.ui.set_card_priority(0,3)
        self.ui.change_search_strategy(str(app.tr('图像寻色')))
        self.helper.pump(.4)

        saved=read_profile(self.root/'profile.json')
        self.assertEqual(saved['regions'][0],dict(enabled=False,target='#12',
            alt='#FFFFFF, #AABBCC',mode='相似颜色',tolerance=12.))
        self.assertEqual(saved['search_strategy'],'atlas')
        self.assertEqual(saved['priority_order'],[2,1,0])
        self.assertEqual([row.priority_menu.get() for row in self.ui.cards],['3','2','1'])
        self.assertEqual(self.helper.errors,[])

    def test_priority_selection_swaps_other_region_and_autosaves(self):
        self.ui.set_card_priority(0,3)
        self.helper.pump(.4)

        self.assertEqual([card.priority.get() for card in self.ui.cards],[3,2,1])
        self.assertEqual([card.priority_menu.get() for card in self.ui.cards],['3','2','1'])
        self.assertEqual(read_profile(self.root/'profile.json')['priority_order'],[2,1,0])
        self.assertEqual(self.helper.errors,[])

    def test_close_flushes_pending_draft_without_waiting_for_debounce(self):
        self.ui.cards[1].target.set('#ABCDEF')
        with patch.object(self.ui,'destroy') as destroy:
            self.ui.close()
        destroy.assert_called_once()
        self.assertEqual(read_profile(self.root/'profile.json')['regions'][1]['target'],'#ABCDEF')
        self.assertIsNone(self.ui._autosave_job)

    def test_custom_presets_are_independent_and_can_be_loaded_repeatedly(self):
        self.ui.save();self.helper.pump(.15)
        dialog=self.ui._dialogs['presets']
        self.addCleanup(lambda:dialog.destroy() if dialog.winfo_exists() else None)
        current=self.ui.current_profile()
        dialog.name.set('自定义双黑')
        dialog.rows[0]['target'].set('#000000')
        dialog.rows[1]['target'].set('#000000')
        dialog.rows[2]['enabled'].set(False)
        dialog.rows[0]['priority'].set('3');dialog.swap_priority(0,'3')
        dialog.save_profile()

        first_id=dialog.selected_id
        self.assertIsNotNone(first_id)
        self.assertEqual(self.ui.current_profile(),current,
                         'Editing a saved preset unexpectedly changed current settings')
        dialog.use_current();dialog.name.set('自定义白色')
        dialog.rows[0]['target'].set('#FFFFFF');dialog.save_profile()
        store=PresetStore(self.root/'presets.json')
        self.assertEqual(len(store.rows()),2)
        self.assertEqual(store.get(first_id)['profile']['priority_order'],[2,1,0])
        dialog.choose('自定义双黑')
        for _ in range(2):dialog.load_selected()
        self.helper.pump(.4)
        saved=read_profile(self.root/'profile.json')
        self.assertEqual(saved['regions'][0]['target'],'#000000')
        self.assertEqual(saved['regions'][1]['target'],'#000000')
        self.assertFalse(saved['regions'][2]['enabled'])
        self.assertEqual(saved['priority_order'],[2,1,0])
        self.assertEqual(self.helper.errors,[])

    def test_busy_load_is_rejected_without_changing_current_settings(self):
        current=self.ui.current_profile()
        changed=self.ui.current_profile();changed['regions'][0]['target']='#ABCDEF'
        self.ui.busy=True
        try:
            with self.assertRaisesRegex(ValueError,'停止'):self.ui.apply_profile(changed)
        finally:self.ui.busy=False
        self.assertEqual(self.ui.current_profile(),current)

    def test_autosave_write_error_is_visible_and_can_be_retried(self):
        self.ui.cards[0].target.set('#ABCDEF')
        with patch.object(app,'write_profile',side_effect=OSError('read-only fixture')):
            self.ui.flush_autosave()
        self.assertTrue(self.ui.detail.cget('text'))
        self.ui.flush_autosave()
        self.assertEqual(read_profile(self.root/'profile.json')['regions'][0]['target'],'#ABCDEF')

    def test_language_switch_updates_existing_preset_placeholder(self):
        self.ui.save();self.helper.pump(.08)
        dialog=self.ui._dialogs['presets']
        self.addCleanup(lambda:dialog.destroy() if dialog.winfo_exists() else None)
        before=app.i18n.language
        try:
            for language in ('English','繁體中文'):
                app.i18n.set_language(language);self.helper.pump(.05)
                self.assertEqual(dialog.name_entry.cget('placeholder_text'),
                                 str(app.tr('方案名称')))
        finally:app.i18n.set_language(before)
        self.assertEqual(self.helper.errors,[])


if __name__=='__main__':unittest.main()
