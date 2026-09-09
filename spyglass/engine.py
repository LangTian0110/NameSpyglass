"""探测引擎：名单分批 → 限速 → 请求 → 落库 → 迁移事件。

被限频/出错时的策略是指数退避与熔断冷却（等待恢复），绝不通过代理轮换绕过封锁。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from .providers.base import NameResult, ProviderError, RateLimited, Status
from .providers.mojang import MojangProvider
from .ratelimit import Backoff, TokenBucket
from .store import Store


@dataclass
class Stats:
    total: int = 0
    checked: int = 0
    available: int = 0
    taken: int = 0
    errors: int = 0
    skipped: int = 0
    retry_wait: float = 0.0
    breaker_trips: int = 0


class Engine:
    def __init__(
        self,
        provider: MojangProvider,
        store: Store,
        notifier,
        *,
        rate_per_sec: float,
        batch_size: int,
        ttl: int,
        backoff_base: float = 5.0,
        backoff_max: float = 600.0,
        max_consecutive_failures: int = 5,
        failure_cooldown: float = 1800.0,
        max_attempts_per_chunk: int = 8,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._provider = provider
        self._store = store
        self._notifier = notifier
        self._bucket = TokenBucket(rate_per_sec, clock=clock, sleep=sleep)
        self._backoff = Backoff(
            base=backoff_base,
            max_delay=backoff_max,
            max_consecutive=max_consecutive_failures,
            cooldown=failure_cooldown,
            clock=clock,
            sleep=sleep,
        )
        self._batch_size = batch_size
        self._ttl = ttl
        self._max_attempts = max_attempts_per_chunk
        self._sleep = sleep
        self._log: Callable[[str], None] = getattr(notifier, "log", lambda msg: None)

    def run(self, names: list[str], force: bool = False) -> Stats:
        stats = Stats(total=len(names))
        pending = []
        for name in names:
            if not force and self._store.fresh(name, self._ttl):
                stats.skipped += 1
            else:
                pending.append(name)
        self._log(f"待探测 {len(pending)} 个（跳过近期已查 {stats.skipped} 个）")

        done = 0
        for chunk in _chunks(pending, self._batch_size):
            for result in self._check_chunk(chunk, stats):
                self._apply(result, stats)
            done += len(chunk)
            self._log(f"进度 {done}/{len(pending)} · 可注册 {stats.available} · 占用 {stats.taken} · 失败 {stats.errors}")
        return stats

    # ---- 内部 -----------------------------------------------------------

    def _check_chunk(self, chunk: list[str], stats: Stats) -> list[NameResult]:
        """带退避重试地探测一批名字；重试耗尽则按 ERROR 记录返回。"""
        for attempt in range(1, self._max_attempts + 1):
            self._bucket.acquire()
            try:
                results = self._provider.check_batch(chunk)
            except RateLimited as exc:
                stats.retry_wait += self._backoff.wait_failure(exc.retry_after)
                self._log(f"触发限频，退避后重试（第 {attempt} 次）")
                continue
            except ProviderError as exc:
                if self._backoff.tripped:
                    self._backoff.wait_if_tripped()
                    stats.breaker_trips += 1
                    self._log("连续失败触发熔断，冷却后继续（策略：等待恢复，不切换 IP）")
                    self._notifier.event("熔断", str(exc))
                    continue
                stats.retry_wait += self._backoff.wait_failure()
                self._log(f"请求失败: {exc}，退避后重试（第 {attempt} 次）")
                continue
            self._backoff.record_success()
            return results
        self._log(f"连续 {self._max_attempts} 次尝试失败，本批 {len(chunk)} 个名字记为 ERROR")
        self._notifier.event("探测失败", f"一批 {len(chunk)} 个名字连续失败，已记为 ERROR")
        return [NameResult(n, Status.ERROR, detail="重试耗尽") for n in chunk]

    def _apply(self, result: NameResult, stats: Stats) -> None:
        old = self._store.upsert(result)
        stats.checked += 1
        if result.status == Status.NOT_FOUND:
            stats.available += 1
        elif result.status == Status.TAKEN:
            stats.taken += 1
        elif result.status == Status.ERROR:
            stats.errors += 1
        self._notify_transition(old, result)

    def _notify_transition(self, old, result: NameResult) -> None:
        if result.status == Status.ERROR:
            return
        if old is None:
            if result.status == Status.NOT_FOUND:
                self._notifier.event("发现可注册 ID", f"{result.name} 当前未被占用")
            return
        if old.status == result.status:
            return
        if old.status == Status.TAKEN and result.status == Status.NOT_FOUND:
            self._notifier.event("ID 释放", f"{result.name} 已被释放，现在可以注册")
        elif old.status == Status.NOT_FOUND and result.status == Status.TAKEN:
            self._notifier.event("ID 被抢注", f"{result.name} 已被注册（UUID: {result.uuid or '未知'}）")


def _chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]
