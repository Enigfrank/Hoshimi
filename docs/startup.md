# 以后怎么启动

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
