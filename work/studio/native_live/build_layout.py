"""Resolve game build files from the selected process's actual module paths."""
from pathlib import Path


def resolve_build_files(module_files):
    if not isinstance(module_files,dict) or not all(k in module_files for k in ('gameassembly.dll','unityplayer.dll')):
        raise ValueError('Selected process has no supported game modules')
    assembly=Path(module_files['gameassembly.dll']).resolve()
    unity=Path(module_files['unityplayer.dll']).resolve()
    if assembly.parent!=unity.parent:raise ValueError('Game modules belong to different installations')
    metadata=assembly.parent/'MabinogiMobile_Data/il2cpp_data/Metadata/global-metadata.dat'
    for path in (assembly,unity,metadata):
        if not path.is_file():raise FileNotFoundError(str(path))
    return dict(gameassembly=assembly,unityplayer=unity,metadata=metadata)
