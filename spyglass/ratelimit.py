"""限频与退避。

令牌桶控制稳态速率；失败时指数退避（尊重 Retry-After），连续失败进入熔断冷却。
被限频/封锁时的策略是等待恢复 —— 不做代理轮换，不绕过封锁。
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable


class TokenBucket:
    """令牌桶：稳态速率 rate token/s，桶容量 capacity。"""

    def __init__(
        self,
        rate: float,
        capacity: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate <= 0:
            raise ValueError("rate 必须为正数")
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last = clock()
        self._clock = clock
        self._sleep = sleep

    def acquire(self) -> None:
        """阻塞直到取得一个令牌。"""
        while True:
            now = self._clock()
            self._tokens = min(self.capacity, self._tokens + (now - self._last) * self.rate)
            self._last = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return
            self._sleep((1.0 - self._tokens) / self.rate)


class Backoff:
    """指数退避 + 抖动 + 熔断。

    - failure_delay(): 根据连续失败次数计算下次重试前应等待的秒数
    - wait_failure(): 计算、累计并 sleep（供引擎在捕获限频/错误后调用）
    - wait_if_tripped(): 熔断打开时 sleep 整个冷却期，然后半开（再失败会立即再次熔断）
    - record_success(): 成功后清零计数并解除熔断
    """

    def __init__(
        self,
        base: float = 5.0,
        max_delay: float = 600.0,
        jitter: float = 0.2,
        max_consecutive: int = 5,
        cooldown: float = 1800.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rng: Callable[[], float] | None = None,
    ) -> None:
        self.base = base
        self.max_delay = max_delay
        self.jitter = jitter
        self.max_consecutive = max_consecutive
        self.cooldown = cooldown
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.random
        self.consecutive = 0
        self._tripped_at: float | None = None

    @property
    def tripped(self) -> bool:
        return self._tripped_at is not None

    def failure_delay(self, retry_after: float | None = None) -> float:
        delay = float(retry_after) if retry_after and retry_after > 0 else min(
            self.base * 2**self.consecutive, self.max_delay
        )
        if retry_after is None or retry_after <= 0:
            delay *= 1 - self.jitter + self._rng() * 2 * self.jitter
        return delay

    def wait_failure(self, retry_after: float | None = None) -> float:
        delay = self.failure_delay(retry_after)  # 首次失败退避 base，之后翻倍
        self.consecutive += 1
        self._sleep(delay)
        if self.consecutive >= self.max_consecutive and not self.tripped:
            self._tripped_at = self._clock()
        return delay

    def wait_if_tripped(self) -> float:
        if not self.tripped:
            return 0.0
        elapsed = self._clock() - self._tripped_at  # type: ignore[arg-type]
        remaining = self.cooldown - elapsed
        if remaining > 0:
            self._sleep(remaining)
        # 半开：允许尝试，但再失败会立即重新熔断
        self._tripped_at = None
        self.consecutive = self.max_consecutive - 1
        return max(remaining, 0.0)

    def record_success(self) -> None:
        self.consecutive = 0
        self._tripped_at = None
