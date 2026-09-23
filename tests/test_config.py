"""Config: env loading, defaults, redaction."""

import pytest

from jevxagent.config import Settings, redact, redact_headers


def test_defaults():
    settings = Settings()
    assert settings.proxy_host == "127.0.0.1"
    assert settings.proxy_port == 8787
    assert settings.jev_enabled is False
    assert settings.routing_enabled is False
    assert settings.jev_confidence_threshold == 0.80
    assert "classification" in settings.jev_routable_types


def test_from_env_file(tmp_path, monkeypatch):
    for key in (
        "CLAUDE_API_KEY", "CLAUDE_BASE_URL", "PROXY_PORT", "JEV_ENABLED",
        "ROUTING_ENABLED", "DATA_DIR",
    ):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "CLAUDE_API_KEY=envkey\n"
        "CLAUDE_BASE_URL=https://env.example.com/\n"
        "PROXY_PORT=9999\n"
        "JEV_ENABLED=true\n"
        "ROUTING_ENABLED=true\n"
        "DATA_DIR=" + str(tmp_path / "d2") + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("JEVAXAGENT_ENV_FILE", str(env_file))
    settings = Settings.from_env()
    assert settings.claude_api_key == "envkey"
    assert settings.claude_base_url == "https://env.example.com"
    assert settings.proxy_port == 9999
    assert settings.jev_enabled is True
    assert settings.routing_enabled is True
    assert settings.data_dir == tmp_path / "d2"


def test_bool_and_float_parsing():
    settings = Settings(
        jev_enabled=True,
        routing_enabled=True,
        jev_timeout_s=2.5,
        jev_confidence_threshold=0.9,
        jev_max_retries=2,
    )
    assert settings.jev_timeout_s == 2.5
    assert settings.jev_confidence_threshold == 0.9
    assert settings.jev_max_retries == 2


def test_redact():
    assert redact("sk-ant-secret-1234567890") == "sk-a...redacted"
    assert redact("short") == "***redacted***"


def test_redact_headers():
    headers = {"x-api-key": "sk-ant-secret", "content-type": "application/json"}
    redacted = redact_headers(headers)
    assert "secret" not in redacted["x-api-key"]
    assert redacted["content-type"] == "application/json"


def test_token_fields_are_not_redacted():
    from jevxagent.config import is_sensitive_key
    from jevxagent.logging_setup import _redact_object

    payload = {
        "input_tokens": 12,
        "output_tokens": 7,
        "cache_read_input_tokens": 3,
        "x-api-key": "sekret",
        "authorization": "Bearer abc",
    }
    redacted = _redact_object(payload)
    assert redacted["input_tokens"] == 12
    assert redacted["output_tokens"] == 7
    assert redacted["cache_read_input_tokens"] == 3
    assert redacted["x-api-key"] == "***redacted***"
    assert redacted["authorization"] == "***redacted***"
    assert is_sensitive_key("API_KEY")
    assert not is_sensitive_key("input_tokens")


def test_db_path_created(settings):
    settings.ensure_data_dir()
    assert settings.db_path().parent.exists()


def test_model_map_parsing_and_remap():
    from jevxagent.config import _parse_model_map

    assert _parse_model_map("") == {}
    assert _parse_model_map("a=b,c=d") == {"a": "b", "c": "d"}
    assert _parse_model_map(" claude-opus-5-5 = claude-sonnet-5 ") == {"claude-opus-5-5": "claude-sonnet-5"}
    assert _parse_model_map("bad") == {}
    assert _parse_model_map("a=b,noequals") == {"a": "b"}

    settings = Settings(claude_model_map={"claude-opus-5-5": "claude-sonnet-5"})
    assert settings.remap_model("claude-opus-5-5") == "claude-sonnet-5"
    assert settings.remap_model("claude-sonnet-5") == "claude-sonnet-5"
