<h1 align="center"><img src="assets/scout_logo.png" alt="SCOUT Logo" width="32" style="vertical-align: middle;"> SCOUT (Open-Source)</h1>

<h3 align="center">
  Active Information Foraging for Long-Text Understanding<br>with Decoupled Epistemic States
</h3>

<p align="center">
  <a href="https://xavierzhang2002.github.io/scout-page/"><img src="https://img.shields.io/badge/Project-Page-blue?style=flat-square" alt="Project Page"></a>
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Context-1M%2B%20tokens-brightgreen?style=flat-square" alt="Context">
  <img src="https://img.shields.io/badge/Built%20on-Claude%20Agent%20SDK-orange?style=flat-square" alt="SDK">
</p>

<p align="center">
  <a href="https://xavierzhang2002.github.io/scout-page/">Paper & Project Page</a> &bull;
  <a href="#about-this-repo">About This Repo</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#configuration">Configuration</a> &bull;
  <a href="#web-ui">Web UI</a> &bull;
  <a href="#architecture">Architecture</a>
</p>

<p align="center">
  <img src="assets/overview.png" alt="SCOUT Architecture Overview">
</p>

---

## About This Repo

This is the open-source implementation of the paper *["SCOUT: Active Information Foraging for Long-Text Understanding with Decoupled Epistemic States"](https://xavierzhang2002.github.io/scout-page/)* (ICML 2026).

The SCOUT Agent in the paper is built on an enterprise-internal agent framework with no current plans for open-source release. To promote community development and reproducibility, we re-implemented SCOUT using the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) — a free, publicly available agent development framework. This repository is that open-source implementation.

The core methodology remains identical — active information foraging, decoupled epistemic states, three-phase foraging strategy, and gap-diagnosed convergence. Due to differences between agent frameworks, there are some implementation-level distinctions (e.g., behavioral enforcement via SDK Hooks instead of framework-native policies). Through testing, this open-source version achieves performance comparable to the original.

---

## Quick Start

### 1. Install

```bash
git clone https://github.com/XavierZhang2002/scout-open.git
cd scout-open

conda create -n scout python=3.12 -y
conda activate scout

pip install -r requirements.txt
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
vim config.yaml   # Fill in your API credentials
```

Minimum configuration:

```yaml
api:
  base_url: "http://localhost:3456"       # Claude Code Router (see below)
  auth_token: "your-token"
  model: "venus,deepseek-v3.1-terminus"   # "provider,model" format
```

### 3. Start Claude Code Router

Unless you are calling Anthropic API directly, you need CCR to translate the API protocol. Configure your LLM providers in `proxy/.claude-code-router/config.json` (see [proxy/README.md](proxy/README.md)), then:

```bash
cd proxy && bash deploy.bash && cd ..
```

### 4. Run

```bash
# Single query mode
python main.py --query "What is the net profit for 2023?" --cwd /path/to/docs

# With Web UI (recommended for interactive use)
cd ui && python start.py
```

**Python API:**

```python
import anyio
from scout.config import load_config
from scout.agent import query_agent

config = load_config("config.yaml")
config.cwd = "/path/to/documents"

result, tiktoken_usage, api_usage, num_turns, tool_usage = anyio.run(
    query_agent,
    "What is the main conclusion of this paper?",
    None, None, None,
    config,
)

print(f"Answer: {result}")
print(f"Turns: {num_turns}, Tokens: {tiktoken_usage}")
```

---

## Configuration

All configuration lives in a single `config.yaml` file at the project root. Copy `config.example.yaml` to get started.

| Section | Purpose |
|---------|---------|
| `api` | LLM connection (base_url, auth_token, model) |
| `eval` | Evaluation LLM (optional, for workspace_evaluate fallback) |
| `agent` | Behavior control (max_turns, planner/evaluator toggles) |
| `tools` | Tool parameters (token thresholds, tokenizer model) |
| `pricing` | Cost estimation (optional) |

### LLM Backend Options

SCOUT communicates via the **Anthropic Messages API** protocol. Since most LLM providers (DeepSeek, Qwen, GPT, Gemini, etc.) do not natively support this protocol, you need the **Claude Code Router (CCR)** to act as a translation layer — unless you are calling the Anthropic API directly.

**Option A: Claude Code Router (recommended for most users)** — A local proxy (included in `proxy/`) that translates Anthropic Messages API into OpenAI/other formats, enabling use of virtually any LLM provider:

