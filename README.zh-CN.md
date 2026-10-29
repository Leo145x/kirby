# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

[English](README.md) | [繁體中文](README.zh-TW.md) | 简体中文

跟你的 agent 说要什么工具，kirby 就从你的 GitHub star 里找出合适的 skill、plugin 或 MCP server，经你确认后安装。

## 用途

你在 GitHub 上 star 了一堆 agent 工具，也整理成 star list。任务需要时，直接在 Claude Code 或 Codex 里问：kirby 会搜索你的 star 和 star list（也可以搜索公开的 GitHub），推荐适合这个任务的工具，并安装你选的那个，不用离开 session。

## 功能

- **优先搜索你的 star**：你的 GitHub star 和 star list、公开的 GitHub（带有 agent 工具类 topic 的 repo），或两者一起。
- **推荐合适的工具**：模型根据你的任务判断每个候选，每个 repo 都附上 star 数和最后 push 的日期。
- **知道要装的是什么**：区分 marketplace、plugin、skill 和 MCP server，以及安装需要什么。
- **安装前先问你**：要在对话框选择“安装”才会安装，也可以先看 README 或换一个。接着选择 scope：`local`、`project` 或 `user`。
- **安装 skill、plugin 或 MCP server 前先扫描**：查找值得留意的模式，例如隐藏 Unicode、针对模型的语句、网络调用或机密环境变量，并在对话框列出每个命中。网络调用和机密、shell 执行或解码同时出现时，标为 warn。整个检查什么都没找到时，对话框用一行说明。plugin 会按 marketplace 条目找到它自己的文件，在另一个 repo 也一样。MCP server 扫描的是命令所运行的已发布 npm 或 PyPI 包，只下载，不安装也不运行。可以直接问模型被标出的那一行在做什么。这只是 pattern 匹配，不是安全审查。
- **查询已知漏洞和恶意包**：向 OSV.dev 查 skill 或 plugin 的依赖包和它的 commit，或 MCP server 的包和它的依赖包，也查 repo 自己在 GitHub 发布的 advisory，每项发现标上 danger、warn 或 info。只有已知的恶意包会拦下安装；没查成的部分会标为 unchecked。
- **有发现时请模型审查文件**：检查找到 danger 或 warn 的发现时，由一个 subagent 读要安装的文件，不告诉它其他检查找到什么，报告最多五项发现，每项一句话。对话框把它们标为模型报告；它们只会增加，不会抵消其他发现。没有传入审查结果或审查无法运行时，对话框用一行说明，安装选项仍然保留。
- **锁定 MCP server 的包版本**：安装命令会改写成检查过的包版本（`npx -y pkg@1.2.3`）。只锁定那个包，不包含它的依赖包。
- **只装你看到的 commit**：skill 会安装对话框显示的那个 commit，即使 repo 之后又有新的 commit 也一样；只有那个 commit 已经不在（例如被 force-push 覆盖）时才会失败。plugin 从对话框显示的 marketplace commit 安装；实际安装前 marketplace 有变动，plugin 会再被移除。安装 plugin 会一并更新你已经添加的 marketplace 时，对话框会说明。
- **用你的语言**：对话框用你使用的语言写。
- **不影响 prompt cache**：在 Claude Code 里，安装 skill、plugin 或 MCP server 都不会让 prompt cache 失效（实测）。唯一的例外是带有 MCP server 的 plugin，在 tool search 关闭时用 `/reload-plugins` 加载；这种情况对话框会注明，Claude Code 在 reload 前也会先警告。
- **支持 Claude Code 和 Codex**。

## 依赖

- 已登录的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`（要读取 `uv.lock` 和 `pyproject.toml` 需 3.11 以上）
- 可选：`npm` 和 `uv`，让查询能算出没有 lockfile 的依赖包版本；没有的话只按包名查询

## 快速开始

Claude Code：

```
claude plugin marketplace add Leo145x/kirby
claude plugin install kirby@kirby
```

Codex：

```
codex plugin marketplace add Leo145x/kirby
codex plugin add kirby@kirby
```

然后直接问就行，例如：

- “有没有能画架构图的 skill？”
- “从我的 AI Tools list 找 code review 的工具”
- “从公开的 GitHub 找能查 postgres 的 MCP”

在 Claude Code 也可以用 `/kirby:inhale` 调用。

## 进一步了解

[说明文档](docs/guide.zh-CN.md) 有完整细节：搜索来源设置、安装流程每一步、各 scope 装到哪里、扫描匹配的内容、漏洞和恶意包查询、模型审查、prompt cache、Codex 版的差异，以及脚本。

## 开发

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
