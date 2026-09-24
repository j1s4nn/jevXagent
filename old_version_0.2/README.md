# jevXagent v0.2

Transparent proxy that routes AI agent prompts through Jev fast decisions before main LLM generation.

## What is Line J?

jevXagent implements **Line J** - injecting Jev's execution context directly into agent requests so the main model sees completed decisions/facts before generating. This eliminates redundant reasoning and cuts output tokens by 60-80%.

```
User Prompt
     │
     v
[ Jev Decision ] ────> 70-200ms
     │
     ├─> Backend Actions (deterministic)
     │
     v
Line J: Inject Context
     │
     v
[ Main Agent ] ────> Generation only
     │
     v
User Answer (3x faster)
```

## Installation

```bash
git clone https://github.com/j1s4nn/jevXagent-v0.2.git
cd jevXagent-v0.2
pip install -e .
```

## Quick Start

```bash
# First run - interactive setup
jevxagent

# Detects installed agents (Claude Code, Codex, Kilo, Cline)
# Prompts for:
#   - Jev API key/URL/model
#   - Agent API key/URL/model
#   - Stats save location

# Proxy starts on http://127.0.0.1:9099
```

### Configure Agent

Point your agent to use proxy:

**Claude Code / Kilo Code:**
```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:9099
```

**Codex:**
```bash
export OPENAI_BASE_URL=http://127.0.0.1:9099
```

**Cline:**
Set base URL in VSCode settings to `http://127.0.0.1:9099`

## Usage

Terminal 1 (Proxy):
```bash
jevxagent
# Runs until Ctrl+C
# Ctrl+S saves statistics snapshot
```

Terminal 2 (Agent):
```bash
claude  # or codex, kilo, cline
# Works normally, routed through Jev
```

## Real-Time Stats

Each request shows:
```
──────────────────────────────────────────────────
Trace: a3f8b2c1
Jev: success | 142ms
Agent: 1120ms
TTFT: 310ms
Total: 1289ms
──────────────────────────────────────────────────
```

## Configuration

Config stored at `~/.jevxagent/config.json`

To reconfigure:
```bash
rm ~/.jevxagent/config.json
jevxagent
```

## Architecture

- **Agent Detection**: Scans for Claude Code/Codex/Kilo/Cline installations
- **Transparent Proxy**: FastAPI server intercepts agent API calls
- **Line J Injection**: Jev context prepended as system message
- **Streaming**: Preserves SSE streaming from agent
- **Fail-Open**: Timeout/error forwards original request
- **Statistics**: JSONL append for each request

## Supported Agents

| Agent | Transport | Detection | Status |
|-------|-----------|-----------|--------|
| Claude Code | Anthropic | `~/.claude/` | ✅ |
| Codex | OpenAI | `~/.codex/` | ✅ |
| Kilo Code | Anthropic | `~/.kilo/` | ✅ |
| Cline | Anthropic | VSCode ext | ✅ |

## Jev ON/OFF

Toggle in config:
```json
{
  "jev_enabled": false
}
```

Restart proxy to apply.

## Token Savings

Line J reduces output tokens 60-80% by:
- Eliminating classification reasoning
- Skipping backend state discovery
- Cutting conversational fluff

Input tokens increase ~50 (cheap) to save ~200+ output tokens (expensive).

Net result: **Faster + Cheaper**

## Requirements

- Python 3.11+
- Jev API access
- One of: Claude Code, Codex, Kilo Code, or Cline

## License

MIT - see [LICENSE](LICENSE)
