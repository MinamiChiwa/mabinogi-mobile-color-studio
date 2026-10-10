"""Check exact bundled production bytecode, assets and a clean portable package."""
import argparse
import hashlib
import json
import marshal
from pathlib import Path
import sys
import types
from PyInstaller.archive.readers import CArchiveReader


def normalized(code):
    return code.replace(co_filename='',co_consts=tuple(normalized(v) if isinstance(v,types.CodeType) else v
                                                     for v in code.co_consts))


def verify(release,source):
    sys.path.insert(0,str(source))
    from build_info import source_identity
    identity=source_identity(source)
    manifest=json.loads((release/'_internal/build-info.json').read_text(encoding='utf-8'))
    assert all(manifest.get(k)==v for k,v in identity.items()),(manifest,identity)
    assert manifest.get('git_commit'), 'Git commit missing from build manifest'
    archive=CArchiveReader(str(release/'ColorStudio.exe'));pyz=archive.open_embedded_archive('PYZ.pyz')
    required={'app','build_info','profile_store','ui_presets','ui_dialogs','ui_strings','region_priority',
              'candidate_ranking','resize_surface','native_status','native_input_compile',
              'native_live.controller','native_live.same_session_dye_planner','native_live.compromise',
              'native_live.project_probe_io','native_live.project_closed_loop_io','native_live.service',
              'native_live.read_dye_window_mapping','native_live.runtime_read','overlay_native','search_overlay'}
    comparisons={}
    for path in [*source.glob('*.py'),*(source/'native_live').rglob('*.py')]:
        if path.name.startswith('test_'):continue
        name=path.relative_to(source).with_suffix('').as_posix().replace('/','.')
        if name.endswith('.__init__'):name=name[:-9]
        if name!='app' and name not in pyz.toc:continue
        code=marshal.loads(archive.extract('app')) if name=='app' else pyz.extract(name)
        comparisons[name]=normalized(code)==normalized(compile(path.read_text(encoding='utf-8'),str(path),'exec'))
    assert required.issubset(comparisons),required-set(comparisons)
    assert all(comparisons.values()),[name for name,ok in comparisons.items() if not ok]
    assets={p.name:(release/'_internal/native_live/assets'/p.name).read_bytes()==p.read_bytes()
            for p in (source/'native_live/assets').glob('*') if p.is_file()}
    assert all(assets.values()),assets
    prohibited={'profile.json','settings.json','presets.json','history.json','native-result.json','native-baseline.json'}
    private=[p.relative_to(release).as_posix() for p in release.rglob('*') if p.is_file() and
             (p.name in prohibited or p.name.endswith(('.checkpoint.json','.input.json','.visual_failure.json')))]
    assert not private,private
    assert not (release/'data').exists() and not (release/'_internal/fixtures').exists()
    return dict(build=manifest,production_modules=len(comparisons),module_comparisons=comparisons,
                assets_match=assets,personal_data_absent=True,
                executable_sha256=hashlib.sha256((release/'ColorStudio.exe').read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release',type=Path)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[1]/'work/studio')
    parser.add_argument('--json',type=Path,required=True)
    args=parser.parse_args();result=verify(args.release,args.source)
    args.json.parent.mkdir(parents=True,exist_ok=True)
    args.json.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Verified',result['production_modules'],'production modules, assets and personal-data exclusion.')
    print('Build:',json.dumps(result['build'],ensure_ascii=False))


if __name__=='__main__':main()
