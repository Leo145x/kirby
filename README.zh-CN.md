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
- **安装 skill 前先扫描**：查找值得留意的模式，例如隐藏 Unicode、针对模型的语句、网络调用或机密环境变量，并在对话框列出每个命中。可以直接问模型被标出的那一行在做什么。这只是 pattern 匹配，不是安全审查；plugin 和 MCP server 不会扫描。
- **只装你看到的 commit**：skill 只会安装对话框显示的那个 commit；实际安装前 repo 有变动，就不会安装。
- **用你的语言**：对话框用你使用的语言写。
- **不影响 prompt cache**：在 Claude Code 里，安装 skill、plugin 或 MCP server 都不会让 prompt cache 失效（实测）。唯一的例外是带有 MCP server 的 plugin，在 tool search 关闭时用 `/reload-plugins` 加载；这种情况对话框会注明，Claude Code 在 reload 前也会先警告。
- **支持 Claude Code 和 Codex**。

## 依赖

- 已登录的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`

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

[说明文档](docs/guide.zh-CN.md) 有完整细节：搜索来源设置、安装流程每一步、各 scope 装到哪里、扫描匹配的内容、prompt cache、Codex 版的差异，以及脚本。

## 开发

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
