# 切回官服

先退出游戏，再执行：

```powershell
Set-Location 'E:\Hoshimi'
pwsh -File .\scripts\switch-client.ps1 -Mode Official -ClientDir 'D:\Games\AetherGazer'
```

看到“已切换：官服”后，用**官方启动器**打开游戏。

**保留 `data/client-switch/`。** 这里保存切换备份和两套登录缓存。

忘了当前连哪边？把命令中的 `Official` 改成 `Status`。
