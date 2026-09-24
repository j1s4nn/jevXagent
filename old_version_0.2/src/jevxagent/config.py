"""Configuration management for jevXagent"""
import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field


class JevConfig(BaseModel):
    """Jev API configuration"""
    api_key: str
    base_url: str = "https://api.typesafe.ai/v1"
    model: str = "jev-1"
    timeout: float = 0.8


class AgentConfig(BaseModel):
    """Agent API configuration"""
    api_key: str
    base_url: str
    model: str


class ProxyConfig(BaseModel):
    """Proxy server configuration"""
    host: str = "127.0.0.1"
    port: int = 9099


class Config(BaseModel):
    """Main configuration"""
    jev: JevConfig
    agent: AgentConfig
    proxy: ProxyConfig
    jev_enabled: bool = True
    stats_path: Optional[Path] = None
    agent_type: str  # claude-code, codex, kilo, cline

    @classmethod
    def load(cls, path: Path) -> "Config":
        """Load config from file"""
        with open(path) as f:
            data = json.load(f)
        return cls(**data)

    def save(self, path: Path) -> None:
        """Save config to file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)


def get_config_path() -> Path:
    """Get default config path"""
    return Path.home() / ".jevxagent" / "config.json"
