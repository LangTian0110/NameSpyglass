"""配置加载：TOML 文件 + 合理默认值。"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields

# 代码层硬上限：官方限频为每 IP 200 请求 / 2 分钟（≈1.67 req/s），
# 无论配置写成多少，速率都不会超过该值，防止误配出危险速率。
HARD_MAX_RATE = 1.5

DEFAULT_HOSTS = ["api.minecraftservices.com", "api.mojang.com"]


@dataclass
class Config:
    rate_per_sec: float = 0.5  # 批量请求速率上限（一次批量 = 1 次请求 = 最多 10 个名字）
    batch_size: int = 10  # 批量端点单次名字数，Mojang 上限 10
    interval: int = 3600  # monitor 模式轮询间隔（秒）
    timeout: float = 15.0  # 单次 HTTP 超时（秒）
    hosts: list[str] = field(default_factory=lambda: list(DEFAULT_HOSTS))
    db_path: str = "spyglass.db"
    output_dir: str = "output"
    ttl: int = 86400  # 结果新鲜期（秒），期内已查过的名字默认跳过
    webhook_url: str = ""
    webhook_template: str = '{"content": "[{event}] {detail}"}'
    toast: bool = True  # Windows 桌面通知（需 winotify，缺失时自动跳过）
    token: str = ""  # 可选 Minecraft access_token，仅 confirm 子命令使用
    # 退避与熔断
    backoff_base: float = 5.0
    backoff_max: float = 600.0
    max_consecutive_failures: int = 5
    failure_cooldown: float = 1800.0

    def __post_init__(self) -> None:
        self.rate_per_sec = min(max(float(self.rate_per_sec), 0.01), HARD_MAX_RATE)
        self.batch_size = min(max(int(self.batch_size), 1), 10)

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        if path is None:
            return cls()
        with open(path, "rb") as f:
            data = tomllib.load(f)
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"配置中存在未知项: {', '.join(sorted(unknown))}")
        return cls(**data)
