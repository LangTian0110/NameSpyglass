"""Provider 抽象与公共类型。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class Status(str, Enum):
    NOT_FOUND = "NOT_FOUND"  # 无此玩家 → 大概率可注册（保留名等特殊情况需认证端点确认）
    TAKEN = "TAKEN"  # 已被占用
    NOT_ALLOWED = "NOT_ALLOWED"  # 被官方保留/禁用，无法注册
    ERROR = "ERROR"  # 本次探测失败


@dataclass
class NameResult:
    name: str
    status: Status
    uuid: str | None = None
    detail: str = ""


class RateLimited(Exception):
    """HTTP 429：应按 Retry-After / 指数退避等待，绝不通过换 IP 绕过。"""

    def __init__(self, retry_after: float | None = None, detail: str = "") -> None:
        super().__init__(detail or f"rate limited (retry_after={retry_after})")
        self.retry_after = retry_after


class ProviderError(Exception):
    """不可解析为结果的错误（网络故障、5xx、持续 403、token 失效等）。"""


class Provider(Protocol):
    def check_batch(self, names: list[str]) -> list[NameResult]: ...
