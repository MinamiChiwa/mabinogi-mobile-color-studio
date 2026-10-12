"""Package current guides without widening the v0.4.2 updater allowlist."""
from pathlib import Path
import posixpath
import re

OBSOLETE_GUIDES=('Korean-validation.cmd','Korean-preflight.cmd','native-window-check.ps1',
    'WINDOW_CHECK.zh-CN.md','WINDOW_CHECK.zh-TW.md','WINDOW_CHECK.en.md',
    'SCREENSHOT_PREVIEW.md','docs/korean-validation.md')


def package_documents(workspace,package):
    from build_info import APP_VERSION
    workspace=Path(workspace);package=Path(package)
    locations={name:name for name in ('README.md','README.zh-TW.md','README.en.md','TESTING.md')}
    locations.update({name:'_internal/docs/'+name for name in ('README.ja.md','README.ko.md')})
    locations.update({'docs/automatic-updates.md':'docs/automatic-updates.md',
        'docs/server-adaptation/server-selection.md':'_internal/docs/server-selection.md',
        'work/studio/VERIFICATION.md':'work/studio/VERIFICATION.md',
        f'docs/release-notes-{APP_VERSION}.md':'RELEASE_NOTES.md'})
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
        text=re.sub(r'\]\(([^)]+)\)',rewrite,document.read_text(encoding='utf-8'))
        output=package/destination;output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(text,encoding='utf-8')
