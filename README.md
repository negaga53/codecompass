# 🧭 CodeCompass

**AI-powered codebase intelligence and onboarding assistant** — built with the [GitHub Copilot SDK](https://github.com/github/copilot-sdk).

> *This is a submission for the [GitHub Copilot CLI Challenge](https://dev.to/challenges/github-2026-01-21)*

CodeCompass helps developers understand, navigate, and contribute to unfamiliar codebases by combining automated repository analysis with an AI agent powered by GitHub Copilot. It builds a semantic knowledge graph from your code and uses custom tools to let the AI answer deep questions about architecture, history, contributors, and documentation freshness.

---

## 🤷 Why CodeCompass Instead of Just Running `copilot`?

Good question. The plain Copilot CLI can answer code questions too. Here's what's **fundamentally different**:

### The Knowledge Graph Advantage

When you run CodeCompass, it **pre-indexes your codebase** (AST parsing, import tracing, symbol mapping) before the first answer. The AI then has **structured access** to information that would otherwise require many sequential file reads to reconstruct:

```
# Plain copilot CLI — "What modules depend on git.py?"
# → Needs to read every .py file, parse imports, correlate... 5-10 tool calls

# CodeCompass — same question answered instantly from the knowledge graph:
$ codecompass ask "What depends on the git module?"
# → KG returns: codecompass.cli, codecompass.ui.app, tests.test_git, tests.test_tools
#    All in ONE tool call via get_module_dependencies
```

### Concrete Use Cases Only CodeCompass Can Do

| Use Case | Plain `copilot` CLI | CodeCompass |
|----------|-------------------|-------------|
| **Generate a dependency graph artifact** | Requires manual/iterative exploration | `codecompass graph` → Mermaid diagram |
| **Export portable onboarding doc** | Can't output to file | `codecompass export -o onboard.md` |
| **Explain recent changes** | No git diff integration | `codecompass diff-explain` |
| **Find who owns a file** | No git blame tools | `get_file_contributors` tool (instant) |
| **Trace module dependencies** | Read files manually | `get_module_dependencies` (from KG) |
| **Detect stale documentation** | Manual comparison | `detect_stale_docs` (auto cross-ref) |
| **Full repo onboarding** | Start from scratch each time | `codecompass onboard` (instant scan) |
| **Architecture with context** | Generic prompt | Domain-specific prompts + pre-built KG |

### The Tool Arsenal

CodeCompass gives the AI **12 specialized tools** in a single session — git history search, commit file listing, contributor analysis, code search, symbol lookup, dependency tracing, doc staleness detection, and GitHub PR/issue context.

### Auto-Context Injection

CodeCompass AI chat flows automatically prepare repository context before response generation. For local-only commands (like `graph` or `export`), context is built as needed by that command.

### Performance Notes

- Indexing time depends on repository size, hardware, and filesystem speed.
- On this repository, indexing is typically near-instant; larger monorepos will take longer.
- For reproducible demos, prefer deterministic outputs like `codecompass graph -o deps.md` and `codecompass export -f json`.

---

## ✨ Features

### 🔍 Intelligent Onboarding
Point CodeCompass at any repo and get an instant, structured overview:
- Detected languages, frameworks, and architecture patterns
- Directory structure with entry points and config files
- CI/CD setup, test directories, and contribution guidelines

### 💬 Multi-Turn Codebase Chat
Ask questions in natural language. The AI agent uses **12 custom tools** to ground answers in actual code:
- Read and search source files
- Search git commit history
- Analyze contributor patterns
- Query the knowledge graph for symbol/import relationships

### 🤔 "Why" Investigation Mode
Ask *why* a design decision was made. The agent reconstructs the narrative by:
- Searching commit messages and PR descriptions
- Analyzing git blame
- Cross-referencing documentation
- Providing citations with commit hashes and timestamps

### 🏗️ Architecture Explorer
Get AI-generated architecture analysis including:
- Component responsibilities and communication patterns
- Module dependency graphs
- Design pattern identification
- Layer boundary analysis

### 👥 Contributor Intelligence
Answer "Who should I ask about X?" by analyzing:
- Per-file and per-directory contribution stats
- Commit recency and ownership signals from git history
- Expertise hints based on touched files and commit history

### 📋 Documentation Freshness Audit
Detect stale documentation:
- README references to files that no longer exist
- Install instructions that don't match current dependencies
- Mismatches between documented commands and repository setup

### 📊 Export
Generate portable onboarding documents or structured data:
- `codecompass export --format=markdown` — full Markdown onboarding guide
- `codecompass export --format=json` — structured JSON knowledge graph

### 🕸️ Dependency Graph
Generate visual module dependency diagrams:
- `codecompass graph` — Mermaid flowchart of internal module dependencies
- `codecompass graph -f text` — plain text dependency listing
- `codecompass graph -o deps.md` — save to file for embedding in docs

### 📝 Diff Explain
AI-powered explanation of recent code changes:
- Analyzes the last N commits with full diffs
- Explains WHAT changed, WHY, and the impact
- Perfect for catching up after time away from a project

### 🖥️ Rich Terminal UI
A beautiful Textual-based TUI with:
- Split-pane layout (sidebar summary + chat)
- Real-time streaming responses
- Thinking indicators during agent processing
- **Settings panel** (Ctrl+S) — edit model, log level, tree depth inline

### ⚙️ Configuration Management
Generate and edit `.codecompass.toml` config files from the CLI or TUI:
- `codecompass config init` — interactive wizard to create a config file
- `codecompass config show` — display resolved settings with source attribution
- `codecompass config set model gpt-4.1` — update a single setting
- `codecompass config path` — show config file location
---

## 🚀 Quick Start

### One-Line Setup

**Linux / macOS:**
```bash
git clone https://github.com/negaga53/codecompass && cd codecompass && bash setup.sh
```

**Windows (PowerShell):**
```powershell
git clone https://github.com/negaga53/codecompass; cd codecompass; .\setup.ps1
```

The interactive setup script will:
1. Check prerequisites (Python 3.10+, Git)
2. Create a virtual environment
3. Install CodeCompass and all dependencies
4. Guide you through GitHub Copilot authentication (OAuth device-flow)
5. Show example commands to get started

---

### Manual Installation

### Prerequisites

- **Python 3.10+**
- **Git** (for git history features)
- A **GitHub account with Copilot access**

### Installation

```bash
pip install -e .
```

### Authentication

CodeCompass uses the GitHub Copilot SDK, which requires authentication via the bundled Copilot CLI. Run the device-flow login once:

```bash
# One-time login (opens browser for GitHub OAuth)
python -c "import copilot; import pathlib; print(pathlib.Path(copilot.__file__).parent / 'bin')"
# Then run: <path>/copilot login
```

Or simply run `codecompass onboard` — if you're not authenticated, it will prompt you.

> **Note**: Personal Access Tokens (PATs) are **not supported** by the Copilot API. You must use the OAuth device-flow login.
>
> Optional GitHub API features (PR/issue lookup) can still use `GITHUB_TOKEN` when configured.

### Usage

```bash
# Scan a repo and see the onboarding summary
codecompass --repo /path/to/repo onboard

# Onboard + start an interactive chat
codecompass onboard --interactive

# Ask a question
codecompass ask "How does authentication work in this project?"

# Ask WHY something exists
codecompass why "Why was Redis added as a dependency?"

# Explore architecture
codecompass architecture

# See contributor intelligence
codecompass contributors

# Audit documentation freshness
codecompass audit

# Export onboarding document
codecompass export --format markdown -o onboarding.md

# Export knowledge graph as JSON
codecompass export --format json -o knowledge.json

# Generate a dependency graph (Mermaid diagram)
codecompass graph

# Generate dependency graph as plain text
codecompass graph -f text -o deps.txt

# AI explanation of recent changes
codecompass diff-explain

# Explain the last 10 commits
codecompass diff-explain -n 10

# Start interactive chat mode
codecompass chat

# Print a deterministic judge demo flow
codecompass demo

# See which commands may consume Copilot premium requests
codecompass premium-usage

# Launch the full TUI
codecompass tui
```

---

## 🏗️ Architecture

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
│  │              │  │  Found PR #42...          │  │
│  └─────────────┘  └───────────────────────────┘  │
│  ┌──────────────────────────────────────────────┐ │
│  │ Status: Connected (model: gpt-4.1)           │ │
│  └──────────────────────────────────────────────┘ │
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

### Custom Tools

CodeCompass extends the Copilot agent with **12 custom tools**:

| Tool | Purpose |
|------|---------|
| `search_git_history` | Search commit messages for a topic or keyword |
| `get_commit_files` | List all files changed in a specific commit |
| `get_file_contributors` | Who worked on a specific file |
| `read_source_file` | Read file contents (with line range support) |
| `search_code` | Grep across repository source files |
| `get_architecture_summary` | High-level repo structure analysis |
| `find_related_docs` | Find documentation related to a source file |
| `detect_stale_docs` | Identify outdated documentation |
| `get_symbol_info` | Look up classes/functions in the knowledge graph |
| `get_module_dependencies` | Show module import/export relationships |
| `get_pr_details` | Fetch PR descriptions, reviews, and comments |
| `search_issues` | Search GitHub Issues for context |

---

## 🔌 Copilot SDK Integration

CodeCompass deeply integrates with the [GitHub Copilot SDK](https://github.com/github/copilot-sdk):

- **`CopilotClient`** — Manages the Copilot CLI process lifecycle
- **`create_session()`** — Creates sessions with custom tools, system messages, and streaming
- **`@define_tool`** — All 12 custom tools use the SDK's Pydantic-based tool definition
- **Streaming** — Real-time `assistant.message_delta` events for responsive UX
- **Multi-turn** — Persistent sessions maintain conversation context across turns
- **Session hooks** — Custom event handlers for the agent lifecycle

```python
from copilot import CopilotClient, define_tool
from pydantic import BaseModel, Field

class SearchGitHistoryParams(BaseModel):
    query: str = Field(description="Search term for commit messages")

@define_tool(description="Search git commit history")
async def search_git_history(params: SearchGitHistoryParams) -> str:
    commits = git_ops.search_log(query=params.query)
    return format_commits(commits)

# Create session with custom tools
client = CopilotClient()
session = await client.create_session({
    "model": "gpt-4.1",
    "streaming": True,
    "tools": [search_git_history],
    "system_message": {"content": ONBOARDING_PROMPT},
})
```

---

## 📁 Project Structure

```
codecompass/
├── pyproject.toml                 # Project config + dependencies
├── README.md                      # This file
├── LICENSE                        # MIT License
├── setup.sh                       # Interactive setup (Linux/macOS)
├── setup.ps1                      # Interactive setup (Windows)
└── src/codecompass/
    ├── __init__.py                # Package metadata
    ├── __main__.py                # python -m codecompass
    ├── cli.py                     # Click CLI (14 commands)
    ├── models.py                  # Pydantic data models
    ├── agent/
    │   ├── agent.py               # Core orchestration logic
    │   ├── client.py              # Copilot SDK client wrapper
    │   ├── prompts.py             # System prompts per mode
    │   └── tools.py               # 12 custom tools for the agent
    ├── github/
    │   ├── client.py              # GitHub REST API client
    │   └── git.py                 # Local git operations (subprocess)
    ├── indexer/
    │   ├── scanner.py             # Repo structure scanner
    │   └── knowledge_graph.py     # AST-based Python symbol graph
    ├── ui/
    │   ├── app.py                 # Textual TUI application
    │   └── widgets.py             # Custom TUI widgets
    └── utils/
        ├── config.py              # Settings management
        └── formatting.py          # Rich output formatting
```

---

## ⚙️ Configuration

CodeCompass can be configured via environment variables or a `.codecompass.toml` file:

```toml
# .codecompass.toml
[codecompass]
model = "gpt-4.1"
tree_depth = 4
max_file_size_kb = 512
log_level = "WARNING"
premium_usage_warnings = true
```

Environment variables:
- `CODECOMPASS_MODEL` — LLM model to use (default: `gpt-4.1`)
- `CODECOMPASS_LOG_LEVEL` — Logging verbosity
- `CODECOMPASS_PREMIUM_USAGE_WARNINGS` — Show/hide premium usage warnings (`true`/`false`)
- `GITHUB_TOKEN` — GitHub token for API features (PR/issue search)

To disable warnings from config:

```bash
codecompass config set premium_usage_warnings false
```

---

## 🛠️ Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/
```

---

## 📄 License

MIT — see [LICENSE](LICENSE).

---

## 🙏 Acknowledgments

- [GitHub Copilot SDK](https://github.com/github/copilot-sdk) — The agentic runtime powering CodeCompass
- [Textual](https://github.com/Textualize/textual) — Beautiful terminal UI framework
- [Rich](https://github.com/Textualize/rich) — Terminal formatting
- [Click](https://github.com/pallets/click) — CLI framework
