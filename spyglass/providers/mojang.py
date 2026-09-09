"""Mojang 免认证查询 Provider。

主力为批量端点（一次最多 10 个名字，官方限频为每 IP 200 请求 / 2 分钟），
两个主机均接受字符串数组 body（已实测验证）：

- api.minecraftservices.com: POST /minecraft/profile/lookup/bulk/byname
- api.mojang.com:            POST /profiles/minecraft

响应只包含存在的玩家（{id, name} 数组），缺席者即未注册 → NOT_FOUND。

单查端点作为批量不可用时的回退：
- api.minecraftservices.com: GET /minecraft/profile/lookup/name/{name}
- api.mojang.com:            GET /users/profiles/minecraft/{name}
  200 = 占用；204/404 = 不存在。

容错策略：
- 已知 Mojang 会偶发随机 403（其自身配置问题）→ 逐主机切换重试；全部 403 视为临时故障上报
- 429 → 抛 RateLimited（由引擎统一退避，不换 IP）
- 5xx / 网络错误 → 逐主机切换；全部失败抛 ProviderError
- 批量端点在所有主机上 404/405/400 → 永久禁用批量，改用逐名单查
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..i18n import t
from .base import NameResult, ProviderError, RateLimited, Status


@dataclass
class _HostCfg:
    bulk_path: str
    single_path: str


_HOST_CONFIG = {
    "api.minecraftservices.com": _HostCfg(
        bulk_path="/minecraft/profile/lookup/bulk/byname",
        single_path="/minecraft/profile/lookup/name/{name}",
    ),
    "api.mojang.com": _HostCfg(
        bulk_path="/profiles/minecraft",
        single_path="/users/profiles/minecraft/{name}",
    ),
}


class MojangProvider:
    def __init__(self, client: httpx.Client, hosts: list[str], timeout: float = 15.0) -> None:
        unknown = [h for h in hosts if h not in _HOST_CONFIG]
        if unknown or not hosts:
            raise ValueError(t("mojang.unsupported_hosts", hosts=unknown or hosts, valid=list(_HOST_CONFIG)))
        self._client = client
        self._hosts = list(hosts)
        self._timeout = timeout
        self._sticky = 0  # 上次成功的主机下标，优先复用
        self._bulk_disabled = False

    # ---- 对外接口 -------------------------------------------------------

    def check_batch(self, names: list[str]) -> list[NameResult]:
        if not self._bulk_disabled:
            try:
                return self._check_bulk(names)
            except _BulkUnavailable:
                self._bulk_disabled = True
        return self._check_singles(names)

    # ---- 批量 -----------------------------------------------------------

    def _check_bulk(self, names: list[str]) -> list[NameResult]:
        errors: list[str] = []
        for offset in range(len(self._hosts)):
            host = self._hosts[(self._sticky + offset) % len(self._hosts)]
            cfg = _HOST_CONFIG[host]
            try:
                resp = self._client.post(
                    f"https://{host}{cfg.bulk_path}", json=list(names), timeout=self._timeout
                )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                errors.append(t("mojang.network_error", host=host, err=exc.__class__.__name__))
                continue
            if resp.status_code == 200:
                self._sticky = self._hosts.index(host)
                return self._parse_bulk(names, resp)
            if resp.status_code == 429:
                raise RateLimited(_retry_after(resp), t("mojang.rate_limited", host=host))
            if resp.status_code in (400, 404, 405):
                # 批量端点缺失/请求形态不符 → 尝试下一主机，全部如此则改走单查
                errors.append(f"{host}: {resp.status_code}")
                continue
            errors.append(f"{host}: HTTP {resp.status_code}")
        raise _BulkUnavailable("; ".join(errors) or t("mojang.no_host"))

    @staticmethod
    def _parse_bulk(names: list[str], resp: httpx.Response) -> list[NameResult]:
        try:
            taken = {p["name"].lower(): p["id"] for p in resp.json()}
        except (ValueError, KeyError, TypeError) as exc:
            raise ProviderError(t("mojang.bulk_parse_failed", err=exc)) from exc
        return [
            NameResult(
                name=n,
                status=Status.TAKEN if n.lower() in taken else Status.NOT_FOUND,
                uuid=taken.get(n.lower()),
            )
            for n in names
        ]

    # ---- 单查回退 -------------------------------------------------------

    def _check_singles(self, names: list[str]) -> list[NameResult]:
        return [self._check_single(n) for n in names]

    def _check_single(self, name: str) -> NameResult:
        errors: list[str] = []
        for offset in range(len(self._hosts)):
            host = self._hosts[(self._sticky + offset) % len(self._hosts)]
            path = _HOST_CONFIG[host].single_path.format(name=name)
            try:
                resp = self._client.get(f"https://{host}{path}", timeout=self._timeout)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                errors.append(t("mojang.network_error", host=host, err=exc.__class__.__name__))
                continue
            if resp.status_code == 200:
                self._sticky = self._hosts.index(host)
                try:
                    data = resp.json()
                except ValueError as exc:
                    raise ProviderError(t("mojang.single_parse_failed", err=exc)) from exc
                return NameResult(name, Status.TAKEN, uuid=data.get("id"))
            if resp.status_code in (204, 404):
                self._sticky = self._hosts.index(host)
                return NameResult(name, Status.NOT_FOUND)
            if resp.status_code == 429:
                raise RateLimited(_retry_after(resp), t("mojang.rate_limited", host=host))
            errors.append(f"{host}: HTTP {resp.status_code}")
        raise ProviderError("; ".join(errors) or t("mojang.no_host"))


class _BulkUnavailable(Exception):
    """批量端点在所有主机上不可用，需回退到单查。"""


def _retry_after(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None
