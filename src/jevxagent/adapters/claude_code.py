"""Claude Code adapter"""
import json
from pathlib import Path
from typing import Optional
from .base import AgentAdapter


class ClaudeCodeAdapter(AgentAdapter):
    """Adapter for Claude Code CLI"""

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def transport(self) -> str:
        return "anthropic"

    def detect(self) -> bool:
        """Check if Claude Code is installed"""
        # Check for .claude directory
        claude_dir = Path.home() / ".claude"
        return claude_dir.exists()

    def get_settings_path(self) -> Optional[Path]:
        """Get Claude Code settings.json path"""
        settings = Path.home() / ".claude" / "settings.json"
        return settings if settings.exists() else None

    def get_api_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get API key and base URL from Claude Code settings"""
        settings_path = self.get_settings_path()
        if not settings_path:
            return None, None

        try:
            with open(settings_path) as f:
                settings = json.load(f)

            api_key = settings.get("apiKey")
            # Claude Code uses ANTHROPIC_BASE_URL env or default
            base_url = settings.get("apiBaseUrl", "https://api.anthropic.com")

            return api_key, base_url
        except Exception:
            return None, None

    def supports_env_override(self) -> bool:
        """Claude Code respects ANTHROPIC_BASE_URL"""
        return True
