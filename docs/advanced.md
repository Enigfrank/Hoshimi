# 进阶设置

## 无需官服登录补齐资源

退出游戏并停止服务端后，在包含 `hoshimi.exe` 的目录执行：

```powershell
.\hoshimi.exe prepare --download-missing --client-dir 'D:\Games\AetherGazer'
```

需要通过官方启动器完成基础安装，并保留本机 `AssetHash_Info.bytes`，以确认资源协议版本。命令从官方公开版本接口取得带 MD5 的主清单，验证本机 `appVersion` 与官方 `matchedAppVersion` 一致；这些值不同于启动器安装包版本，不应手动修改来跳过检查。未携带官服 Cookie、令牌或 SDK 登录缓存。

准备阶段只补齐脚本、寻址表、Unity 清单、音频配置、服务端读取的棋盘资源及各语言语音散列清单。其余模型、音乐、语音和视频在默认 `resource_mode: "proxy"` 下按客户端请求下载。完整文件通过大小和 MD5 校验后才提供响应，因此首次请求大文件可能需要等待；已校验文件直接复用。`direct` 模式由客户端直连官方 CDN，不使用服务端的下载校验与缓存流程。

下载内容保存在客户端 `AetherGazer_Data/StreamingAssets/Windows/` 的散列目录。中断内容使用 `.hoshimi-part` 后缀，重试时核对续传范围；大小或 MD5 不符的内容不会启用。按 `Ctrl+C` 后，可重新执行同一命令继续。

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

仅 Go 编译版提供此功能。首次开服会说明收集范围、接收平台并询问同意；输入 `y` 开启，回车、其他输入或没有输入均保持关闭。结果保存在 `config.json` 的 `telemetry_enabled` 字段，旧配置缺少该字段时会询问一次。无法保存选择时，本次不开启统计。

| 字段 | 内容 |
|---|---|
| 服务端版本 | 构建时注入的版本；直接构建时为 `dev` |
| 系统版本 | Windows NT 主次版本，不含系统构建号、设备型号或硬件信息 |
| 运行时长 | 本次进程各报告区间的秒数 |
| 错误计数 | 开服失败、游戏 TCP、战斗 UDP、HTTP、延迟推送、公告及玩法周期同步的固定类别计数 |
| 临时标识 | 每次启动重新生成，仅关联本次运行的统计事件，不保存到磁盘 |

不上传游戏账号、UID、密码、登录令牌、存档、聊天、照片、完整日志、本机路径或设备标识。不创建 PostHog 人物档案，并在事件中请求禁用 IP 定位、将 IP 属性固定为占位值；第三方接收服务在网络连接层仍可接触来源 IP。数据发送到 PostHog 美国区域（`us.i.posthog.com`）。

持久关闭：停止服务，将现有 `config.json` 中的 `telemetry_enabled` 改为 `false`，再重新启动；不要用一行示例覆盖整个配置。手动设为 `true` 表示同意并重新开启。

仅本次关闭：

```powershell
.\hoshimi.exe --no-telemetry
```

有子命令时写为 `.\hoshimi.exe serve --no-telemetry`。该参数优先于保存的同意，不修改原选择；`--no-log` 只控制本机日志，与使用统计开关独立。`version`、`prepare` 和 `import-official` 不发送统计。

每次开服尝试发送 `hoshimi_started`；运行中每 30 分钟发送 `hoshimi_heartbeat`；正常退出或开服返回错误时尝试发送 `hoshimi_stopped`。`runtime_seconds` 是相邻报告之间的增量，累计运行时长时对后两个事件求和，不能将它当成进程累计时长。启动事件代表开服尝试，不代表一定成功进入游戏；失败可结合 `error_counts.serve_failed` 查看。

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
