"""Default to smoke checks; explicit pytest paths run exactly what was requested."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for folder in (ROOT / 'work/studio', ROOT / 'tests/studio', ROOT / 'scripts'):
    sys.path.insert(0, str(folder))

from scripts.run_tests import PROFILES, select_tests


def pytest_addoption(parser):
    parser.addoption('--test-profile', choices=PROFILES, default=None,
                     help='Optional profile; without paths defaults to smoke')


class _SelectorCase:
    def __init__(self, item):
        self.item = item
    def id(self):
        item = self.item
        module = item.module.__name__.rsplit('.', 1)[-1]
        method = getattr(item, 'originalname', None) or item.name
        return '.'.join(filter(None, (module, item.cls.__name__ if item.cls else '', method)))


def pytest_collection_modifyitems(config, items):
    profile = config.getoption('--test-profile')
    if profile is None and config.option.file_or_dir:
        config._colorstudio_selection = dict(profile='focused', selected_count=len(items))
        return
    cases = [_SelectorCase(item) for item in items]
    selected, selection = select_tests(cases, profile or 'smoke')
    kept = {id(case.item) for case in selected}
    excluded = [item for item in items if id(item) not in kept]
    config._colorstudio_selection = selection
    if excluded:
        config.hook.pytest_deselected(items=excluded)
    items[:] = [item for item in items if id(item) in kept]


def pytest_terminal_summary(terminalreporter, config):
    selection = getattr(config, '_colorstudio_selection', {})
    terminalreporter.write_line('ColorStudio profile: ' + str(selection.get('profile'))
                               + '; selected=' + str(selection.get('selected_count')))
    terminalreporter.write_line('Release evidence verdict: use scripts/run_tests.py --suite release --json <report>.')
