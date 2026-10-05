# Hoshimi Server

Hoshimi（星见）是《深空之眼》PC 客户端的非官方模拟服务端，使用 Python 编写。当前验证环境为 Windows，客户端安装版本 **307**、资源版本 **321（v5.3.1）**。

仓库仅收录自写服务端、GM 管理页面、接入工具与回归验证。**不附带客户端源码、Lua 字节码、游戏资源、客户端 DLL、导出配置、协议表、玩家存档或旧仓库历史。** 使用者须自行准备客户端。本机准备工具读取自己的安装文件，将运行依赖生成到仓库外；请勿将生成结果打包发布。

## 1. 环境与首次启动

需要：

- Windows、PowerShell **7**、64 位 Python **3.10+**。
- 资源下载完整的 PC 客户端，包含 `tolua.dll` 和 `AssetHash_Info.bytes`。
- 准备阶段使用 UnityPy；正常运行仅需 Python 标准库和本机客户端 DLL。

所有命令在项目根目录执行，客户端路径替换为自己的安装位置。推荐将 Python 环境也放在仓库外：

```powershell
Set-Location 'E:\Project\Hoshimi'
$env:AGL_CLIENT_DIR = 'E:\AetherGazerLauncher\AetherGazer'
$env:PYTHONIOENCODING = 'utf-8'

python -m venv "$env:LOCALAPPDATA\Hoshimi\venv"
$pythonPath = Join-Path $env:LOCALAPPDATA 'Hoshimi\venv\Scripts\python.exe'
& $pythonPath -m pip install -r .\requirements-setup.txt
& $pythonPath -B .\prepare_runtime.py
& $pythonPath -B .\server.py
```

准备工具按本机清单查找 `scripts64` 资源包，核对大小和散列，再生成运行依赖。不会下载或修改客户端；失败时会输出原因，中间结果留在外部目录。成功重新准备时，旧依赖保存为同级 `runtime-backup-*` 目录，可在确认后自行清理。

默认运行依赖路径为 `%LOCALAPPDATA%\Hoshimi\runtime`。如需其他位置，**准备和启动须使用同一个设置**：

```powershell
$env:HOSHIMI_RUNTIME_DIR = 'D:\HoshimiRuntime'
& $pythonPath -B .\prepare_runtime.py
& $pythonPath -B .\server.py
```

工具拒绝将依赖输出到本仓库内。客户端更新后先退出游戏、停止服务端，再重新准备；启动时会检查依赖是否匹配当前客户端清单。跨版本兼容性需要重新验证。

后续启动不必重复安装或准备。在新 PowerShell 7 窗口中：

```powershell
Set-Location 'E:\Project\Hoshimi'
$env:AGL_CLIENT_DIR = 'E:\AetherGazerLauncher\AetherGazer'
$pythonPath = Join-Path $env:LOCALAPPDATA 'Hoshimi\venv\Scripts\python.exe'
& $pythonPath -B .\server.py
```

出现“全部服务已就绪”后可连接；在服务窗口按 `Ctrl+C` 停止。

## 2. 官服与私服切换

先退出游戏。首次切换需使用未修改的官方客户端，以便脚本备份原始入口和 SDK 配置。

```powershell
# 切入本地私服
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'E:\AetherGazerLauncher\AetherGazer'

# 查看状态
pwsh -File .\scripts\switch-client.ps1 -Mode Status -ClientDir 'E:\AetherGazerLauncher\AetherGazer'

# 切回官服
pwsh -File .\scripts\switch-client.ps1 -Mode Official -ClientDir 'E:\AetherGazerLauncher\AetherGazer'
```

不指定 `-Mode` 时显示选择菜单。脚本会备份入口、SDK 配置和官私服各自的登录缓存；备份保存在 `data/client-switch/`，须保留。切回官服后通过官方启动器启动。官方修复或更新可能覆盖私服接入设置；更新版本后使用新的 `-StateDir` 备份目录重新切换。

默认接入采用本地 HTTP 登录与官方 HTTPS CDN，**无需安装本地根证书、监听 443 或设置系统代理**。脚本会清理项目域名的旧回环 hosts 映射；若存在这些映射，写入系统 hosts 需要管理员 PowerShell 7。其他代理开启时脚本可能拒绝切换，应先关闭代理。

### 从原项目迁移

本仓库没有复制原项目的账号、SDK 缓存及官服备份。如果客户端已被原项目切入私服，应继续指定**原备份目录**，例如：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local `
    -ClientDir 'E:\AetherGazerLauncher\AetherGazer' `
    -StateDir 'E:\AGL_Server\data\client-switch'
