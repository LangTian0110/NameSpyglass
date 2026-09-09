"""通知：控制台（总是）+ 通用 Webhook + Windows 桌面 toast（可选）。

Webhook 采用 JSON 模板替换（{event} / {detail} 占位符），默认模板兼容 Discord；
钉钉/Server酱 等通过 config 的 webhook_template 适配。
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx

from .net import ssl_context

DEFAULT_TEMPLATE = '{"content": "[{event}] {detail}"}'


class Notifier:
    def __init__(
        self,
        webhook_url: str = "",
        webhook_template: str = DEFAULT_TEMPLATE,
        toast: bool = True,
        client: httpx.Client | None = None,
        out: Callable[[str], None] | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._template = webhook_template or DEFAULT_TEMPLATE
        self._toast = toast
        self._client = client or httpx.Client(timeout=10.0, verify=ssl_context())
        self._owns_client = client is None
        self._out = out or print

    def log(self, message: str) -> None:
        self._out(message)

    def event(self, event: str, detail: str) -> None:
        self._out(f"[{event}] {detail}")
        if self._webhook_url:
            self._send_webhook(event, detail)
        if self._toast:
            self._send_toast(event, detail)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    # ---- 内部 -----------------------------------------------------------

    def _send_webhook(self, event: str, detail: str) -> None:
        body_text = self._template.replace("{event}", event).replace("{detail}", detail)
        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError:
            payload = {"content": f"[{event}] {detail}"}
        try:
            resp = self._client.post(self._webhook_url, json=payload)
            if resp.status_code >= 400:
                self._out(f"Webhook 返回 HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            self._out(f"Webhook 发送失败: {exc.__class__.__name__}")

    @staticmethod
    def _send_toast(event: str, detail: str) -> None:
        try:
            from winotify import Notification

            Notification(app_id="NameSpyglass", title=event, msg=detail).show()
        except Exception:
            pass  # 未安装 winotify 或系统不支持时静默跳过
