# 无陪伴服账号游玩教程

没有陪伴服账号、官服登录后无法下载游戏内资源时，可以先放入项目提供的资源清单，再使用 Hoshimi 的“无需官服登录补齐资源”功能准备运行文件，最后切换私服游玩。准备和下载资源均不需要登录官服。

本教程使用 Hoshimi **0.0.9 或更新版本**，按同一台电脑运行服务端和游戏说明。已有完整资源的用户可以直接按[首次使用](quickstart.md)操作。

## 1. 准备客户端和服务端

- 用官方启动器完成 Windows 64 位 PC 客户端的基础安装，不需要先进入官服。
- 从 [GitHub Releases](https://github.com/Enigfrank/Hoshimi/releases) 下载 `Hoshimi-windows-amd64-v0.0.9.zip` 或更新版本，解压到不含中文的目录，例如 `E:\Hoshimi`。
- 安装 [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)，后面的命令都在 PowerShell 7 中执行。
- 保持联网，并为客户端资源和服务端缓存预留磁盘空间。首次准备不会下载所有模型、语音和视频，游玩时还会继续下载。

下面使用的示例路径为：

| 用途 | 示例路径 |
|---|---|
| Hoshimi 服务端目录，包含 `hoshimi.exe` | `E:\Hoshimi` |
| 游戏客户端目录，包含 `AetherGazer.exe` | `E:\AetherGazerLauncher\AetherGazer` |

如果你的安装位置不同，请替换后续命令中的对应路径。基础客户端必须包含 `AetherGazer.exe` 和 `AetherGazer_Data\Plugins\x86_64\tolua.dll`；资源清单不能代替基础安装。客户端版本应与项目支持的资源版本匹配，参见[功能与限制](features.md)。

## 2. 下载并放入资源清单

先退出游戏、官方启动器，并停止正在运行的 Hoshimi。

1. 打开 [Hoshimi 的 GitHub 页面](https://github.com/Enigfrank/Hoshimi)，点击根目录的 [AssetHash_Info.bytes](https://github.com/Enigfrank/Hoshimi/blob/main/AssetHash_Info.bytes)。
2. 在文件页面点击 **Download raw file（下载原始文件）**，保存为 `AssetHash_Info.bytes`。不要将 GitHub 网页另存为文件，也不要给文件增加 `.txt` 后缀。
3. 打开客户端的以下目录：

   ```text
   E:\AetherGazerLauncher\AetherGazer\AetherGazer_Data\StreamingAssets\Windows
   ```

4. 如果目录中已有同名文件，先将原文件复制到其他文件夹备份，再将下载的 `AssetHash_Info.bytes` 放入此目录，替换同名文件。

完成后，文件的完整路径应为：

```text
E:\AetherGazerLauncher\AetherGazer\AetherGazer_Data\StreamingAssets\Windows\AssetHash_Info.bytes
```

这个文件列出资源名称、大小和散列，不包含全部游戏资源。放入清单后还必须执行下一步；不要手动修改清单版本来跳过版本检查，也不要将其用于不匹配的旧客户端。

## 3. 无需官服登录补齐资源

保持游戏和启动器关闭，在 PowerShell 7 中执行：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe prepare --download-missing --client-dir 'E:\AetherGazerLauncher\AetherGazer'
```

`--client-dir` 填写包含 `AetherGazer.exe` 的游戏目录，不是 `StreamingAssets\Windows`，也不是 Hoshimi 目录。

该命令读取你放入的清单，查询官方公开资源版本，下载并校验必要脚本、寻址表、音频配置、棋盘资源及语音散列清单，再提取本机运行文件。它不会读取官服账号的登录缓存，也不需要先取得陪伴服权限。

**完成标志：** 控制台出现“准备完成”，服务端目录生成 `runtime` 文件夹和 `config.json`。如果下载中断，可重新执行同一命令；已完成的资源会校验复用，可续传的片段会继续下载。出现错误时先处理错误，不要跳过准备直接开服。

已有配置时，确认 `config.json` 中的 `resource_mode` 为默认值 `"proxy"`，以使用服务端下载、校验和缓存流程。配置项说明见[进阶设置](advanced.md#无需官服登录补齐资源)。

## 4. 启动 Hoshimi 并切换私服

在服务端目录执行：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe
```

按控制台提示完成首次启动设置。看到“`Hoshimi 服务已启动`”后，保持窗口开启。

确认游戏仍未运行，另开一个 PowerShell 7 窗口执行：

```powershell
Set-Location 'E:\Hoshimi'
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'E:\AetherGazerLauncher\AetherGazer'
```

首次切换会备份原始官服入口和 SDK 文件，无需登录官服。若提示修改 hosts 需要管理员权限，使用管理员身份打开 PowerShell 7 后重跑切换命令。看到“已切换：本地服”后再进入游戏。

## 5. 登录私服，等待资源自动下载

直接运行游戏目录中的 `AetherGazer.exe`，选择 **密码登录**：

1. 在“手机号”输入框填写自己要使用的私服账号名。
2. 输入为私服单独设置的密码。
3. 登录；账号不存在时由本地服务端自动注册，已有账号需输入正确密码。

这里使用的是私服账号，无需官服账号或陪伴服权限。登录方式与新号说明见[首次使用](quickstart.md)。

游戏请求尚未准备好的场景、角色模型、音视频等资源时，Hoshimi 会从官方 HTTPS CDN 按需下载，完整接收并通过大小和 MD5 校验后，再提供给游戏。首次加载大文件可能需要等待，查看服务端窗口中的 `[资源接收]`、`[资源下载] 已校验` 等提示即可了解进度；不要在下载期间关闭服务端。

运行期间取得的资源副本保存在服务端 `resource-cache/files/`，与游戏写入的客户端资源文件分开，避免文件占用冲突。再次请求会复用已校验缓存，旧版留下的完整 `.hoshimi-part` 也可只读复制并校验复用。缓存和续传说明见[进阶设置](advanced.md#无需官服登录补齐资源)。

## 遇到问题时

| 现象 | 处理方法 |
|---|---|
| 下载不到 GitHub 上的清单 | 确认打开本项目仓库的文件页面；应下载原始 `AssetHash_Info.bytes`，不要保存网页或其他项目的文件 |
| 清单格式无效或缺少资源列表 | 核对文件名、放置目录，重新下载原始文件；不要将 HTML 页面当作 `.bytes` |
| 缺少 `AetherGazer.exe` 或 `tolua.dll` | 用官方启动器修复基础安装；仅复制清单不能补齐程序和动态库 |
| 资源应用版本不匹配，或运行文件与客户端版本不一致 | 停服并更新到匹配的基础客户端，再核对清单并执行准备命令；不要手动改版本号 |
| 缺少官服入口或 SDK 备份，无法切换 | 用官方启动器修复原始客户端文件，保持游戏关闭后重新切换；无需先登录官服 |
| 首次加载场景长时间等待 | 查看服务端下载进度；大文件完整下载、校验后才返回，网络中断时保留片段并重试 |
| CDN 返回 HTTP 403、404 或资源校验失败 | 保留完整错误日志，核对版本和网络后重试；官方已下架或未公开的文件可能无法下载 |
| 登录后仍显示官服相关提示 | 确认服务端已启动、切换脚本显示本地服，并直接运行游戏目录中的 `AetherGazer.exe` |

其他问题见[常见问题](troubleshooting.md)。需要反馈时，按[问题上报指南](reporting.md)提供版本、复现步骤和日志。游戏更新后，应退出游戏并停服，重新核对清单和客户端版本，再执行本教程的准备命令。
