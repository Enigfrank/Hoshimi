# 保存进度与备份

**先停服，再复制 EXE 旁边的整个 `data/` 文件夹。** 恢复时也先停服。

| 位置 | 内容 |
|---|---|
| `data/users/` | 账号、密码摘要、令牌、角色、编队及进度 |
| `data/chat/` | 世界聊天与私聊 |
| `data/announcements.json`、`data/gm/` | 公告与后台操作记录 |
| `data/client-switch/` | 官私服切换备份及登录缓存 |
| `runtime/` | 本机准备的客户端运行文件 |
| `resource-cache/manifests/`、`resource-cache/backups/` | 联网准备取得的官方清单，以及替换前的客户端主清单备份；不属于账号进度 |
| `config.json` | 客户端路径与服务设置 |
| `logs/` | 服务端运行日志，每次启动在 `logs` 文件夹内新建一个 `2026-10-23T20-14-05.log`，可随时删除 |

已有 JSON 存档可在停服后放到 EXE 旁边的 `data/` 中，令牌和密码格式保持兼容。

`data/`、`runtime/`、`resource-cache/`、`logs/` 和 `config.json` 不要上传 Git，也不要放进分发压缩包。

补齐的资源和 `.hoshimi-part` 续传片段保存在客户端资源目录，未放入服务端 `data/`。恢复旧主清单前先退出游戏并停服，确认资源版本；替换清单后需要重新执行 `prepare`。
