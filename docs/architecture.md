# jevXagent Architecture

## Goals

1. Transparent Anthropic-compatible proxy between an LLM agent and its API.
2. Decision routing: cheap, structured operations → JEV; everything else → Claude.
3. Evidence: every claim testable via recorded telemetry.

## Layer separation

```
Request ──► server.py (transport)
                │ /v1/messages          → adapters/anthropic.py → providers/claude.py → upstream
                │ /v1/decision          → router (classifier → policy → executor)
                │                           ├── providers/jev.py
                │                           └── providers/claude.py (fallback + baseline)
                │
                └──► telemetry (events → storage → metrics → charts/reports → CLI)
```

- **Transport layer** (`server.py`, `adapters/`, `providers/`) knows nothing
  about decisions. `/v1/messages` forwards payloads and SSE streams verbatim.
- **Decision layer** (`router/`, `context/`) never touches the main
  conversation stream. It only serves `/v1/decision`.
- **Telemetry layer** (`telemetry/`, `cli/`) observes both.

## Why the decision surface is a separate endpoint

A transparent proxy cannot reliably detect "decision operations" inside the
main agent's opaque request/response stream without rewriting the protocol
(e.g., injecting tools), which risks corrupting client state. Phase 1-3
therefore:

- keep `/v1/messages` a pure relay (Claude stays the global context owner);
- expose decision routing through `POST /v1/decision`, which any local client
  can call.

In-conversation interception is a future phase (MCP tool plugin calling
`/v1/decision`), not a transport hack.

## DecisionEvent model

`router/decision.py` — the fundamental abstraction. Fields:

```
event_id, conversation_id, request_id, context, current_operation,
candidate_action, decision_type, complexity, confidence, routing_status
```

`decision_type` is a `str`-enum (extensible). There is **no** dependency on
`<think>` tokens or any particular reasoning format.

## Routing pipeline

1. **Classifier** (`router/classifier.py`): deterministic regex/length
   heuristics infer `decision_type` and a 0..1 complexity score. Zero model
   calls — the router is always cheaper than the task it routes.
2. **Policy** (`router/policy.py`): `JEV_ENABLED` && `ROUTING_ENABLED` &&
   type ∈ `JEV_ROUTABLE_TYPES` && complexity ≤ `JEV_MAX_COMPLEXITY`.
3. **Executor** (`router/executor.py`):
   - JEV path: build a small structured prompt (context trimmed by
     `context/extractor.py`), request constrained JSON
     (`{"decision": ..., "confidence": ...}`), validate it.
   - Fallback: provider error, timeout, malformed JSON, low confidence →
     Claude (recorded with `routing_status=fallback_claude`).
4. **Telemetry**: one `DecisionRecord` per event plus a `RequestRecord`.

## Context discipline

JEV never receives the full conversation. `context/extractor.py`:

- trims to `JEV_MAX_CONTEXT_CHARS` with a visible truncation marker;
- uses a 4-chars/token budget estimate (budgeting only, never reported as a
  measured token count).

## Telemetry & evidence model

`telemetry/storage.py` keeps two tables:

- `requests`: one row per proxied request (messages + decisions) with status,
  route, latency, API-reported token usage, error;
- `decisions`: one row per decision event with routing status, confidence,
  provider latencies/tokens, fallback flag and reason.

`telemetry/metrics.py` enforces the measured/estimated split:

| Kind | Example |
|---|---|
| measured | JEV calls, Claude calls, latency, API-reported tokens, fallbacks |
| estimated | "Claude tokens avoided", "latency avoided", "cost avoided" — from historical same-category Claude decisions, or configured `CLAUDE_EST_*` / price defaults |
| unavailable | `n/a` — never invented |

Benchmark runs go to a **separate** `benchmark.db`.

## Provider abstraction

`providers/claude.py` — Anthropic-compatible Messages client (JSON + SSE,
usage parsing). `providers/jev.py` — JEV client (assumed OpenAI-compatible
chat completions until the real API is verified; see the "JEV API SUBMISSION
POINT" marker in the file).

## Adapters

`adapters/anthropic.py` owns Anthropic protocol knowledge (headers,
validation, SSE usage collection, error envelopes). An OpenAI-compatible
adapter can be added beside it when needed (e.g. for Kilo Code).

## Config

`config.py` reads env + `.env`; secrets are redacted in logs. No provider
secret is hard-coded anywhere in the source tree.

## Future work

- MCP `jevx_decide` tool → `/v1/decision` (in-conversation decisions).
- Kilo Code integration (custom base URL pointing at the proxy).
- Paired-measurement benchmark (JEV decision vs Claude baseline) via
  `jevXagent benchmark`.
