import json

import httpx
import pytest

from spyglass.config import HARD_MAX_RATE, Config
from spyglass.notify import Notifier


def test_config_clamps_dangerous_values():
    cfg = Config(rate_per_sec=99, batch_size=50)
    assert cfg.rate_per_sec == HARD_MAX_RATE  # 硬上限 1.5
    assert cfg.batch_size == 10  # Mojang 批量上限


def test_config_rejects_unknown_keys(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text("rate_per_sec = 0.5\noops = 1\n", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="oops"):
        Config.load(str(f))


def test_config_lang_defaults_to_auto():
    assert Config().lang == ""


def test_config_lang_accepts_explicit_values():
    assert Config(lang="en").lang == "en"
    assert Config(lang="ZH").lang == "zh"  # 归一化小写


def test_config_rejects_invalid_lang(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('lang = "fr"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="fr"):
        Config.load(str(f))
    with pytest.raises(ValueError, match="fr"):
        Config(lang="fr")


def test_notifier_webhook_template():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read()
        return httpx.Response(204)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = Notifier(
        webhook_url="http://hook.example",
        webhook_template='{"title": "{event}", "body": "{detail}"}',
        toast=False,
        client=client,
        out=lambda _msg: None,
    )
    notifier.event("ID 释放", "foo_ 已被释放")
    assert json.loads(captured["json"]) == {"title": "ID 释放", "body": "foo_ 已被释放"}


def test_notifier_falls_back_on_bad_template():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.read()
        return httpx.Response(200)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    notifier = Notifier(
        webhook_url="http://hook.example",
        webhook_template="not-json-{event}",
        toast=False,
        client=client,
        out=lambda _msg: None,
    )
    notifier.event("发现可注册 ID", "abc")
    body = captured["json"]
    assert b"abc" in body and b"content" in body  # 回退为 Discord 风格 content
