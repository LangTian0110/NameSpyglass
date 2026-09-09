# NameSpyglass

**English** | [简体中文](README.zh-CN.md)

A list-driven availability checker and release monitor for Minecraft usernames (IDs).

It queries Mojang's official API to detect which IDs on your list are unregistered,
continuously watches for status changes (released / sniped), persists results to
disk, and pushes notifications via webhooks and Windows desktop toasts.

## Compliance Boundaries (Design Premises)

This tool deliberately does **not** do the following — please don't modify it to:

- **No full key-space enumeration**: it only probes the IDs on your list
  (put the ones you actually want into `names.txt`). All 3–4 character
  alphanumeric combinations total roughly 1.73 million; scanning at that scale
  violates the Minecraft EULA, and Mojang will auto-ban accounts that send
  large volumes of failing requests.
- **No proxy rotation to evade blocks**: when rate-limited (429) or blocked
  (403), the strategy is **exponential backoff + circuit-breaker cooldown and
  wait for recovery** — it never bypasses anti-abuse mechanisms by switching IPs.

Compliant rate reference ([Minecraft Wiki: Mojang API](https://minecraft.wiki/w/Mojang_API)):
most endpoints allow **200 requests / 2 minutes per IP** (≈1.67 req/s). This tool
defaults to 0.5 req/s (the batch endpoint checks 10 names per request, i.e. about
300 names/minute by default), with a hard cap of 1.5 req/s in code.

## How It Works

| Endpoint | Auth | Verdict |
|---|---|---|
| `POST api.minecraftservices.com/minecraft/profile/lookup/bulk/byname` | none | Primary. The body is a string array of names (≤10); the response only contains existing players, so absence = unregistered |
| `POST api.mojang.com/profiles/minecraft` | none | Backup host with the same semantics; automatic failover |
| `GET …/users/profiles/minecraft/{name}`, `GET …/minecraft/profile/lookup/name/{name}` | none | Single-lookup fallback: 200 = taken, 204/404 = unregistered |
| `GET api.minecraftservices.com/minecraft/profile/name/{name}/available` | Bearer token | Authenticated final confirmation (officially limited to 20 calls / 5 min / account); also identifies reserved names (NOT_ALLOWED) |

> Note: 404 (unregistered) does not guarantee registrable — officially reserved
> names can only be identified through the authenticated endpoint (the `confirm`
> subcommand). The token is valid for about 24 hours; update your config and
> rerun after it expires.

## Installation

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows; Linux/macOS use .venv/bin/pip
```

## Usage

```bash
# Prepare your list (one ID per line, 3-16 chars of letters/digits/underscores,
# # starts a comment; see names.example.txt for a sample)
cp names.example.txt my_names.txt   # edit it into the IDs you want

# One-shot check: results are written to output/available.txt and output/results.csv
python -m spyglass check --names my_names.txt

# Ignore the 24h freshness window and force a re-check
python -m spyglass check --names my_names.txt --force

# Continuous monitoring: re-check every hour, detect "released / sniped" and push
# notifications (Ctrl+C exits safely)
python -m spyglass monitor --names my_names.txt --interval 3600

# Summarize current results (can be run standalone at any time)
python -m spyglass report

# Optional: confirm the top N candidates via the authenticated endpoint (needs a token)
python -m spyglass confirm --top 5 --token <MINECRAFT_ACCESS_TOKEN>
```

Common options: `--config config.toml` (auto-loaded by default), `--db`,
`--output-dir`, `--rate`, `--batch-size`, `--quiet`, `--lang en|zh`.

Progress is written to SQLite (`spyglass.db`) in real time; if interrupted, just
rerun to resume — names checked within the last 24 hours are skipped automatically.

## Internationalization

All user-facing text (CLI help, progress output, event names, webhook payloads,
error messages) is bilingual — English and Simplified Chinese. On startup the
language follows the system automatically (a Chinese system shows Chinese,
anything else shows English). Override it with `--lang en|zh`, or pin it via the
`lang` key in `config.toml` (`""` means auto-detect). Event names in webhook
payloads follow the same language setting.

## Configuration

Copy `config.example.toml` to `config.toml` and adjust as needed. Common options:

| Key | Default | Description |
|---|---|---|
| `rate_per_sec` | 0.5 | Batch request rate, hard cap 1.5 (official limit 200 req/2min) |
| `interval` | 3600 | monitor polling interval (seconds) |
| `ttl` | 86400 | Result freshness window (seconds); entries within it are skipped |
| `webhook_url` | empty | Generic JSON webhook |
| `toast` | true | Windows desktop notification (requires winotify; skipped if missing) |
| `token` | empty | Minecraft access_token (only used by confirm) |
| `lang` | auto | Output language: `en` or `zh`; empty/omitted follows the system language |

### Webhook Template Examples

`{event}` / `{detail}` are placeholders in `webhook_template`:

```toml
# Discord (this is the default template)
webhook_template = '{"content": "[{event}] {detail}"}'

# DingTalk bot
webhook_template = '{"msgtype":"text","text":{"content":"[{event}] {detail}"}}'

# ServerChan (set webhook_url to https://sctapi.ftqq.com/<SENDKEY>.send)
webhook_template = '{"title":"{event}","desp":"{detail}"}'
```

Events emitted (the language follows the configured `lang`):
`Registrable ID found`, `ID released`, `ID sniped`, `Circuit breaker tripped`, `Probe failed`.

## Rate Limiting & Fault Tolerance

- A **token bucket** controls the steady-state rate; **exponential backoff**
  (starts at 5s, doubles, capped at 10min, with jitter) honors `Retry-After`
  first on 429.
- Five consecutive failures trip the **circuit breaker**, which cools down for
  30 minutes before a half-open retry — the answer to being blocked is to wait,
  not to switch IPs.
- Mojang is known to return **sporadic random 403s** (a problem on their side):
  a single retry + automatic switching between two hosts
  (api.minecraftservices.com / api.mojang.com).
- Falls back to per-name lookups automatically when the batch endpoint is
  unavailable; TLS uses the operating system certificate store
  ([truststore](https://pypi.org/project/truststore/)), avoiding certifi's
  incomplete certificate chain issues in some network environments.

## Development

```bash
.venv/Scripts/python -m pytest -q   # 27 unit tests, all mocked, no real API calls
```

Code structure: under `spyglass/`, `names` (list validation) → `providers`
(API adapters) → `ratelimit` (token bucket / backoff / circuit breaker) →
`store` (SQLite) → `engine` (scheduling & events) → `monitor`/`notify`/`cli`.

## License

[MIT](LICENSE)
