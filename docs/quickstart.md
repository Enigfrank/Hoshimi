# 首次使用

## 1. 在 GitHub 下载

在本项目的 GitHub 页面：

1. 打开本项目的 **GitHub Releases**，下载所需版本的 <strong><code>Hoshimi-windows-amd64-v[版本号].zip</code></strong>，例如 `Hoshimi-windows-amd64-v0.0.1.zip`。
2. 解压到你选择的文件夹，例如 `E:\Hoshimi`。

**成功标志：** 解压后的文件夹中有 `hoshimi.exe` 和 `scripts` 文件夹。

后面的命令都在包含 `hoshimi.exe` 的文件夹中执行。下文用 `E:\Hoshimi` 举例，你可以换成自己的路径。

路径不要包含中文。启动时会检查 EXE 所在目录、当前工作目录，以及实际使用的配置、存档、运行文件、客户端资源和 Lua 动态库目录；检测到中文会显示具体位置、给出处理办法并退出，不创建日志或初始化服务。请迁移目录并更新 `config.json`、启动参数或环境变量后重试。


## 2. 准备好客户端和 PowerShell 7

需要这两样：

- Windows 64 位 PC 游戏客户端。用官方启动器下载完整资源。
- [PowerShell 7](https://github.com/PowerShell/PowerShell/releases)。

找到游戏文件夹，里面应有 <strong><code>AetherGazer.exe</code></strong>。记下这个文件夹的完整路径。

打开 **PowerShell 7**，执行：

```powershell
$PSVersionTable.PSVersion
```

**成功标志：** 主版本号是 `7`。后面所有命令都在 PowerShell 7 中执行。

## 3. 准备运行文件

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

## 4. 启动服务端

在刚才的窗口执行：

```powershell
.\hoshimi.exe
```

每次启动会先显示服务端版本和编译时间。首次启动会显示免费软件提示和交流频道。**按回车继续**，以后启动无需再次确认。

**成功标志：** 出现“`Hoshimi 服务已启动`”。

**保持这个窗口开着。** 关闭窗口会停止服务端。

## 5. 切换客户端，进入游戏

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