```

切回官服时也用相同 `-StateDir`。如果原备份丢失，先通过官方启动器恢复客户端，再首次切换；仅提供 `-OfficialConfigPath` 原始 `url.txt` 不能代替 SDK 备份。不要将客户端备份或存档加入 Git。

## 3. 登录与账号

私服启动后直接运行 `AetherGazer.exe`，选择**密码登录**：在“手机号”输入框填写私服账号名。

- 账号不存在：使用输入的账号和密码自动注册。
- 账号存在：密码匹配后登录；账号名大小写不敏感。
- 普通新号：一级朝约、初始体力、零货币与材料；跳过操作引导，剧情入口全部解锁，默认零星。实战星级和领奖状态独立保存。
- `Developer` 为本地体验账号，首次密码登录绑定输入的密码，默认拥有满配角色与皮肤。新仓库不含原项目账号与进度。

密码以加盐摘要保存，令牌和账号数据保存在 `data/`。不要使用官服或其他服务的密码。

## 4. 配置与资源下载

优先用环境变量配置，也可将 [config.example.py](config.example.py) 复制为 `config_local.py`。本地配置中同名值会覆盖环境变量，修改后重启服务。

| 环境变量 | 默认值 / 用途 |
|---|---|
| `AGL_CLIENT_DIR` | 本机客户端根目录，必须按实际位置设置 |
| `HOSHIMI_RUNTIME_DIR` | `%LOCALAPPDATA%\Hoshimi\runtime`，仓库外的运行依赖 |
| `AGL_HOST` | `0.0.0.0`，监听地址 |
| `AGL_HTTP_PORT` | `8080`，SDK、服务器列表与 GM 后台 |
| `AGL_TCP_PORT` | `5001`，游戏 TCP 和战斗 UDP 共用端口号 |
| `AGL_ENABLE_HTTPS` | `0`，默认不启用旧证书接入 |
| `AGL_RESOURCE_MODE` | `direct`，客户端直连官方 CDN；`proxy` 由服务端转发 |
| `AGL_RESOURCE_DOWNLOAD_URL` | 官方资源 CDN 根地址，通常无需更改 |

资源地址依据本机清单生成，客户端直接向官方 CDN 请求缺失资源。官服已下架的文件可能无法下载。本项目不提供历史活动资源，也不保证与官服实时排期一致。

如果更改 HTTP 端口，切换脚本的 `-LocalPort` 和 GM 后台地址也要同步修改。游戏 TCP/UDP 端口必须同时调整。

## 5. GM 指令与后台

在游戏**世界聊天**中发送指令，使用 `/` 或 `$` 前缀。指令修改当前登录账号，成功后保存并同步在线客户端。

| 示例 | 效果 |
|---|---|
| `/unlock character` | 全部可玩角色满配、全部永久皮肤、全部大厅场景与额外视角 |
| `/give 36 100` | 增加指定物品；此例增加 100 共鸣辉芒 |
| `/gold 99999` | 将金币设为指定数量 |
| `/diamond 99999` | 将移转之辉设为指定数量 |
| `/flower 99999` | 设置 PC/安卓移转之花余额，并清零 iOS 与免费余额 |
| `/stamina 240` | 将体力设为指定数量 |
| `/level 85` | 设置玩家等级，限制在 1–100 |
| `/help` | 查看指令及别名 |

`give` 增加库存，其他余额指令直接设置目标值。数量上限为 `2000000000`，单次最多发放 1000 个刻印或钥从实例。无效物品、非可玩角色等会被拒绝。

打开 http://127.0.0.1:8080/gm/ 使用 GM 后台，仅允许服务器本机访问：

- 查询账号、货币、角色、配装、进度与编队。
- 执行指令、搜索本机物品定义、下载物品 CSV。
- 给一个账号或全部现有账号发附件邮件，附件每行填写 `物品ID 数量`。
- 创建、编辑、删除公告及设置排期；公告变化会同步在线客户端。

**聊天 GM 指令目前对所有登录账号开放**，适合本地体验和熟人测试。

## 6. 公网部署与其他玩家连接

服务端目前下发回环地址 `127.0.0.1`。远程玩家需要本机转发，单改入口 URL 不足以接入。服主同样需要 Windows、对应版本的完整客户端与外部运行依赖，按首次启动步骤部署。

服务端配置：

```powershell
$env:AGL_HOST = '0.0.0.0'
$env:AGL_HTTP_PORT = '8080'
$env:AGL_TCP_PORT = '5001'
$env:AGL_ENABLE_HTTPS = '0'
$env:AGL_RESOURCE_MODE = 'direct'
& $pythonPath -B .\server.py
```

在云安全组、Windows 防火墙放行 **TCP 8080、TCP 5001、UDP 5001**；家用网络还需路由器转发。当前 SDK 认证使用 HTTP，建议服主与玩家先通过 VPN 建立加密连接，仅对 VPN 网段放行端口。

每位玩家准备相同版本客户端及 `scripts/switch-client.ps1`、`scripts/sdk-config.ps1`，保持两者同目录。玩家无需准备服务端运行依赖。另从 [GOST v3 发布页](https://github.com/go-gost/gost/releases) 下载 Windows 可执行程序，自行保存在仓库外。

玩家先退出游戏、停止自己电脑上的服务端，确保本机 8080、TCP/UDP 5001 未被占用，然后执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
$serverAddress = '203.0.113.10' # 替换为服主的 VPN IP 或公网 IP
& 'D:\Tools\gost.exe' -L "tcp://127.0.0.1:8080/${serverAddress}:8080" `
    -L "tcp://127.0.0.1:5001/${serverAddress}:5001" `
    -L "udp://127.0.0.1:5001/${serverAddress}:5001"
```

