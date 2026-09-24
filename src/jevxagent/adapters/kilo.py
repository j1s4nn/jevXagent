"""Kilo Code adapter"""
import json
from pathlib import Path
from typing import Optional
from .base import AgentAdapter


class KiloAdapter(AgentAdapter):
    """Adapter for Kilo Code"""

    @property
    def name(self) -> str:
        return "Kilo Code"

    @property
    def transport(self) -> str:
        return "anthropic"

    def detect(self) -> bool:
        """Check if Kilo Code is installed"""
        # Check for .kilo directory
        kilo_dir = Path.home() / ".kilo"
        return kilo_dir.exists()

    def get_settings_path(self) -> Optional[Path]:
        """Get Kilo Code settings.json path"""
        settings = Path.home() / ".kilo" / "settings.json"
        return settings if settings.exists() else None

    def get_api_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get API key and base URL from Kilo Code settings"""
        settings_path = self.get_settings_path()
        if not settings_path:
            return None, None

        try:
            with open(settings_path) as f:
                settings = json.load(f)

            api_key = settings.get("apiKey") or settings.get("anthropic_api_key")
            base_url = settings.get("apiBaseUrl", "https://api.anthropic.com")

            return api_key, base_url
        except Exception:
            return None, None

    def supports_env_override(self) -> bool:
        """Kilo Code respects ANTHROPIC_BASE_URL"""
        return True
