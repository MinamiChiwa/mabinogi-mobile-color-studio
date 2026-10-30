"""Region rules sent to the engine and the saved profile format."""
import pytest

from business import RuleSource
from profile_store import canonical_profile, default_profile, read_profile, write_profile


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def card(enabled=True, target='#a1b2c3', alt='', mode='精准 HEX', tolerance=8.0):
    source = RuleSource()
    source.enabled, source.target, source.alt = Var(enabled), Var(target), Var(alt)
    source.mode, source.tolerance = Var(mode), Var(tolerance)
    return source


def test_exact_rule_normalizes_target_and_alternatives():
    rule = card(alt='#ffffff， eaeaea ,').rule()
    assert rule == {'enabled': True, 'colors': ['#A1B2C3', '#FFFFFF', '#EAEAEA'],
                    'exact': True, 'tolerance': 8.0}


def test_similar_rule_keeps_tolerance():
    rule = card(mode='相似颜色', tolerance=12).rule()
    assert rule['exact'] is False and rule['tolerance'] == 12


def test_disabled_region_sends_no_colors():
    assert card(enabled=False, target='not a color').rule() == {
        'enabled': False, 'colors': [], 'exact': True, 'tolerance': 0}


def test_invalid_target_is_rejected():
    with pytest.raises(ValueError):
        card(target='#12').rule()


def test_profile_round_trip(tmp_path):
    profile = default_profile()
    profile['regions'][1].update(target='#336699', mode='相似颜色', tolerance=15)
    profile['priority_order'] = [2, 0, 1]
    path = tmp_path / 'profile.json'
    write_profile(path, profile)
    assert read_profile(path) == canonical_profile(profile)


def test_legacy_atlas_strategy_migrates_to_screenshot():
    profile = dict(default_profile(), search_strategy='atlas')
    assert canonical_profile(profile)['search_strategy'] == 'screenshot'


@pytest.mark.parametrize('order', [[0, 0, 1], [0, 1], [0, 1, 3]])
def test_profile_rejects_invalid_priority(order):
    with pytest.raises(ValueError):
        canonical_profile(dict(default_profile(), priority_order=order))
