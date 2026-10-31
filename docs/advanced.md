# 进阶设置

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
