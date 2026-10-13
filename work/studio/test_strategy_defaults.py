"""One-time screenshot defaults, existing player settings and update staging."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from profile_store import default_profile,read_profile,write_profile,PresetStore

class StrategyDefaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def legacy_data(self):
        profile=default_profile();profile['search_strategy']='native'
        profile['regions'][0]['target']='#12';profile['regions'][1]['mode']='相似颜色'
        profile['regions'][1]['tolerance']=13.;profile['priority_order']=[2,0,1]
        settings=dict(search_strategy='native',language='한국어',server='kr',unknown_option=42)
        preset=copy.deepcopy(profile);preset['regions'][0]['target']='#000000'
        presets=dict(schema=1,presets=[dict(id='white',name='白色',profile=preset)])
        for name,value in (('settings.json',settings),('profile.json',profile),('presets.json',presets)):
            (self.root/name).write_text(json.dumps(value),encoding='utf8')
        return settings,profile,presets

    def test_new_and_legacy_profiles_default_to_screenshot(self):
        self.assertEqual(default_profile()['search_strategy'],'atlas')
        self.assertEqual(read_profile(self.root/'missing.json')['search_strategy'],'atlas')
        (self.root/'profile.json').write_text(json.dumps(default_profile()['regions']),encoding='utf8')
        self.assertEqual(read_profile(self.root/'profile.json')['search_strategy'],'atlas')

    def test_existing_draft_settings_and_presets_switch_without_losing_options(self):
        from strategy_defaults import migrate_strategy_defaults
        settings,profile,presets=self.legacy_data()
        result=migrate_strategy_defaults(self.root)
        self.assertEqual(result['settings']['search_strategy'],'atlas')
        self.assertEqual(result['errors'],[])
        for name,expected in (('settings.json',settings),('profile.json',profile),('presets.json',presets)):
            actual=json.loads((self.root/name).read_text(encoding='utf8'))
            actual.pop('screenshot_default_revision',None)
            if name=='presets.json':actual['presets'][0]['profile']['search_strategy']='native'
            else:actual['search_strategy']='native'
            self.assertEqual(actual,expected)

    def test_native_choice_after_upgrade_survives_autosave_and_preset_edits(self):
        from strategy_defaults import migrate_strategy_defaults
        self.legacy_data();migrate_strategy_defaults(self.root)
        profile=read_profile(self.root/'profile.json');profile['search_strategy']='native'
        profile['regions'][0]['target']='#000000';write_profile(self.root/'profile.json',profile)
        store=PresetStore(self.root/'presets.json');store.save('主动选择精准',profile)
        settings=json.loads((self.root/'settings.json').read_text(encoding='utf8'))
        settings['search_strategy']='native';(self.root/'settings.json').write_text(json.dumps(settings),encoding='utf8')
        migrate_strategy_defaults(self.root)
        self.assertEqual(read_profile(self.root/'profile.json')['search_strategy'],'native')
        self.assertEqual(store.rows()[-1]['profile']['search_strategy'],'native')
        self.assertEqual(json.loads((self.root/'settings.json').read_text())['search_strategy'],'native')

    def test_update_health_staging_changes_no_user_files(self):
        from strategy_defaults import migrate_strategy_defaults
        self.legacy_data();before={p.name:p.read_bytes() for p in self.root.iterdir()}
        preview=migrate_strategy_defaults(self.root,persist=False)
        self.assertEqual(preview['settings']['search_strategy'],'atlas')
        self.assertEqual(preview['profile']['search_strategy'],'atlas')
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)
        migrate_strategy_defaults(self.root)
        self.assertEqual(read_profile(self.root/'profile.json')['search_strategy'],'atlas')

    def test_broken_profile_is_preserved_and_does_not_reset_other_files_again(self):
        from strategy_defaults import migrate_strategy_defaults
        self.legacy_data();(self.root/'profile.json').write_bytes(b'{broken')
        result=migrate_strategy_defaults(self.root)
        self.assertTrue(result['errors']);self.assertEqual((self.root/'profile.json').read_bytes(),b'{broken')
        self.assertEqual(result['settings']['search_strategy'],'atlas')
        settings=result['settings'];settings['search_strategy']='native'
        (self.root/'settings.json').write_text(json.dumps(settings),encoding='utf8')
        self.assertEqual(migrate_strategy_defaults(self.root)['settings']['search_strategy'],'native')

    def test_unwritable_migration_still_selects_screenshot_in_memory(self):
        from strategy_defaults import migrate_strategy_defaults
        self.legacy_data();before={p.name:p.read_bytes() for p in self.root.iterdir()}
        with patch('strategy_defaults._write',side_effect=OSError('denied')):
            result=migrate_strategy_defaults(self.root)
        self.assertEqual(result['settings']['search_strategy'],'atlas')
        self.assertEqual(result['profile']['search_strategy'],'atlas')
        self.assertTrue(result['errors'])
        self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)

    def test_explicit_native_choice_after_failed_migration_is_not_overwritten(self):
        from strategy_defaults import migrate_strategy_defaults
        from ui_settings import save_settings,read_settings
        self.legacy_data();(self.root/'settings.json').write_text('{broken',encoding='utf8')
        migrate_strategy_defaults(self.root)
        save_settings(self.root/'settings.json',search_strategy='native')
        migrate_strategy_defaults(self.root)
        self.assertEqual(read_settings(self.root/'settings.json')['search_strategy'],'native')

if __name__=='__main__':unittest.main()
