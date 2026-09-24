"""Agent adapters for different AI coding agents"""
from .base import AgentAdapter
from .claude_code import ClaudeCodeAdapter
from .codex import CodexAdapter
from .kilo import KiloAdapter
from .cline import ClineAdapter

__all__ = [
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "KiloAdapter",
    "ClineAdapter",
]
