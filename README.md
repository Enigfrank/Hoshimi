# Hoshimi

Hoshimi（星见）非官方游戏模拟服务端，适合本地体验和熟人测试。

- **下载：** [GitHub Releases](https://github.com/Enigfrank/Hoshimi/releases)，选择 `Hoshimi-windows-amd64-v[版本号].zip`。
- **使用文档：** [Hoshimi 文档](https://hoshimi.ecso.top)，首次使用从[安装教程](https://hoshimi.ecso.top/#/quickstart)开始。
- **运行环境：** Windows 64 位、已完成基础安装的 PC 游戏客户端、PowerShell 7；缺失资源可按安装教程补齐，无需先登录官服。服务端路径不要包含中文。
- **更新前：** 退出游戏、停止服务端并备份 `data/`、`config.json` 与 `runtime/`。
- **问题反馈：** 先阅读[问题上报指南](REPORTING.md)，再提交 [Issue](https://github.com/Enigfrank/Hoshimi/issues)。

完整教程的 Markdown 源文件位于 [docs](docs/README.md)  [QQ交流群](https://qm.qq.com/q/qXXTrw69Mc)

## 可选使用统计

首次开服会单独询问是否允许设备使用统计，只有输入 `y` 才开启，默认关闭。统计通过 Umami Cloud 收集项目专属 HWID 哈希、启动会话时间、服务端与 Go 版本、Windows 版本、CPU 架构及逻辑核心数、启动结果和耗时、运行时长、固定错误类别计数及服务进程资源占用。同一设备可跨启动关联，不上传原始硬件编号、游戏账号、存档、聊天、照片、完整日志或本机路径。请求使用占位 IP，第三方接收服务在网络连接层仍可接触来源 IP。


在 `config.json` 中设置 `"telemetry_enabled": false` 可持续关闭；启动时使用 `hoshimi.exe --no-telemetry` 可仅关闭本次统计。关闭统计或无法连接统计平台均不影响游戏，没有联网启动限制。详细字段及统计口径见 [使用统计说明](docs/advanced.md#可选使用统计)。

本项目与游戏官方无关联。许可见 [LICENSE](LICENSE)，依赖声明见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。
