# jevXagent Usage Guide

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/j1s4nn/jevXagent.git
cd jevXagent

# Install the package
pip install -e .
```

### 2. First Time Setup

Run the CLI for the first time:

```bash
python -m jevxagent
```

You'll be guided through an interactive setup:

1. **Agent Detection**: The system will scan for installed agents (Claude Code, Codex, Kilo, Cline)
2. **Agent Selection**: Choose which agent you want to use
3. **API Configuration**: 
   - Agent API key (auto-detected from agent settings if available)
   - Agent model name (e.g., `claude-sonnet-4-20250514`)
   - Jev API key
   - Jev base URL (default: `https://api.typesafe.ai/v1`)
   - Jev model (default: `jev-1`)
4. **Statistics Path**: Where to save request statistics (default: `./jevxagent_stats.jsonl`)

Configuration is saved to `~/.jevxagent/config.json`

## Using jevXagent

### Terminal 1: Start the Proxy

```bash
cd jevXagent
python -m jevxagent
```

Keep this terminal open. You'll see:
```
==================================================
jevXagent v0.2
==================================================
Mode: Project
Agent: claude-code
Agent Model: claude-sonnet-4-20250514
Jev: ON
Jev Model: jev-1
Proxy: http://127.0.0.1:9099
Stats: ./jevxagent_stats.jsonl

Ctrl+S  Save statistics snapshot
Ctrl+C  Stop jevXagent
==================================================

Configure your agent to use the proxy:
   export ANTHROPIC_BASE_URL=http://127.0.0.1:9099
   (or OPENAI_BASE_URL for OpenAI-based agents)

Proxy running. Waiting for requests...
```

### Terminal 2: Use Your Agent

**For Claude Code / Kilo:**
```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:9099
claude
```

**For Codex:**
```bash
export OPENAI_BASE_URL=http://127.0.0.1:9099
codex
```

**For Cline (VSCode):**
1. Open VSCode Settings
2. Search for "Cline API Base URL"
3. Set to: `http://127.0.0.1:9099`

Now use your agent normally! Every request will be routed through jevXagent.

## Real-Time Metrics

Each request displays metrics in Terminal 1:

```
──────────────────────────────────────────────────
Request #1 | Trace: a3f8b2c1
Jev: success | 142ms
  Tokens: in=31 out=0
Agent: 1120ms
  TTFT: 310ms
  Tokens: in=1842 out=126 total=1968
Total: 1289ms
──────────────────────────────────────────────────
```

### Understanding Metrics

- **Request #**: Sequential request counter
- **Trace**: Unique ID for this request
- **Jev**: Status and latency of Jev decision
  - success: Jev completed successfully
  - timeout: Jev timed out (failed open to agent)
  - error: Jev had an error (failed open to agent)
- **Agent**: Main LLM response time
  - TTFT: Time To First Token
  - Tokens: Input/output token counts
- **Total**: End-to-end latency

## Saving Statistics

### Manual Save (Ctrl+S)

Press `Ctrl+S` in Terminal 1 to save a statistics snapshot:

```
==================================================
STATISTICS SNAPSHOT
==================================================
Total Requests: 47
Jev Enabled: 47
Bypassed: 3
Avg Jev Latency: 128ms
Avg Total Latency: 1156ms
Saved to: ./jevxagent_stats.jsonl
==================================================
```

### Automatic Save

Statistics are automatically saved to the JSONL file after each request.

## Jev ON/OFF Toggle

To disable Jev and test without the optimization:

1. Edit `~/.jevxagent/config.json`
2. Set `"jev_enabled": false`
3. Restart jevXagent (Ctrl+C, then restart)

With Jev OFF:
- Requests go directly to the agent
- No Jev decision or context injection
- Metrics still collected for comparison

## Advanced Usage

### Custom Configuration Path

```bash
# Use a different config
export JEVXAGENT_CONFIG=/path/to/custom/config.json
python -m jevxagent
```

### Reconfigure

```bash
# Delete existing config to start fresh
rm ~/.jevxagent/config.json
python -m jevxagent
```

### Project-Specific Stats

Each project can have its own stats file:

```bash
cd project-a
python -m jevxagent  # Saves to project-a/jevxagent_stats.jsonl

cd ../project-b
python -m jevxagent  # Saves to project-b/jevxagent_stats.jsonl
```

## How Line J Works

jevXagent implements "Line J" - injecting Jev's execution context directly into agent requests:

### Without jevXagent (Slow)
```
User: "restart the pod"
  ↓
Agent: [classifies, thinks, generates code] (2-3 seconds)
  ↓
Response: Long explanation + code
```

### With jevXagent (Fast)
```
User: "restart the pod"
  ↓
Jev: [fast decision] (120ms) → "DevOps, urgent, needs kubectl script"
  ↓
Line J: Inject context into request
  ↓
Agent: [sees decisions, just generates code] (500ms)
  ↓
Response: Concise code only
```

**Token Savings**: 60-80% reduction in output tokens
**Speed**: 3x faster responses
**Cost**: Significantly lower (output tokens are 3-5x more expensive than input)

## Media Content Bypass

jevXagent automatically bypasses Jev for requests containing:
- Images (`.png`, `.jpg`, `.jpeg`)
- PDFs (`.pdf`)
- Documents (`.doc`, `.docx`)
- Keywords: "image", "screenshot"

This ensures media-heavy requests go directly to the agent without delay.

## Troubleshooting

### No agents detected
```
No supported agents found.
```

**Solution**: Install at least one supported agent (Claude Code, Codex, Kilo Code, or Cline)

### Config validation errors
```
Configuration errors:
  - Agent API key is missing
```

**Solution**: Reconfigure with valid credentials
```bash
rm ~/.jevxagent/config.json
python -m jevxagent
```

### Agent not connecting to proxy
```bash
# Verify environment variable is set
echo $ANTHROPIC_BASE_URL
# Should show: http://127.0.0.1:9099
```

### Port already in use
If port 9099 is taken, edit config and change:
```json
"proxy": {
  "port": 9100
}
```

## Statistics File Format

The `jevxagent_stats.jsonl` file contains one JSON record per line:

```json
{
  "timestamp": "2024-09-24T10:30:45.123Z",
  "trace_id": "a3f8b2c1",
  "jev_enabled": true,
  "jev_status": "success",
  "jev_latency_ms": 142,
  "jev_input_tokens": 31,
  "jev_output_tokens": 0,
  "backend_latency_ms": 18,
  "agent_called": true,
  "agent_ttft_ms": 310,
  "agent_latency_ms": 1120,
  "agent_input_tokens": 1842,
  "agent_output_tokens": 126,
  "total_latency_ms": 1289,
  "bypass": false
}
```

You can analyze this with standard tools:
```bash
# Count total requests
wc -l jevxagent_stats.jsonl

# Average latency with jq
jq -s 'map(.total_latency_ms) | add / length' jevxagent_stats.jsonl
```

## Best Practices

1. **Keep Terminal 1 Open**: The proxy must be running for agents to work
2. **Save Statistics Regularly**: Press Ctrl+S periodically to see cumulative stats
3. **Compare Jev ON vs OFF**: Test with both modes to measure actual improvements
4. **Per-Project Stats**: Use different directories for different projects
5. **Monitor Token Usage**: Check metrics to verify token savings
