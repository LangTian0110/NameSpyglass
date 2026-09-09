"""monitor 模式：周期性复查名单，检测状态迁移（释放/被抢注）并导出结果。"""

from __future__ import annotations

import time
from collections.abc import Callable

from .i18n import t


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
        log(t("monitor.round_start", n=round_no))
        stats = engine.run(names)
        export()
        log(
            t(
                "monitor.round_done",
                n=round_no,
                a=stats.available,
                t=stats.taken,
                e=stats.errors,
                w=f"{stats.retry_wait:.0f}",
                i=interval,
            )
        )
        time.sleep(interval)
