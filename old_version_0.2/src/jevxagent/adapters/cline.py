"""Cline adapter"""
import json
from pathlib import Path
from typing import Optional
from .base import AgentAdapter


class ClineAdapter(AgentAdapter):
    """Adapter for Cline (VSCode extension)"""

    @property
    def name(self) -> str:
        return "Cline"

    @property
    def transport(self) -> str:
        return "anthropic"

    def detect(self) -> bool:
        """Check if Cline is installed via VSCode extensions"""
        vscode_extensions = Path.home() / ".vscode" / "extensions"
        if not vscode_extensions.exists():
            return False

        # Check for Cline extension directory
        for ext_dir in vscode_extensions.iterdir():
            if "cline" in ext_dir.name.lower():
                return True
        return False

    def get_settings_path(self) -> Optional[Path]:
        """Get Cline settings path from VSCode"""
        # Cline stores settings in VSCode settings.json
        vscode_settings = Path.home() / ".config" / "Code" / "User" / "settings.json"
        if not vscode_settings.exists():
            # Try Windows path
            vscode_settings = Path.home() / "AppData" / "Roaming" / "Code" / "User" / "settings.json"

        return vscode_settings if vscode_settings.exists() else None

    def get_api_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get API key and base URL from Cline/VSCode settings"""
        settings_path = self.get_settings_path()
        if not settings_path:
            return None, None

        try:
            with open(settings_path) as f:
                settings = json.load(f)

            # Cline typically uses these keys in VSCode settings
            api_key = settings.get("cline.anthropicApiKey") or settings.get("anthropic.apiKey")
            base_url = settings.get("cline.apiBaseUrl", "https://api.anthropic.com")

            return api_key, base_url
        except Exception:
            return None, None

    def supports_env_override(self) -> bool:
        """Cline may respect ANTHROPIC_BASE_URL depending on version"""
        return True
