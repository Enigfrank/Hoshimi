# Hoshimi

Hoshimi（星见）非官方游戏模拟服务端，适合本地体验和熟人测试。

第一次使用，按下面 **1 → 2 → 3 → 4 → 5** 做。每次只做一步。

| 你想做什么 | 点这里 |
|---|---|
| 第一次玩 | [首次使用](#首次使用) |
| 再次开服 | [以后怎么启动](#以后怎么启动) |
| 更新服务端 | [更新指南](#更新指南) |
| 回官服 | [切回官服](#切回官服) |
| 加角色或货币 | [GM 指令](#gm-指令) |
| 连朋友的服 | [连接朋友的服务器](#连接朋友的服务器) |
| 处理报错 | [常见问题](#常见问题) |
| 上报问题 | [问题上报指南](REPORTING.md) |

## 首次使用

### 1. 在 GitHub 下载

在本项目的 GitHub 页面：

1. 打开本项目的 **GitHub Releases**，下载所需版本的 **`Hoshimi-windows-amd64-v[版本号].zip`**，例如 `Hoshimi-windows-amd64-v0.0.1.zip`。
2. 解压到你选择的文件夹，例如 `E:\Hoshimi`。

**成功标志：** 解压后的文件夹中有 `hoshimi.exe` 和 `scripts` 文件夹。

后面的命令都在包含 `hoshimi.exe` 的文件夹中执行。下文用 `E:\Hoshimi` 举例，你可以换成自己的路径。


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

每次启动会先显示服务端版本和编译时间。首次启动会显示免费软件提示和交流频道。**按回车继续**，以后启动无需再次确认。

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

普通新号直接使用客户端最大等级，初始体力为 100，货币和材料为零。跳过操作引导，剧情入口全部解锁，默认零星。

想体验满配，用 `Developer` 账号。第一次登录时输入的密码会成为这个账号的密码。

登录由私服验证，缺少的游戏资源默认由本地服务转发官方 HTTPS CDN 下载

## 以后怎么启动

打开 PowerShell 7，执行：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe
```

看到“服务已启动”后，直接打开游戏。客户端仍处于本地服时，不用重复切换。

**停止服务：** 在服务端窗口按 `Ctrl+C`。

客户端路径会保存在 `config.json` 中，下次无需再填写。

仅查看服务端版本和编译时间：

```powershell
.\hoshimi.exe version
```

## 更新指南

### 1. 下载新版

在 **GitHub Releases** 下载 `Hoshimi-windows-amd64-v[版本号].zip`，先阅读该版本的更新说明和客户端要求。

### 2. 停服并备份

退出游戏，在旧服务端窗口按 `Ctrl+C` 停服。将**整个服务端文件夹**复制到另一处作为备份，例如把 `E:\Hoshimi` 备份到 `E:\Hoshimi-backup`。

以下内容必须保留：

| 文件或目录 | 内容 |
|---|---|
| `data/` | 账号、游戏进度、官私服切换备份等 |
| `config.json` | 客户端路径与服务设置 |
| `runtime/` | 已准备的客户端运行文件 |

使用 `--home`、`--runtime-dir` 或自定义存储路径时，还要备份实际使用的目录，更新后沿用原启动参数。

### 3. 替换程序

将新版压缩包解压到临时文件夹，再把其中的 `hoshimi.exe`、`scripts/` 和说明文件复制到原服务端文件夹，覆盖同名文件。

**保留原有 `data/`、`runtime/` 和 `config.json`，不要用 `config.example.json` 替换现有配置。**

仅更新服务端且发布说明没有额外要求时，可继续使用现有运行文件和客户端切换状态。游戏客户端同时更新，或发布说明要求重新准备时，按 [游戏更新后](#游戏更新后) 操作。

### 4. 检查并启动

在 PowerShell 7 中执行：

```powershell
Set-Location 'E:\Hoshimi'
.\hoshimi.exe version
.\hoshimi.exe
```

确认显示的版本与下载版本一致、出现“服务已启动”，再用原账号登录，检查角色、货币和进度。

更新失败需要回退时，先退出游戏并停服，另行保留更新后的文件夹，再从升级前备份恢复整个服务端文件夹。**恢复后的进度以备份时为准。**

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

在后台的周期活动区域，可以为梦境再构、迭代校验、多维变量及第四代神经矩阵分别设置 **1–8760 小时**的全服刷新周期，并查看下次刷新时间。

默认每 168 小时刷新，按北京时间周一 05:00 对齐。修改后，仅更改的玩法从保存时重新计时，不立即清空进度；重复保存相同值不延长周期。到期清除当期挑战进度及当期领奖记录，新一期可重新领奖；已获得的角色、道具、多维局外成长及永久解锁保留。服务重启不会延长截止时间，离线账号在下次登录时刷新。

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
| `logs/` | 服务端运行日志，每次启动在 `logs` 文件夹内新建一个 `2026-10-23T20-14-05.log`，可随时删除 |

已有 JSON 存档可在停服后放到 EXE 旁边的 `data/` 中，令牌和密码格式保持兼容。

`data/`、`runtime/`、`logs/` 和 `config.json` 不要上传 Git，也不要放进分发压缩包。

## 常见问题

找到你遇到的那一项，只处理这一项。

| 提示或现象 | 下一步 |
|---|---|
| 找不到 `hoshimi.exe` | 回到第 1 步下载并解压 `Hoshimi-windows-amd64-v[版本号].zip`，再打开包含 EXE 的文件夹 |
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

仍无法解决时，请按 [问题上报指南](REPORTING.md) 提供版本、复现步骤和日志，再到 GitHub Issues 上报。

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

### 第四代神经矩阵与弥弥观测站

神经矩阵仅开放第四代「并发序列·钢铁暴君」，包含三个普通关和一个五队挑战关，支持跨关锁定角色、任务领奖、单队／单关／全部重置及登录恢复。前三代不在当前实现范围。手动重置保留本期最高分和已达成、已领取任务；周期到期则清除这些当期记录，进行中的旧战斗不能跨期结算。

采用**本地评分规则，不等同官服公式**。耗时 `t` 为战报毫秒数向下取整后的秒数：普通关胜利得分为 `max(4000, 5060 - ceil(t² / 20))`，失败或退出为零；挑战关得分为 `min(30000, floor(出战角色总伤害 / 4000))`，失败仍按伤害计分，主动退出为零。零分不覆盖已有完成记录，挑战任务按正分记录及累计分数达成。

弥弥观测站支持地区页面初始化、派遣、领取、技能升级、弥弥解锁及周累计奖励；随机探索事件尚未实现。

## 进阶设置

### 誓约照片（仅同机）

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

<details>
<summary>修改端口或文件位置</summary>

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

</details>

## 发布内容与许可

本项目只发布编译好的服务端及配套接入脚本，不公开服务端源码。发布包不包含客户端脚本、资源或存档；运行所需文件由你在本机从客户端准备。

许可见 [LICENSE](LICENSE)，依赖许可见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。游戏、客户端、资源和商标属于各自权利人，本项目与官方无关联。
