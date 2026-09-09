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

from ..i18n import t
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
            raise ValueError(t("auth.token_required"))
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
            raise ProviderError(t("auth.token_invalid"))
        if resp.status_code == 429:
            retry = resp.headers.get("Retry-After")
            raise RateLimited(float(retry) if retry and retry.replace(".", "").isdigit() else None)
        if resp.status_code != 200:
            raise ProviderError(t("auth.http_error", code=resp.status_code))
        status = _STATUS_MAP.get(resp.json().get("status"))
        if status is None:
            raise ProviderError(t("auth.unknown_status", text=resp.text[:100]))
        detail = {
            Status.NOT_FOUND: t("auth.detail_available"),
            Status.TAKEN: t("auth.detail_duplicate"),
            Status.NOT_ALLOWED: t("auth.detail_not_allowed"),
        }[status]
        return NameResult(name, status, detail=detail)
