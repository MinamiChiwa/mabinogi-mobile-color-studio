"""Pytest uses the canonical offline selector; release verdicts use run_tests.py."""
from scripts.run_tests import PROFILES, select_tests


def pytest_addoption(parser):
    parser.addoption('--test-profile', choices=PROFILES, default='quick',
                     help='quick (default), release, research, or full')


class _SelectorCase:
    def __init__(self, item):
        self.item = item
    def id(self):
        item = self.item
        module = item.module.__name__.rsplit('.', 1)[-1]
        method = getattr(item, 'originalname', None) or item.name
        return '.'.join(filter(None, (module, item.cls.__name__ if item.cls else '', method)))


def pytest_collection_modifyitems(config, items):
    cases = [_SelectorCase(item) for item in items]
    selected, selection = select_tests(cases, config.getoption('--test-profile'))
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
