# Hoshimi Server

Hoshimi（星见）是用于本地体验和熟人测试的非官方游戏模拟服务端。

**第一次使用：从 GitHub 下载开始，按下面的 1 → 2 → 3 → 4 → 5 做。每次只做一步。**

已经装好了？直接看 [以后怎么启动](#以后怎么启动)。

| 你现在想做什么 | 点这里 |
|---|---|
| 第一次在自己电脑上玩 | [首次使用](#首次使用) |
| 再次打开私服 | [以后怎么启动](#以后怎么启动) |
| 切回官服 | [切回官服](#切回官服) |
| 加角色、皮肤或货币 | [GM 指令](#gm-指令) |
| 连朋友的服务器 | [连接朋友的服务器](#连接朋友的服务器) |
| 遇到报错 | [常见问题](#常见问题) |

## 首次使用

### 1. 从 GitHub 下载并解压

在你正在阅读这份 README 的 **GitHub 项目页面**操作：

1. 回到页面顶部，点击绿色的 **Code** 按钮。
2. 点击 **Download ZIP**，等待下载完成。
3. 打开电脑的“下载”文件夹，找到刚下载的 `.zip` 压缩包。
4. 右键压缩包，选择 **全部解压缩**，再打开解压后的文件夹。
5. 找到里面包含 `server.py` 的文件夹，将它放到你方便找到的位置。

**看到什么算成功：** 同一个文件夹里能看到 `server.py`、`README.md` 和 `scripts` 文件夹。

解压后可能多套一层文件夹，继续往里打开，直到看见 `server.py`。请先解压，再使用里面的文件。

下文用 `E:\Project\Hoshimi` 举例。你可以把包含 `server.py` 的文件夹命名为 `Hoshimi` 并放到这个位置，也可以使用其他位置；第 3 步填写实际路径即可。

### 2. 准备好这三样

- Windows 电脑。
- **PowerShell 7** 和 **64 位 Python 3.10 或更新版本**。
- 已通过官方启动器下载完整资源的 PC 游戏客户端。

不确定工具装好没有？打开 **PowerShell 7**，复制下面两行：

```powershell
$PSVersionTable.PSVersion
python --version
```

**看到什么算成功：** 第一项主版本是 `7`，第二项是 `Python 3.10` 或更新版本。

提示“找不到 python”？先安装 Python，安装时勾选 **Add python.exe to PATH**，再重新打开 PowerShell 7。

### 3. 填两个文件夹位置

在同一个 PowerShell 7 窗口中执行。

**只改引号里的路径。**

```powershell
Set-Location 'E:\Project\Hoshimi'
$env:AGL_CLIENT_DIR = 'D:\Games\AetherGazer'
```

- 第一行：Hoshimi 文件夹，里面应有 `server.py`。
- 第二行：游戏文件夹，里面应有 `AetherGazer.exe`。

**看到什么算成功：** 没有红色报错。接下来的步骤继续用这个窗口。

### 4. 安装并准备文件

复制这一段，等待执行完：

```powershell
python -m venv "$env:LOCALAPPDATA\Hoshimi\venv"
$pythonPath = Join-Path $env:LOCALAPPDATA 'Hoshimi\venv\Scripts\python.exe'
& $pythonPath -m pip install -r .\requirements-setup.txt
& $pythonPath -B .\prepare_runtime.py
```

**看到什么算成功：** 最后出现“准备完成”，下面列出角色、货币和补给数量。

准备工具会读取你电脑上的客户端，把服务端需要的文件放到单独的本机文件夹。正常情况下，这一步只需做一次；游戏更新后要重新准备。

**出现红色报错就先停在这一步，去看 [常见问题](#常见问题)。**

### 5. 启动私服，进入游戏

先启动服务端：

```powershell
& $pythonPath -B .\server.py
```

**看到什么算成功：** 出现“全部服务已就绪，等待连接”。保持这个窗口开着。

然后，**另开一个 PowerShell 7 窗口**。确认游戏已退出，执行：

```powershell
Set-Location 'E:\Project\Hoshimi'
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
```

路径填法与第 3 步相同。首次切换需要能正常连接官服的客户端，脚本会保存切回官服所需的备份。

**看到什么算成功：** 出现“已切换：本地服”。

最后：

1. 直接打开游戏文件夹里的 `AetherGazer.exe`。
2. 选择 **密码登录**。
3. 在“手机号”输入框填写你想用的**私服账号名**。
4. 输入密码，登录。

**账号不存在会自动注册；已有账号需要密码正确。** 请为私服单独设置密码。

普通新号从一级朝约开始，使用初始体力，货币和材料为零。操作引导已跳过，剧情入口全部解锁，默认零星；通关结果和领奖记录会保存。

想直接体验满配？使用 `Developer` 账号。第一次登录时输入的密码会成为这个账号的密码。

## 以后怎么启动

每次重新打开 PowerShell 7，复制下面四行。**改好前两行的路径。**

```powershell
Set-Location 'E:\Project\Hoshimi'
$env:AGL_CLIENT_DIR = 'D:\Games\AetherGazer'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Hoshimi\venv\Scripts\python.exe'
& $pythonPath -B .\server.py
```

看到“全部服务已就绪”后，直接打开游戏。客户端仍处于本地服时，不用重复切换。

**停止私服：** 在服务端窗口按 `Ctrl+C`。

## 切回官服

先退出游戏。在 Hoshimi 文件夹中打开 PowerShell 7，执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Official -ClientDir 'D:\Games\AetherGazer'
```

看到“已切换：官服”后，通过**官方启动器**打开游戏。

**请保留 `data/client-switch/` 文件夹。** 它保存切换备份和两套登录缓存。

忘了当前连哪边？执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Status -ClientDir 'D:\Games\AetherGazer'
```

## GM 指令

打开游戏的 **世界聊天**，输入指令并发送。成功后会收到 `GM系统` 的回复。

**想解锁全部角色、永久皮肤、场景和额外视角？发这一条：**

```text
/unlock character
```

角色会变成满配，数据会保存。

其他常用指令：

| 在聊天里发送 | 会发生什么 |
|---|---|
| `/gold 99999` | 把金币设为 99999 |
| `/diamond 99999` | 把移转之辉设为 99999 |
| `/flower 99999` | 把 PC/安卓移转之花设为 99999，并清零 iOS 与免费余额 |
| `/stamina 240` | 把体力设为 240 |
| `/level 85` | 把玩家等级设为 85，支持 1–100 |
| `/give 36 100` | 增加 100 共鸣辉芒 |
| `/help` | 查看全部指令和别名 |

`give` 是**增加**数量，其他余额指令是**设置**数量。指令只修改当前登录账号；也可以用 `$` 替代 `/`。

### 用网页管理

服务端运行时，在服务器电脑的浏览器打开：

**http://127.0.0.1:8080/gm/**

可以查账号、搜索物品、执行指令、发邮件和管理公告。邮件附件每行填写 `物品ID 数量`。

后台仅允许服务器本机访问。**游戏聊天中的 GM 指令对所有登录账号开放**，邀请玩家前请先确认能接受这一点。

## 连接朋友的服务器

**如果你只是玩家，跳过“首次使用”的服务端安装步骤。** 你需要：

- 与朋友相同版本的游戏客户端。
- PowerShell 7。
- Hoshimi 的 `scripts/` 文件夹。
- [GOST v3 的 Windows 版](https://github.com/go-gost/gost/releases)。将程序放在例如 `D:\Tools\gost.exe`。
- 朋友提供的服务器地址，推荐使用 VPN 地址。

### 1. 切换客户端

退出游戏，并停止自己电脑上的服务端。在 Hoshimi 文件夹中执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
```

### 2. 开启连接

把第一行的示例地址换成朋友提供的地址。第二行的程序路径按实际位置填写。

```powershell
$serverAddress = '203.0.113.10'
& 'D:\Tools\gost.exe' -L "tcp://127.0.0.1:8080/${serverAddress}:8080" `
    -L "tcp://127.0.0.1:5001/${serverAddress}:5001" `
    -L "udp://127.0.0.1:5001/${serverAddress}:5001"
```

**保持这个窗口开着。** 再直接打开游戏，用自己的私服账号登录。

进度保存在朋友的服务器上。不同玩家应使用不同账号名。

结束时先退出游戏，再到连接窗口按 `Ctrl+C`。需要回官服时，执行 [切回官服](#切回官服) 的命令。

## 常见问题

先找你看到的提示，只处理对应这一项。

| 现象或提示 | 下一步 |
|---|---|
| 找不到 `server.py` 或 `requirements-setup.txt` | 检查当前文件夹，应进入 Hoshimi 根目录 |
| 找不到 `python` | 安装 Python 并勾选添加到 PATH，再重新打开 PowerShell 7 |
| 找不到 `tolua.dll` | 检查游戏路径，选择包含 `AetherGazer.exe` 的文件夹 |
| 缺少 `scripts64` 或资源散列不符 | 用官方启动器补下载或修复游戏资源，再执行准备命令 |
| 提示本机依赖与客户端版本不一致 | 按下方“游戏更新后”重新准备文件 |
| 找不到 `Hoshimi\venv\Scripts\python.exe` | 回到首次使用第 4 步，创建 Python 环境 |
| 提示端口被占用 | 关闭另一份服务端或连接程序，再启动；本机需要 8080 和 TCP/UDP 5001 |
| 切换时提示游戏未退出 | 先退出游戏，再执行切换命令 |
| 提示修改 hosts 需要管理员权限 | 用管理员身份打开 **PowerShell 7**，重新执行切换命令 |
| 提示系统代理已启用 | 关闭系统代理，再切换 |
| 缺少官服入口或 SDK 备份 | 用官方启动器恢复客户端，再首次切换；已有切换备份的处理见下方说明 |
| 连朋友的服务器能进大厅，但战斗卡住 | 双方检查 **UDP 5001** 是否转发并放行 |
| 账号或密码错误 | 检查账号和密码；已有账号不会因输入新密码而重新注册 |

### 游戏更新后

先退出游戏并停止服务端，再在 PowerShell 7 中执行。前两行改成自己的路径：

```powershell
Set-Location 'E:\Project\Hoshimi'
$env:AGL_CLIENT_DIR = 'D:\Games\AetherGazer'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Hoshimi\venv\Scripts\python.exe'
& $pythonPath -B .\prepare_runtime.py
```

看到“准备完成”后，按 [以后怎么启动](#以后怎么启动) 开服。

如果切换脚本提示 SDK 备份版本不匹配，先用官方启动器修复客户端，再使用一个新的备份文件夹：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer' -StateDir 'D:\HoshimiBackups\client-switch-v2'
```

之后切回官服也要带上同一个 `-StateDir`。新客户端版本是否可用仍需验证。

<details>
<summary>已经有切换备份，怎么继续使用？</summary>

切换命令加上 `-StateDir`，指向你保存备份的文件夹：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer' -StateDir 'D:\HoshimiBackups\client-switch'
```

切回官服时，把 `Local` 换成 `Official`，其他参数不变。

备份文件夹需要包含匹配该客户端的入口与 SDK 备份。只有 `url.txt` 不能完成 SDK 恢复；备份丢失时请先用官方启动器修复。

</details>

### 战斗血条或鼠标视角异常

先退出游戏，在 Hoshimi 文件夹中执行：

```powershell
pwsh -File .\scripts\repair-battle-controls.ps1
```

脚本会备份设置并显示备份位置。要恢复设置，使用 `-Restore '备份文件完整路径'`。

## 保存进度与备份

**要备份进度：先停服，再复制整个 `data/` 文件夹。** 恢复时也先停服，再还原备份。

| 文件夹 | 保存什么 |
|---|---|
| `data/users/` | 账号、密码摘要、登录令牌、角色和进度 |
| `data/chat/` | 世界聊天和私聊 |
| `data/announcements.json`、`data/gm/` | 公告和后台操作记录 |
| `data/client-switch/` | 官私服切换备份与登录缓存 |
| `data/client-settings/` | 战斗界面和控制设置备份 |

这些文件首次使用后才会生成。**不要把 `data/` 上传到 Git 或发给其他玩家。**

## 功能与限制

当前验证版本：安装版 **307**，资源版 **321（v5.3.1）**。

支持账号注册登录、角色养成、皮肤、编队与配装保存、商店、任务、签到、邮件、公告、剧情进度、单人战斗、角色/钥从探测和活动皮肤抽奖。

当前客户端可读取 84 个可玩角色、307 种货币定义和 884 条补给描述。普通新号货币为零；已有体验账号缺失的货币默认补到 `99999`。

使用前了解这几项：

- 补给商品统一售价 **1 移转之辉**，价格与排期由本地服务决定。
- 活动是否可用取决于客户端资源，排期可能与官服不同。
- 探测包含自选、基础概率、保底、重复奖励、辉芒和记录保存；没有复刻未公开的概率递增曲线。
- 部分多维变量节点、复杂地图事件、活动玩法和联机尚未完成。
- 剧情入口解锁后，地图里的前置任务仍可能需要完成。
- 游戏默认直接从官方 CDN 下载缺失资源；已下架的文件可能无法下载。

## 其他设置

下面只在需要时展开，首次使用可以跳过。

<details>
<summary>我想部署服务器，让朋友来玩</summary>

**先在服务器电脑上完成“首次使用”并确认可以正常开服。** 服务器需要 Windows 和相同版本的完整客户端。

默认监听 `0.0.0.0`，无需额外修改监听地址。在云安全组和 Windows 防火墙放行：

| 要放行的端口 | 用途 |
|---|---|
| TCP 8080 | 登录和服务器列表 |
| TCP 5001 | 游戏连接 |
| UDP 5001 | 战斗连接 |

家用网络还需在路由器上转发这些端口。

当前登录使用 HTTP，推荐先与玩家建立 VPN 连接，并只向 VPN 网段开放这些端口。聊天 GM 指令对所有登录玩家开放，适合熟人测试。

把服务器地址发给朋友，请他们按 [连接朋友的服务器](#连接朋友的服务器) 操作。玩家不需要安装服务端，也不需要准备服务端运行文件。

检查连接时，玩家在另一个 PowerShell 7 窗口执行：

```powershell
Test-NetConnection 127.0.0.1 -Port 8080
Test-NetConnection 127.0.0.1 -Port 5001
Invoke-RestMethod 'http://127.0.0.1:8080/skzy-activity/gateway/get?action=server&version=307&mixId=0'
```

前两项确认本机 TCP 监听，第三项应返回远程服务器列表。这些命令不能验证 UDP。

</details>

<details>
<summary>我想修改端口、文件位置或下载方式</summary>

可以设置环境变量，也可把 [config.example.py](config.example.py) 复制为 `config_local.py` 后编辑。`config_local.py` 中的同名设置优先，修改后需要重启服务端。

| 设置名称 | 默认值 / 用途 |
|---|---|
| `AGL_CLIENT_DIR` | 游戏文件夹，必须填写实际位置 |
| `HOSHIMI_RUNTIME_DIR` | 本机准备文件的位置，默认在 `%LOCALAPPDATA%\Hoshimi\runtime` |
| `AGL_HOST` | `0.0.0.0`，服务端监听地址 |
| `AGL_HTTP_PORT` | `8080`，登录与后台端口 |
| `AGL_TCP_PORT` | `5001`，游戏 TCP 和战斗 UDP 端口 |
| `AGL_ENABLE_HTTPS` | `0`，默认无需本地证书 |
| `AGL_RESOURCE_MODE` | `direct` 直连官方 CDN；`proxy` 由服务端转发 |
| `AGL_RESOURCE_DOWNLOAD_URL` | 官方资源下载地址，通常不用改 |

想改变准备文件的位置，先设置下面这一行，再执行准备或启动命令：

```powershell
$env:HOSHIMI_RUNTIME_DIR = 'D:\HoshimiRuntime'
```

**以后每个用于准备或开服的新窗口，都要设置相同路径。** 这个文件夹必须放在 Hoshimi 仓库外。

改变 HTTP 端口时，切换命令还需加 `-LocalPort 新端口`，后台地址也要同步修改。改变游戏端口时，需要同时修改 TCP/UDP 放行与玩家转发。

本机准备工具不下载资源，也不修改客户端。重新准备成功后，会留下 `runtime-backup-*` 备份；确认服务正常后可自行清理。

</details>

<details>
<summary>我想运行开发验证或提交 Git</summary>

按“以后怎么启动”的前三行设置好路径和 `$pythonPath`，然后执行：

```powershell
& $pythonPath -B -m tests.test_local_auth
& $pythonPath -B -m tests.test_gacha
& $pythonPath -B -m tests.test_gm_unlock
& $pythonPath -B -m tests.test_developer_supply
```

验证覆盖账号、抽奖、辉芒、满配角色、场景和重启保存，使用临时存档，不修改正式账号，也不占用游戏端口。

提交前检查文件列表：

```powershell
git status --short
git diff --cached --stat
git ls-files
```

`.gitignore` 已排除存档、私有配置、客户端文件、生成数据、证书、缓存和备份。不要用 `git add -f` 强行加入这些内容。

</details>

## 代码与许可

仓库包含自写服务端、管理页面、接入工具和验证代码，不附带客户端源码或游戏资源。

代码许可见 [LICENSE](LICENSE)。游戏及客户端、资源和商标属于各自权利人，本项目与官方无关联