```bash
cd proxy && bash deploy.bash   # Starts proxy on localhost:3456
```

The `model` field uses `"provider,model_name"` format for routing:
- `"venus,deepseek-v3.1-terminus"` — Route to Venus platform
- `"ds,deepseek-chat"` — Route to DeepSeek API directly
- `"openrouter,anthropic/claude-sonnet-4.5"` — Route via OpenRouter

See [proxy/README.md](proxy/README.md) for full setup guide.

**Option B: Direct Anthropic API** — If you have direct access to the Anthropic API (api.anthropic.com), you can skip CCR entirely and point `base_url` directly at it. This is the only case where CCR is not needed.

### CLI Options

| Flag | Description |
|------|-------------|
| `--config PATH` | Path to config.yaml |
| `--model MODEL` | Override model |
| `--cwd DIR` | Working directory (where documents live) |
| `--query TEXT` | Single query (omit for interactive) |
| `--max-turns N` | Maximum agent turns |
| `--no-planner` | Disable Planner SubAgent |
| `--no-evaluator` | Disable Evaluator SubAgent |

---

## Web UI

SCOUT includes a web interface for interactive document querying with real-time agent visualization. The UI server embeds the SCOUT Agent directly — no separate backend process is needed.

<p align="center">
  <img src="assets/Scout-ui.png" alt="Scout UI" width="80%">
</p>

**Prerequisites:** `config.yaml` must be configured and CCR must be running (if using non-Anthropic models) before starting the UI.

```bash
cd ui
python start.py                # http://localhost:8080
python start.py --port 9000    # Custom port
```

Features:
- File upload (.txt, .md, .json, .csv, .html, .xml, .log)
- Real-time WebSocket event stream (thinking, tool calls, results)
- Workspace viewer (inspect the agent's epistemic state)
- Configuration panel & metrics dashboard

> **Note:** The Web UI is still under active development and may contain bugs. Contributions and PRs are welcome!

---

## Architecture

```
scout-open/
├── main.py                     # CLI entry point
├── config.example.yaml         # Configuration template
├── scout/                      # Core agent package
│   ├── agent.py               # query_agent() — execution loop
│   ├── config.py              # ScoutConfig + load_config()
│   ├── mcp_server.py          # 6 MCP tools
│   ├── hooks/                 # 4 behavioral hooks
│   │   ├── read_guard.py      # Pre-read file safety check
│   │   ├── auto_record_reminder.py
│   │   ├── eval_guard.py      # Must-evaluate-before-stop
│   │   └── token_tracker.py
│   ├── prompts/               # 11 modular prompt files
│   ├── agents/                # Planner + Evaluator SubAgents
│   ├── tools/                 # Tool implementations
│   ├── sessions/              # Checkpoint/resume (optional)
│   └── permissions/           # Tool access control
├── ui/                        # Web UI (FastAPI + Vue 3)
└── proxy/                     # Claude Code Router
```

### Hooks (Behavioral Enforcement)

| Hook | Trigger | Effect |
|------|---------|--------|
| `read_guard` | Before Read/Grep | Auto-checks file size; injects warnings for large files |
| `auto_record_reminder` | After Read/Grep | Reminds agent to record findings to workspace |
| `eval_guard` | After tools + on Stop | Blocks premature stopping without sufficiency evaluation |
| `token_tracker` | After all tools | Records call counts and output sizes |

### SubAgents

- **Planner** — Analyzes the query, decomposes into sub-tasks and search strategies
- **Evaluator** — Reviews the workspace, determines if collected information is sufficient

---

## Acknowledgments

- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python) — The agent framework powering this open-source implementation
- [Claude Code Router](https://github.com/musistudio/claude-code-router) — API routing proxy (bundled in `proxy/`)

---

## Claude Code Skill (Experimental)

We are experimenting with integrating SCOUT's core capabilities into a [Claude Code Skill](https://docs.anthropic.com/en/docs/claude-code/skills) — a native slash-command plugin that lets Claude Code itself act as the reading agent, without requiring the full SDK runtime.

The skill lives in [`scout-skill/`](scout-skill/) and reimplements SCOUT's three-phase strategy (Plan → Gather → Verify) as a set of prompt modules and lightweight Python scripts that Claude Code can invoke directly.

> **Status: Under active development and testing.** The skill is not yet production-ready. Contributions, feedback, and bug reports are welcome.

---

<p align="center">
  <sub>Built for the long-context reasoning community</sub>
</p>
