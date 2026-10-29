# kirby

[![M8ven Score](https://m8ven.ai/badge/mcp/leo145x-kirby-1trnl2?v=28c193f5aba552f95702e44af0339b36)](https://m8ven.ai/mcp/leo145x-kirby-1trnl2?s=readme)

[English](README.md) | 繁體中文 | [简体中文](README.zh-CN.md)

跟你的 agent 說要什麼工具，kirby 就從你的 GitHub star 裡找出合適的 skill、plugin 或 MCP server，經你確認後安裝。

## 用途

你在 GitHub 上 star 了一堆 agent 工具，也整理成 star list。任務需要時，直接在 Claude Code 或 Codex 裡問：kirby 會搜尋你的 star 和 star list（也可以搜尋公開的 GitHub），推薦適合這個任務的工具，並安裝你選的那個，不用離開 session。

## 功能

- **優先搜尋你的 star**：你的 GitHub star 和 star list、公開的 GitHub（有 agent 工具類 topic 的 repo），或兩者一起。
- **推薦合適的工具**：模型依你的任務判斷每個候選，每個 repo 都附上 star 數和最後 push 的日期。
- **知道要裝的是什麼**：分辨 marketplace、plugin、skill 和 MCP server，以及安裝需要什麼。
- **安裝前先問你**：要在對話框選「安裝」才會安裝，也可以先看 README 或換一個。接著選 scope：`local`、`project` 或 `user`。
- **安裝 skill、plugin 或 MCP server 前先掃描**：找值得留意的模式，例如隱藏 Unicode、針對模型的語句、網路呼叫或機密環境變數，並在對話框列出每個命中。網路呼叫和機密、shell 執行或解碼同時出現時，標為 warn。整個檢查什麼都沒找到時，對話框用一行說明。plugin 會依 marketplace 條目找到它自己的檔案，在另一個 repo 也一樣。MCP server 掃描的是指令所執行的已發布 npm 或 PyPI 套件，只下載，不安裝也不執行。可以直接問模型被標出的那一行在做什麼。這只是 pattern 比對，不是安全審查。
- **查詢已知漏洞和惡意套件**：向 OSV.dev 查 skill 或 plugin 的相依套件和它的 commit，或 MCP server 的套件和它的相依套件，也查 repo 自己在 GitHub 發布的 advisory，每項發現標上 danger、warn 或 info。只有已知的惡意套件會擋下安裝；沒查成的部分會標為 unchecked。
- **有發現時請模型審查檔案**：檢查找到 danger 或 warn 的發現時，由一個 subagent 讀要安裝的檔案，不告訴它其他檢查找到什麼，回報最多五項發現，每項一句話。對話框把它們標為模型回報；它們只會增加，不會抵銷其他發現。沒有傳入審查結果或審查無法執行時，對話框用一行說明，安裝選項仍然保留。
- **鎖定 MCP server 的套件版本**：安裝指令會改寫成檢查過的套件版本（`npx -y pkg@1.2.3`）。只鎖定那個套件，不包含它的相依套件。
- **只裝你看到的 commit**：skill 會安裝對話框顯示的那個 commit，即使 repo 之後又有新的 commit 也一樣；只有那個 commit 已經不在（例如被 force-push 蓋掉）時才會失敗。plugin 從對話框顯示的 marketplace commit 安裝；實際安裝前 marketplace 有變動，plugin 會再被移除。安裝 plugin 會一併更新你已經加入的 marketplace 時，對話框會說明。
- **用你的語言**：對話框用你使用的語言寫。
- **不影響 prompt cache**：在 Claude Code 裡，安裝 skill、plugin 或 MCP server 都不會讓 prompt cache 失效（實測）。唯一的例外是帶有 MCP server 的 plugin，在 tool search 關閉時用 `/reload-plugins` 載入；這種情況對話框會註明，Claude Code 在 reload 前也會先警告。
- **支援 Claude Code 和 Codex**。

## 需求

- 已登入的 [`gh`](https://cli.github.com/) CLI（`gh auth login`）
- `git`
- `python3`（要讀 `uv.lock` 和 `pyproject.toml` 需 3.11 以上）
- 選用：`npm` 和 `uv`，讓查詢能算出沒有 lockfile 的相依套件版本；沒有的話只用名稱查詢

## 快速開始

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

然後直接問就行，例如：

- 「有沒有能畫架構圖的 skill？」
- 「從我的 AI Tools list 找 code review 的工具」
- 「從公開的 GitHub 找能查 postgres 的 MCP」

在 Claude Code 也可以用 `/kirby:inhale` 叫用。

## 進一步了解

[說明文件](docs/guide.zh-TW.md) 有完整細節：搜尋來源設定、安裝流程每一步、各 scope 裝到哪裡、掃描比對的內容、漏洞和惡意套件查詢、模型審查、prompt cache、Codex 版的差異，以及腳本。

## 開發

```
claude plugin validate .
claude plugin test .
python3 -B -m unittest discover -s tests
```

## License

[MIT](LICENSE)
