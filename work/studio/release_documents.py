"""Keep user guides in portable releases and development documents online."""
from pathlib import Path
import posixpath
import re
import shutil

USER_GUIDES=('README.md','README.zh-TW.md','README.en.md')


def development_document_path(relative):
    parts=relative.casefold().split('/')
    return (parts[0] in {'docs','work'} or
            (len(parts)>1 and parts[0]=='_internal' and parts[1] in {'docs','work'}) or
            (len(parts)==1 and Path(parts[0]).stem in {'testing','release_notes'}))


def validate_package_documents(package):
    package=Path(package)
    unwanted=[p.relative_to(package).as_posix() for p in package.rglob('*')
              if development_document_path(p.relative_to(package).as_posix())]
    if unwanted:raise ValueError('Development documents in release: '+', '.join(unwanted))


def _remove_packaged_path(package,path):
    # Cleanup only known build-output paths; never recurse outside this package.
    if path.is_symlink():path.unlink();return
    if not path.resolve().is_relative_to(package.resolve()):
        raise ValueError('Package cleanup outside build output: '+str(path))
    if path.is_dir():shutil.rmtree(path)
    elif path.is_file():path.unlink()

OBSOLETE_GUIDES=('Korean-validation.cmd','Korean-preflight.cmd','native-window-check.ps1',
    'WINDOW_CHECK.zh-CN.md','WINDOW_CHECK.zh-TW.md','WINDOW_CHECK.en.md',
    'SCREENSHOT_PREVIEW.md','docs/korean-validation.md')


def package_documents(workspace,package):
    from build_info import APP_VERSION
    workspace=Path(workspace);package=Path(package)
    # These root filenames are also accepted by already-released updaters.
    # Japanese/Korean guides and development references remain linked online.
    locations={name:name for name in USER_GUIDES}
    package.mkdir(parents=True,exist_ok=True)
    for path in list(package.iterdir()):
        if development_document_path(path.name):_remove_packaged_path(package,path)
        elif path.name.casefold()=='_internal' and path.is_dir():
            for child in list(path.iterdir()):
                if development_document_path('_internal/'+child.name):
                    _remove_packaged_path(package,child)
    for name in OBSOLETE_GUIDES:
        path=package/name
        if path.is_file():path.unlink()
    for source,destination in locations.items():
        document=workspace/source
        if not document.is_file():continue
        def rewrite(match):
            link=match.group(1)
            if '://' in link or link.startswith(('#','mailto:')):return match.group()
            relative,separator,fragment=link.partition('#')
            target=posixpath.normpath(posixpath.join(posixpath.dirname(source),relative))
            if target in locations:
                url=posixpath.relpath(locations[target],posixpath.dirname(destination) or '.')
            else:
                url=f'https://github.com/MinamiChiwa/mabinogi-mobile-color-studio/blob/v{APP_VERSION}/{target}'
            return ']('+url+(separator+fragment if separator else '')+')'
        text=re.sub(r'^## (?:开发与测试|開發與測試|Development and tests)\n.*?(?=^## |\Z)',
                    '',document.read_text(encoding='utf-8'),flags=re.MULTILINE|re.DOTALL)
        text=re.sub(r'\]\(([^)]+)\)',rewrite,text)
        output=package/destination;output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(text,encoding='utf-8')
    validate_package_documents(package)
