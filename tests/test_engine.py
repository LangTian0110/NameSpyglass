from spyglass.engine import Engine
from spyglass import i18n
from spyglass.notify import Notifier
from spyglass.providers.base import NameResult, RateLimited, Status
from spyglass.ratelimit import TokenBucket
from spyglass.store import Store


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class FakeProvider:
    """按预设序列返回结果或抛异常，并记录每次收到的批次。"""

    def __init__(self, script=None):
        self.script = list(script or [])
        self.calls = []

    def check_batch(self, names):
        self.calls.append(list(names))
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        raise RateLimited()  # 未编排时持续限频，用于测重试耗尽


def make_engine(provider, store, script_msgs):
    clock = FakeClock()

    def sleep(s):
        clock.t += s

    bucket = TokenBucket(1000.0, clock=clock, sleep=sleep)  # 测试中不限速
    notifier = Notifier(toast=False, out=script_msgs.append)
    engine = Engine(
        provider,
        store,
        notifier,
        rate_per_sec=1000.0,
        batch_size=2,
        ttl=86400,
        max_attempts_per_chunk=3,
        clock=clock,
        sleep=sleep,
    )
    return engine, notifier


def results(*pairs):
    out = []
    for p in pairs:
        out.append(NameResult(p[0], p[1], uuid=p[2] if len(p) > 2 else None))
    return out


def test_run_records_and_events(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    msgs = []
    provider = FakeProvider(
        [
            results(("a", Status.NOT_FOUND), ("b", Status.TAKEN, "u-b")),
            results(("ok_name", Status.NOT_FOUND)),
        ]
    )
    engine, notifier = make_engine(provider, store, msgs)

    stats = engine.run(["a", "b", "ok_name"])

    assert stats.checked == 3 and stats.available == 2 and stats.taken == 1
    assert store.get("a").status == Status.NOT_FOUND
    # 首次发现未注册 → 事件通知（两条 NOT_FOUND 名字各一条）。事件名随语言而变，断言用 key 前缀避免硬编码。
    event_tag = f"[{i18n.t('engine.event_found')}]"
    events = [m for m in msgs if m.startswith(event_tag)]
    assert len(events) == 2
    notifier.close()


def test_transition_events(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    msgs = []
    store.upsert(NameResult("x", Status.TAKEN, uuid="old"))
    store.upsert(NameResult("y", Status.NOT_FOUND))

    provider = FakeProvider(
        [
            results(("x", Status.NOT_FOUND)),  # 释放
            results(("y", Status.TAKEN, "new")),  # 被抢注
        ]
    )
    engine, notifier = make_engine(provider, store, msgs)
    # 预置记录在新鲜期内，需 force 才会真正重查
    engine.run(["x"], force=True)
    engine.run(["y"], force=True)

    released_tag = f"[{i18n.t('engine.event_released')}]"
    sniped_tag = f"[{i18n.t('engine.event_sniped')}]"
    assert any(m.startswith(released_tag) and "x" in m for m in msgs)
    assert any(m.startswith(sniped_tag) and "y" in m for m in msgs)
    assert store.get("x").prev_status == Status.TAKEN
    assert store.get("y").prev_status == Status.NOT_FOUND
    notifier.close()


def test_ttl_skips_fresh_names(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    msgs = []
    provider = FakeProvider([results(("a", Status.NOT_FOUND))])
    engine, notifier = make_engine(provider, store, msgs)

    engine.run(["a"])
    stats2 = engine.run(["a"])
    assert stats2.skipped == 1 and stats2.checked == 0 and len(provider.calls) == 1

    provider.script.append(results(("a", Status.NOT_FOUND)))  # force 重查也需成功返回
    stats3 = engine.run(["a"], force=True)
    assert stats3.skipped == 0 and len(provider.calls) == 2
    notifier.close()


def test_rate_limit_then_retry(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    msgs = []
    provider = FakeProvider(
        script=[RateLimited(retry_after=7.0), results(("a", Status.NOT_FOUND))]
    )
    engine, notifier = make_engine(provider, store, msgs)

    stats = engine.run(["a"])

    assert len(provider.calls) == 2  # 第一次被限频，第二次成功
    assert stats.retry_wait == 7.0
    assert store.get("a").status == Status.NOT_FOUND
    notifier.close()


def test_retries_exhausted_marks_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    msgs = []
    provider = FakeProvider()  # 始终抛 RateLimited
    engine, notifier = make_engine(provider, store, msgs)

    stats = engine.run(["a", "b"])

    assert len(provider.calls) == 3  # max_attempts_per_chunk=3
    assert stats.errors == 2
    assert store.get("a").status == Status.ERROR
    notifier.close()
