import json
import tempfile
import unittest
from pathlib import Path

from updater.manifest import verify_ed25519
from scripts.build_update_assets import build_assets


class UpdateAssetTests(unittest.TestCase):
    seed=bytes.fromhex('9d61b19deffd5a60ba844af492ec2cc4' '4449c5697b326919703bac031cae7f60')
    public=bytes.fromhex('d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a')

    def test_packaged_korean_launchers_and_guide_are_owned_but_other_scripts_are_not(self):
        from updater.manifest import ManifestError,validate_relative_path
        from scripts.verify_update_assets import verify_assets
        from _updater_test_support import KEYS
        paths=('Korean-preflight.cmd','Korean-validation.cmd','docs/korean-validation.md',
            'docs/server-selection.md','SCREENSHOT_PREVIEW.md')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'exe')
            for name in paths:
                target=root/name;target.parent.mkdir(exist_ok=True);target.write_bytes(b'official validation entry')
            out=Path(temp)/'assets';build_assets(root,out,'0.4.2','stable',self.seed)
            self.assertEqual(verify_assets(out,root,trusted_keys=KEYS)['files'],6)
            for name in ('User-launcher.cmd','docs/personal.md','data/custom.cmd'):
                with self.subTest(name=name),self.assertRaises(ManifestError):validate_relative_path(name)

    def test_missing_package_cannot_generate_empty_signed_release(self):
        with tempfile.TemporaryDirectory() as temp,self.assertRaises(ValueError):
            build_assets(Path(temp)/'missing',Path(temp)/'out','0.4.3','stable',self.seed)

    def test_offline_asset_names_are_clearly_update_only(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'exe')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',self.seed)
            out=Path(temp)/'new'
            report=build_assets(root,out,'0.4.3','stable',self.seed,
                previous_manifest=old/'update-manifest.json')
            self.assertEqual(report['offline_name'],'UPDATE-ONLY-ColorStudio-0.4.3-win-x64.zip')
            self.assertEqual(report['delta_name'],'UPDATE-ONLY-ColorStudio-from-0.4.2-to-0.4.3-win-x64.zip')

    def test_delta_rename_with_identical_contents_includes_required_target_blob(self):
        from updater.offline import import_offline
        from _updater_test_support import KEYS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'_internal').mkdir();(root/'ColorStudio.exe').write_bytes(b'exe')
            (root/'_internal/old.dll').write_bytes(b'same');old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',self.seed)
            old_raw=(old/'update-manifest.json').read_bytes();(root/'_internal/old.dll').rename(root/'_internal/new.dll')
            out=Path(temp)/'new';report=build_assets(root,out,'0.4.3','stable',self.seed,previous_manifest=old/'update-manifest.json')
            (root/'_internal/new.dll').rename(root/'_internal/old.dll')
            manifest=import_offline(out/report['delta_name'],Path(temp)/'cache',trusted_keys=KEYS,root=root,old_raw=old_raw)
            self.assertIn('_internal/new.dll',[row.path for row in manifest.files])

    def test_many_small_resources_are_bundled_and_each_file_is_still_verified(self):
        from scripts.verify_update_assets import verify_assets
        from _updater_test_support import KEYS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';resources=root/'_internal/resources';resources.mkdir(parents=True)
            (root/'ColorStudio.exe').write_bytes(b'exe')
            for index in range(200):(resources/f'{index}.txt').write_bytes(f'resource-{index}'.encode())
            out=Path(temp)/'out';report=build_assets(root,out,'0.4.3','stable',self.seed)
            self.assertLess(len(report['blobs']),10)
            self.assertEqual(verify_assets(out,root,trusted_keys=KEYS)['files'],201)

    def test_manifest_matches_application_and_offline_zip_is_self_contained(self):
        with tempfile.TemporaryDirectory() as temp:
            package=Path(temp)/'ColorStudio';out=Path(temp)/'assets';package.mkdir();(package/'_internal').mkdir()
            (package/'ColorStudio.exe').write_bytes(b'new exe')
            (package/'_internal'/'a.dll').write_bytes(b'dll')
            (package/'data').mkdir();(package/'data'/'history.json').write_text('private')
            result=build_assets(package,out,'0.4.2','stable',self.seed)
            raw=(out/'update-manifest.json').read_bytes();sig=(out/'update-manifest.sig').read_bytes()
            self.assertTrue(verify_ed25519(raw,sig,self.public))
            manifest=json.loads(raw)
            self.assertEqual({row['path'] for row in manifest['files']},{'ColorStudio.exe','_internal/a.dll'})
            self.assertFalse(any('data/' in row['path'] for row in manifest['files']))
            self.assertTrue((out/result['offline_name']).exists())

    def test_changed_blob_report_excludes_unchanged_previous_file(self):
        with tempfile.TemporaryDirectory() as temp:
            package=Path(temp)/'ColorStudio';out=Path(temp)/'assets';package.mkdir();(package/'_internal').mkdir()
            (package/'ColorStudio.exe').write_bytes(b'exe')
            (package/'_internal/same.dll').write_bytes(b'same');(package/'_internal/new.dll').write_bytes(b'new')
            result=build_assets(package,out,'0.4.2','stable',self.seed)
            self.assertEqual(result['file_count'],3)
            self.assertGreater(result['download_bytes'],0)

    def test_delta_offline_import_reuses_local_files_and_rejects_wrong_base(self):
        from updater.offline import import_offline,OfflinePackageError
        from updater.manifest import verify_manifest
        from _updater_test_support import KEYS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'安装 目录';root.mkdir();(root/'_internal').mkdir()
            (root/'ColorStudio.exe').write_bytes(b'old');(root/'_internal/a.dll').write_bytes(b'same')
            old=Path(temp)/'old';build_assets(root,old,'0.4.2','stable',self.seed)
            old_raw=(old/'update-manifest.json').read_bytes()
            (root/'ColorStudio.exe').write_bytes(b'new')
            out=Path(temp)/'new';report=build_assets(root,out,'0.4.3','stable',self.seed,
                previous_manifest=old/'update-manifest.json')
            (root/'ColorStudio.exe').write_bytes(b'old')
            manifest=import_offline(out/report['delta_name'],Path(temp)/'cache',trusted_keys=KEYS,
                root=root,old_raw=old_raw)
            self.assertEqual(manifest.version,'0.4.3')
            self.assertEqual((Path(temp)/'cache/update-manifest.json').read_bytes(),(out/'update-manifest.json').read_bytes(),
                'Online/full/delta updates must install the same ownership baseline for the next update')
            (root/'_internal/a.dll').write_bytes(b'modified')
            with self.assertRaises(OfflinePackageError):
                import_offline(out/report['delta_name'],Path(temp)/'wrong',trusted_keys=KEYS,root=root,old_raw=b'wrong')

    def test_asset_verifier_rejects_bad_signature_and_extra_application_file(self):
        from scripts.verify_update_assets import verify_assets
        from _updater_test_support import KEYS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'exe')
            out=Path(temp)/'out';build_assets(root,out,'0.4.3','stable',self.seed)
            verify_assets(out,root,trusted_keys=KEYS)
            (out/'update-manifest.sig').write_bytes(b'x'*64)
            with self.assertRaises(ValueError):verify_assets(out,root,trusted_keys=KEYS)

    def test_asset_verifier_checks_update_only_archive_and_requires_full_package(self):
        import zipfile
        from scripts.verify_update_assets import verify_assets
        from _updater_test_support import KEYS
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'app';root.mkdir();(root/'ColorStudio.exe').write_bytes(b'exe')
            out=Path(temp)/'assets';report=build_assets(root,out,'0.4.3','stable',self.seed)
            archive=out/report['offline_name']
            with zipfile.ZipFile(archive,'w') as broken:
                for name in ('update-manifest.json','update-manifest.sig'):
                    broken.write(out/name,name)
            with self.assertRaisesRegex(ValueError,'incomplete'):
                verify_assets(out,root,trusted_keys=KEYS)
            archive.unlink()
            with self.assertRaisesRegex(ValueError,'offline'):
                verify_assets(out,root,trusted_keys=KEYS)


if __name__=='__main__':unittest.main()
