# 常见问题

找到你遇到的那一项，只处理这一项。

| 提示或现象 | 下一步 |
|---|---|
| 找不到 `hoshimi.exe` | 回到[首次使用第 1 步](quickstart.md#_1-在-github-下载)下载并解压 `Hoshimi-windows-amd64-v[版本号].zip`，再打开包含 EXE 的文件夹 |
| 缺少运行元数据、配置或协议表 | 回到[首次使用第 3 步](quickstart.md#_3-准备运行文件)执行 `prepare` |
| 运行文件与客户端版本不一致 | 停服，更新客户端，然后重新准备 |
| 缺少 `scripts64`、`tolua.dll` 或资源散列错误 | 检查游戏路径，用官方启动器补下载或修复资源 |
| 检测到中文路径，服务端已停止启动 | 按提示将对应目录移动到不含中文的路径，更新配置或启动参数，并从不含中文的工作目录启动 |
| 准备时“拒绝访问” | 停服，关闭使用 `runtime` 的程序，再重试；准备工具会重试短暂占用并在失败时保留文件 |
| 端口被占用 | 检查是否开了另一份服务端或 GOST，本机不能重复占用 8080 和 5001 |
| 切换时提示游戏未退出 | 先退出游戏，再切换 |
| 修改 hosts 需要管理员权限 | 用管理员身份打开 PowerShell 7，重新执行切换命令 |
| 提示系统代理已启用 | 关闭系统代理，再切换 |
| 缺少官服入口或 SDK 备份 | 先用官方启动器修复客户端，再切换 |
| 账号或密码错误 | 检查密码；已有账号不会因输入新密码而重新注册 |
| 能进大厅，战斗卡住 | 检查 UDP 5001 的转发与放行 |

仍无法解决时，请按 [问题上报指南](reporting.md) 提供版本、复现步骤和日志，再到 GitHub Issues 上报。

常见的参数错误、JSON 格式错误、端口占用、文件缺失和权限问题会附带中文处理建议及详细原因。路径或配置检查未通过时尚未创建日志，请复制控制台中的完整提示。

## 游戏更新后

先退出游戏并停止服务端，重新执行：

```powershell
.\hoshimi.exe prepare --client-dir 'D:\Games\AetherGazer'
```

准备成功后再开服。旧运行文件会保留为 `runtime-backup-*`，确认正常后可自行清理。

如果切换脚本提示 SDK 备份版本不匹配，先用官方启动器修复，再指定新的备份目录：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer' -StateDir 'D:\HoshimiBackups\v2'
```

以后切回官服也要使用同一个 `-StateDir`。

## 血条或鼠标视角异常

先退出游戏，再执行：

```powershell
pwsh -File .\scripts\repair-battle-controls.ps1
```

脚本会备份设置并显示位置。恢复时使用 `-Restore '备份文件完整路径'`。
