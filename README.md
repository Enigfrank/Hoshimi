# Hoshimi Server

Hoshimi（星见）是用 Go 编写的非官方游戏模拟服务端，适合本地体验和熟人测试。

第一次使用，按下面 **1 → 2 → 3 → 4 → 5** 做。每次只做一步。

| 你想做什么 | 点这里 |
|---|---|
| 第一次玩 | [首次使用](#首次使用) |
| 再次开服 | [以后怎么启动](#以后怎么启动) |
| 回官服 | [切回官服](#切回官服) |
| 加角色或货币 | [GM 指令](#gm-指令) |
| 连朋友的服 | [连接朋友的服务器](#连接朋友的服务器) |
| 处理报错 | [常见问题](#常见问题) |

## 首次使用

### 1. 在 GitHub 下载

在本项目的 GitHub 页面：

 下载 **`Hoshimi-windows-amd64.zip`**。


请先解压，再使用。下文用 `E:\Hoshimi` 举例，你可以换成自己的文件夹。

<details>
<summary>GitHub 还没有发布压缩包？点击这里自己构建</summary>

1. 回到 GitHub 页面顶部，点击绿色 **Code** → **Download ZIP**。
2. 解压，打开包含 `go.mod` 的文件夹。
3. 安装 [Go 1.25 或更新版本的 Windows 64 位版](https://go.dev/dl/) 和 [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)。
4. 在此文件夹打开 PowerShell 7，执行：

```powershell
pwsh -File .\scripts\build.ps1
```

如果 Go 没有加入 PATH，填写它的位置。例如 Go 安装在 `F:\Go`：

```powershell
pwsh -File .\scripts\build.ps1 -GoPath 'F:\Go\bin\go.exe'
```

**成功标志：** 出现“构建完成”和“分发压缩包”。

打开 `dist` 文件夹，解压里面的 `Hoshimi-windows-amd64.zip`，然后从下面第 2 步继续。

构建工具仅用于生成 EXE。运行 EXE 时不需要安装 Go。

</details>

### 2. 准备好客户端和 PowerShell 7

需要这两样：

- Windows 64 位 PC 游戏客户端。用官方启动器下载完整资源。
- [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)。

找到游戏文件夹，里面应有 **`AetherGazer.exe`**。记下这个文件夹的完整路径。

打开 **PowerShell 7**，执行：

```powershell
$PSVersionTable.PSVersion
```

**成功标志：** 主版本号是 `7`。后面所有命令都在 PowerShell 7 中执行。

### 3. 准备运行文件

先退出游戏。下面两行，**只改引号里的路径**：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe prepare --client-dir 'D:\Games\AetherGazer'
```

- 第一行：包含 `hoshimi.exe` 的文件夹。
- 第二行：包含 `AetherGazer.exe` 的游戏文件夹。

等待完成。

**成功标志：** 出现“准备完成”，EXE 旁边生成 `runtime` 文件夹和 `config.json`。

`runtime/` 保存本机提取的脚本、协议表、配置表和 Lua 动态库

正常情况下只准备一次。游戏更新后，再执行这一步。

### 4. 启动服务端

在刚才的窗口执行：

```powershell
.\hoshimi.exe
```

**成功标志：** 出现“`Hoshimi 服务已启动`”。

**保持这个窗口开着。** 关闭窗口会停止服务端。

### 5. 切换客户端，进入游戏

确认游戏已退出。**另开一个 PowerShell 7 窗口**，执行：

```powershell
Set-Location 'E:\Hoshimi'
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
```

路径与第 3 步相同。首次切换需要可正常连接官服的客户端，脚本会保存恢复备份。

**成功标志：** 出现“已切换：本地服”。

然后：

1. 直接打开游戏文件夹中的 `AetherGazer.exe`。
2. 选择 **密码登录**。
3. 在“手机号”输入框填写你想用的**私服账号名**。
4. 输入密码，登录。

**账号不存在会自动注册。已有账号需要密码正确。** 请为私服单独设置密码。

普通新号从一级朝约开始，初始体力为 100，货币和材料为零。跳过操作引导，剧情入口全部解锁，默认零星。

想体验满配，用 `Developer` 账号。第一次登录时输入的密码会成为这个账号的密码。

登录由私服验证，缺少的游戏资源默认从官方 HTTPS CDN 下载

## 以后怎么启动

打开 PowerShell 7，执行：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe
```

看到“服务已启动”后，直接打开游戏。客户端仍处于本地服时，不用重复切换。

**停止服务：** 在服务端窗口按 `Ctrl+C`。

客户端路径会保存在 `config.json` 中，下次无需再填写。

## 切回官服

先退出游戏，再执行：

```powershell
Set-Location 'E:\Hoshimi'
pwsh -File .\scripts\switch-client.ps1 -Mode Official -ClientDir 'D:\Games\AetherGazer'
```

看到“已切换：官服”后，用**官方启动器**打开游戏。

**保留 `data/client-switch/`。** 这里保存切换备份和两套登录缓存。

忘了当前连哪边？把命令中的 `Official` 改成 `Status`。

## GM 指令

在游戏的**世界聊天**中发送指令。成功后会收到 `GM系统` 的回复。

解锁所有满配角色、永久皮肤、场景和额外视角：

```text
/unlock character
```

| 发送这条指令 | 效果 |
|---|---|
| `/gold 99999` | 金币设为 99999 |
| `/diamond 99999` | 移转之辉设为 99999 |
| `/flower 99999` | PC/安卓移转之花设为 99999，清零 iOS 与免费余额 |
| `/stamina 240` | 体力设为 240 |
| `/level 85` | 玩家等级设为 85，支持 1–100 |
| `/give 36 100` | 增加 100 共鸣辉芒 |
| `/help` | 查看指令和别名 |

`give` 是**增加**数量；余额指令是**设置**数量。数据会保存。

服务端运行时，在服务器电脑的浏览器打开 **http://127.0.0.1:8080/gm/**。

后台可查账号、搜索物品、执行指令、发邮件和管理公告。页面已包含在 EXE 中。

后台只允许服务器本机访问。游戏聊天中的 GM 指令对所有登录玩家开放，适合熟人测试。

## 连接朋友的服务器

**如果你只是玩家，不需要启动服务端或准备 `runtime`。**

准备：同版本客户端、PowerShell 7、Hoshimi 的 `scripts/` 文件夹，以及 [GOST v3 Windows 版](https://github.com/go-gost/gost/releases)。

### 1. 切换客户端

退出游戏，并停止自己电脑上的服务端，然后执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
```

### 2. 开启连接

下面第一行换成朋友给的服务器地址，第二行换成你的 GOST 路径：

```powershell
$serverAddress = '203.0.113.10'
& 'D:\Tools\gost.exe' -L "tcp://127.0.0.1:8080/${serverAddress}:8080" `
    -L "tcp://127.0.0.1:5001/${serverAddress}:5001" `
    -L "udp://127.0.0.1:5001/${serverAddress}:5001"
```

**保持此窗口开着。** 直接打开游戏，用自己的私服账号登录。

进度保存在朋友的服务器上。不同玩家使用不同账号名。

结束时退出游戏，在 GOST 窗口按 `Ctrl+C`。回官服时执行 [切回官服](#切回官服)。

<details>
<summary>我是服主，怎么部署到公网？</summary>

1. 在服务器电脑完成“首次使用”。服务器需要 Windows 64 位和同版本客户端。
2. 在云安全组、Windows 防火墙放行下面三个端口。家用网络还需路由器端口转发。

| 端口 | 用途 |
|---|---|
| TCP 8080 | 登录与服务器列表 |
| TCP 5001 | 游戏连接 |
| UDP 5001 | 战斗连接 |

3. 启动 `hoshimi.exe`，把服务器地址发给玩家。
4. 玩家按上面的“连接朋友的服务器”连接。

默认监听 `0.0.0.0`。游戏网关下发 `127.0.0.1`，玩家的 GOST 会将它转发到服务器。

登录使用 HTTP。推荐双方先加入同一个 VPN，并只向 VPN 网段开放端口。

玩家可以用下面命令检查本机转发是否工作：

```powershell
Test-NetConnection 127.0.0.1 -Port 8080
Test-NetConnection 127.0.0.1 -Port 5001
Invoke-RestMethod 'http://127.0.0.1:8080/skzy-activity/gateway/get?action=server&version=307&mixId=0'
```

TCP 检查成功不能证明 UDP 可用。进大厅后战斗卡住时，重点检查 UDP 5001。

</details>

## 保存进度与备份

**先停服，再复制 EXE 旁边的整个 `data/` 文件夹。** 恢复时也先停服。

| 位置 | 内容 |
|---|---|
| `data/users/` | 账号、密码摘要、令牌、角色、编队及进度 |
| `data/chat/` | 世界聊天与私聊 |
| `data/announcements.json`、`data/gm/` | 公告与后台操作记录 |
| `data/client-switch/` | 官私服切换备份及登录缓存 |
| `runtime/` | 本机准备的客户端运行文件 |
| `config.json` | 客户端路径与服务设置 |

已有 JSON 存档可在停服后放到 EXE 旁边的 `data/` 中，令牌和密码格式保持兼容。

`data/`、`runtime/` 和 `config.json` 不要上传 Git，也不要放进分发压缩包。

## 常见问题

找到你遇到的那一项，只处理这一项。

| 提示或现象 | 下一步 |
|---|---|
| 找不到 `hoshimi.exe` | 先解压发布版；下载的是 Code ZIP 时，用第 1 步里的构建教程 |
| 找不到 `go` | 运行 EXE 不需要 Go；构建时安装 Go 或给构建脚本传 `-GoPath` |
| 缺少运行元数据、配置或协议表 | 回到第 3 步执行 `prepare` |
| 运行文件与客户端版本不一致 | 停服，更新客户端，然后重新准备 |
| 缺少 `scripts64`、`tolua.dll` 或资源散列错误 | 检查游戏路径，用官方启动器补下载或修复资源 |
| 准备时“拒绝访问” | 停服，关闭使用 `runtime` 的程序，再重试；准备工具会重试短暂占用并在失败时保留文件 |
| 端口被占用 | 检查是否开了另一份服务端或 GOST，本机不能重复占用 8080 和 5001 |
| 切换时提示游戏未退出 | 先退出游戏，再切换 |
| 修改 hosts 需要管理员权限 | 用管理员身份打开 PowerShell 7，重新执行切换命令 |
| 提示系统代理已启用 | 关闭系统代理，再切换 |
| 缺少官服入口或 SDK 备份 | 先用官方启动器修复客户端，再切换 |
| 账号或密码错误 | 检查密码；已有账号不会因输入新密码而重新注册 |
| 能进大厅，战斗卡住 | 检查 UDP 5001 的转发与放行 |

### 游戏更新后

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

### 血条或鼠标视角异常

先退出游戏，再执行：

```powershell
pwsh -File .\scripts\repair-battle-controls.ps1
```

脚本会备份设置并显示位置。恢复时使用 `-Restore '备份文件完整路径'`。

## 功能与限制

已验证客户端：安装版 **307**，资源版 **321（v5.3.1）**。

支持注册登录、角色与配装、编队保存、商店、任务、签到、邮件、公告、剧情进度、单人战斗、角色和钥从探测、活动皮肤抽奖，以及 GM 管理。

- 普通新号货币为零；体验账号缺失的货币默认补到 `99999`。
- 补给商品统一售价 **1 移转之辉**，排期与价格由本地服务决定。
- 活动入口依赖客户端已有资源，排期可能与官服不同。
- 探测包含自选、基础概率、保底、重复奖励、辉芒和记录；未实现未公开的概率递增曲线。
- 部分复杂地图事件、活动玩法和联机尚未完成。
- 剧情入口解锁后，地图内的前置任务仍可能需要完成。
- 官方 CDN 上已下架的资源可能无法下载。

## 进阶设置

<details>
<summary>修改端口或文件位置</summary>

准备成功后，编辑 EXE 旁边的 `config.json`。格式参考 [config.example.json](config.example.json)。修改后重启服务端。

| 字段 | 默认值 / 用途 |
|---|---|
| `client_dir` | 本机游戏文件夹，由准备命令保存 |
| `runtime_dir` | `runtime`，相对路径以 EXE 所在目录为起点 |
| `host` | `0.0.0.0` |
| `http_port` | `8080` |
| `game_port` | `5001`，TCP 与 UDP 共用端口号 |
| `enable_https` | `false`，默认无需证书 |
| `resource_mode` | `direct` 直连官方 CDN，`proxy` 由服务端转发 |
| `resource_url` | 官方资源 CDN 地址 |

兼容 `AGL_CLIENT_DIR`、`AGL_HOST`、`AGL_HTTP_PORT`、`AGL_TCP_PORT`、`AGL_ENABLE_HTTPS`、`AGL_RESOURCE_MODE`、`AGL_RESOURCE_DOWNLOAD_URL` 和 `HOSHIMI_RUNTIME_DIR` 环境变量，**环境变量优先于 JSON**。

改 HTTP 端口后，切换脚本加 `-LocalPort 新端口`，GM 和玩家转发也要改。游戏端口变化时，TCP/UDP 放行与玩家转发一并修改。

`--home '其他文件夹'` 可指定配置与存档目录；`--runtime-dir '完整路径'` 可临时指定运行文件位置。默认无需这些参数。

</details>

<details>
<summary>开发验证与发布</summary>

只运行普通检查：

```powershell
go test ./...
go vet ./...
```

有完整客户端和已准备的运行文件时，运行协议集成测试：

```powershell
$env:HOSHIMI_TEST_CLIENT = 'D:\Games\AetherGazer'
$env:HOSHIMI_TEST_RUNTIME = 'E:\Hoshimi\runtime'
go test ./internal/server -v -count=1 -timeout 5m
```

测试使用临时账号目录和临时端口，不修改正式存档。覆盖登录、自选及保底、辉芒、皮肤奖池、编队、GM、商店、邮件、战斗结算与 UDP 重传。

构建分发包：

```powershell
pwsh -File .\scripts\build.ps1
```

脚本按固定清单打包 EXE、README、许可、配置示例和接入脚本，不包含本机 `runtime` 或 `data`。

提交前检查 `git status --short` 和 `git diff --cached --stat`。不要用 `git add -f` 加入被忽略的客户端文件。

</details>

## 代码与许可

仓库包含自写 Go 服务端

许可见 [LICENSE](LICENSE)，依赖许可见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。游戏、客户端、资源和商标属于各自权利人，本项目与官方无关联。