保持转发窗口运行，再直接打开游戏并用自己的私服账号登录。玩家存档保存在远程服务器；同名账号属于同一账号。退出后关闭游戏，在转发窗口按 `Ctrl+C`。切回官服使用前述 `-Mode Official` 命令。

连接检查：

```powershell
Test-NetConnection 127.0.0.1 -Port 8080
Test-NetConnection 127.0.0.1 -Port 5001
Invoke-RestMethod 'http://127.0.0.1:8080/skzy-activity/gateway/get?action=server&version=307&mixId=0'
```

前两项仅检查本机 TCP 监听，第三项应返回远程服务器列表。能进大厅但战斗卡住时检查 **UDP 5001**；`Test-NetConnection` 不验证 UDP。端口修改时同时调整服务端、放行规则和玩家转发。

## 7. 存档、备份与目录

| 路径 | 内容 |
|---|---|
| 根目录 `*.py` | 自写服务端业务与配置 |
| `gm_web/` | 自写管理页面 |
| `scripts/` | 官私服切换、SDK 接入与战斗控制修复 |
| `tests/` | 真实协议与隔离存档回归验证 |
| `data/users/` | 账号、密码摘要、令牌与玩家进度；首次运行生成 |
| `data/chat/` | 世界聊天与私聊 |
| `data/announcements.json`、`data/gm/` | 公告和后台审计 |
| `data/client-switch/`、`data/client-settings/` | 本机切换和控制设置备份 |
| 仓库外 `Hoshimi/runtime/` | 由本机客户端生成的 Lua、协议表和配置，不属于发布文件 |

停服后备份整个 `data/`，不要只备份单个角色文件。恢复时同样先停服，再还原完整备份。运行依赖可以重新准备；客户端切换备份丢失时需通过官方启动器恢复配置。

战斗 HUD 或鼠标视角异常时，退出游戏后可执行：

```powershell
pwsh -File .\scripts\repair-battle-controls.ps1
```

脚本会备份原控制设置；恢复时传入 `-Restore '备份文件完整路径'`。

## 8. 已实现与限制

已实现私服注册认证、登录推送、货币库存、角色养成和皮肤、配队与配装持久化、商店交易、任务签到、邮件公告、剧情进度与奖励、单人战斗通信，以及角色/钥从探测和活动皮肤抽奖。

当前版本准备结果包括 84 个可玩角色、307 种货币定义、884 条补给描述。原账号缺失货币默认补 `99999`，普通新号默认 `0`。补给商品使用本地编号，统一售价 **1 移转之辉**，不代表官服商品目录与真实价格。

活动开放基于本机资源，主题活动采用本地排期。探测实现自选、基础概率、保底、重复奖励、辉芒、记录与重启恢复，未复刻未公开的概率递增曲线。皮肤与场景抽奖开放本机配置支持的期次。

多维变量的商店等节点、因果观测与虚构推演的复杂地图事件、部分活动玩法及联机尚未完整实现。入口可见不代表流程完整；剧情解锁也不取消地图内的前置任务要求。

## 9. 验证与 Git

准备运行依赖并设置客户端环境变量后，在根目录执行：

```powershell
& $pythonPath -B -m tests.test_local_auth
& $pythonPath -B -m tests.test_gacha
& $pythonPath -B -m tests.test_gm_unlock
& $pythonPath -B -m tests.test_developer_supply
```

这些验证使用临时账号目录，不会修改正式存档或占用游戏端口。覆盖注册认证、白号、抽卡与皮肤抽奖、辉芒入账、满配角色/场景、在线同步和重启恢复。

本目录使用独立的 `main` 分支与全新 Git 历史，未继承原仓库对象，也未配置远程地址。提交前检查：

```powershell
git status --short
git diff --cached --stat
git ls-files
```

`.gitignore` 已排除存档、私有配置、客户端源码与资源、导出表、证书、缓存和备份。禁止使用 `git add -f` 把这些内容加入仓库；也不要分享仓库外生成的依赖。

## 许可证

自写代码遵循 [MIT LICENSE](LICENSE)，保留原贡献者版权声明。游戏及其客户端、资源、名称和商标属于各自权利人，本项目与官方无关联。排除客户端文件不代表获得权利人授权，也不能保证不会收到 DMCA 或其他权利主张。
