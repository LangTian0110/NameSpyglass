# NameSpyglass

[English](README.md) | **简体中文**

名单驱动的 Minecraft ID（用户名）可用性探测与释放监控工具。

调用 Mojang 官方 API 实时检测名单内哪些 ID 未被注册，持续监控占用状态变化
（释放 / 被抢注），结果落盘并可通过 Webhook、Windows 桌面通知推送。

## 合规边界（设计前提）

本工具刻意**不做**以下事情，请勿自行改造去做：

- **不做全量键空间遍历**：只探测名单内的 ID（把你真正想要的填进 `names.txt`）。
  3-4 位字母数字全组合约 173 万个，规模化扫描违反 Minecraft 使用条款，
  且 Mojang 会因大量错误请求自动封禁账号。
- **不做代理轮换规避封锁**：被限频（429）或封锁（403）时，策略是
  **指数退避 + 熔断冷却，等待恢复**，绝不通过换 IP 绕过对方的反滥用机制。

合规的速率参考（来自 [Minecraft Wiki: Mojang API](https://minecraft.wiki/w/Mojang_API)）：
大部分端点每 IP **200 请求 / 2 分钟**（≈1.67 req/s）。本工具默认 0.5 req/s
（批量端点一次查 10 个名字，即默认约 300 名字/分钟），代码硬上限 1.5 req/s。

## 工作原理

| 端点 | 认证 | 判定 |
|---|---|---|
| `POST api.minecraftservices.com/minecraft/profile/lookup/bulk/byname` | 无 | 主力。body 为名字字符串数组（≤10 个），响应只含存在的玩家，缺席者=未注册 |
| `POST api.mojang.com/profiles/minecraft` | 无 | 同上语义的备用主机，自动容错切换 |
| `GET …/users/profiles/minecraft/{name}`、`GET …/minecraft/profile/lookup/name/{name}` | 无 | 单查回退：200=占用，204/404=未注册 |
| `GET api.minecraftservices.com/minecraft/profile/name/{name}/available` | Bearer token | 认证版最终确认（官方限 20 次/5 分钟/账号），能甄别保留名（NOT_ALLOWED） |

> 注意：404（未注册）不等于一定可注册——被官方保留的名字需用认证端点
> （`confirm` 子命令）才能甄别。Token 约 24 小时有效，过期后更新配置重跑。

## 安装

**Windows — 免装 Python：** 从 [Latest Release](https://github.com/LangTian0110/NameSpyglass/releases/latest)
下载单文件 `spyglass.exe`，直接跳到「使用」章节。

**源码安装**（任意平台）：

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt   # Windows；Linux/macOS 用 .venv/bin/pip
```

## 使用

```bash
# 准备名单（一行一个 ID，3-16 位字母/数字/下划线，# 为注释；示例见 names.example.txt）
cp names.example.txt my_names.txt   # 编辑成你想要的 ID

# 一次性探测：结果写入 output/available.txt 与 output/results.csv
python -m spyglass check --names my_names.txt

# 忽略 24h 新鲜期强制重查
python -m spyglass check --names my_names.txt --force

# 持续监控：每小时复查一轮，检测“释放/被抢注”并推送通知（Ctrl+C 安全中断）
python -m spyglass monitor --names my_names.txt --interval 3600

# 汇总当前结果（可随时单独执行）
python -m spyglass report

# 可选：用认证端点对前 N 个候选做最终确认（需配置 token）
python -m spyglass confirm --top 5 --token <MINECRAFT_ACCESS_TOKEN>
```

通用参数：`--config config.toml`（默认自动加载）、`--db`、`--output-dir`、
`--rate`、`--batch-size`、`--quiet`、`--lang en|zh`。

> 使用 Release 里的 `spyglass.exe`？把 `python -m spyglass` 换成 `spyglass`
> （或 exe 的完整路径）即可，其余完全一致。

进度实时写入 SQLite（`spyglass.db`），中断后直接重跑即可续扫，
24 小时内查过的名字自动跳过。

## 国际化

所有面向用户的文案（CLI 帮助、进度输出、事件名、webhook 载荷、错误信息）均支持
英文与简体中文两种语言。启动时自动跟随系统语言（中文系统显示中文，其余显示英文）；
也可用 `--lang en|zh` 临时覆盖，或在 `config.toml` 的 `lang` 项固定（留空 `""`
为自动检测）。webhook 载荷中的事件名随之本地化。

## 配置

复制 `config.example.toml` 为 `config.toml` 按需修改，常用项：

| 项 | 默认 | 说明 |
|---|---|---|
| `rate_per_sec` | 0.5 | 批量请求速率，硬上限 1.5（官方限频 200 req/2min） |
| `interval` | 3600 | monitor 轮询间隔（秒） |
| `ttl` | 86400 | 结果新鲜期（秒），期内跳过 |
| `webhook_url` | 空 | 通用 JSON Webhook |
| `toast` | true | Windows 桌面通知（需 winotify，缺失自动跳过） |
| `token` | 空 | Minecraft access_token（仅 confirm 用） |
| `lang` | 自动 | 输出语言：`en` 或 `zh`；留空/缺省时跟随系统语言 |

### 通知适配示例

`webhook_template` 中 `{event}` / `{detail}` 为占位符：

```toml
# Discord（默认模板即是）
webhook_template = '{"content": "[{event}] {detail}"}'

# 钉钉机器人
webhook_template = '{"msgtype":"text","text":{"content":"[{event}] {detail}"}}'

# Server酱（webhook_url 填 https://sctapi.ftqq.com/<SENDKEY>.send）
webhook_template = '{"title":"{event}","desp":"{detail}"}'
```

触发的事件（文案语言随 `lang` 配置）：
`发现可注册 ID`、`ID 释放`、`ID 被抢注`、`熔断`、`探测失败`。

## 限频与容错设计

- **令牌桶**控制稳态速率；**指数退避**（5s 起翻倍，封顶 10min，带抖动），
  429 时优先尊重 `Retry-After`。
- 连续 5 次失败进入**熔断**，冷却 30 分钟后半开重试——应对封锁的方式是等，
  不是换 IP。
- Mojang 已知会**偶发随机 403**（其自身配置问题）：单次重试 + 双主机
  （api.minecraftservices.com / api.mojang.com）自动切换。
- 批量端点不可用时自动回退逐名单查；TLS 使用操作系统证书库
  （[truststore](https://pypi.org/project/truststore/)），规避 certifi 包在
  部分网络环境下证书链不全的问题。

## 单文件 exe（打包与下载）

每个 GitHub Release 都附带预构建的单文件 `spyglass.exe`（约 12.9 MB）——
[点这里下载最新版](https://github.com/LangTian0110/NameSpyglass/releases/latest)。
放到任意目录即可运行，无需安装 Python。

也可以从源码自行打包：

```bash
# 运行构建脚本（产出 dist/spyglass.exe，约 12 MB）
build_exe.bat
```

使用方式与 Python 脚本版本完全一致：

```bash
dist/spyglass.exe check --names my_names.txt
dist/spyglass.exe --lang en check --names my_names.txt
dist/spyglass.exe monitor --names my_names.txt --interval 3600
dist/spyglass.exe report
```

注意事项：

- 这是单文件控制台构建：首次启动可能需要数秒完成解压到临时目录的过程。
- 工作路径（`names.txt`、`config.toml`、`spyglass.db`、`output/`）与脚本版行为相同——基于当前工作目录的相对路径。
- 本方案不使用 UPX 等压缩壳，以避免杀毒软件误报。
- Release 中的二进制未签名，首次运行 Windows SmartScreen 可能弹出警告
  （点「更多信息」→「仍要运行」即可）。

## 开发

```bash
.venv/Scripts/python -m pytest -q   # 46 个测试（单测全部 mock；exe 套件每次运行会先构建一次 .exe）
```

代码结构：`spyglass/` 下 `names`(名单校验) → `providers`(API 适配) →
`ratelimit`(令牌桶/退避/熔断) → `store`(SQLite) → `engine`(调度与事件) →
`monitor`/`notify`/`cli`。

## 许可证

[MIT](LICENSE)
