"""认证版可用性确认 Provider（可选功能）。

端点: GET https://api.minecraftservices.com/minecraft/profile/name/{name}/available
认证: Authorization: Bearer <Minecraft access_token>
官方限制: 每账号 20 次 / 5 分钟，仅适合对少量候选 ID 做最终确认（保留名等
NOT_ALLOWED 场景只能靠它甄别）。

token 来源：Minecraft 启动器会话（约 24 小时有效，过期需更新配置）。
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from ..ratelimit import TokenBucket
from .base import NameResult, ProviderError, RateLimited, Status

# 20 次 / 300 秒，直接取保守整值
_AUTH_RATE_PER_SEC = 20 / 300


_STATUS_MAP = {
    "AVAILABLE": Status.NOT_FOUND,
    "DUPLICATE": Status.TAKEN,
    "NOT_ALLOWED": Status.NOT_ALLOWED,
}


class MCAuthProvider:
    def __init__(
        self,
        client: httpx.Client,
        token: str,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not token:
            raise ValueError("需要 Minecraft access_token（config 的 token 项）")
        self._client = client
        self._token = token
        self._bucket = TokenBucket(_AUTH_RATE_PER_SEC, clock=clock, sleep=sleep)

    def check(self, name: str) -> NameResult:
        self._bucket.acquire()
        resp = self._client.get(
            f"https://api.minecraftservices.com/minecraft/profile/name/{name}/available",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=15.0,
        )
        if resp.status_code == 401:
            raise ProviderError("token 无效或已过期，请更新配置中的 token")
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            raise RateLimited(float(retry) if retry and retry.replace(".", "").isdigit() else None)
        if resp.status_code != 200:
            raise ProviderError(f"认证端点返回 HTTP {resp.status_code}")
        status = _STATUS_MAP.get(resp.json().get("status"))
        if status is None:
            raise ProviderError(f"认证端点返回未知状态: {resp.text[:100]}")
        detail = "认证端点确认" + {
            Status.NOT_FOUND: "可注册",
            Status.TAKEN: "已占用",
            Status.NOT_ALLOWED: "保留名",
        }[status]
        return NameResult(name, status, detail=detail)
