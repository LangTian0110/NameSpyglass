"""TLS 信任配置。

httpx 默认使用 certifi 证书包，某些网络环境下会因证书链不全而
CERTIFICATE_VERIFY_FAILED。优先改用操作系统证书库（Windows 证书库可自动
补齐中间证书），truststore 缺失时回退 Python 默认行为。
"""

from __future__ import annotations

import ssl


def ssl_context() -> ssl.SSLContext:
    try:
        import truststore

        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        return ssl.create_default_context()
