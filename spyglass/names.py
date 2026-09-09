"""名单加载与校验。

Minecraft 用户名规则：3-16 个字符，仅限字母、数字、下划线。
"""

from __future__ import annotations

import re

NAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")


def validate_name(name: str) -> str | None:
    """返回错误原因；合法时返回 None。"""
    if not NAME_RE.match(name):
        return "需为 3-16 位字母/数字/下划线"
    return None


def load_names(path: str) -> tuple[list[str], list[str]]:
    """读取名单文件，返回 (合法名单, 跳过原因列表)。

    大小写不敏感去重（查询结果与大小写无关），保留首次出现的原始写法。
    """
    names: list[str] = []
    seen: set[str] = set()
    skipped: list[str] = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            reason = validate_name(line)
            if reason:
                skipped.append(f"第{lineno}行 '{line}': {reason}")
                continue
            if line.lower() in seen:
                skipped.append(f"第{lineno}行 '{line}': 重复")
                continue
            seen.add(line.lower())
            names.append(line)
    return names, skipped
