"""双语消息目录：英文（默认）与简体中文。

仅收录运行时用户可见文案（CLI 输出、日志、事件、webhook 载荷、错误信息）；
模块 docstring 与代码注释面向开发者，不在此列。

语言选择优先级（见 cli._resolve_lang）：--lang 参数 > config 的 lang
（显式 en/zh）> detect_system_lang() 按系统语言自动推断（中文系统 → zh，
其余 → en）。config 的 lang 留空 "" 时同样走自动推断。

用法：t("key", **kwargs) 按当前语言取词并填空；缺键回退英文，仍缺则原样返回键名。
"""

from __future__ import annotations

import sys

LANGUAGES = ("en", "zh")
DEFAULT_LANG = "en"

_lang: str = DEFAULT_LANG


def detect_system_lang() -> str:
    """按操作系统语言推断界面语言：中文系统（含 zh_TW 等繁体区）→ 'zh'，其余 → 'en'。"""
    for candidate in _locale_candidates():
        if candidate.lower().startswith("zh"):
            return "zh"
    return "en"


def _locale_candidates() -> list[str]:
    """收集系统语言线索，按可信度排序：
    1. 用户默认 locale（Windows 即系统区域设置；POSIX 源自会话 LANG/LC_* 环境变量）
    2. Windows UI 语言（GetUserDefaultLCID，反映“显示语言”而非区域格式）
    """
    import locale as _locale

    candidates: list[str] = []
    try:
        raw = _locale.getdefaultlocale()
        if raw and raw[0]:
            candidates.append(raw[0])
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            lcid = ctypes.windll.kernel32.GetUserDefaultLCID()
            if lcid:
                name = _locale.windows_locale.get(lcid, "")
                if name:
                    candidates.append(name)
        except Exception:
            pass
    return [c for c in candidates if c]

_MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # ---- cli ----
        "cli.description": (
            "Minecraft ID availability checker and release monitor"
            " (compliant: list-driven, backoff on rate limits, no proxy rotation)"
        ),
        "cli.help_config": "Path to the TOML config file (auto-loads ./config.toml by default)",
        "cli.help_lang": "Output language: en or zh (default: follow the system language)",
        "cli.help_names": "Name list file, one ID per line",
        "cli.help_db": "SQLite path (overrides config)",
        "cli.help_output_dir": "Output directory (overrides config)",
        "cli.help_rate": "Request rate req/s (hard cap 1.5)",
        "cli.help_batch_size": "Names per batch request (<=10)",
        "cli.help_token": "Minecraft access_token (for confirm)",
        "cli.help_quiet": "Reduce console output",
        "cli.help_check": "Run a one-shot check of the name list",
        "cli.help_force": "Ignore the freshness window and force a re-check",
        "cli.help_monitor": "Continuously monitor the list for released/sniped IDs",
        "cli.help_interval": "Polling interval in seconds (default from config)",
        "cli.help_report": "Summarize and export current results",
        "cli.help_confirm": "Final confirmation of candidates via the authenticated endpoint (20 calls / 5 min)",
        "cli.help_top": "Confirm the top N unregistered candidates",
        "cli.interrupted": "\nInterrupted; progress is saved to SQLite in real time — rerun to resume.",
        "cli.names_file_missing": "Name list file not found: {path}",
        "cli.skip_prefix": "  Skipped: {reason}",
        "cli.no_valid_ids": "No valid IDs in {path} (rules: 3-16 chars of letters/digits/underscores)",
        "cli.monitor_stopped": "Monitoring stopped; progress saved.",
        "cli.status_summary": "Status summary:",
        "cli.no_records": "(no records)",
        "cli.report_available": "{n} currently registrable, written to {path}",
        "cli.token_required": "Minecraft access_token required: pass --token or set the token key in the config file.",
        "cli.no_candidates": "No unregistered candidates in the database to confirm.",
        "cli.confirming": "Confirming {n} candidates via the authenticated endpoint (limited to 20 calls / 5 min, please wait):",
        "cli.confirm_result": "  {name}: {status} ({detail})",
        "cli.summary_done": (
            "Done: checked {checked} (skipped {skipped}) · available {available} · taken {taken} ·"
            " errors {errors} · total backoff {wait}s"
        ),
        "cli.summary_paths": "Registrable list: {available_path}  Details: {results_path}",
        # ---- engine ----
        "engine.pending": "To check: {n} (skipped {m} recently checked)",
        "engine.progress": "Progress {done}/{total} · available {a} · taken {t} · errors {e}",
        "engine.rate_limited_retry": "Rate limited; backing off and retrying (attempt {attempt})",
        "engine.breaker_cooling": (
            "Consecutive failures tripped the circuit breaker; cooling down before continuing"
            " (policy: wait for recovery, never switch IPs)"
        ),
        "engine.request_failed_retry": "Request failed: {exc}; backing off and retrying (attempt {attempt})",
        "engine.batch_error": "{n} consecutive attempts failed; marking {m} names in this batch as ERROR",
        "engine.retries_exhausted": "retries exhausted",
        "engine.unknown_uuid": "unknown",
        # 事件名（进入 webhook 载荷，故为完整词句）
        "engine.event_found": "Registrable ID found",
        "engine.detail_found": "{name} is currently unregistered",
        "engine.event_released": "ID released",
        "engine.detail_released": "{name} has been released and is now registrable",
        "engine.event_sniped": "ID sniped",
        "engine.detail_sniped": "{name} has been registered (UUID: {uuid})",
        "engine.event_breaker": "Circuit breaker tripped",
        "engine.event_probe_failed": "Probe failed",
        "engine.detail_probe_failed": "A batch of {n} names failed repeatedly and was marked as ERROR",
        # ---- monitor ----
        "monitor.round_start": "—— Round {n} start ——",
        "monitor.round_done": (
            "—— Round {n} done: available {a} · taken {t} · errors {e} · total backoff {w}s ·"
            " next round in {i}s ——"
        ),
        # ---- names ----
        "names.invalid_format": "must be 3-16 chars of letters/digits/underscores",
        "names.skip_line": "line {lineno} '{line}': {reason}",
        "names.duplicate": "duplicate",
        # ---- notify ----
        "notify.webhook_http": "Webhook returned HTTP {code}",
        "notify.webhook_failed": "Webhook send failed: {err}",
        # ---- providers/mojang ----
        "mojang.unsupported_hosts": "Unsupported hosts: {hosts}; valid: {valid}",
        "mojang.network_error": "{host}: network error {err}",
        "mojang.rate_limited": "{host} returned 429",
        "mojang.no_host": "no reachable host",
        "mojang.bulk_parse_failed": "Failed to parse bulk response: {err}",
        "mojang.single_parse_failed": "Failed to parse single-lookup response: {err}",
        # ---- providers/mcservices_auth ----
        "auth.token_required": "Minecraft access_token required (the token key in the config file)",
        "auth.token_invalid": "token is invalid or expired; update the token in your config",
        "auth.http_error": "Authenticated endpoint returned HTTP {code}",
        "auth.unknown_status": "Authenticated endpoint returned unknown status: {text}",
        "auth.detail_available": "Confirmed via authenticated endpoint: registrable",
        "auth.detail_duplicate": "Confirmed via authenticated endpoint: taken",
        "auth.detail_not_allowed": "Confirmed via authenticated endpoint: reserved name",
        # ---- ratelimit ----
        "ratelimit.rate_positive": "rate must be positive",
        # ---- config ----
        "config.unknown_keys": "Unknown config keys: {keys}",
        "config.invalid_lang": "Invalid lang '{lang}'; supported: en, zh, or empty for auto-detection",
    },
    "zh": {
        # ---- cli ----
        "cli.description": "Minecraft ID 可用性探测与释放监控（合规版：名单驱动、限频退避、无代理轮换）",
        "cli.help_config": "TOML 配置文件路径（默认自动加载 ./config.toml）",
        "cli.help_lang": "输出语言：en 或 zh（默认跟随系统语言）",
        "cli.help_names": "名单文件，一行一个 ID",
        "cli.help_db": "SQLite 路径（覆盖配置）",
        "cli.help_output_dir": "输出目录（覆盖配置）",
        "cli.help_rate": "请求速率 req/s（硬上限 1.5）",
        "cli.help_batch_size": "批量端点单次名字数（≤10）",
        "cli.help_token": "Minecraft access_token（confirm 用）",
        "cli.help_quiet": "减少控制台输出",
        "cli.help_check": "一次性探测名单",
        "cli.help_force": "忽略结果新鲜期，强制重查",
        "cli.help_monitor": "持续监控名单，检测 ID 释放/被抢注",
        "cli.help_interval": "轮询间隔秒数（默认取配置）",
        "cli.help_report": "汇总并导出当前结果",
        "cli.help_confirm": "用认证端点对候选做最终确认（20 次/5 分钟）",
        "cli.help_top": "确认前 N 个未注册候选",
        "cli.interrupted": "\n已中断；进度实时保存在 SQLite 中，可直接重跑续扫。",
        "cli.names_file_missing": "名单文件不存在: {path}",
        "cli.skip_prefix": "  跳过: {reason}",
        "cli.no_valid_ids": "名单 {path} 中没有合法 ID（规则：3-16 位字母/数字/下划线）",
        "cli.monitor_stopped": "监控已停止，进度已保存。",
        "cli.status_summary": "状态汇总:",
        "cli.no_records": "（无记录）",
        "cli.report_available": "当前可注册 {n} 个，已写入 {path}",
        "cli.token_required": "需要 Minecraft access_token：通过 --token 或配置文件的 token 项提供。",
        "cli.no_candidates": "库中没有未注册候选可确认。",
        "cli.confirming": "将用认证端点确认 {n} 个候选（限制 20 次/5 分钟，请耐心等待）:",
        "cli.confirm_result": "  {name}: {status}（{detail}）",
        "cli.summary_done": (
            "完成：探测 {checked}（跳过 {skipped}）· 可注册 {available} · 占用 {taken} ·"
            " 失败 {errors} · 退避累计 {wait}s"
        ),
        "cli.summary_paths": "可注册名单: {available_path}  明细: {results_path}",
        # ---- engine ----
        "engine.pending": "待探测 {n} 个（跳过近期已查 {m} 个）",
        "engine.progress": "进度 {done}/{total} · 可注册 {a} · 占用 {t} · 失败 {e}",
        "engine.rate_limited_retry": "触发限频，退避后重试（第 {attempt} 次）",
        "engine.breaker_cooling": "连续失败触发熔断，冷却后继续（策略：等待恢复，不切换 IP）",
        "engine.request_failed_retry": "请求失败: {exc}，退避后重试（第 {attempt} 次）",
        "engine.batch_error": "连续 {n} 次尝试失败，本批 {m} 个名字记为 ERROR",
        "engine.retries_exhausted": "重试耗尽",
        "engine.unknown_uuid": "未知",
        # 事件名（进入 webhook 载荷，故为完整词句）
        "engine.event_found": "发现可注册 ID",
        "engine.detail_found": "{name} 当前未被占用",
        "engine.event_released": "ID 释放",
        "engine.detail_released": "{name} 已被释放，现在可以注册",
        "engine.event_sniped": "ID 被抢注",
        "engine.detail_sniped": "{name} 已被注册（UUID: {uuid}）",
        "engine.event_breaker": "熔断",
        "engine.event_probe_failed": "探测失败",
        "engine.detail_probe_failed": "一批 {n} 个名字连续失败，已记为 ERROR",
        # ---- monitor ----
        "monitor.round_start": "—— 第 {n} 轮探测开始 ——",
        "monitor.round_done": (
            "—— 第 {n} 轮完成：可注册 {a} · 占用 {t} · 失败 {e} · 退避累计 {w}s，下一轮 {i}s 后 ——"
        ),
        # ---- names ----
        "names.invalid_format": "需为 3-16 位字母/数字/下划线",
        "names.skip_line": "第{lineno}行 '{line}': {reason}",
        "names.duplicate": "重复",
        # ---- notify ----
        "notify.webhook_http": "Webhook 返回 HTTP {code}",
        "notify.webhook_failed": "Webhook 发送失败: {err}",
        # ---- providers/mojang ----
        "mojang.unsupported_hosts": "不支持的主机: {hosts}，可选: {valid}",
        "mojang.network_error": "{host}: 网络错误 {err}",
        "mojang.rate_limited": "{host} 返回 429",
        "mojang.no_host": "无可用主机",
        "mojang.bulk_parse_failed": "批量响应解析失败: {err}",
        "mojang.single_parse_failed": "单查响应解析失败: {err}",
        # ---- providers/mcservices_auth ----
        "auth.token_required": "需要 Minecraft access_token（config 的 token 项）",
        "auth.token_invalid": "token 无效或已过期，请更新配置中的 token",
        "auth.http_error": "认证端点返回 HTTP {code}",
        "auth.unknown_status": "认证端点返回未知状态: {text}",
        "auth.detail_available": "认证端点确认：可注册",
        "auth.detail_duplicate": "认证端点确认：已占用",
        "auth.detail_not_allowed": "认证端点确认：保留名",
        # ---- ratelimit ----
        "ratelimit.rate_positive": "rate 必须为正数",
        # ---- config ----
        "config.unknown_keys": "配置中存在未知项: {keys}",
        "config.invalid_lang": "无效的 lang '{lang}'，支持: en、zh 或留空自动检测",
    },
}


def set_lang(lang: str) -> None:
    """设置当前语言；非法值直接抛错（CLI 层已用 choices 前置拦截）。"""
    global _lang
    if lang not in LANGUAGES:
        raise ValueError(f"unknown language: {lang!r}; supported: {', '.join(LANGUAGES)}")
    _lang = lang


def get_lang() -> str:
    return _lang


def t(key: str, **kwargs: object) -> str:
    """取当前语言的文案并填空；缺键回退英文，仍缺则返回键名便于暴露问题。"""
    template = _MESSAGES[_lang].get(key) or _MESSAGES[DEFAULT_LANG].get(key)
    if template is None:
        return key
    return template.format(**kwargs)
