"""Configuration system.

All settings are read from environment variables, optionally loaded from a
`.env` file (searched from the current directory upward, then the repo root,
or forced via JEVAXAGENT_ENV_FILE). Provider secrets are never hard-coded.

Secrets are redacted in any human-readable output (logs, reports).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR_DEFAULT = REPO_ROOT / "data"

DEFAULT_ROUTABLE_TYPES = (
    "classification,binary_decision,multiple_choice,selection,simple_extraction,"
    "simple_comparison,entity_identification,verification,relevance,"
    "url_classification,simple_transformation,next_action,tool_selection"
)

_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|authorization|x-api-key|token|password|secret|[_-]key)", re.IGNORECASE
)

_SAFE_TOKEN_KEYS = {
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "thinking_tokens",
    "jev_input_tokens",
    "jev_output_tokens",
    "claude_input_tokens",
    "claude_output_tokens",
    "prompt_tokens",
    "completion_tokens",
}


def is_sensitive_key(key: str) -> bool:
    """True if a field name indicates a secret. Token-count fields are NOT
    secrets and are never redacted."""
    lowered = key.lower()
    if lowered in _SAFE_TOKEN_KEYS:
        return False
    return bool(_SENSITIVE_RE.search(lowered))


def _find_env_file() -> Path | None:
    explicit = os.environ.get("JEVAXAGENT_ENV_FILE")
    if explicit and Path(explicit).is_file():
        return Path(explicit)
    cur = Path.cwd()
    for directory in [cur, *cur.parents]:
        if (directory / ".env").is_file():
            return directory / ".env"
    if (REPO_ROOT / ".env").is_file():
        return REPO_ROOT / ".env"
    return None


def _to_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _to_float(value, default: float) -> float:
    if value is None or str(value).strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _to_int(value, default: int) -> int:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _csv(value, default: str) -> list[str]:
    raw = value if value is not None else default
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _parse_model_map(value) -> dict[str, str]:
    """Parse CLAUDE_MODEL_MAP="from=to,from2=to2" into a lookup dict."""
    result: dict[str, str] = {}
    if not value:
        return result
    for item in str(value).split(","):
        item = item.strip()
        if not item or "=" not in item:
            continue
        src, _, dst = item.partition("=")
        src, dst = src.strip(), dst.strip()
        if src and dst:
            result[src] = dst
    return result


@dataclass
class Settings:
    # Claude (primary provider)
    claude_api_key: str = ""
    claude_base_url: str = "https://api-cc.freemodel.dev"
    claude_timeout_s: float = 300.0
    claude_model_map: dict[str, str] = field(default_factory=dict)

    # JEV (decision coprocessor)
    jev_api_key: str = ""
    jev_base_url: str = ""
    jev_model: str = ""

    # proxy server
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 8787

    # routing
    jev_enabled: bool = False
    routing_enabled: bool = False
    jev_routable_types: list[str] = field(default_factory=lambda: _csv(None, DEFAULT_ROUTABLE_TYPES))

    # JEV behavior
    jev_timeout_s: float = 3.0
    jev_max_retries: int = 1
    jev_confidence_threshold: float = 0.80
    jev_max_context_chars: int = 4000
    jev_max_complexity: float = 0.60

    # logging
    log_level: str = "INFO"
    debug_requests: bool = False

    # telemetry / privacy
    data_dir: Path = DATA_DIR_DEFAULT
    store_prompts: bool = False
    store_responses: bool = False
    store_decision_context: bool = False

    # cost / estimation model (per 1M tokens); empty/0 => metric unavailable
    claude_input_price_per_mtok: float = 0.0
    claude_output_price_per_mtok: float = 0.0
    jev_input_price_per_mtok: float = 0.0
    jev_output_price_per_mtok: float = 0.0
    claude_est_ms_per_decision: float = 0.0
    claude_est_input_tokens_per_decision: float = 0.0
    claude_est_output_tokens_per_decision: float = 0.0

    @classmethod
    def from_env(cls) -> "Settings":
        env_file = _find_env_file()
        if env_file is not None:
            load_dotenv(env_file, override=False)
        env = os.environ

        data_dir = env.get("DATA_DIR", "").strip()
        return cls(
            claude_api_key=env.get("CLAUDE_API_KEY", "").strip(),
            claude_base_url=env.get("CLAUDE_BASE_URL", "https://api-cc.freemodel.dev").strip().rstrip("/"),
            claude_timeout_s=_to_float(env.get("CLAUDE_TIMEOUT_S"), 300.0),
            claude_model_map=_parse_model_map(env.get("CLAUDE_MODEL_MAP")),
            jev_api_key=env.get("JEV_API_KEY", "").strip(),
            jev_base_url=env.get("JEV_BASE_URL", "").strip().rstrip("/"),
            jev_model=env.get("JEV_MODEL", "").strip(),
            proxy_host=env.get("PROXY_HOST", "127.0.0.1").strip(),
            proxy_port=_to_int(env.get("PROXY_PORT"), 8787),
            jev_enabled=_to_bool(env.get("JEV_ENABLED"), False),
            routing_enabled=_to_bool(env.get("ROUTING_ENABLED"), False),
            jev_routable_types=_csv(env.get("JEV_ROUTABLE_TYPES"), DEFAULT_ROUTABLE_TYPES),
            jev_timeout_s=_to_float(env.get("JEV_TIMEOUT_S"), 3.0),
            jev_max_retries=_to_int(env.get("JEV_MAX_RETRIES"), 1),
            jev_confidence_threshold=_to_float(env.get("JEV_CONFIDENCE_THRESHOLD"), 0.80),
            jev_max_context_chars=_to_int(env.get("JEV_MAX_CONTEXT_CHARS"), 4000),
            jev_max_complexity=_to_float(env.get("JEV_MAX_COMPLEXITY"), 0.60),
            log_level=env.get("LOG_LEVEL", "INFO").strip().upper(),
            debug_requests=_to_bool(env.get("DEBUG_REQUESTS"), False),
            data_dir=Path(data_dir).expanduser() if data_dir else DATA_DIR_DEFAULT,
            store_prompts=_to_bool(env.get("STORE_PROMPTS"), False),
            store_responses=_to_bool(env.get("STORE_RESPONSES"), False),
            store_decision_context=_to_bool(env.get("STORE_DECISION_CONTEXT"), False),
            claude_input_price_per_mtok=_to_float(env.get("CLAUDE_INPUT_PRICE_PER_MTOK"), 0.0),
            claude_output_price_per_mtok=_to_float(env.get("CLAUDE_OUTPUT_PRICE_PER_MTOK"), 0.0),
            jev_input_price_per_mtok=_to_float(env.get("JEV_INPUT_PRICE_PER_MTOK"), 0.0),
            jev_output_price_per_mtok=_to_float(env.get("JEV_OUTPUT_PRICE_PER_MTOK"), 0.0),
            claude_est_ms_per_decision=_to_float(env.get("CLAUDE_EST_MS_PER_DECISION"), 0.0),
            claude_est_input_tokens_per_decision=_to_float(
                env.get("CLAUDE_EST_INPUT_TOKENS_PER_DECISION"), 0.0
            ),
            claude_est_output_tokens_per_decision=_to_float(
                env.get("CLAUDE_EST_OUTPUT_TOKENS_PER_DECISION"), 0.0
            ),
        )

    def remap_model(self, model: str) -> str:
        """Map a client-requested model id to an upstream-supported id."""
        return self.claude_model_map.get(model, model)

    def ensure_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir

    def db_path(self) -> Path:
        return self.data_dir / "telemetry.db"


def redact(value: str) -> str:
    """Redact a header/value pair for logging."""
    return f"{value[:4]}...redacted" if value and len(value) > 8 else "***redacted***"


def redact_headers(headers: dict) -> dict:
    out = {}
    for key, value in headers.items():
        out[key] = redact(value) if is_sensitive_key(key) else value
    return out
