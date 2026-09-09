import json

import httpx
import pytest

from spyglass.providers.base import ProviderError, RateLimited
from spyglass.providers.mojang import MojangProvider


def make_provider(handler, hosts=None):
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return MojangProvider(client, hosts or ["api.minecraftservices.com", "api.mojang.com"])


def test_bulk_partial_taken():
    """批量响应只含存在的玩家，缺席者判为未注册。"""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.read())
        return httpx.Response(200, json=[{"id": "uuid-a", "name": "Alpha"}])

    provider = make_provider(handler)
    results = provider.check_batch(["Alpha", "Beta"])

    assert "bulk/byname" in seen["url"]
    assert seen["body"] == ["Alpha", "Beta"]  # 新端点 body 为字符串数组
    by_name = {r.name: r for r in results}
    assert by_name["Alpha"].status.value == "TAKEN"
    assert by_name["Alpha"].uuid == "uuid-a"
    assert by_name["Beta"].status.value == "NOT_FOUND"


def test_legacy_bulk_body_shape():
    """api.mojang.com 的旧批量端点同样接受字符串数组（已实测验证）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.mojang.com"
        assert request.url.path == "/profiles/minecraft"
        assert json.loads(request.read()) == ["alpha"]
        return httpx.Response(200, json=[{"id": "u", "name": "Alpha"}])

    provider = make_provider(handler, hosts=["api.mojang.com"])
    results = provider.check_batch(["alpha"])
    assert results[0].status.value == "TAKEN"


def test_fallback_to_singles_when_bulk_missing():
    """批量端点 404 时自动回退逐名单查。"""
    singles_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(404)  # 批量端点不存在
        singles_seen.append(request.url.path)
        if request.url.path.endswith("/Gamma"):
            return httpx.Response(200, json={"id": "uuid-g", "name": "Gamma"})
        return httpx.Response(204)

    provider = make_provider(handler)
    results = provider.check_batch(["Gamma", "Delta"])

    by_name = {r.name: r for r in results}
    assert by_name["Gamma"].status.value == "TAKEN"
    assert by_name["Delta"].status.value == "NOT_FOUND"
    assert len(singles_seen) == 2


def test_rate_limited_raises_with_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "12"})

    provider = make_provider(handler)
    with pytest.raises(RateLimited) as excinfo:
        provider.check_batch(["Alpha"])
    assert excinfo.value.retry_after == 12.0


def test_failover_on_403_to_second_host():
    """Mojang 已知偶发 403：应切换到下一主机而不是失败。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "api.minecraftservices.com":
            return httpx.Response(403)
        assert json.loads(request.read()) == ["alpha"]
        return httpx.Response(200, json=[{"id": "u", "name": "Alpha"}])

    provider = make_provider(handler)
    results = provider.check_batch(["alpha"])
    assert results[0].status.value == "TAKEN"


def test_all_hosts_403_raises_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    provider = make_provider(handler)
    with pytest.raises(ProviderError):
        provider.check_batch(["alpha"])


def test_unknown_host_rejected():
    with pytest.raises(ValueError):
        make_provider(lambda req: httpx.Response(200), hosts=["example.com"])
