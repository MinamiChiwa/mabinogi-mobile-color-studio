import copy
import json
import tempfile
import unittest
from pathlib import Path

from profile_store import default_profile, read_profile, write_profile, PresetStore


class ProfileStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_draft_retains_incomplete_input_and_priorities_after_restart(self):
        profile = default_profile()
        profile['regions'][0]['target'] = '#12'
        profile['priority_order'] = [2, 0, 1]
        write_profile(self.root / 'profile.json', profile)
        self.assertEqual(read_profile(self.root / 'profile.json'), profile)

    def test_legacy_single_profile_migrates_without_losing_colors(self):
        old = default_profile()['regions']
        old[1]['target'] = '#ABCDEF'
        (self.root / 'profile.json').write_text(json.dumps(old), encoding='utf-8')
        new = read_profile(self.root / 'profile.json')
        self.assertEqual(new['regions'], old)
        self.assertEqual(new['priority_order'], [0, 1, 2])

    def test_named_presets_are_independent_editable_and_removable(self):
        store = PresetStore(self.root / 'presets.json')
        first = default_profile()
        second = copy.deepcopy(first)
        second['regions'][0]['target'] = '#FFFFFF'
        a = store.save('黑色', first)
        b = store.save('白色', second)
        first['regions'][0]['target'] = '#FF0000'
        restarted = PresetStore(store.path)
        self.assertEqual(len(restarted.rows()), 2)
        self.assertEqual(restarted.get(a)['profile']['regions'][0]['target'], '#202020')
        restarted.save('白色改名', second, preset_id=b)
        self.assertEqual(restarted.get(b)['name'], '白色改名')
        restarted.delete(a)
        self.assertEqual([row['id'] for row in restarted.rows()], [b])

    def test_invalid_or_duplicate_preset_does_not_overwrite_existing(self):
        store = PresetStore(self.root / 'presets.json')
        saved = store.save('方案', default_profile())
        with self.assertRaises(ValueError):
            store.save('方案', default_profile())
        invalid = default_profile()
        invalid['regions'][0]['target'] = '#12'
        with self.assertRaises(ValueError):
            store.save('无效', invalid)
        self.assertEqual(len(store.rows()), 1)
        self.assertEqual(store.get(saved)['name'], '方案')

    def test_corrupt_preset_library_is_not_silently_replaced(self):
        path = self.root / 'presets.json'
        path.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            PresetStore(path).save('新方案', default_profile())
        self.assertEqual(path.read_text(encoding='utf-8'), '{broken')

    def test_corrupt_draft_is_reported_and_kept(self):
        path=self.root/'profile.json';path.write_text('{broken',encoding='utf-8')
        with self.assertRaises(ValueError):read_profile(path)
        self.assertEqual(path.read_text(encoding='utf-8'),'{broken')
        write_profile(path,default_profile())
        backups=list(self.root.glob('profile.json.unreadable-*'))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'),'{broken')

    def test_legacy_profile_keeps_separately_saved_search_strategy(self):
        path=self.root/'profile.json'
        path.write_text(json.dumps(default_profile()['regions']),encoding='utf-8')
        self.assertEqual(read_profile(path,search_strategy='atlas')['search_strategy'],'atlas')

    def test_read_only_data_migration_preserves_presets(self):
        from app_data import _copy_user_data
        src, dst = self.root / 'old', self.root / 'new'
        src.mkdir(); dst.mkdir()
        (src / 'presets.json').write_text('{"schema": 1, "presets": []}', encoding='utf-8')
        _copy_user_data(src, dst)
        self.assertTrue((dst / 'presets.json').exists())


if __name__ == '__main__':
    unittest.main()
