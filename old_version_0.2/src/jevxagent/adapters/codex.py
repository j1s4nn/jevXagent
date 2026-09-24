"""Codex adapter"""
from pathlib import Path
from typing import Optional
from .base import AgentAdapter


class CodexAdapter(AgentAdapter):
    """Adapter for Codex"""

    @property
    def name(self) -> str:
        return "Codex"

    @property
    def transport(self) -> str:
        return "openai"

    def detect(self) -> bool:
        """Check if Codex is installed"""
        # Check for .codex directory
        codex_dir = Path.home() / ".codex"
        return codex_dir.exists()

    def get_settings_path(self) -> Optional[Path]:
        """Get Codex config path"""
        config = Path.home() / ".codex" / "config.json"
        return config if config.exists() else None

    def get_api_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get API key and base URL from Codex config"""
        import json

        config_path = self.get_settings_path()
        if not config_path:
            return None, None

        try:
            with open(config_path) as f:
                config = json.load(f)

            api_key = config.get("openai_api_key") or config.get("apiKey")
            base_url = config.get("openai_base_url") or config.get("baseUrl", "https://api.openai.com/v1")

            return api_key, base_url
        except Exception:
            return None, None

    def supports_env_override(self) -> bool:
        """Codex respects OPENAI_BASE_URL"""
        return True
