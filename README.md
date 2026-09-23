# jevXagent — When JEV Meets LLM Agent

A local LLM proxy that sits between an LLM agent (e.g. **Claude Code**) and its
primary LLM API. The primary model (Claude) keeps **global context** and does
**complex reasoning**; a fast auxiliary model (**JEV**) acts as a
**decision coprocessor** for suitable low-complexity operations.

> **Status:** Phase 1 (transparent proxy) **works** and is verified against a
> real Claude Code session. Decision routing, telemetry and statistics are
> implemented; **JEV is OFF by default** until a real JEV API key is available.
> All savings claims are **hypotheses to be measured** — nothing is invented.

---

## Table of contents

1. [The problem](#the-problem)
2. [The core idea](#the-core-idea)
3. [Architecture](#architecture)
4. [Current status — what works today](#current-status)
5. [Quickstart — step-by-step](#quickstart)
6. [Configuration reference](#configuration)
7. [JEV integration (when you get a real API key)](#jev-integration)
8. [Decision routing API](#decision-routing-api)
9. [Statistics CLI](#statistics-cli)
10. [Benchmark mode](#benchmark-mode)
11. [Testing](#testing)
12. [Security](#security)
13. [Project structure](#project-structure)
14. [Roadmap](#roadmap)
15. [Troubleshooting](#troubleshooting)
16. [License](#license)

---

## The problem

An agentic workflow (coding, research, automation) is not one giant reasoning
operation. It is a long sequence of **many small decisions**:

- What is this object?
- Which category / option / tool / connector / argument?
- Is this result relevant? Did the tool return what I expected?
- Should I continue? What should happen next?
- Does this satisfy the requirement? Is this result valid?

Today every one of those micro-decisions is handled by the primary model —
the most expensive, most capable model in the pipeline.

## The core idea

> **Claude = global context owner and deep reasoner.
> JEV = high-speed decision coprocessor.
> jevXagent = middleware that routes each operation to the right model.**

```
LLM Agent (e.g. Claude Code)
   │
   ▼
jevXagent Proxy ── detect / extract context / decide routing
   │
   ├──► JEV      fast, simple decisions (structured YES/NO, choice, label)
   └──► Claude   complex reasoning, planning, coding, synthesis
```

### Research hypothesis (to be tested, not assumed)

> Agentic LLM workflows contain a large number of low-complexity decision
> operations that do not necessarily require the primary high-capability
> model. A fast auxiliary model may handle a substantial subset of them,
> reducing latency and expensive-model usage while preserving overall task
> quality.

jevXagent is the instrument used to **test** that hypothesis. The statistics
layer exists so you can answer — with recorded data — whether routing actually
made your agent faster or cheaper. Every estimated number is labelled as an
estimate; every measured number comes from a real recorded call.

## Architecture

```
                        ┌──────────────────────────────┐
 Claude Code ──────────►│ jevXagent (FastAPI + httpx) │
   (Anthropic API)      │                              │
                        │  /v1/messages  transparent   │──► Claude API
                        │               relay (SSE)    │
                        │                              │
                        │  /v1/decision  router        │──► JEV   (fast decisions)
                        │               + fallback ────┘──► Claude (fallback/baseline)
                        │                              │
                        │  telemetry store (SQLite)    │
                        │  statistics CLI              │
                        └──────────────────────────────┘
```

Design principles (enforced in code):

1. **The primary model keeps global context.** JEV never receives the full
   conversation — only a small, trimmed decision context
   (`src/jevxagent/context/extractor.py`).
2. **Transport and routing are separated.** `/v1/messages` is a pure relay and
   never touches the router; routing happens on the dedicated `/v1/decision`
   surface.
3. **Fail safely.** JEV uncertain / timeout / malformed output / complex task
   → **Claude**. Correctness first, latency/cost second.
4. **The router is cheaper than the task.** Routing decisions use deterministic
   regex/length heuristics — no model call is made to decide routing.
5. **No `<think>`-format dependence.** The internal abstraction is the
   *decision event*, not a particular reasoning format.

## Current status

| Area | Status |
|---|---|
| Transparent Anthropic-compatible proxy (`/v1/messages`, SSE streaming) | ✅ **Working**, verified with a real Claude Code session |
| Telemetry: request + decision records (latency, API-reported tokens, fallbacks) | ✅ Working |
| Statistics CLI dashboard, charts, export, report, reset | ✅ Working |
| Decision routing endpoint `/v1/decision` (Claude path live-tested) | ✅ Working |
| JEV provider | ⏸ Implemented, **disabled** — waiting for a real JEV API |
| Benchmark mode | ✅ Implemented (requires configured providers) |
| In-conversation interception (MCP tool) | 📋 Planned, see [Roadmap](#roadmap) |
| Kilo Code support | 📋 Planned, see [Roadmap](#roadmap) |

## Quickstart

Requirements: Python 3.11+, and a Claude Code installation.

### 1. Get the code

```bash
git clone https://github.com/j1s4nn/jevXagent.git
cd jevXagent
```

### 2. Create a virtual environment and install

```bash
python -m venv .venv
```

Windows (PowerShell):

```powershell
.\.venv\Scripts\activate
python -m pip install -e ".[dev]"
```

macOS / Linux:

```bash
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Configure secrets

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```ini
CLAUDE_API_KEY=your-claude-api-key
CLAUDE_BASE_URL=https://your-anthropic-compatible-api.example.com
```

`.env` is gitignored — it is **never** committed.

### 4. Start the proxy

```powershell
jevXagent serve
```

You should see:

```text
jevXagent 0.1.0 listening on http://127.0.0.1:8787
  upstream Claude API : https://your-api.example.com
  JEV enabled         : False
  routing enabled     : False
```

### 5. Point Claude Code at the proxy

Edit `C:\Users\<you>\.claude\settings.json` (macOS/Linux:
`~/.claude/settings.json`) and change **only** the `env` block:

```json
"env": {
  "ANTHROPIC_API_KEY": "jevx-local-proxy",
  "ANTHROPIC_BASE_URL": "http://127.0.0.1:8787",
  "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"
}
```

**Make a backup first:**

```powershell
Copy-Item $env:USERPROFILE\.claude\settings.json $env:USERPROFILE\.claude\settings.backup.json
```

How authentication works: Claude Code sends `ANTHROPIC_API_KEY` as the
`x-api-key` header. The proxy **replaces it** with the real `CLAUDE_API_KEY`
from its `.env` before forwarding upstream. If `CLAUDE_API_KEY` is empty, the
proxy forwards the client's key unchanged (transparent behavior). If neither
exists, the proxy returns a 401.

To revert: restore the backup file.

### 6. Verify

```powershell
curl.exe http://127.0.0.1:8787/healthz
```

Then just use Claude Code normally:

```powershell
claude -p "Reply with exactly: CC_OK"
```

If Claude Code answers, the proxy is working.

## Configuration

All configuration is environment-based (`.env` supported). See
`.env.example` for the full list.

| Variable | Default | Description |
|---|---|---|
| `CLAUDE_API_KEY` | — | Upstream Claude API key (overrides client-sent key) |
| `CLAUDE_BASE_URL` | `https://api-cc.freemodel.dev` | Anthropic-compatible upstream base URL |
| `CLAUDE_TIMEOUT_S` | `300` | Upstream request timeout |
| `JEV_API_KEY` | — | JEV API key (see below) |
| `JEV_BASE_URL` | — | JEV API base URL |
| `JEV_MODEL` | `jev` | JEV model id |
| `PROXY_HOST` / `PROXY_PORT` | `127.0.0.1` / `8787` | Proxy bind address |
| `JEV_ENABLED` | `false` | Allow JEV routing |
| `ROUTING_ENABLED` | `false` | Enable decision routing |
| `JEV_ROUTABLE_TYPES` | (list) | Decision types allowed to route to JEV |
| `JEV_TIMEOUT_S` | `3.0` | JEV timeout (fallback to Claude on timeout) |
| `JEV_MAX_RETRIES` | `1` | JEV retries |
| `JEV_CONFIDENCE_THRESHOLD` | `0.80` | Minimum JEV confidence, else fallback |
| `JEV_MAX_CONTEXT_CHARS` | `4000` | Max context characters sent to JEV |
| `JEV_MAX_COMPLEXITY` | `0.60` | Above this complexity → always Claude |
| `LOG_LEVEL` | `INFO` | Log level |
| `DEBUG_REQUESTS` | `false` | Verbose request logging |
| `DATA_DIR` | `<repo>/data` | Telemetry database location |
| `STORE_PROMPTS` / `STORE_RESPONSES` / `STORE_DECISION_CONTEXT` | `false` | Privacy switches (metadata-only by default) |
| `CLAUDE_*_PRICE_PER_MTOK` / `JEV_*_PRICE_PER_MTOK` | — | Per-1M-token prices for **estimated** cost |
| `CLAUDE_EST_*` | — | Configured baseline estimates (used only when no historical data exists) |

## JEV integration

JEV is not yet reachable: at the time of writing the JEV server has no login
system, so the `JEV_API_KEY` in `.env` is a **placeholder**
(`aaaaaabbbbbbbcccccccddddddeeeeeeffffff`).

When you receive a real JEV API key:

1. Open `.env` and set `JEV_API_KEY`, `JEV_BASE_URL`, `JEV_MODEL`.
2. Open [`src/jevxagent/providers/jev.py`](src/jevxagent/providers/jev.py)
   — the **"JEV API SUBMISSION POINT"** is marked at the top of the file.
   It currently assumes an OpenAI-compatible
   `POST {JEV_BASE_URL}/v1/chat/completions` with
   `Authorization: Bearer <key>`. **Verify this against the real JEV docs**
   and adjust `build_request()` / `_parse()` if the protocol differs.
3. Set `JEV_ENABLED=true` and `ROUTING_ENABLED=true` in `.env`.
4. Test connectivity directly:

   ```powershell
   curl.exe http://127.0.0.1:8787/healthz
   # jev_configured should become true
   ```

## Decision routing API

The proxy exposes a dedicated decision endpoint (independent from the main
conversation — Claude's context is never touched):

```http
POST /v1/decision
Content-Type: application/json

{
  "question": "Is this a GitHub repository URL?",
  "context": "The user supplied: https://github.com/j1s4nn/jevXagent",
  "options": [],
  "format": "yesno",
  "decision_type": ""
}
```

| Field | Meaning |
|---|---|
| `question` | The decision question (required) |
| `context` | Optional supporting context (trimmed before JEV) |
| `options` | Optional list of choices (multiple-choice routing) |
| `format` | `decision` (default), `yesno`, `choice`, `label` |
| `decision_type` | Optional explicit type; if empty, inferred deterministically |

Response:

```json
{
  "decision": "YES",
  "confidence": 0.98,
  "provider": "jev",
  "fallback": false,
  "routing_status": "routed_jev",
  "decision_type": "url_classification",
  "complexity": 0.0,
  "latency_ms": 23.1,
  "request_id": "..."
}
```

### Decision types

`classification`, `selection`, `routing`, `verification`, `relevance`,
`tool_selection`, `entity_identification`, `simple_comparison`,
`simple_extraction`, `simple_transformation`, `next_action`,
`binary_decision`, `multiple_choice`, `url_classification`, `other`
(extensible — see `src/jevxagent/telemetry/events.py`).

### Fallback rules

JEV is used only when **all** of these hold:

- `JEV_ENABLED=true` and `ROUTING_ENABLED=true`
- the decision type is in `JEV_ROUTABLE_TYPES`
- the deterministic complexity score ≤ `JEV_MAX_COMPLEXITY`

and the JEV response:

- parses as valid JSON with a `decision` field
- has `confidence` ≥ `JEV_CONFIDENCE_THRESHOLD`
- arrives before `JEV_TIMEOUT_S`

In **every** other case the decision is handled by Claude. Quality first.

## Statistics CLI

The evidence layer. Every number comes from the telemetry store.

```powershell
jevXagent statistics          # dashboard (all time)
jevXagent stats               # alias
jevXagent statistics --today  # calendar day
jevXagent statistics --7d
jevXagent statistics --30d
jevXagent statistics --all
```

```text
╔═══════════════════════════════════════════════════════╗
║                  jevXagent Statistics                 ║
╠═══════════════════════════════════════════════════════╣
║ Total decision events                    0            ║
║ JEV handled                              0            ║
║ Claude handled                           0            ║
║ JEV fallback                             0            ║
║ JEV routing rate                        n/a           ║
╠═══════════════════════════════════════════════════════╣
║ Messages proxied (via Claude)            2            ║
║ ...                                                     ║
╚═══════════════════════════════════════════════════════╝
```

Options:

| Flag | Effect |
|---|---|
| `--report` | Full report including a **measurement methodology** section |
| `--save [PATH]` | Save charts (SVG) + raw CSV/JSON (default `./stats`, timestamped files) |
| `--export csv\|json` | Export the actual recorded events |
| `--reset` | Delete all telemetry (requires `--yes` when not interactive) |

### Measured vs estimated

- **Measured:** provider calls, latency, API-reported tokens, fallbacks, errors.
- **Estimated:** `Estimated Claude tokens avoided`, `Estimated latency
  avoided`, `Estimated cost avoided` — computed from historical Claude
  decisions of the same category, or from configured `CLAUDE_EST_*` / price
  defaults. Marked with `*` in the dashboard and never presented as
  measurements.
- **Unavailable:** shown as `n/a` — nothing is invented. If the API does not
  report token counts, the dashboard says so.

## Benchmark mode

Controlled comparison of **Claude-only** vs **JEV-routed** decisions on a test
set (JSONL). Benchmark data is stored in a **separate** database
(`data/benchmark.db`) and is never mixed with production statistics.

```powershell
jevXagent benchmark --set examples/benchmark_sample.jsonl
jevXagent benchmark --mode claude-only
jevXagent benchmark --mode jev-routed
```

It reports per-item latency, route, and agreement between the Claude baseline
and the routed decision (or against an `expected` field when provided).

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The test suite uses in-memory fake upstreams — **no network calls and no API
keys are used**. It covers the transparent relay (JSON + SSE), header/auth
behavior, error relay, JEV routing and every fallback path, telemetry
aggregation, and the CLI.

## Security

- API keys live in `.env` (gitignored) — never committed, never logged.
- Structured logs redact every secret-like field (`x-api-key`,
  `authorization`, …); token-count fields are not treated as secrets.
- Telemetry stores metadata only. Full prompts/responses are not stored unless
  explicitly enabled via `STORE_PROMPTS` / `STORE_RESPONSES` /
  `STORE_DECISION_CONTEXT`.
- The proxy binds to `127.0.0.1` by default.

## Project structure

```text
jevXagent/
├── src/jevxagent/
│   ├── server.py            # FastAPI app: relay + decision endpoint
│   ├── config.py            # env-based configuration, secret redaction
│   ├── logging_setup.py     # structured JSON logging
│   ├── __main__.py          # CLI entry point
│   ├── adapters/
│   │   └── anthropic.py     # Anthropic protocol knowledge (more adapters can be added)
│   ├── providers/
│   │   ├── claude.py        # upstream Messages client (streaming)
│   │   └── jev.py           # JEV client — marked "JEV API SUBMISSION POINT"
│   ├── router/
│   │   ├── decision.py      # DecisionEvent abstraction
│   │   ├── classifier.py    # deterministic type + complexity inference
│   │   ├── policy.py        # conservative routing policy
│   │   └── executor.py      # JEV/Claude execution with fallback
│   ├── context/
│   │   └── extractor.py     # small-context extraction for JEV
│   ├── telemetry/
│   │   ├── events.py        # RequestRecord / DecisionRecord
│   │   ├── storage.py       # SQLite store
│   │   ├── metrics.py       # measured vs estimated aggregation
│   │   ├── charts.py        # text + SVG charts
│   │   └── reports.py       # report generation
│   └── cli/
│       ├── statistics.py    # jevXagent statistics
│       └── benchmark.py     # jevXagent benchmark
├── tests/                   # 80+ tests, no network
├── examples/benchmark_sample.jsonl
├── docs/architecture.md
├── docs/PHASE_LOG.md
├── .env.example             # placeholders only
└── pyproject.toml
```

## Roadmap

1. **Real JEV API** — fill in `JEV_API_KEY` / `JEV_BASE_URL`, verify the
   protocol in `providers/jev.py`, enable routing, and run the decision tests
   live.
2. **In-conversation interception** — expose a `jevx_decide` tool via a small
   MCP server plugin so an agent can call JEV decisions mid-conversation
   through `/v1/decision` (the current safe integration point).
3. **Kilo Code support** — inspect Kilo Code's provider/base-URL configuration
   and, if it supports a custom Anthropic-compatible base URL, point it at
   `http://127.0.0.1:8787`. The provider/adapter layers were built for this.
4. **Benchmark evidence** — run the controlled benchmark and answer, with
   data: *how many decision operations can safely be delegated to JEV?*

## Troubleshooting

| Symptom | Fix |
|---|---|
| `claude` fails to start / connection refused | Proxy not running — start with `jevXagent serve` |
| 401 from the proxy | `CLAUDE_API_KEY` empty in `.env` **and** no `x-api-key` sent |
| 502 from the proxy | Upstream unreachable — check `CLAUDE_BASE_URL` |
| `JEV is not configured` in benchmark | Set `JEV_API_KEY` + `JEV_BASE_URL` in `.env` |
| Statistics empty | No traffic through the proxy yet — data is recorded per request |
| Box-drawing characters look wrong | Use Windows Terminal; the CLI forces UTF-8 output |
| Revert everything | Restore `settings.backup.json` over `settings.json` |

## License

MIT — see [LICENSE](LICENSE).
