"""Request/response models"""
from typing import Any, Optional, Literal
from pydantic import BaseModel


class Message(BaseModel):
    """Chat message"""
    role: str
    content: str


class UsageInfo(BaseModel):
    """Token usage information"""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatRequest(BaseModel):
    """Standardized chat request"""
    model: str
    messages: list[Message]
    stream: bool = False
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


class ChatResponse(BaseModel):
    """Standardized chat response"""
    id: str
    model: str
    choices: list[dict[str, Any]]
    usage: Optional[UsageInfo] = None


class ProxyMetrics(BaseModel):
    """Metrics for single request"""
    trace_id: str
    jev_enabled: bool
    jev_status: str  # success, timeout, error, disabled
    jev_latency_ms: float = 0
    jev_input_tokens: int = 0
    jev_output_tokens: int = 0
    backend_latency_ms: float = 0
    agent_called: bool = True
    agent_ttft_ms: Optional[float] = None
    agent_latency_ms: float = 0
    agent_input_tokens: int = 0
    agent_output_tokens: int = 0
    total_latency_ms: float = 0
    bypass: bool = False
