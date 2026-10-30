# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

[English](README.md) | [繁體中文](README.zh-TW.md) | 简体中文

跟你的 agent 说要什么工具，kirby 就从你的 GitHub star 里找出合适的 skill、plugin 或 MCP server，并在你确认之前先检查它会装进什么。

## 用途

kirby 做两件事，一前一后。

**帮你找到工具。** 你在 GitHub 上 star 了一堆 agent 工具，也整理成 star list。任务需要时，直接在 Claude Code 或 Codex 里问：kirby 会搜索你的 star 和 star list（也可以搜索公开的 GitHub），推荐适合这个任务的工具，并安装你选的那个，不用离开 session。

**装之前先帮你检查。** 安装对话框出现之前，kirby 会先看一遍要装的东西：扫描文件，查询工具本身和依赖包有没有已知漏洞或恶意包，有发现时再请模型审查文件。每项发现都会列在对话框里，让你清楚自己装的是什么。安装仍然只需点一下；只有已知的恶意包会被拦下。

## 功能

### 找工具

- **优先搜索你的 star**：你的 GitHub star 和 star list、公开的 GitHub（带有 agent 工具类 topic 的 repo），或两者一起。
- **推荐合适的工具**：模型根据你的任务判断每个候选，每个 repo 都附上 star 数和最后 push 的日期。
- **知道要装的是什么**：区分 marketplace、plugin、skill 和 MCP server，以及安装需要什么。

### 安装前检查

- **扫描实际要安装的文件**：skill 的文件、plugin 自己的文件（在另一个 repo 也一样），或 MCP server 命令所运行的已发布 npm、PyPI 包（只下载，不安装也不运行）。查找的是值得留意的模式，例如隐藏 Unicode、针对模型的语句、网络调用或机密环境变量。这只是 pattern 匹配，不是安全审查；被标出的那一行在做什么，可以直接问模型。
- **查询已知漏洞和恶意包**：查工具本身和它的依赖包，数据来自 OSV.dev，以及 repo 自己在 GitHub 发布的 advisory。
- **有发现时请模型审查文件**：扫描或查询找到 danger 或 warn 的发现时，由一个只能读取文件的 subagent（Claude Code 里是 kirby 的审查 agent）报告最多五项发现，并标为模型报告。
- **每项发现一行，附带严重度**：danger、warn 或 info。没能运行的部分会标 unchecked，不会当成没找到；什么都没找到的工具只有一行 `check: nothing found`。
- **默认点一下就能装**：任何发现都不会让你多走一步。只有已知的恶意包会拦下安装。
- **装的就是你看到的**：skill 安装对话框显示的那个 commit，即使 repo 之后有了新的 commit；plugin 装完后如果 marketplace 不在检查过的 commit，会再移除；MCP server 的命令会锁定在检查过的包版本（它的依赖不会）。

### 安装

- **安装前先问你**：要在对话框选择“安装”才会安装，也可以先看 README 或换一个。接着选择 scope：`local`、`project` 或 `user`。
- **用你的语言**：对话框用你使用的语言写。其中的事实由 kirby 自己写，有英文、繁體中文和简体中文；模型只选语言。
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

[说明文档](docs/guide.zh-CN.md) 有完整细节：搜索来源设置；安装前检查，包括每个部分检查什么、严重度、什么会拦下安装、模型审查，以及哪些有锁定；安装流程每一步和各 scope 装到哪里；prompt cache；Codex 版的差异；以及脚本。

## 开发

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
