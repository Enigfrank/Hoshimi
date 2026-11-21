# 保存进度与备份

**先停服，再复制实际存档目录中的整个 `data/` 文件夹。** 默认位于 EXE 旁，指定 `--home` 时位于该参数指定的目录。恢复时也先停服。

| 位置 | 内容 |
|---|---|
| `data/users/` | 账号、密码摘要、令牌、角色、编队及进度 |
| `data/chat/` | 世界聊天与私聊 |
| `data/announcements.json`、`data/gm/` | 公告与后台操作记录 |
| `data/client-switch/` | 切换脚本默认的官私服备份及登录缓存，相对于发布包目录。指定 `-StateDir` 时备份实际目录 |
| `data/photos/`、`data/official-snapshots/` | 本地保存的照片和官服导入快照 |
| `runtime/` | 本机准备的客户端运行文件 |
| `resource-cache/manifests/`、`resource-cache/backups/` | 联网准备取得的官方清单，以及替换前的客户端主清单备份；不属于账号进度 |
| `resource-cache/files/` | 游戏运行期间按需取得的资源副本与续传片段；不属于账号进度，停服后可删除，后续可能重新下载 |
| `config.json` | 客户端路径与服务设置 |
| `logs/` | 默认日志目录，文件按启动时间命名。使用 `--log-dir` 时查看指定目录，使用 `--no-log` 时仅保留控制台输出 |

已有 JSON 存档可在停服后放到实际使用的 `data/` 中，令牌和密码格式保持兼容。若通过 `--runtime-dir` 或配置指定了其他运行文件目录，备份时一并保留。

`data/`、`runtime/`、`resource-cache/`、`logs/` 和 `config.json` 不要上传 Git，也不要放进分发压缩包。

准备阶段补齐的资源和对应 `.hoshimi-part` 续传片段保存在客户端资源目录；`prepare --download-missing --all` 下载的主资源位于 `StreamingAssets/Windows/`，全部语言语音位于 `StreamingAssets/Voice/<语言>/`。游戏运行期间按需取得的资源和续传片段保存在服务端 `resource-cache/files/`，均未放入服务端 `data/`。恢复旧主清单前先退出游戏并停服，确认资源版本；替换清单后需要重新执行 `prepare`。
