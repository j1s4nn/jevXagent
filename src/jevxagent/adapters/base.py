"""Base adapter interface"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


class AgentAdapter(ABC):
    """Base adapter for AI coding agents"""

    @abstractmethod
    def detect(self) -> bool:
        """Check if agent is installed"""
        pass

    @abstractmethod
    def get_settings_path(self) -> Optional[Path]:
        """Get agent settings file path"""
        pass

    @abstractmethod
    def get_api_config(self) -> tuple[Optional[str], Optional[str]]:
        """Get API key and base URL from agent settings

        Returns:
            (api_key, base_url) tuple, None if not found
        """
        pass

    @abstractmethod
    def supports_env_override(self) -> bool:
        """Check if agent supports base URL override via environment"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent display name"""
        pass

    @property
    @abstractmethod
    def transport(self) -> str:
        """API transport type: 'anthropic' or 'openai'"""
        pass
