"""SQLite 结果存储：支持断点续扫与状态迁移检测。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .providers.base import NameResult, Status


@dataclass
class Record:
    name: str
    status: Status
    uuid: str | None
    detail: str
    first_seen: str
    last_checked: str
    prev_status: Status | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


class Store:
    def __init__(self, path: str) -> None:
        self._conn = sqlite3.connect(path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS results (
                name TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                uuid TEXT,
                detail TEXT NOT NULL DEFAULT '',
                first_seen TEXT NOT NULL,
                last_checked TEXT NOT NULL,
                prev_status TEXT
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def get(self, name: str) -> Record | None:
        row = self._conn.execute(
            "SELECT * FROM results WHERE lower(name) = lower(?)", (name,)
        ).fetchone()
        if row is None:
            return None
        return Record(
            name=row["name"],
            status=Status(row["status"]),
            uuid=row["uuid"],
            detail=row["detail"],
            first_seen=row["first_seen"],
            last_checked=row["last_checked"],
            prev_status=Status(row["prev_status"]) if row["prev_status"] else None,
        )

    def upsert(self, result: NameResult) -> Record | None:
        """写入探测结果，返回更新前的旧记录（用于迁移检测）；无旧记录时返回 None。"""
        old = self.get(result.name)
        now = _now()
        if old is None:
            self._conn.execute(
                "INSERT INTO results (name, status, uuid, detail, first_seen, last_checked, prev_status)"
                " VALUES (?, ?, ?, ?, ?, ?, NULL)",
                (result.name, result.status.value, result.uuid, result.detail, now, now),
            )
        else:
            prev = old.status if old.status != result.status else old.prev_status
            self._conn.execute(
                "UPDATE results SET status = ?, uuid = ?, detail = ?, last_checked = ?, prev_status = ?"
                " WHERE lower(name) = lower(?)",
                (result.status.value, result.uuid, result.detail, now, prev.value if prev else None, result.name),
            )
        self._conn.commit()
        return old

    def all(self) -> list[Record]:
        rows = self._conn.execute("SELECT * FROM results ORDER BY first_seen").fetchall()
        return [
            Record(
                name=r["name"],
                status=Status(r["status"]),
                uuid=r["uuid"],
                detail=r["detail"],
                first_seen=r["first_seen"],
                last_checked=r["last_checked"],
                prev_status=Status(r["prev_status"]) if r["prev_status"] else None,
            )
            for r in rows
        ]

    def fresh(self, name: str, ttl_seconds: int) -> bool:
        """该名字是否在新鲜期内已成功探测过（ERROR 不算新鲜）。"""
        rec = self.get(name)
        if rec is None or rec.status == Status.ERROR:
            return False
        return _parse(rec.last_checked) >= datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)

    def count_by_status(self) -> dict[str, int]:
        rows = self._conn.execute("SELECT status, COUNT(*) AS n FROM results GROUP BY status").fetchall()
        return {r["status"]: r["n"] for r in rows}
