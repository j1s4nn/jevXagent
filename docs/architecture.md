# jevXagent Architecture

## Goals

1. Transparent Anthropic-compatible proxy between an LLM agent and its API.
2. Decision routing: cheap, structured operations → JEV; everything else → Claude.
3. Evidence: every claim testable via recorded telemetry.

## Layer separation

```
Request ──► server.py (transport)
                │ /v1/messages          → adapters/anthropic.py → providers/claude.py → upstream
                │                           └─► intercept observable decision events
                │                               (router/interceptor.py → executor → JEV)
                │ /v1/decision          → router (classifier → policy → executor)
                │                           ├── providers/jev.py
                │                           └── providers/claude.py (fallback + baseline)
                │
                └──► telemetry (events → storage → metrics → charts/reports → CLI)
```

- **Transport layer** (`server.py`, `adapters/`, `providers/`) relays `/v1/messages`
  payloads and SSE streams verbatim. It additionally *observes* the response
  for tool-selection decisions (non-blocking; see below).
- **Decision layer** (`router/`, `context/`) serves `/v1/decision` and the
  auto-detected events from real traffic.
- **Telemetry layer** (`telemetry/`, `cli/`) observes both.

## Decision surfaces: explicit vs. observed

Two ways a decision reaches JEV:

1. **Explicit** — `POST /v1/decision`. A local client asks a question directly.
2. **Observed (interception)** — the proxy inspects the *observable* API
   boundary. When Claude's response to `/v1/messages` contains a `tool_use`
   block, the proxy detects a `tool_selection` decision event (candidates =
   the request's declared `tools`) and routes it to JEV in the background.

The interception is **non-blocking and advisory**: a transparent proxy cannot
safely block or rewrite Claude's already-generated tool selection, and it must
never break streaming or add latency to the critical path. JEV's structured
decision is recorded alongside Claude's actual choice (as
`candidate_action` in telemetry) for later verification/optimization. This
operates only at observable agent-interaction boundaries — never on internal
tokens, logits, or hidden reasoning.

## DecisionEvent model

`router/decision.py` — the fundamental abstraction. Fields:

```
event_id, conversation_id, request_id, context, current_operation,
candidate_action, decision_type, complexity, confidence, routing_status,
options, answer_format, source
```

`decision_type` is a `str`-enum (extensible). There is **no** dependency on
`<think>` tokens or any particular reasoning format. `source` is `"manual"`
(`/v1/decision`), `"intercept"` (detected from `/v1/messages` traffic), or
`"mcp"` (the `jevx_decide` MCP tool).

## Routing pipeline

1. **Interceptor** (`router/interceptor.py`): detects observable decision
   events (currently `tool_selection`) from `/v1/messages` traffic. Pure,
   stateless detection — no network calls.
2. **Classifier** (`router/classifier.py`): deterministic regex/length
   heuristics infer `decision_type` and a 0..1 complexity score for explicit
   `/v1/decision` requests. Zero model calls.
3. **Policy** (`router/policy.py`): `JEV_ENABLED` && `ROUTING_ENABLED` &&
   type ∈ `JEV_ROUTABLE_TYPES` && complexity ≤ `JEV_MAX_COMPLEXITY`.
4. **Executor** (`router/executor.py`):
   - JEV path: map the `DecisionEvent` into a JEV Decisions request
     (`state` + typed `questions` — `choice` / `noul` / `score`), then read
     the structured `answers` (calibrated probabilities / confidence).
   - Fallback: provider error, timeout, malformed response, low confidence →
     Claude (recorded with `routing_status=fallback_claude`).
5. **Telemetry**: one `DecisionRecord` per event plus a `RequestRecord`.
   `DecisionRecord.meta` carries `source`, `conversation_id`, `candidate_action`,
   `jev_choice` and `verdict` so decisions can be grouped per workflow and
   compared with Claude's actual choices.

## Verification layer

`router/verification.py` compares JEV's structured decision against Claude's
observable choice (`candidate_action`) for intercepted events and emits a
`verdict`:

- `agree` / `disagree` — JEV agreed/disagreed with Claude's tool choice.
- `jev_unavailable` — JEV failed (timeout/error/low confidence) and fell back.

This is advisory: disagreements are logged (`jev_disagreement`) and surfaced
as an agreement rate in `jevXagent statistics` / `--report` / `--export`. The
proxy flags and records; it never blocks or rewrites traffic.

## MCP `jevx_decide`

`mcp_server.py` exposes a `jevx_decide` MCP tool (`jevXagent mcp`, stdio) for
decision events that are **not observable** at the `/v1/messages` boundary
(e.g. file selection, relevance, verification). It builds a `DecisionEvent`
(`source="mcp"`) and runs it through the same `DecisionExecutor`, so it reuses
the existing JEV/Claude/fallback infrastructure.

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
usage parsing). `providers/jev.py` — JEV client for the OpenRouter Decisions
API (structured, typed `choice` / `noul` / `score` answers; never treated as a
text-generation model).

## Adapters

`adapters/anthropic.py` owns Anthropic protocol knowledge (headers,
validation, SSE usage collection, error envelopes). An OpenAI-compatible
adapter can be added beside it when needed (e.g. for Kilo Code).

## Config

`config.py` reads env + `.env`; secrets are redacted in logs. No provider
secret is hard-coded anywhere in the source tree.

## Future work

- Verification/optimization that *acts* on disagreements (e.g. surface a
  warning to the user, or a "trust JEV over Claude for tool X" override) —
  currently recorded and logged, not acted upon.
- Kilo Code integration (custom base URL pointing at the proxy).
- Paired-measurement benchmark (JEV decision vs Claude baseline) via
  `jevXagent benchmark`.
