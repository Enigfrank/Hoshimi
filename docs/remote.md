# 连接朋友的服务器

**如果你只是玩家，不需要启动服务端或准备 `runtime`。**

准备：同版本客户端、PowerShell 7、Hoshimi 的 `scripts/` 文件夹，以及 [GOST v3 Windows 版](https://github.com/go-gost/gost/releases)。

## 1. 切换客户端

退出游戏，并停止自己电脑上的服务端，然后执行：

```powershell
pwsh -File .\scripts\switch-client.ps1 -Mode Local -ClientDir 'D:\Games\AetherGazer'
```

## 2. 开启连接

下面第一行换成朋友给的服务器地址，第二行换成你的 GOST 路径：

```powershell
$serverAddress = '203.0.113.10'
& 'D:\Tools\gost.exe' -L "tcp://127.0.0.1:8080/${serverAddress}:8080" `
    -L "tcp://127.0.0.1:5001/${serverAddress}:5001" `
    -L "udp://127.0.0.1:5001/${serverAddress}:5001"
```

**保持此窗口开着。** 直接打开游戏，用自己的私服账号登录。

进度保存在朋友的服务器上。不同玩家使用不同账号名。

结束时退出游戏，在 GOST 窗口按 `Ctrl+C`。回官服时执行 [切回官服](switch-official.md)。

## 服主：部署到公网

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
