"""Use the same test scopes as the standard-library runner."""
from collections import Counter
from run_tests import PROFILES, profile_for


def pytest_addoption(parser):
    parser.addoption('--test-profile', choices=PROFILES, default='production',
                     help='production (default), diagnostics, legacy, fixtures, or all')


def pytest_collection_modifyitems(config, items):
    profile = config.getoption('--test-profile')
    kept, excluded = [], []
    counts = Counter()
    for item in items:
        scope = profile_for(item.module.__name__, item.cls.__name__ if item.cls else '',
                            getattr(item, 'originalname', None) or item.name)
        counts[scope] += 1
        (kept if profile == 'all' or scope == profile else excluded).append(item)
    config._colorstudio_test_counts = counts
    if excluded:
        config.hook.pytest_deselected(items=excluded)
        items[:] = kept


def pytest_terminal_summary(terminalreporter, config):
    counts = getattr(config, '_colorstudio_test_counts', {})
    terminalreporter.write_line('Test profiles: ' + ', '.join(
        f'{name}={counts.get(name, 0)}' for name in PROFILES[:-1]))
