# Hoshimi Issue 助手

根据公开文档回复 Issue，并复用仓库现有分类标签。工作流和脚本仅用于 GitHub Issue 维护，不属于服务端程序，也不放入构建包。

## 配置

在 Hoshimi 的 Settings → Secrets and variables → Actions 配置：

| 类型 | 名称 | 含义 |
|---|---|---|
| Secret | `OPENAI_KEY` | OpenAI 兼容接口的密钥 |
| Variable | `PR_AGENT_API_BASE` | 与现有 PR Bot 共用的 API 地址；只有域名时自动补 `/v1`，已有路径则原样使用 |
| Variable | `PR_AGENT_MODEL` | 与现有 PR Bot 共用的模型名称 |

接口需要支持 Chat Completions、`response_format: json_object` 和 `max_completion_tokens`。脚本只使用 Python 3.12 标准库，不安装额外运行依赖。

## 触发方式

- 新 Issue：自动回复一次并分类。编辑 Issue、普通后续评论、PR 评论和 Bot 评论不触发分析。
- 人工重新分析：仓库拥有者或当前有 write、maintain、admin 权限的维护者，在开放 Issue 中单独评论 `/issue-bot`。同一条命令重复投递不会重复回复；需要再次分析时新建一条命令评论。
- 只读预览：在 Actions → Issue Assistant → Run workflow 中填写 Issue 编号；运行摘要显示回复草稿，不发布评论、不修改标签，允许预览历史已关闭 Issue。

Issue 事件始终检出默认分支。GitHub 要求工作流先进入默认分支，才能手工触发；此后手工预览可检出所选工作流分支。首次真实模型预览需要在合并后执行。所有终端步骤使用 PowerShell 7。

## 回复和分类

资料来自当前检出的 `README.md`、`REPORTING.md` 和 `docs/*.md`。建议必须附有能逐字匹配文档的引用，程序生成对应文件和行号的链接。文本匹配只能验证引用存在，建议是否由引用支持仍需要通过草稿审阅判断。

仅分析 Issue 正文和最近 30 条评论中的文本，不下载附件或读取图片，也不访问私有源码仓库。模型看到附件链接时，应说明未读取附件，按需请用户粘贴关键文字。模型调用失败或输出验证失败时，工作流报错，未发布未验证的回复。

问题类型最多一个：`Bug`、`Question`、`Enhancement`、`Documentation`。模块最多两个：`Account-auth`、`Battle`、`Protocol`、`Gm-admin`、`Data-persistence`、`Client-compatibility`。不确定时允许空分类，现有 `size/M` 不参与自动分类。

人工标签保留。人工已指定类型时，不再添加其他类型；人工模块标签占用模块名额。人工标签本身超过数量限制时仍保留，不替维护者删改。重新分析只删除仍能通过标签事件 ID 确认由本助手添加的标签；人工删除后重新添加的同名标签也予以保留。

回复末尾的 HTML 注释保存事件去重和标签所有权信息，请勿手工删除。仅接受 `github-actions[bot]` 发布的状态，用户粘贴相同注释无效。回复先记录操作计划，再执行分类；分类中途失败后重跑同一事件会恢复计划，不再次调用模型或发布回复。

## 本机只读预览

先将上述 API 配置和有仓库读取权限的 `GITHUB_TOKEN` 放入当前进程环境变量，再从仓库根目录运行：

```powershell
$env:GITHUB_REPOSITORY = 'Enigfrank/Hoshimi'
$env:ISSUE_BOT_DOCS_REF = git rev-parse HEAD
python -B .github/issue-bot/main.py --preview 24 --output "$env:TEMP/hoshimi-issue-24.json"
```

GitHub Secrets 不可读回本机。本机没有模型密钥时，使用 Actions 的只读预览入口。预览仍会调用模型并消耗 API 配额。
