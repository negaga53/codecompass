---
title: 🧭 CodeCompass — AI-Powered Codebase Intelligence Powered by Github Copilot SDK
published: true
tags: devchallenge, githubchallenge, cli, githubcopilot
---

*This is a submission for the [GitHub Copilot CLI Challenge](https://dev.to/challenges/github-2026-01-21)*

## What I Built

**CodeCompass** is an AI-powered codebase intelligence and onboarding assistant that helps developers understand, navigate, and contribute to unfamiliar codebases — instantly. Powered by Github Copilot SDK.

Point it at any repository, and it:
- **Scans and indexes** the codebase (languages, frameworks, entry points, structure)
- **Builds a knowledge graph** from AST parsing, import tracing, and symbol mapping
- **Answers questions** grounded in actual code, git history, and contributor data
- **Generates artifacts** like dependency diagrams, onboarding docs, and change summaries

I built this because every time I join a new project or revisit an old one, I spend a lot of time reading READMEs, tracing imports, etc... CodeCompass compresses that entire onboarding process into seconds.

### Why Not Just Use Copilot CLI / Chat Directly?

Running `copilot` or Copilot Chat starts from scratch every time — reading files one by one, with no/limited access to git history, PRs, or contributor data. You'd need to manually prompt-engineer context and invoke tools yourself to get useful results.

CodeCompass is **purpose-built for repository analysis**:

- **Pre-indexed codebase** — AST parsing, import tracing, symbol mapping happen *before* the first question, so the AI answers from structured data instead of guessing
- **Automatic GitHub API access** — PRs, issues, reviews, and commit history are wired in as tools. Ask "Show me PR #464 and search for BYOK issues" and the AI fetches real data instantly — no manual setup
- **12 specialized tools in every session** — git history search, contributor analysis, dependency tracing, doc staleness detection, symbol lookup, code search — all available automatically
- **Knowledge graph queries** — "What modules depend on git.py?" is answered in one tool call from the graph, not 5-10 sequential file reads

### CLI-First = Automatable

Because CodeCompass is also a CLI tool, it fits naturally into CI/CD pipelines:

```bash
# Generate onboarding docs on every release
codecompass onboard --ai -o docs/onboarding.md --yes

# Audit docs for staleness in CI — fail the build if docs are stale
codecompass audit --yes

# Export a dependency graph for the wiki
codecompass graph -o deps.md

# Summarize recent changes for a Slack notification
codecompass diff-explain --commits 5 --yes

# Export knowledge graph as structured data
codecompass onboard -o knowledge.json -f json
```

Ir supports no interactive prompts, no manual intervention — just structured output from AI-powered analysis.

### Key Features

| Feature | What It Does |
|---------|-------------|
| **Instant Onboarding** | Scans any repo — detects languages, frameworks, CI, entry points, test dirs |
| **AI Narrative Summary** | Optional `--ai` flag generates an AI-written project overview |
| **Dependency Graph** | Generates Mermaid diagrams of module dependencies from AST analysis |
| **Diff Explain** | AI-powered analysis of recent commits — WHAT changed, WHY, and the impact |
| **Natural Language Q&A** | Ask questions about the codebase; AI uses 12 custom tools to find answers |
| **"Why" Investigation** | Reconstruct design decisions from commits, PRs, and blame data |
| **Doc Freshness Audit** | Detect stale documentation that no longer matches the code |
| **Contributor Intelligence** | Find who owns a file, who's active, who to ask about X |
| **GitHub Intelligence** | Query PRs, issues, and reviews directly from the CLI |
| **Rich TUI** | Textual-based split-pane interface with streaming AI responses |
| **Premium Awareness** | Shows model cost before AI calls; free models auto-confirm |
| **Configuration** | `.codecompass.toml` with interactive wizard, env vars, CLI flags |

### Technologies

- **Python** (Click CLI, Pydantic models, asyncio)
- **[GitHub Copilot SDK](https://github.com/github/copilot-sdk)** — the agentic runtime (JSON-RPC, streaming, custom tools, `billing.multiplier` for premium-rate detection)
- **Textual** — terminal UI framework
- **Rich** — terminal formatting
- **AST module** — Python knowledge graph builder

---

## Demo

All demos below show CodeCompass analyzing the **[GitHub Copilot SDK](https://github.com/github/copilot-sdk)** repository — a real, multi-language (Python, TypeScript, Go, .NET) codebase with 303 files and 73,000+ lines.

### 🖥️ Rich Terminal UI — Interactive Codebase Chat

Launch the TUI and get a split-pane interface: repo summary on the left, AI chat on the right. Ask anything about the codebase in natural language, with real-time streaming responses.

![TUI Demo](demos/tui.gif)

```bash
codecompass --repo ../copilot-sdk tui
> Explain the architecture of this codebase
```

The TUI scans the repo instantly, displays a structured summary (languages, frameworks, entry points, CI detection), and opens an interactive chat session powered by the Copilot SDK with 12 custom tools.

---

### 🔍 GitHub Intelligence — PR Details & Issue Search

Ask about pull requests and issues directly from the command line. The AI uses the `get_pr_details` and `search_issues` tools to fetch live data from the GitHub API — no manual setup required.

![GitHub Tools Demo](demos/github_tools.gif)

```bash
codecompass --repo ../copilot-sdk ask "Show me PR #464 details and search issues about BYOK"
```

In one prompt, the AI retrieves PR #464 (RPC codegen by SteveSandersonMS, merged 2026-02-13) and finds 5 BYOK-related issues — all grounded in real GitHub data, fetched automatically.

---

### 📝 AI-Powered Diff Explanation

Analyzes recent commits with full diffs, then uses the Copilot SDK to generate a human-readable summary. Perfect for catching up after time away from a project — or for generating release notes in CI.

![Diff Explain Demo](demos/diff_explain.gif)

```bash
codecompass --repo ../copilot-sdk diff-explain --commits 3
```

The AI explains **what** changed, **why** it was likely done, the **impact** on the system, and **what new developers should understand**.

---

The AI has access to **12 custom tools** in a single session:

| Tool | Purpose |
|------|---------|
| `search_git_history` | Search commit messages by keyword |
| `get_file_contributors` | Who worked on a specific file |
| `read_source_file` | Read file contents with line ranges |
| `search_code` | Grep across the repository |
| `get_architecture_summary` | High-level repo structure analysis |
| `detect_stale_docs` | Find outdated documentation |
| `get_symbol_info` | Look up classes/functions in the knowledge graph |
| `get_module_dependencies` | Module import/export relationships |
| `get_pr_details` | Fetch PR descriptions and reviews |
| `search_issues` | Search GitHub Issues for context |

---

## My Experience with GitHub Copilot CLI

Building CodeCompass with the Copilot CLI was a revelatory experience. Here's what stood out:

### What Copilot CLI Did Well

- **Planification** — It gave me a very detailed overview of the project.
- **Interactivity** — I was asked a lot of questions during planning and implementation, which really nailed the final result and made me realize I had a few design issues during the planning phase (bonus: it helped me save a few premium requests).
- **Custom tools** — This may be subjective, but I felt like the CLI supported more tools than the regular VS Code extension.
- **Demos** — The CLI even helped me create the demos, which genuinely surprised me (GIF!).

### Challenges

- **Context window limits** — As the repository grew larger, I had to go through a few iterations to clean up unused code.
- **Files navigation** — Not having a GUI made navigating files and reviewing changes a bit harder. I had to work somewhat blindly on many changes, whereas in VS Code I had much more control.

---

## Summary

CodeCompass turns any codebase into something you can *talk to*. It pre-indexes the code, builds a semantic knowledge graph, and gives the Copilot AI structured tools to answer deep questions — saving you the time and prompt engineering you'd need to get similar results from generic Copilot CLI or Chat.

**Built entirely with GitHub Copilot CLI** — from the initial scaffolding to the final polish.

- 📦 **GitHub Repository:** [https://github.com/negaga53/codecompass](https://github.com/negaga53/codecompass)
- 📄 **License:** MIT

---

*Questions or feedback? I'd love to hear from you!*