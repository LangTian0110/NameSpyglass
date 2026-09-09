import sqlite3

from spyglass.providers.base import NameResult, Status
from spyglass.store import Store


def test_upsert_new_and_update(tmp_path):
    store = Store(str(tmp_path / "t.db"))

    assert store.get("Notch") is None
    old = store.upsert(NameResult("Notch", Status.NOT_FOUND))
    assert old is None

    rec = store.get("notch")  # 大小写不敏感匹配
    assert rec.status == Status.NOT_FOUND
    first_seen = rec.first_seen

    old = store.upsert(NameResult("Notch", Status.TAKEN, uuid="u-1"))
    assert old.status == Status.NOT_FOUND  # 返回更新前的记录供迁移检测

    rec = store.get("Notch")
    assert rec.status == Status.TAKEN
    assert rec.uuid == "u-1"
    assert rec.prev_status == Status.NOT_FOUND
    assert rec.first_seen == first_seen  # 首见时间保留
    store.close()


def test_same_status_keeps_prev(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.upsert(NameResult("a", Status.TAKEN, uuid="x"))
    store.upsert(NameResult("a", Status.TAKEN, uuid="x"))
    rec = store.get("a")
    assert rec.prev_status is None  # 未发生迁移
    store.close()


def test_fresh_and_error(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.upsert(NameResult("a", Status.TAKEN))
    store.upsert(NameResult("b", Status.ERROR, detail="x"))

    assert store.fresh("a", ttl_seconds=86400)
    assert not store.fresh("b", ttl_seconds=86400)  # ERROR 不算新鲜

    # 人为把 a 的检查时间改旧 → 超出新鲜期
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("UPDATE results SET last_checked = '2020-01-01T00:00:00+00:00' WHERE name = 'a'")
    conn.commit()
    conn.close()
    assert not store.fresh("a", ttl_seconds=86400)
    store.close()


def test_all_and_counts(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    store.upsert(NameResult("a", Status.NOT_FOUND))
    store.upsert(NameResult("b", Status.TAKEN))
    store.upsert(NameResult("c", Status.TAKEN))
    assert len(store.all()) == 3
    assert store.count_by_status() == {"NOT_FOUND": 1, "TAKEN": 2}
    store.close()
