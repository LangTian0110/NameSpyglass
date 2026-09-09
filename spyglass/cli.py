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

from . import i18n
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
    # 优先级：--lang 参数 > config.toml 显式 lang > 系统语言自动检测
    i18n.set_lang(_resolve_lang(argv))
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print(i18n.t("cli.interrupted"))
        return 130


# ---- 参数 ---------------------------------------------------------------

def _resolve_lang(argv: list[str] | None) -> str:
    """在构建 parser 前确定语言，保证 --help 也是本地化的。"""
    raw = list(sys.argv[1:] if argv is None else argv)
    # 1) --lang 显式参数（非法值交给 argparse 的 choices 报错）
    it = iter(raw)
    for tok in it:
        if tok == "--lang":
            try:
                value = next(it).strip().lower()
            except StopIteration:
                value = ""
            if value in i18n.LANGUAGES:
                return value
        elif tok.startswith("--lang="):
            value = tok.split("=", 1)[1].strip().lower()
            if value in i18n.LANGUAGES:
                return value
    # 2) config.toml 显式 lang（空串 "" 表示自动，交给第 3 步）
    cfg_path = _config_path_from_argv(raw)
    if cfg_path is None and Path("config.toml").is_file():
        cfg_path = "config.toml"
    if cfg_path and Path(cfg_path).is_file():
        try:
            cfg_lang = Config.load(cfg_path).lang.strip().lower()
            if cfg_lang in i18n.LANGUAGES:
                return cfg_lang
        except Exception:
            pass
    # 3) 跟随系统语言
    return i18n.detect_system_lang()


def _config_path_from_argv(argv: list[str]) -> str | None:
    it = iter(argv)
    for tok in it:
        if tok == "--config":
            try:
                return next(it)
            except StopIteration:
                return None
        if tok.startswith("--config="):
            return tok.split("=", 1)[1]
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spyglass",
        description=i18n.t("cli.description"),
    )
    parser.add_argument("--config", default=None, help=i18n.t("cli.help_config"))
    parser.add_argument("--lang", choices=list(i18n.LANGUAGES), default=None, help=i18n.t("cli.help_lang"))
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--names", default="names.txt", help=i18n.t("cli.help_names"))
        sp.add_argument("--db", default=None, help=i18n.t("cli.help_db"))
        sp.add_argument("--output-dir", default=None, help=i18n.t("cli.help_output_dir"))
        sp.add_argument("--rate", type=float, default=None, help=i18n.t("cli.help_rate"))
        sp.add_argument("--batch-size", type=int, default=None, help=i18n.t("cli.help_batch_size"))
        sp.add_argument("--token", default=None, help=i18n.t("cli.help_token"))
        sp.add_argument("--quiet", action="store_true", help=i18n.t("cli.help_quiet"))

    sp_check = sub.add_parser("check", help=i18n.t("cli.help_check"))
    add_common(sp_check)
    sp_check.add_argument("--force", action="store_true", help=i18n.t("cli.help_force"))
    sp_check.set_defaults(func=_cmd_check)

    sp_monitor = sub.add_parser("monitor", help=i18n.t("cli.help_monitor"))
    add_common(sp_monitor)
    sp_monitor.add_argument("--interval", type=int, default=None, help=i18n.t("cli.help_interval"))
    sp_monitor.set_defaults(func=_cmd_monitor)

    sp_report = sub.add_parser("report", help=i18n.t("cli.help_report"))
    sp_report.add_argument("--db", default=None)
    sp_report.add_argument("--output-dir", default=None)
    sp_report.set_defaults(func=_cmd_report)

    sp_confirm = sub.add_parser("confirm", help=i18n.t("cli.help_confirm"))
    sp_confirm.add_argument("--db", default=None)
    sp_confirm.add_argument("--top", type=int, default=5, help=i18n.t("cli.help_top"))
    sp_confirm.add_argument("--token", default=None, help=i18n.t("cli.help_token"))
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
    # 语言已在 main() 中按 “--lang > config > 系统检测” 解析完成，此处不再改动
    return cfg


def _load_names_or_exit(path: str) -> list[str]:
    try:
        names, skipped = load_names(path)
    except FileNotFoundError:
        print(i18n.t("cli.names_file_missing", path=path), file=sys.stderr)
        raise SystemExit(2)
    for s in skipped:
        print(i18n.t("cli.skip_prefix", reason=s))
    if not names:
        print(i18n.t("cli.no_valid_ids", path=path), file=sys.stderr)
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
    print(i18n.t("cli.monitor_stopped"))
    return 0


def _cmd_report(args) -> int:
    cfg = _load_config(args)
    store = Store(cfg.db_path)
    try:
        out_dir = export_results(store, cfg.output_dir)
        counts = store.count_by_status()
        print(i18n.t("cli.status_summary"), " · ".join(f"{k}={v}" for k, v in sorted(counts.items())) or i18n.t("cli.no_records"))
        available = [r.name for r in store.all() if r.status == Status.NOT_FOUND]
        print(i18n.t("cli.report_available", n=len(available), path=out_dir / "available.txt"))
    finally:
        store.close()
    return 0


def _cmd_confirm(args) -> int:
    cfg = _load_config(args)
    token = cfg.token
    if not token:
        print(i18n.t("cli.token_required"), file=sys.stderr)
        return 2
    store = Store(cfg.db_path)
    candidates = [r.name for r in store.all() if r.status == Status.NOT_FOUND][: max(args.top, 0)]
    if not candidates:
        print(i18n.t("cli.no_candidates"))
        store.close()
        return 0
    print(i18n.t("cli.confirming", n=len(candidates)))
    client = httpx.Client(timeout=15.0, verify=ssl_context())
    provider = MCAuthProvider(client, token)
    try:
        for name in candidates:
            result = provider.check(name)
            store.upsert(result)
            print(i18n.t("cli.confirm_result", name=result.name, status=result.status.value, detail=result.detail))
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
        i18n.t(
            "cli.summary_done",
            checked=stats.checked,
            skipped=stats.skipped,
            available=stats.available,
            taken=stats.taken,
            errors=stats.errors,
            wait=f"{stats.retry_wait:.0f}",
        )
    )
    print(i18n.t("cli.summary_paths", available_path=out_dir / "available.txt", results_path=out_dir / "results.csv"))


def _safe_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
