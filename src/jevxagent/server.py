"""FastAPI server — the jevXagent proxy.

Endpoints:
  POST /v1/messages   Anthropic-compatible Messages API (transparent relay)
  GET  /v1/models     transparent passthrough (client compatibility)
  POST /v1/decision   jevXagent decision-routing endpoint (JEV / Claude + fallback)
  GET  /healthz       liveness + feature flags

Transport (relay) and decision routing are separated: /v1/messages never
touches the router. All telemetry recording is deferred to the telemetry layer.
"""

from __future__ import annotations

import json
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from . import __version__
from .adapters import anthropic as adapter
from .config import Settings
from .logging_setup import get_logger, log_event
from .providers.base import ProviderError
from .providers.claude import ClaudeProvider, parse_usage_from_body
from .providers.jev import JevProvider
from .router.classifier import estimate_complexity, infer_decision_type
from .router.decision import DecisionEvent
from .router.executor import DecisionExecutor
from .telemetry.events import DecisionType, RequestRecord
from .telemetry.storage import TelemetryStore

logger = get_logger()


def create_app(
    settings: Settings,
    store: Optional[TelemetryStore] = None,
    claude_client: Optional[httpx.AsyncClient] = None,
    jev_client: Optional[httpx.AsyncClient] = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await app.state.claude.aclose()
        await app.state.jev.aclose()
        app.state.store.close()

    app = FastAPI(
        title="jevXagent",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.store = store or TelemetryStore(settings)
    claude = ClaudeProvider(settings, client=claude_client)
    jev = JevProvider(settings, client=jev_client)
    app.state.claude = claude
    app.state.jev = jev
    app.state.executor = DecisionExecutor(settings, app.state.store, claude, jev)

    @app.get("/healthz")
    async def healthz() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "jev_enabled": settings.jev_enabled,
            "routing_enabled": settings.routing_enabled,
            "jev_configured": jev.is_configured(),
        }

    @app.get("/v1/models")
    async def models(request: Request) -> Response:
        return await _passthrough(request, settings, claude, stream=False)

    @app.post("/v1/messages")
    async def messages(request: Request) -> Response:
        return await _handle_messages(request, settings, claude, store=app.state.store)

    @app.post("/v1/decision")
    async def decision(request: Request) -> JSONResponse:
        return await _handle_decision(request, app.state.executor, app.state.store)

    return app


async def _handle_messages(
    request: Request,
    settings: Settings,
    claude: ClaudeProvider,
    store: TelemetryStore,
) -> Response:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    body = await request.body()

    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(adapter.anthropic_error(400, "Failed to parse request body"), 400, request_id)

    problem = adapter.validate_payload(payload)
    if problem:
        return _json_response(
            adapter.anthropic_error(400, problem, "invalid_request_error"), 400, request_id
        )

    stream = adapter.is_stream_request(payload)
    model = str(payload.get("model") or "")
    meta = adapter.extract_meta(payload)
    content_kinds = adapter.parse_content_types(payload)

    client_key = request.headers.get("x-api-key")
    try:
        claude.build_headers(client_key)
    except ProviderError:
        return _json_response(
            adapter.anthropic_error(
                401, "Missing API key (set CLAUDE_API_KEY or send x-api-key)", "authentication_error"
            ),
            401,
            request_id,
        )

    if settings.debug_requests:
        log_event(
            logger,
            "request",
            request_id=request_id,
            model=model,
            stream=stream,
            summary=meta["summary"],
            content=content_kinds,
        )

    record = RequestRecord(
        request_id=request_id,
        model=model,
        operation="messages",
        stream=stream,
        route="claude",
        summary=f"{meta['summary']} content={content_kinds}",
    )

    if not stream:
        try:
            response = await claude.post(payload, client_key=client_key)
        except ProviderError as exc:
            return await _provider_error(request_id, exc, record, store, start)

        record.status = response.status_code
        record.claude_ms = response.latency_ms
        record.total_ms = (time.perf_counter() - start) * 1000.0
        usage = parse_usage_from_body(response.body)
        _apply_usage(record, usage)
        if response.status_code >= 400:
            record.error = _error_message(response.body)
        _finish(record, store, request_id, stream=False, status=response.status_code)
        headers = adapter.filter_response_headers(response.headers)
        return Response(
            content=response.body,
            status_code=response.status_code,
            media_type=headers.pop("content-type", "application/json"),
            headers=headers,
        )

    try:
        upstream = await claude.stream(payload, client_key=client_key)
    except ProviderError as exc:
        return await _provider_error(request_id, exc, record, store, start)

    record.status = upstream.status_code
    record.claude_ms = upstream.first_byte_ms or 0.0

    if upstream.status_code >= 400:
        error_lines: list[str] = []
        async for line in upstream.lines:
            error_lines.append(line)
        body_bytes = ("\n".join(error_lines)).encode("utf-8", errors="replace")
        record.error = _error_message(body_bytes)
        record.total_ms = (time.perf_counter() - start) * 1000.0
        _finish(record, store, request_id, stream=True, status=record.status)
        return Response(
            content=body_bytes,
            status_code=upstream.status_code,
            media_type="application/json",
            headers=adapter.filter_response_headers(upstream.headers),
        )

    collector = adapter.SseUsageCollector()

    async def relay():
        first_yield = True
        try:
            async for line in upstream.lines:
                if first_yield:
                    record.claude_ms = (time.perf_counter() - start) * 1000.0
                    first_yield = False
                collector.on_line(line)
                yield line + "\n"
        finally:
            _apply_usage(record, collector.usage)
            record.total_ms = (time.perf_counter() - start) * 1000.0
            _finish(record, store, request_id, stream=True, status=record.status)

    headers = adapter.filter_response_headers(upstream.headers)
    media_type = headers.pop("content-type", "text/event-stream")
    return StreamingResponse(
        relay(),
        status_code=upstream.status_code,
        media_type=media_type,
        headers=headers,
    )


async def _handle_decision(
    request: Request,
    executor: DecisionExecutor,
    store: TelemetryStore,
) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
    start = time.perf_counter()
    try:
        body = json.loads(await request.body())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _json_response(adapter.anthropic_error(400, "Failed to parse request body"), 400, request_id)

    question = str(body.get("question") or body.get("operation") or "").strip()
    if not question:
        return _json_response(
            adapter.anthropic_error(400, "Field 'question' is required", "invalid_request_error"),
            400,
            request_id,
        )

    context = str(body.get("context") or "")
    options = body.get("options")
    if options is not None and (not isinstance(options, list) or not all(isinstance(o, str) for o in options)):
        return _json_response(
            adapter.anthropic_error(400, "Field 'options' must be an array of strings", "invalid_request_error"),
            400,
            request_id,
        )
    options = [str(o) for o in options] if options else []
    answer_format = str(body.get("format") or "decision")
    if answer_format not in {"decision", "choice", "label", "yesno"}:
        answer_format = "decision"

    event = DecisionEvent(
        request_id=request_id,
        conversation_id=str(body.get("conversation_id") or ""),
        context=context,
        current_operation=question,
        candidate_action=str(body.get("candidate_action") or ""),
        options=options,
        answer_format=answer_format,
    )

    explicit_type = str(body.get("decision_type") or "").strip()
    if explicit_type:
        try:
            event.decision_type = DecisionType(explicit_type)
        except ValueError:
            event.decision_type = DecisionType.OTHER
    else:
        event.decision_type = infer_decision_type(question, options, context)

    event.complexity = estimate_complexity(question, options, context)

    result = await executor.execute(event)

    total_ms = (time.perf_counter() - start) * 1000.0
    result["total_latency_ms"] = round(total_ms, 1)
    store.record_request(
        RequestRecord(
            request_id=request_id,
            model="decision",
            operation="decision",
            stream=False,
            route=result["provider"],
            status=200,
            total_ms=total_ms,
            claude_ms=result["latency_ms"] if result["provider"] == "claude" else 0.0,
            jev_ms=result["latency_ms"] if result["provider"] == "jev" else 0.0,
            summary=f"type={result['decision_type']} complexity={result['complexity']}",
        )
    )
    return JSONResponse(result)


async def _passthrough(
    request: Request,
    settings: Settings,
    claude: ClaudeProvider,
    stream: bool,
) -> Response:
    client_key = request.headers.get("x-api-key")
    try:
        response = await claude.models(client_key=client_key)
    except ProviderError as exc:
        return _json_response(adapter.anthropic_error(502, str(exc)), 502, "")
    filtered = adapter.filter_response_headers(response.headers)
    return Response(
        content=response.body,
        status_code=response.status_code,
        media_type=filtered.pop("content-type", "application/json"),
        headers=filtered,
    )


async def _provider_error(
    request_id: str,
    exc: ProviderError,
    record: RequestRecord,
    store: TelemetryStore,
    start: float,
) -> JSONResponse:
    record.status = exc.status or 502
    record.error = str(exc)
    record.total_ms = (time.perf_counter() - start) * 1000.0
    _finish(record, store, request_id, stream=False, status=record.status)
    error_type = "authentication_error" if exc.status == 401 else "api_error"
    return _json_response(
        adapter.anthropic_error(record.status, str(exc), error_type), record.status, request_id
    )


def _apply_usage(record: RequestRecord, usage: dict) -> None:
    for key, value in usage.items():
        if hasattr(record, key):
            setattr(record, key, value)


def _error_message(body: bytes) -> str:
    try:
        data = json.loads(body)
        return str((data.get("error") or {}).get("message", ""))[:200]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return body[:200].decode("utf-8", errors="replace")


def _finish(
    record: RequestRecord,
    store: TelemetryStore,
    request_id: str,
    stream: bool,
    status: int,
) -> None:
    store.record_request(record)
    if record.error:
        log_event(logger, "request_error", request_id=request_id, error=record.error[:200])
    else:
        log_event(
            logger,
            "request_done",
            request_id=request_id,
            stream=stream,
            status=status,
            model=record.model,
            total_ms=round(record.total_ms, 1),
            claude_ms=round(record.claude_ms, 1),
            input_tokens=record.input_tokens,
            output_tokens=record.output_tokens,
        )


def _json_response(payload: dict, status: int, request_id: str) -> JSONResponse:
    headers = {"x-jevxagent-request-id": request_id} if request_id else {}
    return JSONResponse(payload, status_code=status, headers=headers)
