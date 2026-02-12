# 🧭 CodeCompass

**AI-powered codebase intelligence and onboarding assistant** — built with the [GitHub Copilot SDK](https://github.com/github/copilot-sdk).

> *This is a submission for the [GitHub Copilot CLI Challenge](https://dev.to/challenges/github-2026-01-21)*

CodeCompass helps developers understand, navigate, and contribute to unfamiliar codebases by combining automated repository analysis with an AI agent powered by GitHub Copilot. It builds a semantic knowledge graph from your code and uses custom tools to let the AI answer deep questions about architecture, history, contributors, and documentation freshness.

![CodeCompass Demo](docs/demo-placeholder.png)

---

## ✨ Features

### 🔍 Intelligent Onboarding
Point CodeCompass at any repo and get an instant, structured overview:
- Detected languages, frameworks, and architecture patterns
- Directory structure with entry points and config files
- CI/CD setup, test directories, and contribution guidelines

### 💬 Multi-Turn Codebase Chat
Ask questions in natural language. The AI agent uses **10 custom tools** to ground answers in actual code:
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
- Active vs. dormant areas (bus factor detection)
- Expertise mapping based on commit history

### 📋 Documentation Freshness Audit
Detect stale documentation:
- README references to files that no longer exist
- Install instructions that don't match current dependencies
- Docstring drift from actual function signatures

### 🖥️ Rich Terminal UI
A beautiful Textual-based TUI with:
- Split-pane layout (sidebar summary + chat)
- Real-time streaming responses
- Thinking indicators during agent processing

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.10+**
- **[GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli)** installed and authenticated
- **Git** (for git history features)

### Installation

```bash
pip install -e .
```

### Usage

```bash
# Scan a repo and see the onboarding summary
codecompass onboard --repo /path/to/repo

# Onboard + start an interactive chat
codecompass onboard --repo /path/to/repo --interactive

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

# Start interactive chat mode
codecompass chat

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
│  │ Status: Connected (model: gpt-4o)            │ │
│  └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
        ↕ GitHub Copilot SDK (JSON-RPC)
┌──────────────────────────────────────────────────┐
│         Copilot CLI (server mode)                 │
│  ┌──────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ Built-in │ │ 10 Custom │ │ Knowledge Graph  │ │
│  │ Tools    │ │ Tools     │ │ + Git Analysis   │ │
│  └──────────┘ └───────────┘ └──────────────────┘ │
└──────────────────────────────────────────────────┘
```

### Custom Tools

CodeCompass extends the Copilot agent with **10 custom tools**:

| Tool | Purpose |
|------|---------|
| `search_git_history` | Search commit messages for a topic or keyword |
| `get_file_contributors` | Who worked on a specific file |
| `read_source_file` | Read file contents (with line range support) |
| `search_code` | Grep across repository source files |
| `get_architecture_summary` | High-level repo structure analysis |
| `find_related_docs` | Find documentation related to a source file |
| `detect_stale_docs` | Identify outdated documentation |
| `get_symbol_info` | Look up classes/functions in the knowledge graph |
| `get_module_dependencies` | Show module import/export relationships |
| `search_prs` | Search GitHub PRs and issues (via API) |

---

## 🔌 Copilot SDK Integration

CodeCompass deeply integrates with the [GitHub Copilot SDK](https://github.com/github/copilot-sdk):

- **`CopilotClient`** — Manages the Copilot CLI process lifecycle
- **`create_session()`** — Creates sessions with custom tools, system messages, and streaming
- **`@define_tool`** — All 10 custom tools use the SDK's Pydantic-based tool definition
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
    "model": "gpt-4o",
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
└── src/codecompass/
    ├── __init__.py                # Package metadata
    ├── __main__.py                # python -m codecompass
    ├── cli.py                     # Click CLI (8 commands)
    ├── models.py                  # Pydantic data models
    ├── agent/
    │   ├── agent.py               # Core orchestration logic
    │   ├── client.py              # Copilot SDK client wrapper
    │   ├── prompts.py             # System prompts per mode
    │   └── tools.py               # 10 custom tools for the agent
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
model = "gpt-4o"
tree_depth = 4
max_file_size_kb = 512
log_level = "WARNING"
```

Environment variables:
- `GITHUB_TOKEN` — GitHub token for API features (PR search, etc.)
- `CODECOMPASS_MODEL` — LLM model to use
- `CODECOMPASS_LOG_LEVEL` — Logging verbosity

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
