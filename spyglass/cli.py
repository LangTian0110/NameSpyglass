"""命令行入口。

用法:
  python -m spyglass check   [--names names.txt] [--force]
  python -m spyglass monitor [--names names.txt] [--interval 3600]
  python -m spyglass report
  python -m spyglass confirm [--top 5]   （需配置 token，认证端点最终确认）
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import httpx

from .config import Config
from .engine import Engine
from .monitor import run_monitor
from .names import load_names
from .net import ssl_context
from .notify import Notifier
from .providers.base import Status
from .providers.mcservices_auth import MCAuthProvider
from .providers.mojang import MojangProvider
from .store import Store


def main(argv: list[str] | None = None) -> int:
    _safe_utf8_console()
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n已中断；进度实时保存在 SQLite 中，可直接重跑续扫。")
        return 130


# ---- 参数 ---------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spyglass",
        description="Minecraft ID 可用性探测与释放监控（合规版：名单驱动、限频退避、无代理轮换）",
    )
    parser.add_argument("--config", default=None, help="TOML 配置文件路径（默认自动加载 ./config.toml）")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--names", default="names.txt", help="名单文件，一行一个 ID")
        sp.add_argument("--db", default=None, help="SQLite 路径（覆盖配置）")
        sp.add_argument("--output-dir", default=None, help="输出目录（覆盖配置）")
        sp.add_argument("--rate", type=float, default=None, help="请求速率 req/s（硬上限 1.5）")
        sp.add_argument("--batch-size", type=int, default=None, help="批量端点单次名字数（≤10）")
        sp.add_argument("--token", default=None, help="Minecraft access_token（confirm 用）")
        sp.add_argument("--quiet", action="store_true", help="减少控制台输出")

    sp_check = sub.add_parser("check", help="一次性探测名单")
    add_common(sp_check)
    sp_check.add_argument("--force", action="store_true", help="忽略结果新鲜期，强制重查")
    sp_check.set_defaults(func=_cmd_check)

    sp_monitor = sub.add_parser("monitor", help="持续监控名单，检测 ID 释放/被抢注")
    add_common(sp_monitor)
    sp_monitor.add_argument("--interval", type=int, default=None, help="轮询间隔秒数（默认取配置）")
    sp_monitor.set_defaults(func=_cmd_monitor)

    sp_report = sub.add_parser("report", help="汇总并导出当前结果")
    sp_report.add_argument("--db", default=None)
    sp_report.add_argument("--output-dir", default=None)
    sp_report.set_defaults(func=_cmd_report)

    sp_confirm = sub.add_parser("confirm", help="用认证端点对候选做最终确认（20 次/5 分钟）")
    sp_confirm.add_argument("--db", default=None)
    sp_confirm.add_argument("--top", type=int, default=5, help="确认前 N 个未注册候选")
    sp_confirm.add_argument("--token", default=None, help="Minecraft access_token")
    sp_confirm.set_defaults(func=_cmd_confirm)
    return parser


# ---- 运行时组装 ---------------------------------------------------------

def _load_config(args) -> Config:
    path = getattr(args, "config", None)
    if path is None and Path("config.toml").is_file():
        path = "config.toml"
    cfg = Config.load(path)
    # CLI 参数优先覆盖配置文件
    if getattr(args, "db", None):
        cfg.db_path = args.db
    if getattr(args, "output_dir", None):
        cfg.output_dir = args.output_dir
    if getattr(args, "rate", None):
        cfg.rate_per_sec = args.rate
    if getattr(args, "batch_size", None):
        cfg.batch_size = args.batch_size
    if getattr(args, "token", None):
        cfg.token = args.token
    return cfg


def _load_names_or_exit(path: str) -> list[str]:
    try:
        names, skipped = load_names(path)
    except FileNotFoundError:
        print(f"名单文件不存在: {path}", file=sys.stderr)
        raise SystemExit(2)
    for s in skipped:
        print(f"  跳过: {s}")
    if not names:
        print(f"名单 {path} 中没有合法 ID（规则：3-16 位字母/数字/下划线）", file=sys.stderr)
        raise SystemExit(2)
    return names


def _make_engine(cfg: Config, quiet: bool) -> tuple[Engine, Notifier, Store]:
    store = Store(cfg.db_path)
    notifier = Notifier(cfg.webhook_url, cfg.webhook_template, cfg.toast, out=None if not quiet else lambda _msg: None)
    client = httpx.Client(timeout=cfg.timeout, verify=ssl_context())
    provider = MojangProvider(client, cfg.hosts, timeout=cfg.timeout)
    engine = Engine(
        provider,
        store,
        notifier,
        rate_per_sec=cfg.rate_per_sec,
        batch_size=cfg.batch_size,
        ttl=cfg.ttl,
        backoff_base=cfg.backoff_base,
        backoff_max=cfg.backoff_max,
        max_consecutive_failures=cfg.max_consecutive_failures,
        failure_cooldown=cfg.failure_cooldown,
    )
    return engine, notifier, store


# ---- 子命令 -------------------------------------------------------------

def _cmd_check(args) -> int:
    cfg = _load_config(args)
    names = _load_names_or_exit(args.names)
    engine, notifier, store = _make_engine(cfg, args.quiet)
    try:
        stats = engine.run(names, force=args.force)
    finally:
        notifier.close()
    out_dir = export_results(store, cfg.output_dir)
    store.close()
    _print_summary(stats, out_dir)
    return 0


def _cmd_monitor(args) -> int:
    cfg = _load_config(args)
    if args.interval:
        cfg.interval = args.interval
    names = _load_names_or_exit(args.names)
    engine, notifier, store = _make_engine(cfg, args.quiet)
    try:
        run_monitor(engine, names, cfg.interval, lambda: export_results(store, cfg.output_dir), notifier.log)
    except KeyboardInterrupt:
        pass
    finally:
        notifier.close()
        store.close()
    print("监控已停止，进度已保存。")
    return 0


def _cmd_report(args) -> int:
    cfg = _load_config(args)
    store = Store(cfg.db_path)
    try:
        out_dir = export_results(store, cfg.output_dir)
        counts = store.count_by_status()
        print("状态汇总:", " · ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "（无记录）")
        available = [r.name for r in store.all() if r.status == Status.NOT_FOUND]
        print(f"当前可注册 {len(available)} 个，已写入 {out_dir / 'available.txt'}")
    finally:
        store.close()
    return 0


def _cmd_confirm(args) -> int:
    cfg = _load_config(args)
    token = cfg.token
    if not token:
        print("需要 Minecraft access_token：通过 --token 或配置文件的 token 项提供。", file=sys.stderr)
        return 2
    store = Store(cfg.db_path)
    candidates = [r.name for r in store.all() if r.status == Status.NOT_FOUND][: max(args.top, 0)]
    if not candidates:
        print("库中没有未注册候选可确认。")
        store.close()
        return 0
    print(f"将用认证端点确认 {len(candidates)} 个候选（限制 20 次/5 分钟，请耐心等待）:")
    client = httpx.Client(timeout=15.0, verify=ssl_context())
    provider = MCAuthProvider(client, token)
    try:
        for name in candidates:
            result = provider.check(name)
            store.upsert(result)
            print(f"  {result.name}: {result.status.value}（{result.detail}）")
    finally:
        client.close()
        store.close()
    return 0


# ---- 导出与汇总 ---------------------------------------------------------

def export_results(store: Store, output_dir: str) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    records = store.all()

    available = [r.name for r in records if r.status == Status.NOT_FOUND]
    (out / "available.txt").write_text(
        "\n".join(available) + ("\n" if available else ""), encoding="utf-8"
    )

    with (out / "results.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "status", "uuid", "detail", "first_seen", "last_checked", "prev_status"])
        for r in records:
            writer.writerow(
                [r.name, r.status.value, r.uuid or "", r.detail, r.first_seen, r.last_checked,
                 r.prev_status.value if r.prev_status else ""]
            )
    return out


def _print_summary(stats, out_dir: Path) -> None:
    print(
        f"完成：探测 {stats.checked}（跳过 {stats.skipped}）· "
        f"可注册 {stats.available} · 占用 {stats.taken} · 失败 {stats.errors} · "
        f"退避累计 {stats.retry_wait:.0f}s"
    )
    print(f"可注册名单: {out_dir / 'available.txt'}  明细: {out_dir / 'results.csv'}")


def _safe_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
