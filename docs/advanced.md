# 进阶设置

## 无需官服登录补齐资源

没有陪伴服账号、需要先从 GitHub 下载资源清单时，按[无陪伴服账号游玩教程](no-companion-account.md)操作；该教程包含清单放置路径、准备命令和切服登录步骤。

退出游戏并停止服务端后，在包含 `hoshimi.exe` 的目录执行：

```powershell
.\hoshimi.exe prepare --download-missing --client-dir 'D:\Games\AetherGazer'
```

需要通过官方启动器完成基础安装，并保留本机 `AssetHash_Info.bytes`，以确认资源协议版本。命令从官方公开版本接口取得带 MD5 的主清单，验证本机 `appVersion` 与官方 `matchedAppVersion` 一致；这些值不同于启动器安装包版本，不应手动修改来跳过检查。未携带官服 Cookie、令牌或 SDK 登录缓存。

准备阶段只补齐脚本、寻址表、Unity 清单、音频配置、服务端读取的棋盘资源及各语言语音散列清单。其余模型、音乐、语音和视频在默认 `resource_mode: "proxy"` 下按客户端请求下载。完整文件通过大小和 MD5 校验后才提供响应，因此首次请求大文件可能需要等待；已校验文件直接复用。`direct` 模式由客户端直连官方 CDN，不使用服务端的下载校验与缓存流程。

准备阶段的必要资源保存在客户端 `AetherGazer_Data/StreamingAssets/Windows/` 的散列目录。游戏运行期间的按需资源保存在服务端 `resource-cache/files/` 的散列目录，响应始终读取独立缓存，避免与游戏写入客户端资源时争用同一文件。已有客户端完整资源或旧版留下的完整 `.hoshimi-part` 会只读复制到缓存，重新校验后复用，无需重复下载；未完成的旧版客户端片段保留原位，不迁移。

中断内容使用 `.hoshimi-part` 后缀，重试时核对续传范围；大小或 MD5 不符的内容不会启用。按 `Ctrl+C` 后，可重新执行同一命令继续。服务端缓存不属于账号进度，停服后可以删除；删除后可能需要重新下载。

原始官方主清单与语音包总清单保存在服务端 `resource-cache/manifests/`。需要替换客户端主清单时，旧文件先备份到 `resource-cache/backups/assethash_<旧文件MD5>.bytes`。同一资源版本下，已有且校验完整的本机 `scripts64` 补丁会保留，不会将补丁散列当作官方资源下载。

此功能依赖官方公开接口和 CDN 仍提供对应文件；不授予官服登录权限。缺少基础安装文件、版本不匹配或官方资源不可用时，按提示修复后重试。离线准备仍使用不带 `--download-missing` 的原命令。

## 誓约照片（仅同机）

客户端照片 SDK 固定使用 HTTPS。需要保存婚纱照时，在新版服务端目录手动执行：

```powershell
pwsh -File .\scripts\enable-photo-upload.ps1 -Mode Enable
```

脚本生成仅用于 `127.0.0.1` 的证书，将其信任到当前 Windows 用户的根证书库，并备份原配置、启用 `enable_https`。不会启动或重启服务。请自行启动新版服务、重新登录后测试拍照。游戏与服务端须在同一台电脑、同一 Windows 用户下运行；远程玩家不适用此配置。

已有 `cert.pem`、`key.pem` 或启用记录时脚本拒绝覆盖。HTTPS 端口需空闲（默认 `443`）；环境变量仍优先于配置。未启用 HTTPS 时上传配置会明确返回失败，不再下发缺少凭据的假成功响应。

照片保存在 `data/photos`，应与账号存档一起备份。证书有效期一年；过期后先恢复再重新启用。恢复命令如下，仅在配置和证书未被后续修改时逐字节还原，并删除该脚本添加的证书信任：

```powershell
pwsh -File .\scripts\enable-photo-upload.ps1 -Mode Disable
```

## 可选使用统计

仅 Go 编译版提供此功能。首次开服会说明收集范围、接收平台并询问同意；输入 `y` 开启，回车、其他输入或没有输入均保持关闭。结果保存在 `config.json` 的 `telemetry_enabled` 字段，本次授权范围保存在 `telemetry_consent`，当前值为 `umami-hwid-v1`。无法保存选择时，本次不开启统计。

旧配置缺少选择时会询问一次。曾同意旧版 PostHog 统计但没有当前授权范围的配置会重新询问，不会自动上传设备标识；此前设置为 `false` 的配置继续保持关闭。

| 字段 | 内容 |
|---|---|
| 设备标识 | SMBIOS Type 1 UUID 经项目命名空间和 SHA-256 派生的 HWID 哈希，作为 Umami `id`，不上传原始 UUID |
| 启动会话 | `session_started_at`，本次进程统计开始的 UTC 时间，用于区分同一设备的多次开服 |
| 环境 | `server_version`、`go_version`、`os`、`os_version`、`arch`、`cpu_threads`；系统版本含 Windows NT 主次版本和构建号 |
| 启动 | `startup_ms`；成功事件表示业务初始化和全部监听已完成，失败事件含固定 `failure_stage` |
| 运行时长 | `runtime_seconds`，相邻运行报告区间的秒数 |
| 进程资源 | `heap_alloc_mb`（Go 堆分配）、`process_working_set_mb`（进程驻留内存，读取失败时省略）、`goroutines`；MB 按 1024 × 1024 字节换算 |
| 错误计数 | 非零的 `error_serve_failed`、`error_game_tcp`、`error_battle_udp`、`error_http`、`error_delayed_push`、`error_activity_sync`，只含固定类别和次数 |

