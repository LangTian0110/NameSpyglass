"""monitor 模式：周期性复查名单，检测状态迁移（释放/被抢注）并导出结果。"""

from __future__ import annotations

import time
from collections.abc import Callable


def run_monitor(
    engine,
    names: list[str],
    interval: int,
    export: Callable[[], object],
    log: Callable[[str], None],
) -> None:
    round_no = 0
    while True:
        round_no += 1
        log(f"—— 第 {round_no} 轮探测开始 ——")
        stats = engine.run(names)
        export()
        log(
            f"—— 第 {round_no} 轮完成：可注册 {stats.available} · 占用 {stats.taken} · "
            f"失败 {stats.errors} · 退避累计 {stats.retry_wait:.0f}s，下一轮 {interval}s 后 ——"
        )
        time.sleep(interval)
