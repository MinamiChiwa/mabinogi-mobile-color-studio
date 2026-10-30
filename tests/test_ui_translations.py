"""Every fixed QML label has a translation in each non-Chinese language."""
import re

import pytest

import i18n
from qt_ui import QML_DIR
from qt_ui.i18n_qt import translate

LABEL = re.compile(r"Loc\.t\('([^'\\]+)'\)")
HAN = re.compile(r'[\u4e00-\u9fff]')
# Words written the same in Japanese as in Simplified Chinese.
SAME_IN_JAPANESE = {' / 平均 ', ' · 最大 ΔE ', '不透明度', '保存', '停止', '停止  F9', '最近'}


def qml_labels():
    labels = set()
    for path in QML_DIR.glob('*.qml'):
        labels.update(label for label in LABEL.findall(path.read_text(encoding='utf-8')) if HAN.search(label))
    return sorted(labels)


@pytest.fixture
def language(monkeypatch):
    def use(name):
        monkeypatch.setattr(i18n, 'language', name)
        i18n._translate.cache_clear()
    yield use
    i18n._translate.cache_clear()


def test_english_labels_contain_no_chinese(language):
    language('English')
    missing = [label for label in qml_labels() if HAN.search(translate(label))]
    assert missing == []


def test_korean_labels_contain_no_chinese(language):
    language('한국어')
    missing = [label for label in qml_labels() if HAN.search(translate(label))]
    assert missing == []


def test_japanese_labels_are_translated(language):
    language('日本語')
    missing = [label for label in qml_labels()
               if translate(label) == label and label not in SAME_IN_JAPANESE]
    assert missing == []