这属于可跨启动关联的设备使用统计，不是完全匿名统计。不上传原始硬件编号、游戏账号、UID、密码、登录令牌、存档、聊天、照片、完整日志、本机路径、计算机名或用户名。数据发送到 Umami Cloud（`cloud.umami.is/api/send`），请求使用固定主机名 `hoshimi.local`、路径 `/server` 和占位 IP `0.0.0.0`，不包含本机网络地址；第三方接收服务在网络连接层仍可接触来源 IP。

设备 UUID 缺失、为全零或全 `FF`、读取失败时，本次不发送统计，不改用随机标识。更换主板、虚拟机克隆或固件提供重复 UUID 会影响设备识别；它不能作为授权或准确人数依据。

持久关闭：停止服务，将现有 `config.json` 中的 `telemetry_enabled` 改为 `false`，再重新启动；不要用一行示例覆盖整个配置。需要重新开启时，将该字段改为 `true`；若 `telemetry_consent` 不是当前范围，启动时仍需明确同意。也可删除这两个字段，在下次启动时重新选择。

仅本次关闭：

```powershell
.\hoshimi.exe --no-telemetry
```

有子命令时写为 `.\hoshimi.exe serve --no-telemetry`。该参数优先于保存的同意，不修改原选择；`--no-log` 只控制本机日志，与使用统计开关独立。`version`、`prepare` 和 `import-official` 不发送统计。

业务初始化和全部监听完成后发送 `hoshimi_started`，包括环境字段和启动耗时；启动失败时改为发送 `hoshimi_start_failed`，失败阶段限定为 `business_init`、`http_listen`、`game_tcp_listen`、`battle_udp_listen`、`https_certificate`、`https_listen`，不上传错误原文或路径。

成功运行中每 6 小时发送 `hoshimi_heartbeat`；正常退出或服务返回错误时尝试发送 `hoshimi_stopped`。后两个事件仅包含启动会话、区间运行时长、进程资源和非零错误计数。环境不随心跳重复发送。`runtime_seconds` 是相邻报告之间的增量，累计运行时长时对心跳、停止及启动失败事件求和，不能当作进程累计时长；它包含启动准备所用时间。

Umami 按 `id` 关联设备，按 `session_started_at` 关联本次进程。面板访客或会话总数不等于独立设备数，设备数应按 Distinct ID 去重。统计不收集玩家在线人数、玩家账号或功能操作详情。

默认频率按 Umami Cloud Hobby 免费套餐设计。事件本身和每个自定义属性均消耗额度，设备规模或频繁重启仍可能耗尽套餐；固定 HWID 不会免除事件额度。此实现不使用查询 API 或后台管理密钥。

上报在后台完成，单次请求最多两秒，正常停服时最多等待两秒。发送失败直接丢弃，不重试、不在磁盘缓存，不影响开服或游戏；强制结束进程可能丢失最后一个报告区间。因此这些数据是使用统计估计，不作为准确在线人数或独立安装人数。

## 修改端口或文件位置

准备成功后，编辑 EXE 旁边的 `config.json`。格式参考同一文件夹中的 `config.example.json`。修改后重启服务端。

| 字段 | 默认值 / 用途 |
|---|---|
| `client_dir` | 本机游戏文件夹，由准备命令保存 |
| `runtime_dir` | `runtime`，相对路径以 EXE 所在目录为起点 |
| `host` | `0.0.0.0` |
| `http_port` | `8080` |
| `game_port` | `5001`，TCP 与 UDP 共用端口号 |
| `enable_https` | `false`，默认无需证书 |
| `resource_mode` | `proxy` 由服务端转发缺失资源，`direct` 直连官方 CDN |
| `resource_url` | 官方资源 CDN 地址 |

兼容 `AGL_CLIENT_DIR`、`AGL_HOST`、`AGL_HTTP_PORT`、`AGL_TCP_PORT`、`AGL_ENABLE_HTTPS`、`AGL_RESOURCE_MODE`、`AGL_RESOURCE_DOWNLOAD_URL` 和 `HOSHIMI_RUNTIME_DIR` 环境变量，**环境变量优先于 JSON**。

改 HTTP 端口后，切换脚本加 `-LocalPort 新端口`，GM 和玩家转发也要改。游戏端口变化时，TCP/UDP 放行与玩家转发一并修改。

`--home '其他文件夹'` 可指定配置与存档目录；`--runtime-dir '完整路径'` 可临时指定运行文件位置。默认无需这些参数。

日志可通过以下启动参数调整（不影响控制台输出）：

~~~powershell
.\hoshimi.exe --no-log
.\hoshimi.exe --log-dir 'E:\Hoshimi Logs'
~~~

`--no-log` 不创建或写入日志文件，包括协议兜底诊断的 JSONL 日志（仍保留本次进程内统计）；`--log-dir` 将控制台对应的运行日志文件直接写入指定目录，相对路径基于启动时的工作目录，默认仍为 EXE 旁的 `logs/`。两者同时指定时，`--no-log` 优先，不创建日志目录，也不会删除已有日志。使用子命令时将参数放在子命令之后，例如 `hoshimi.exe serve --no-log`。
