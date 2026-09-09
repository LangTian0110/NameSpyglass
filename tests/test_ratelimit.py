import pytest

from spyglass.ratelimit import Backoff, TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make_sleeper(clock):
    slept = []

    def sleep(s):
        slept.append(s)
        clock.t += s

    return slept, sleep


def test_token_bucket_paces_requests():
    clock = FakeClock()
    slept, sleep = make_sleeper(clock)
    bucket = TokenBucket(rate=10.0, capacity=1.0, clock=clock, sleep=sleep)

    bucket.acquire()  # 容量内的第一个令牌立即可用
    assert slept == []

    bucket.acquire()  # 第二个需等待 1/rate = 0.1s
    assert slept == [pytest.approx(0.1)]


def test_backoff_exponential_with_cap():
    clock = FakeClock()
    slept, sleep = make_sleeper(clock)
    backoff = Backoff(base=5, max_delay=60, jitter=0, clock=clock, sleep=sleep)

    delays = [backoff.wait_failure() for _ in range(7)]
    assert delays == [5, 10, 20, 40, 60, 60, 60]  # 指数增长，封顶 max_delay


def test_backoff_honors_retry_after_without_jitter():
    clock = FakeClock()
    slept, sleep = make_sleeper(clock)
    backoff = Backoff(base=5, jitter=0.9, clock=clock, sleep=sleep)

    delay = backoff.wait_failure(retry_after=7.0)
    assert delay == 7.0  # Retry-After 原样尊重，不加抖动


def test_backoff_breaker_trips_and_half_opens():
    clock = FakeClock()
    slept, sleep = make_sleeper(clock)
    backoff = Backoff(
        base=1, max_delay=10, jitter=0, max_consecutive=3, cooldown=1800, clock=clock, sleep=sleep
    )

    for _ in range(3):
        backoff.wait_failure()
    assert backoff.tripped

    backoff.wait_if_tripped()  # 冷却整个 1800s 后半开
    assert not backoff.tripped
    assert backoff.consecutive == 2  # 半开状态：再失败一次即重新熔断

    backoff.wait_failure()
    assert backoff.tripped  # 半开失败 → 立即再熔断

    backoff.record_success()
    assert not backoff.tripped and backoff.consecutive == 0


def test_backoff_success_resets():
    backoff = Backoff(jitter=0)
    backoff.wait_failure()
    backoff.wait_failure()
    backoff.record_success()
    assert backoff.consecutive == 0
    assert backoff.failure_delay() == 5  # 从头计数
