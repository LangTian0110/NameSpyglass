import pytest

from spyglass import i18n


@pytest.fixture(autouse=True)
def restore_default_lang():
    """每条用例结束后恢复默认语言，避免影响其他测试模块。"""
    yield
    i18n.set_lang(i18n.DEFAULT_LANG)


def test_default_language_is_english():
    assert i18n.get_lang() == "en"
    assert i18n.t("cli.monitor_stopped") == "Monitoring stopped; progress saved."


def test_switch_to_chinese():
    i18n.set_lang("zh")
    assert i18n.t("cli.monitor_stopped") == "监控已停止，进度已保存。"


def test_format_with_kwargs():
    i18n.set_lang("en")
    msg = i18n.t("names.skip_line", lineno=3, line="ab", reason="too short")
    assert msg == "line 3 'ab': too short"


def test_unknown_key_returns_key_itself():
    assert i18n.t("no.such_key") == "no.such_key"


def test_set_lang_rejects_unknown_language():
    with pytest.raises(ValueError):
        i18n.set_lang("fr")


def test_every_zh_message_has_en_counterpart():
    en = i18n._MESSAGES["en"]
    zh = i18n._MESSAGES["zh"]
    assert set(zh) == set(en), "两种语言的键必须一一对应"


# ---- 系统语言检测 ----

def test_detect_chinese_system(monkeypatch):
    monkeypatch.setattr(i18n, "_locale_candidates", lambda: ["zh_CN.utf8", "en_US"])
    assert i18n.detect_system_lang() == "zh"


def test_detect_chinese_traditional_system(monkeypatch):
    monkeypatch.setattr(i18n, "_locale_candidates", lambda: ["zh_TW"])
    assert i18n.detect_system_lang() == "zh"


def test_detect_english_system(monkeypatch):
    monkeypatch.setattr(i18n, "_locale_candidates", lambda: ["en_US", "C"])
    assert i18n.detect_system_lang() == "en"


def test_detect_falls_back_to_english_when_unknown(monkeypatch):
    monkeypatch.setattr(i18n, "_locale_candidates", lambda: ["C", "POSIX"])
    assert i18n.detect_system_lang() == "en"
