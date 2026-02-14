---
title: 🧭 CodeCompass — AI-Powered Codebase Intelligence Built with the Copilot SDK
published: true
tags: devchallenge, githubchallenge, cli, githubcopilot
---

*This is a submission for the [GitHub Copilot CLI Challenge](https://dev.to/challenges/github-2026-01-21)*

## What I Built

**CodeCompass** is an AI-powered codebase intelligence and onboarding assistant that helps developers understand, navigate, and contribute to unfamiliar codebases — instantly.

Point it at any repository, and it:
- **Scans and indexes** the codebase (languages, frameworks, entry points, structure)
- **Builds a knowledge graph** from AST parsing, import tracing, and symbol mapping
- **Answers questions** grounded in actual code, git history, and contributor data
- **Generates artifacts** like dependency diagrams, onboarding docs, and change summaries

Unlike just running `copilot` in a terminal, CodeCompass gives the AI **12 custom tools** and a **pre-built knowledge graph** — so answers come from structured data instead of sequential file reads.

I built this because every time I join a new project or revisit an old one, I spend hours reading READMEs, tracing imports, and asking "who owns this file?" CodeCompass compresses that entire onboarding process into seconds.

### Key Features

| Feature | What It Does |
|---------|-------------|
| **Instant Onboarding** | Scans any repo — detects languages, frameworks, CI, entry points, test dirs |
| **Dependency Graph** | Generates Mermaid diagrams of module dependencies from AST analysis |
| **Diff Explain** | AI-powered analysis of recent commits — WHAT changed, WHY, and the impact |
| **Natural Language Q&A** | Ask questions about the codebase; AI uses 12 custom tools to find answers |
| **Export** | Generate portable Markdown or JSON onboarding documents |
| **Doc Freshness Audit** | Detect stale documentation that no longer matches the code |
| **Contributor Intelligence** | Find who owns a file, who's active, who to ask about X |
| **Rich TUI** | Textual-based split-pane interface with streaming AI responses |
| **Configuration** | `.codecompass.toml` with interactive wizard, env vars, CLI flags |

### Technologies

- **Python** (Click CLI, Pydantic models, asyncio)
- **[GitHub Copilot SDK](https://github.com/github/copilot-sdk)** — the agentic runtime (JSON-RPC, streaming, custom tools)
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

Ask about pull requests and issues directly from the command line. The AI uses the `get_pr_details` and `search_issues` tools to fetch live data from the GitHub API.

![GitHub Tools Demo](demos/github_tools.gif)

```bash
codecompass --repo ../copilot-sdk ask "Show me PR #464 details and search issues about BYOK"
```

In one prompt, the AI retrieves PR #464 (RPC codegen by SteveSandersonMS, merged 2026-02-13) and finds 5 BYOK-related issues — all grounded in real GitHub data.

---

### 📝 AI-Powered Diff Explanation

Analyzes recent commits with full diffs, then uses the Copilot SDK to generate a human-readable summary. Perfect for catching up after time away from a project.

![Diff Explain Demo](demos/diff_explain.gif)

```bash
codecompass --repo ../copilot-sdk diff-explain -n 3
```

The AI explains **what** changed, **why** it was likely done, the **impact** on the system, and **what new developers should understand**.

---

### The Knowledge Graph Advantage

This is what makes CodeCompass different from just asking `copilot` a question:

```
# Plain copilot CLI — "What modules depend on git.py?"
# → Needs to read every .py file, parse imports, correlate... 5-10 tool calls

# CodeCompass — same question, answered instantly from the knowledge graph:
$ codecompass ask "What depends on the git module?"
# → KG returns: cli, ui.app, tests.test_git, tests.test_tools
#   All in ONE tool call via get_module_dependencies
```

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

### The SDK Made It Possible

CodeCompass is built on the **[GitHub Copilot SDK](https://github.com/github/copilot-sdk)** — the Python SDK that provides programmatic access to the same Copilot engine. The `@define_tool` decorator with Pydantic models made it trivial to expose my knowledge graph operations as tools the AI can call:

```python
from copilot import CopilotClient, define_tool
from pydantic import BaseModel, Field

class GetModuleDepsParams(BaseModel):
    module: str = Field(description="Module name to look up")

@define_tool(description="Show module import/export relationships")
async def get_module_dependencies(params: GetModuleDepsParams) -> str:
    deps = knowledge_graph.dependencies(params.module)
    return format_dependencies(deps)
```

The SDK handles JSON-RPC communication, streaming, tool invocation, and session management — I focused entirely on the domain logic.

### What Copilot CLI Did Well

- **Streaming responses** feel natural — the TUI and CLI both show text appearing word-by-word
- **Multi-turn conversations** maintain context across questions in chat mode
- **Custom tools** are the killer feature — the AI becomes genuinely useful when it can query structured data instead of guessing
- **The permission model** (asking before running sensitive commands) builds trust

### Challenges

- **Context window limits** with large repos — I had to be strategic about what context to inject
- **Balancing local vs. AI** — some features (onboard, graph, export) are intentionally local-only and deterministic, which makes them reliable and fast

### Architecture

```
┌──────────────────────────────────────────────────┐
│            CodeCompass TUI (Textual)              │
│  ┌─────────────┐  ┌───────────────────────────┐  │
│  │  Repo        │  │  Copilot Agent Chat       │  │
│  │  Summary     │  │  (streaming responses)    │  │
│  │              │  │                           │  │
│  │  Languages   │  │  > Why did we add Redis?  │  │
│  │  Frameworks  │  │                           │  │
│  │  Structure   │  │  Searching git history... │  │
│  └─────────────┘  └───────────────────────────┘  │
└──────────────────────────────────────────────────┘
        ↕ GitHub Copilot SDK (JSON-RPC)
┌──────────────────────────────────────────────────┐
│         Copilot CLI (server mode)                 │
│  ┌──────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ Built-in │ │ 12 Custom │ │ Knowledge Graph  │ │
│  │ Tools    │ │ Tools     │ │ + Git Analysis   │ │
│  └──────────┘ └───────────┘ └──────────────────┘ │
└──────────────────────────────────────────────────┘
```

---

## Summary

CodeCompass turns any codebase into something you can *talk to*. It pre-indexes the code, builds a semantic knowledge graph, and gives the Copilot AI structured tools to answer deep questions about architecture, history, contributors, and documentation freshness.

**Built entirely with the GitHub Copilot CLI and SDK** — from the initial scaffolding to the final polish.

- 📦 **GitHub Repository:** [https://github.com/negaga53/codecompass](https://github.com/negaga53/codecompass)
- 📄 **License:** MIT

---

*Questions or feedback? I'd love to hear from you!*
